"""实时统计收集器。

数据来源两条，互补：

1. **内核日志** —— 内核每完成或跳过一个文件都会打印带类型前缀的消息：

       【视频】… 文件下载成功
       【图集】…_1 文件下载成功
       【封面】… 文件下载成功
       【音乐】… 文件下载成功
       【视频】… 存在下载记录或文件已存在，跳过下载
       【图集】…_2 文件已存在，跳过下载
       {show} 文件大小超出限制，跳过下载

   按类型分别累计「下载」与「跳过」，可覆盖音乐 / 封面这些内核自身
   ``statistics_count()`` 并不统计的类型。

2. **引擎自身计数** —— 处理了多少个账号、解析出多少个作品 ID、
   去重预过滤跳过了多少个作品（这部分内核日志里没有）。

本模块不依赖 Qt，便于离线单元测试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["TaskStats", "TYPE_ORDER", "format_entries", "format_chips"]

#: 展示顺序（其余类型排在后面）
TYPE_ORDER: tuple[str, ...] = ("视频", "图集", "实况", "音乐", "封面", "动图")

#: 形如 【视频】名称 文件下载成功 / 【图集】名称_1 跳过下载
_FILE_RESULT = re.compile(
    r"^【(?P<type>[^】]+)】.*?(?P<result>文件下载成功|跳过下载)$"
)

#: 作品自身没有可用下载地址，属于作品级失败而非文件级跳过
_EXTRACT_FAILED = "提取文件下载地址失败"

#: 因超出体积上限而跳过
_SIZE_SKIPPED = "文件大小超出限制"

#: 内核在账号 / 合集模式下打印的作品总数：``共获取到 N 个账号发布作品``
_FOUND_WORKS = re.compile(r"共获取到 (\d+) 个")


@dataclass
class TypeCounter:
    """某一类文件的下载 / 跳过计数。"""

    download: int = 0
    skip: int = 0

    @property
    def total(self) -> int:
        return self.download + self.skip


@dataclass
class TaskStats:
    """一次任务运行期间的实时统计。"""

    # ---- 引擎提供的计数 ---- #
    accounts_done: int = 0
    accounts_total: int = 0
    work_ids: int = 0
    dedup_skipped: int = 0

    # ---- 由日志累计 ---- #
    types: dict[str, TypeCounter] = field(default_factory=dict)
    size_skipped: int = 0
    extract_failed: int = 0

    # ------------------------------------------------------------------ #
    def counter(self, type_name: str) -> TypeCounter:
        return self.types.setdefault(type_name, TypeCounter())

    def feed_log(self, text: str) -> bool:
        """消费一条内核日志，返回统计是否有变化。"""
        if not text:
            return False
        stripped = text.strip()

        # 账号 / 合集模式：内核会打印本次列表包含多少个作品
        found = _FOUND_WORKS.search(stripped)
        if found:
            self.work_ids += int(found.group(1))
            return True

        matched = _FILE_RESULT.match(stripped)
        if not matched:
            return False

        type_name = matched.group("type").strip()
        result = matched.group("result")
        if not type_name:
            return False

        if result == "文件下载成功":
            self.counter(type_name).download += 1
            return True

        # 跳过：区分「作品无下载地址」「体积超限」「文件/记录命中」
        if _EXTRACT_FAILED in stripped:
            self.extract_failed += 1
            return True
        self.counter(type_name).skip += 1
        if _SIZE_SKIPPED in stripped:
            self.size_skipped += 1
        return True

    # ------------------------------------------------------------------ #
    def set_accounts(self, done: int, total: int) -> None:
        self.accounts_done = done
        self.accounts_total = total

    def ordered_types(self) -> list[str]:
        """按固定顺序返回出现过的类型（未出现的已知类型也保留，便于界面稳定）。"""
        known = [t for t in TYPE_ORDER]
        extra = sorted(t for t in self.types if t not in known)
        return known + extra

    @property
    def total_download(self) -> int:
        return sum(c.download for c in self.types.values())

    @property
    def total_skip(self) -> int:
        return sum(c.skip for c in self.types.values())

    def snapshot(self) -> dict[str, Any]:
        return {
            "accounts_done": self.accounts_done,
            "accounts_total": self.accounts_total,
            "work_ids": self.work_ids,
            "dedup_skipped": self.dedup_skipped,
            "types": {
                name: {"download": c.download, "skip": c.skip}
                for name, c in self.types.items()
            },
            "size_skipped": self.size_skipped,
            "extract_failed": self.extract_failed,
            "total_download": self.total_download,
            "total_skip": self.total_skip,
        }


def format_entries(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """把快照转换成结构化计数项，供界面绘制计数栏。

    每项形如::

        {"key": "视频", "kind": "pair", "download": 12, "skip": 8}
        {"key": "作品 ID", "kind": "single", "value": "209"}
    """
    entries: list[dict[str, Any]] = []

    total = snapshot.get("accounts_total") or 0
    done = snapshot.get("accounts_done") or 0
    if total or done:
        entries.append(
            {
                "key": "账号",
                "kind": "single",
                "value": f"{done}/{total}" if total else str(done),
            }
        )
    if snapshot.get("work_ids"):
        entries.append(
            {"key": "作品 ID", "kind": "single", "value": str(snapshot["work_ids"])}
        )
    if snapshot.get("dedup_skipped"):
        entries.append(
            {
                "key": "预过滤跳过",
                "kind": "single",
                "value": str(snapshot["dedup_skipped"]),
            }
        )

    types = snapshot.get("types") or {}
    for name in TYPE_ORDER:
        item = types.get(name) or {}
        entries.append(
            {
                "key": name,
                "kind": "pair",
                "download": int(item.get("download", 0)),
                "skip": int(item.get("skip", 0)),
            }
        )
    for name in sorted(t for t in types if t not in TYPE_ORDER):
        item = types[name]
        entries.append(
            {
                "key": name,
                "kind": "pair",
                "download": int(item.get("download", 0)),
                "skip": int(item.get("skip", 0)),
            }
        )

    if snapshot.get("size_skipped"):
        entries.append(
            {"key": "体积超限", "kind": "single", "value": str(snapshot["size_skipped"])}
        )
    if snapshot.get("extract_failed"):
        entries.append(
            {
                "key": "地址提取失败",
                "kind": "single",
                "value": str(snapshot["extract_failed"]),
            }
        )
    return entries


def format_chips(snapshot: dict[str, Any]) -> list[tuple[str, str]]:
    """兼容用的简化接口：把结构化计数项压成 ``(标签, 文本)``。"""
    chips: list[tuple[str, str]] = []
    for entry in format_entries(snapshot):
        if entry["kind"] == "single":
            chips.append((entry["key"], str(entry["value"])))
        else:
            chips.append((entry["key"], f"{entry['download']}/{entry['skip']}"))
    return chips
