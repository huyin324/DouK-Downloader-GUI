"""去重优化。

上游内核的去重发生在 ``Downloader.download_video`` / ``download_image`` 内部，
也就是**已经拿到作品详情之后**才判断是否需要下载文件。对于“批量下载链接作品”
模式，这意味着即使全部作品都已下载过，程序仍然会为每一个链接发起一次详情接口
请求——纯粹的时间与带宽浪费。

本模块提供两层增强：

1. **预过滤**（``filter_ids`` / ``filter_items``）
   在发起详情请求之前，先用一条批量 SQL 查询比对本地下载记录，
   命中记录的作品直接剔除，完全不产生网络流量。

2. **文件一致性校验**（``reconcile``，可选）
   下载记录存在但磁盘文件缺失时（手工删除、跨盘迁移、异常中断），
   把该 ID 判为“记录失效”，重新纳入下载队列，避免漏下。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from re import compile as re_compile
from typing import Any, Iterable, Sequence

__all__ = ["DedupManager"]

#: 作品 ID 形如 19 位数字（与上游 DownloadRecorder.detail 的正则保持一致）
_ID_PATTERN = re_compile(r"\d{19}")

#: 单次 SQL IN 查询的参数上限，避免超出 SQLite 变量数量限制
_SQL_CHUNK = 400

#: 目录扫描的文件数量上限，超过则放弃校验以避免卡死
_SCAN_LIMIT = 300_000


class DedupManager:
    """基于下载记录表的去重管理器。"""

    def __init__(
        self,
        database: Any,
        root: Path,
        config: dict,
        log: Any,
    ) -> None:
        self.db = database
        self.root = Path(root)
        self.enabled = bool(config.get("dedup_prefilter", True))
        self.verify_file = bool(config.get("dedup_verify_file", False))
        self.verbose = bool(config.get("dedup_skip_log", True))
        self.record_enable = bool(config.get("record_enable", True))
        self.log = log
        #: 累计跳过的作品 ID，供任务结束时统计
        self.skipped_ids: set[str] = set()
        self.recovered_ids: set[str] = set()

    # ------------------------------------------------------------------ #
    # 基础查询
    # ------------------------------------------------------------------ #
    async def existing_ids(self, ids: Sequence[str]) -> set[str]:
        """批量查询给定 ID 中哪些已存在下载记录。"""
        candidates = [i for i in dict.fromkeys(ids) if i]
        if not candidates or not self.record_enable:
            return set()

        found: set[str] = set()
        cursor = self.db.cursor
        for start in range(0, len(candidates), _SQL_CHUNK):
            part = candidates[start : start + _SQL_CHUNK]
            placeholders = ",".join("?" * len(part))
            await cursor.execute(
                f"SELECT ID FROM download_data WHERE ID IN ({placeholders})",
                part,
            )
            found.update(row[0] for row in await cursor.fetchall())
        return found

    # ------------------------------------------------------------------ #
    # 预过滤
    # ------------------------------------------------------------------ #
    async def filter_ids(self, ids: Iterable[str]) -> tuple[list[str], list[str]]:
        """按下载记录过滤作品 ID。

        :return: ``(待处理 ID 列表, 被跳过 ID 列表)``，均保持原有顺序
        """
        ordered = [i for i in dict.fromkeys(ids) if i]
        if not self.enabled or not ordered:
            return ordered, []

        recorded = await self.existing_ids(ordered)
        if self.verify_file and recorded:
            recorded = await self._reconcile_with_files(recorded)

        skipped = [i for i in ordered if i in recorded]
        kept = [i for i in ordered if i not in recorded]
        self.skipped_ids.update(skipped)

        if skipped:
            self.log(
                f"[去重] 预过滤：共 {len(ordered)} 个作品，"
                f"命中 {len(skipped)} 个已下载记录并直接跳过，"
                f"实际需要处理 {len(kept)} 个（未产生任何接口请求）。"
            )
            if self.verbose:
                preview = "、".join(skipped[:20])
                more = f" …（共 {len(skipped)} 个）" if len(skipped) > 20 else ""
                self.log(f"[去重] 跳过清单：{preview}{more}")
        return kept, skipped

    async def filter_items(
        self, items: Sequence[dict]
    ) -> tuple[list[dict], list[str]]:
        """按下载记录过滤“已解析完成的作品数据”（用于账号 / 合集模式）。"""
        if not self.enabled or not items:
            return list(items), []

        ids = [str(i.get("id", "")) for i in items]
        recorded = await self.existing_ids(ids)
        if self.verify_file and recorded:
            recorded = await self._reconcile_with_files(recorded)

        kept: list[dict] = []
        skipped: list[str] = []
        for item, id_ in zip(items, ids):
            if id_ and id_ in recorded:
                skipped.append(id_)
            else:
                kept.append(item)

        self.skipped_ids.update(skipped)
        if skipped:
            self.log(
                f"[去重] 预过滤：账号/合集列表共 {len(items)} 个作品，"
                f"跳过 {len(skipped)} 个已下载作品，实际需要下载 {len(kept)} 个。"
            )
        return kept, skipped

    # ------------------------------------------------------------------ #
    # 文件一致性校验
    # ------------------------------------------------------------------ #
    async def _reconcile_with_files(self, recorded: set[str]) -> set[str]:
        """校验记录对应的文件是否真实存在，返回仍然有效的记录集合。"""
        if not self.root.is_dir():
            return recorded
        try:
            present = await asyncio.to_thread(self._scan_filenames)
        except Exception as exc:  # 扫描失败时保持原结论，不影响主流程
            self.log(f"[去重] 本地文件校验失败，已忽略本次校验：{exc!r}")
            return recorded

        invalid = {i for i in recorded if i not in present}
        if invalid:
            self.recovered_ids.update(invalid)
            self.log(
                f"[去重] 本地文件校验：{len(invalid)} 个作品的下载记录存在但文件缺失，"
                f"已重新加入下载队列。"
            )
            preview = "、".join(sorted(invalid)[:20])
            more = f" …（共 {len(invalid)} 个）" if len(invalid) > 20 else ""
            self.log(f"[去重] 需补下清单：{preview}{more}")
        return recorded - invalid

    def _scan_filenames(self) -> set[str]:
        """扫描保存目录，收集文件名中出现过的 19 位作品 ID。"""
        names: list[str] = []
        count = 0
        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            names.append(path.stem)
            count += 1
            if count >= _SCAN_LIMIT:
                break
        blob = "\n".join(names)
        return set(_ID_PATTERN.findall(blob))

    # ------------------------------------------------------------------ #
    def summary(self) -> str:
        """返回一行统计文本。"""
        parts = [f"跳过已下载作品 {len(self.skipped_ids)} 个"]
        if self.recovered_ids:
            parts.append(f"其中因文件缺失而重新下载 {len(self.recovered_ids)} 个")
        return "；".join(parts)
