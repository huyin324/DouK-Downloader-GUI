"""下载引擎。

职责：在**完全不修改上游下载逻辑**的前提下，把内核的采集能力接入图形界面。

具体做法：

1. 运行在独立的 ``QThread`` 中，自带 asyncio 事件循环，避免阻塞界面；
2. 先安装反爬虫补丁，再导入内核业务模块（顺序不可颠倒，
   因为 ``@Retry.retry`` 装饰器在模块导入时完成绑定）；
3. 把界面配置展开成上游 ``settings.json`` 的结构后写入内核 ``Volume`` 目录，
   随后完全交由内核的 ``Parameter`` / ``TikTok`` / ``Downloader`` 执行；
4. 通过替换实例方法 ``download_detail_batch`` 注入去重预过滤，
   通过替换 ``suspend`` / ``get_wait_time`` 等模块属性注入节流策略。

内核源码保持原样，所有增强都是运行时的、可关闭的。
"""

from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass, field
from inspect import isawaitable
from re import sub as re_sub
from typing import Any, Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from . import antispider, upstream_fixes
from .dedup import DedupManager
from .link_analysis import URL_PATTERN, split_by_resolution
from .logbridge import QtConsole
from .paths import DOWNLOADS_DIR, ensure_upstream_on_path
from .stats import TaskStats

__all__ = ["TaskRequest", "EngineWorker", "normalize_cookie"]


def normalize_cookie(text: str) -> str:
    """兼容两种 Cookie 写法。

    - 浏览器复制的原始串：``k1=v1; k2=v2``
    - 内核旧版配置里的 JSON 对象：``{"k1": "v1", "k2": "v2"}``

    统一转换为内核可直接使用的字符串形式。
    """
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return raw
    try:
        from json import loads

        payload = loads(raw)
    except Exception:  # noqa: BLE001
        return raw
    if not isinstance(payload, dict):
        return raw
    return "; ".join(
        f"{key}={value}"
        for key, value in payload.items()
        if key and value not in (None, "")
    )


# --------------------------------------------------------------------------- #
# 任务描述
# --------------------------------------------------------------------------- #
@dataclass
class TaskRequest:
    """一次采集任务的输入。"""

    platform: str = "douyin"          # douyin | tiktok
    mode: str = "detail"              # detail | account | mix | live
    links: list[str] = field(default_factory=list)
    account_tab: str = "post"

    MODE_NAMES = {
        "detail": "批量下载链接作品",
        "account": "批量下载账号作品",
        "mix": "批量下载合集作品",
        "live": "获取直播拉流地址",
    }

    PLATFORM_NAMES = {"douyin": "抖音", "tiktok": "TikTok"}

    @property
    def title(self) -> str:
        return (
            f"{self.PLATFORM_NAMES.get(self.platform, self.platform)} · "
            f"{self.MODE_NAMES.get(self.mode, self.mode)}"
        )


# --------------------------------------------------------------------------- #
# 信号
# --------------------------------------------------------------------------- #
class EngineSignals(QObject):
    """引擎 -> 界面 的信号集合。"""

    message = pyqtSignal(str, str)     # (级别, 文本) —— 同时作为 QtConsole 的日志总线
    phase = pyqtSignal(str)            # 当前阶段描述
    progress = pyqtSignal(int, int)    # (已完成, 总数)
    stats = pyqtSignal(dict)           # 实时统计快照（见 app/stats.py）
    finished = pyqtSignal(dict)        # 统计信息
    failed = pyqtSignal(str)


# --------------------------------------------------------------------------- #
# 执行上下文
# --------------------------------------------------------------------------- #
@dataclass
class _Context:
    cfg: dict
    req: TaskRequest
    console: Any
    parameter: Any
    tiktok: Any
    dedup: DedupManager
    log: Callable[[str, str], None]
    phase: Callable[[str], None]
    progress: Callable[[int, int], None]
    is_stopping: Callable[[], bool]
    inter_delay: float
    suspend_every: int
    suspend_seconds: float
    wait_avg: float = 6.0
    counters: Any = None
    push_stats: Callable[[], None] | None = None
    stats: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 引擎
# --------------------------------------------------------------------------- #
class EngineWorker(QThread):
    """在后台线程中执行一次采集任务。"""

    def __init__(self, config: dict, request: TaskRequest, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config = dict(config)
        self.request = request
        self.signals = EngineSignals()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._stopping = False
        #: 运行期对象引用（parameter / tiktok / dedup / console），便于诊断与自测
        self.runtime: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def stop(self) -> None:
        """请求停止任务（线程安全）。"""
        self._stopping = True
        loop, task = self._loop, self._task
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass

    @property
    def stopping(self) -> bool:
        return self._stopping

    def run(self) -> None:  # noqa: D102 - QThread 入口
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._task = self._loop.create_task(self._amain())
            self._loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            self.signals.message.emit("warning", "任务已停止。")
        except Exception as exc:  # noqa: BLE001
            self.signals.message.emit("error", f"任务执行失败：{exc!r}")
            for line in traceback.format_exc().splitlines():
                self.signals.message.emit("debug", line)
            self.signals.failed.emit(f"{exc}")
        finally:
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:  # noqa: BLE001
                pass
            self._loop.close()
            self._loop = None
            self._task = None

    # ------------------------------------------------------------------ #
    # 主流程
    # ------------------------------------------------------------------ #
    async def _amain(self) -> dict:
        cfg, req = self.config, self.request
        counters = TaskStats()

        def push_stats() -> None:
            self.signals.stats.emit(counters.snapshot())

        def log(level: str, text: str) -> None:
            # 顺带消费内核日志，累计各类文件的下载 / 跳过数量
            if counters.feed_log(text):
                push_stats()
            self.signals.message.emit(level, text)

        phase = lambda text: self.signals.phase.emit(text)  # noqa: E731
        progress = lambda done, total: self.signals.progress.emit(done, total)  # noqa: E731
        push_stats()

        log("system", "=" * 72)
        log("system", f"任务开始：{req.title}")
        log("system", f"待处理链接 {len(req.links)} 条")

        # --- 1. 载入内核并安装反爬补丁（顺序关键） -------------------- #
        ensure_upstream_on_path()

        def on_kernel_log(level: str, text: str) -> None:
            """内核输出不经过本模块的 log()，需要在控制台层单独接入统计。"""
            if counters.feed_log(text):
                push_stats()

        console = QtConsole.build(self.signals, listener=on_kernel_log)
        early = antispider.apply(cfg, console)
        for line in antispider.describe(early):
            log("system", line)

        # --- 2. 生成指纹画像并展开设置 -------------------------------- #
        profile = self._pick_profile()
        if profile:
            log("system", f"本次指纹画像：{profile['desc']}")
        settings_dict = self._build_settings(req, profile)

        # --- 3. 导入内核业务模块并安装依赖业务模块的补丁 -------------- #
        from src.config import Parameter, Settings
        from src.custom import (
            TEXT_REPLACEMENT,
            VOLUME,
        )
        from src.manager import Database, DownloadRecorder
        from src.module import Cookie
        from src.record import BaseLogger, LoggerManager
        from src.application.main_terminal import TikTok

        late = antispider.apply_after_import(cfg, console)
        for line in antispider.describe(late):
            log("system", line)

        for line in upstream_fixes.describe(
            upstream_fixes.install(cfg, lambda text: log("system", text))
        ):
            log("system", line)

        # --- 4. 构造内核对象 ------------------------------------------ #
        settings = Settings(VOLUME, console)
        settings.update(settings_dict)

        database = Database()
        await database.__aenter__()
        parameter = None
        try:
            recorder = DownloadRecorder(database, bool(cfg.get("record_enable", True)), console)
            logger_cls = LoggerManager if cfg.get("logger_file") else BaseLogger
            cookie_object = Cookie(settings, console)

            phase("正在初始化采集参数…")
            try:
                parameter = Parameter(
                    settings,
                    cookie_object,
                    logger=logger_cls,
                    console=console,
                    **settings.read(),
                    recorder=recorder,
                )
            except Exception as exc:  # noqa: BLE001
                if profile is None:
                    raise
                log("warning", f"使用随机指纹初始化失败（{exc}），回退为配置中的固定指纹重试。")
                settings.update(self._build_settings(req, None))
                parameter = Parameter(
                    settings,
                    cookie_object,
                    logger=logger_cls,
                    console=console,
                    **settings.read(),
                    recorder=recorder,
                )

            parameter.set_headers_cookie()
            parameter.CLEANER.set_rule(TEXT_REPLACEMENT, True)
            log("info", f"文件保存根目录：{parameter.root}")
            self._report_cookie_state(parameter, req, log)

            phase("正在更新平台请求参数（msToken / ttwid）…")
            try:
                await parameter.update_params()
            except Exception as exc:  # noqa: BLE001
                log("warning", f"在线更新平台参数失败，改用本地参数：{exc!r}")
                try:
                    await parameter.update_params_offline()
                except Exception as exc2:  # noqa: BLE001
                    log("warning", f"本地参数更新同样失败，将直接使用 Cookie 中的值：{exc2!r}")

            tiktok = TikTok(parameter, database, server_mode=True)
            dedup = DedupManager(database, parameter.root, cfg, lambda t: log("system", t))
            self._install_dedup_hook(tiktok, dedup, cfg, log)

            self.runtime = {
                "console": console,
                "parameter": parameter,
                "tiktok": tiktok,
                "dedup": dedup,
                "catalogue": antispider.supported_impersonate(),
            }

            ctx = _Context(
                cfg=cfg,
                req=req,
                console=console,
                parameter=parameter,
                tiktok=tiktok,
                dedup=dedup,
                log=log,
                phase=phase,
                progress=progress,
                is_stopping=lambda: self._stopping,
                inter_delay=float(early.inter_item_delay or 0.0),
                suspend_every=int(early.suspend_every or 0),
                suspend_seconds=float(early.suspend_seconds or 0.0),
                wait_avg=float(early.wait_avg or 6.0),
                counters=counters,
                push_stats=push_stats,
                stats={
                    "平台": TaskRequest.PLATFORM_NAMES.get(req.platform, req.platform),
                    "模式": TaskRequest.MODE_NAMES.get(req.mode, req.mode),
                    "提交链接": len(req.links),
                    "跳过已下载": 0,
                    "处理作品": 0,
                },
            )

            phase(f"开始执行：{req.title}")
            stats = await self._dispatch(ctx)
            stats["跳过已下载"] = len(dedup.skipped_ids)
            counters.dedup_skipped = len(dedup.skipped_ids)
            push_stats()
            if dedup.recovered_ids:
                stats["补下作品"] = len(dedup.recovered_ids)
            stats["下载文件"] = counters.total_download
            stats["跳过文件"] = counters.total_skip
            stats["状态"] = "已停止" if self._stopping else "已完成"
            progress(1, 1)

            breakdown = "；".join(
                f"{name} 下载 {c.download} / 跳过 {c.skip}"
                for name, c in counters.types.items()
                if c.total
            )
            log("system", "-" * 72)
            if breakdown:
                log("system", f"文件统计：{breakdown}")
            log("system", "任务结束：" + "；".join(f"{k} {v}" for k, v in stats.items()))
            self.signals.finished.emit(stats)
            return stats
        finally:
            phase("正在释放连接…")
            if parameter is not None:
                try:
                    await parameter.close_client()
                except Exception:  # noqa: BLE001
                    pass
            try:
                await database.close()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #
    # 模式分发
    # ------------------------------------------------------------------ #
    async def _dispatch(self, ctx: _Context) -> dict:
        match ctx.req.mode:
            case "detail":
                return await self._run_detail(ctx)
            case "account":
                return await self._run_account(ctx)
            case "mix":
                return await self._run_mix(ctx)
            case "live":
                return await self._run_live(ctx)
            case _:
                raise ValueError(f"不支持的任务模式：{ctx.req.mode}")

    async def _run_detail(self, ctx: _Context) -> dict:
        """批量下载链接作品：解析链接 -> 预过滤 -> 逐个走内核详情流程。"""
        tiktok_flag = ctx.req.platform == "tiktok"
        link_obj = ctx.tiktok.links_tiktok if tiktok_flag else ctx.tiktok.links

        urls = list(dict.fromkeys(URL_PATTERN.findall("\n".join(ctx.req.links))))
        if not urls:
            ctx.log(
                "warning",
                "提交内容中没有找到任何链接（需以 http:// 或 https:// 开头）。",
            )
            return ctx.stats

        # 内核原本对**每条**链接都发一次请求（目的是解析短链跳转）并按反爬间隔等待。
        # 实测 113 条链接会静默跑 12 分钟。实际上只有短链需要请求：
        # 完整链接里的作品 ID 可以直接正则提取，无需联网。
        short_links, direct_links = split_by_resolution(urls)
        if direct_links:
            ctx.log(
                "info",
                f"共 {len(urls)} 条链接：短链 {len(short_links)} 条需联网解析，"
                f"{len(direct_links)} 条完整链接直接提取作品 ID"
                f"（省下 {len(direct_links)} 次请求）",
            )

        ids: list[str] = []

        # ---- 完整链接：直接提取，零请求 ---- #
        if direct_links:
            extracted = link_obj.detail("\n".join(direct_links))
            if isawaitable(extracted):
                extracted = await extracted
            ids.extend(extracted or [])
            ctx.log(
                "info",
                f"完整链接解析完成，得到 {len(ids)} 个作品 ID",
            )

        # ---- 短链：逐条请求解析，输出进度与预估耗时 ---- #
        if short_links:
            estimate = len(short_links) * max(ctx.wait_avg, 0.1) / 60
            ctx.log(
                "info",
                f"开始解析 {len(short_links)} 条短链，预计至少 {estimate:.1f} 分钟；"
                f"日志会定期输出进度，可随时点「停止」。",
            )
            for index, url in enumerate(short_links, start=1):
                if ctx.is_stopping():
                    break
                ctx.phase(f"正在解析短链（{index}/{len(short_links)}）")
                try:
                    found = await link_obj.run(url, "detail")
                except Exception as exc:  # noqa: BLE001
                    ctx.log("warning", f"短链解析失败（已跳过）：{url} — {exc!r}")
                    found = []
                ids.extend(found or [])
                ctx.progress(index, len(short_links))
                if index % 10 == 0 or index == len(short_links):
                    ctx.log(
                        "info",
                        f"短链解析进度 {index}/{len(short_links)}，"
                        f"已得到 {len(ids)} 个作品 ID",
                    )

        ids = [i for i in dict.fromkeys(ids) if i]
        if not ids:
            ctx.log("warning", "未能从上述链接中解析出任何作品 ID。")
            ctx.log("warning", self._no_id_hint())
            return ctx.stats
        ctx.log("success", f"共解析出 {len(ids)} 个作品 ID。")
        ctx.counters.work_ids = len(ids)
        ctx.push_stats()

        # ---- 关键优化：请求详情之前先按下载记录预过滤 ---- #
        kept, _skipped = await ctx.dedup.filter_ids(ids)
        ctx.counters.dedup_skipped = len(ctx.dedup.skipped_ids)
        ctx.push_stats()
        if not kept:
            ctx.log("success", "全部作品均已下载过，本次不会产生任何接口请求与文件下载。")
            return ctx.stats

        ctx.progress(0, len(kept))
        ctx.counters.set_accounts(0, len(kept))
        root, params, logger_cls = ctx.tiktok.record.run(ctx.parameter)
        async with logger_cls(root, console=ctx.console, **params) as record:
            for index, id_ in enumerate(kept, start=1):
                if ctx.is_stopping():
                    break
                try:
                    await ctx.tiktok._handle_detail([id_], tiktok_flag, record)
                    ctx.stats["处理作品"] += 1
                except Exception as exc:  # noqa: BLE001
                    ctx.log("error", f"作品 {id_} 处理失败：{exc!r}")
                ctx.progress(index, len(kept))
                ctx.counters.set_accounts(index, len(kept))
                ctx.push_stats()
                if index < len(kept):
                    await self._pace(ctx, index)
        return ctx.stats

    async def _run_account(self, ctx: _Context) -> dict:
        """批量下载账号作品。"""
        tiktok_flag = ctx.req.platform == "tiktok"
        links = ctx.req.links
        ctx.progress(0, len(links))
        ctx.counters.set_accounts(0, len(links))
        ctx.push_stats()
        for index, url in enumerate(links, start=1):
            if ctx.is_stopping():
                break
            try:
                sec_user_id = await ctx.tiktok.check_sec_user_id(url, tiktok_flag)
                if not sec_user_id:
                    ctx.log("warning", f"未能从 {url} 提取 sec_user_id，已跳过。")
                    continue
                await ctx.tiktok.deal_account_detail(
                    index,
                    sec_user_id=sec_user_id,
                    tab=ctx.req.account_tab,
                    tiktok=tiktok_flag,
                )
                ctx.stats["处理作品"] += 1
            except Exception as exc:  # noqa: BLE001
                ctx.log("error", f"账号 {url} 处理失败：{exc!r}")
            ctx.progress(index, len(links))
            ctx.counters.set_accounts(index, len(links))
            ctx.push_stats()
            if index < len(links):
                await self._pace(ctx, index)
        return ctx.stats

    async def _run_mix(self, ctx: _Context) -> dict:
        """批量下载合集作品。"""
        tiktok_flag = ctx.req.platform == "tiktok"
        links = ctx.req.links
        ctx.progress(0, len(links))
        ctx.counters.set_accounts(0, len(links))
        ctx.push_stats()
        for index, url in enumerate(links, start=1):
            if ctx.is_stopping():
                break
            try:
                mix_id, id_, title = await ctx.tiktok._check_mix_id(url, tiktok_flag)
                if not id_:
                    ctx.log("warning", f"未能从 {url} 获取作品 ID 或合集 ID，已跳过。")
                    continue
                await ctx.tiktok.deal_mix_detail(
                    mix_id,
                    id_,
                    "",
                    index,
                    tiktok=tiktok_flag,
                    mix_title=title,
                )
                ctx.stats["处理作品"] += 1
            except Exception as exc:  # noqa: BLE001
                ctx.log("error", f"合集 {url} 处理失败：{exc!r}")
            ctx.progress(index, len(links))
            ctx.counters.set_accounts(index, len(links))
            ctx.push_stats()
            if index < len(links):
                await self._pace(ctx, index)
        return ctx.stats

    async def _run_live(self, ctx: _Context) -> dict:
        """获取直播拉流地址（可选交给 FFmpeg 录制）。"""
        tiktok_flag = ctx.req.platform == "tiktok"
        link_obj = ctx.tiktok.links_tiktok if tiktok_flag else ctx.tiktok.links
        text = "\n".join(ctx.req.links)

        ctx.phase("正在解析直播地址…")
        ids = await link_obj.run(text, type_="live")
        if not ids:
            ctx.log("warning", "未能解析出任何直播 ID。")
            return ctx.stats
        if not ctx.cfg.get("live_qualities"):
            ctx.log(
                "warning",
                "未设置“直播清晰度”，程序只会列出拉流地址而不会录制；"
                "如需自动录制请在高级设置中填写清晰度（如 origin 或序号 1）。",
            )

        ctx.log("info", f"共解析出 {len(ids)} 个直播 ID，正在获取直播数据……")
        if tiktok_flag:
            live_data = [await ctx.tiktok.get_live_data_tiktok(i) for i in ids]
            live_data = await ctx.tiktok.extractor.run(live_data, None, "live", tiktok=True)
            tasks = ctx.tiktok.show_live_info_tiktok(live_data)
        else:
            live_data = [await ctx.tiktok.get_live_data(i) for i in ids]
            live_data = await ctx.tiktok.extractor.run(live_data, None, "live")
            tasks = ctx.tiktok.show_live_info(live_data)

        ctx.stats["处理作品"] = len(tasks)
        if tasks:
            ctx.phase("正在启动直播录制…")
            await ctx.tiktok.downloader.run(tasks, type_="live", tiktok=tiktok_flag)
        else:
            ctx.log("info", "没有可下载的直播任务（可能直播已结束或未选择清晰度）。")
        return ctx.stats

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    @staticmethod
    def _no_id_hint() -> str:
        """解析不出作品 ID 时给出可操作的排查建议。"""
        return (
            "最常见的原因是下载类型选错：当前是「批量下载链接作品」，"
            "它只识别含 19 位作品 ID 的链接"
            "（例如 https://www.douyin.com/video/7300000000000000000）。"
            "如果提交的是账号主页链接，请把「下载类型」改为「批量下载账号作品」；"
            "如果是合集链接，请改为「批量下载合集作品」。"
        )

    async def _pace(self, ctx: _Context, index: int) -> None:
        """作品之间的额外间隔与批次休眠。"""
        if ctx.inter_delay > 0:
            await asyncio.sleep(ctx.inter_delay)
        if (
            ctx.suspend_every
            and ctx.suspend_seconds > 0
            and index % ctx.suspend_every == 0
        ):
            ctx.log(
                "info",
                f"已连续处理 {index} 个对象，主动休眠 {ctx.suspend_seconds:.0f} 秒规避频率风控……",
            )
            await asyncio.sleep(ctx.suspend_seconds)

    @staticmethod
    def _install_dedup_hook(tiktok: Any, dedup: DedupManager, cfg: dict, log) -> None:
        """用去重预过滤包装实例方法 ``download_detail_batch``。

        账号 / 合集模式会在解析出完整作品列表后调用该方法，
        此处过滤可以避免对已下载作品重走下载流程。
        """
        if not cfg.get("dedup_prefilter", True):
            return
        original = tiktok.download_detail_batch

        async def patched(data, *args, **kwargs):
            if not data:
                return None
            kept, _skipped = await dedup.filter_items(data)
            if not kept:
                log("info", "[去重] 本次列表中的作品均已下载，跳过下载阶段。")
                return None
            return await original(kept, *args, **kwargs)

        tiktok.download_detail_batch = patched

    @staticmethod
    def _report_cookie_state(parameter: Any, req: TaskRequest, log) -> None:
        if req.platform == "tiktok":
            ok = getattr(parameter, "cookie_tiktok_state", False)
            name = "TikTok Cookie"
        else:
            ok = getattr(parameter, "cookie_state", False)
            name = "抖音 Cookie"
        if ok:
            log("success", f"{name} 校验通过：已处于登录状态。")
        else:
            log(
                "warning",
                f"{name} 未检测到登录标识（sessionid/sessionid_ss），"
                f"部分接口可能返回空数据或触发风控。",
            )

    # ------------------------------------------------------------------ #
    # 指纹与设置构造
    # ------------------------------------------------------------------ #
    def _pick_profile(self) -> dict | None:
        cfg = self.config
        if not cfg.get("antispider_enable", True):
            return None
        if not cfg.get("ua_rotate", True):
            return None
        pool = list(cfg.get("impersonate_pool") or [])
        # TikTok 的请求参数内嵌完整 UA 串且 browser_name 固定为 Mozilla，
        # 改用 WebKit/Gecko 的 UA 结构会偏离内核预期，因此仅轮换 Blink 内核族。
        blink_only = self.request.platform == "tiktok"
        try:
            return antispider.pick_fingerprint(pool, blink_only=blink_only)
        except Exception:
            return None

    def _build_settings(self, req: TaskRequest, profile: dict | None) -> dict:
        """把界面配置展开为上游 settings.json 的结构。"""
        cfg = self.config
        douyin = req.platform == "douyin"

        name_format = " ".join(cfg.get("name_format") or []) or "create_time type nickname desc"
        root = str(cfg.get("root") or "").strip() or str(DOWNLOADS_DIR)

        return {
            "accounts_urls": [],
            "accounts_urls_tiktok": [],
            "mix_urls": [],
            "mix_urls_tiktok": [],
            "owner_url": {
                "mark": "",
                "url": "",
                "uid": "",
                "sec_uid": "",
                "nickname": "",
            },
            "owner_url_tiktok": None,
            "root": root,
            "folder_name": str(cfg.get("folder_name") or "Download"),
            "name_format": name_format,
            "desc_length": int(cfg.get("desc_length") or 64),
            "name_length": int(cfg.get("name_length") or 128),
            "date_format": str(cfg.get("date_format") or "%Y-%m-%d %H:%M:%S"),
            "split": str(cfg.get("split") or "-"),
            "folder_mode": bool(cfg.get("folder_mode")),
            "music": bool(cfg.get("music")),
            "truncate": int(cfg.get("truncate") or 50),
            "storage_format": str(cfg.get("storage_format") or ""),
            "cookie": normalize_cookie(str(cfg.get("cookie") or "")) if douyin else "",
            "cookie_tiktok": (
                "" if douyin else normalize_cookie(str(cfg.get("cookie_tiktok") or ""))
            ),
            "dynamic_cover": bool(cfg.get("dynamic_cover")),
            "static_cover": bool(cfg.get("static_cover")),
            "proxy": str(cfg.get("proxy") or "") if douyin else "",
            "proxy_tiktok": "" if douyin else str(cfg.get("proxy_tiktok") or ""),
            "twc_tiktok": "",
            "download": bool(cfg.get("download")),
            "max_size": int(cfg.get("max_size") or 0),
            "chunk": int(cfg.get("chunk") or 2097152),
            "timeout": int(cfg.get("timeout") or 10),
            "max_retry": int(cfg.get("max_retry") if cfg.get("max_retry") is not None else 5),
            "max_pages": int(cfg.get("max_pages") or 0),
            "run_command": "",
            "ffmpeg": str(cfg.get("ffmpeg") or ""),
            "live_qualities": str(cfg.get("live_qualities") or ""),
            "original_quality": bool(cfg.get("original_quality")),
            # 本次任务只跑当前分页对应的平台，避免另一平台做无谓的参数初始化
            "douyin_platform": douyin,
            "tiktok_platform": not douyin,
            "browser_info": self._browser_info_douyin(profile),
            "browser_info_tiktok": self._browser_info_tiktok(profile),
        }

    def _browser_info_douyin(self, profile: dict | None) -> dict:
        cfg = self.config
        info = {
            "impersonate": str(cfg.get("browser_info_impersonate") or "chrome146"),
            "pc_libra_divert": str(cfg.get("browser_info_pc_libra_divert") or "Mac"),
            "browser_language": str(cfg.get("browser_info_browser_language") or "zh-CN"),
            "browser_platform": str(cfg.get("browser_info_browser_platform") or "MacIntel"),
            "browser_name": str(cfg.get("browser_info_browser_name") or "Chrome"),
            "browser_version": str(cfg.get("browser_info_browser_version") or "146.0.0.0"),
            "engine_name": str(cfg.get("browser_info_engine_name") or "Blink"),
            "engine_version": str(cfg.get("browser_info_engine_version") or "146.0.0.0"),
            "os_name": str(cfg.get("browser_info_os_name") or "Mac OS"),
            "os_version": str(cfg.get("browser_info_os_version") or "10.15.7"),
            "webid": str(cfg.get("browser_info_webid") or ""),
        }
        if profile:
            # 整套替换，保证 TLS 指纹、UA、平台、系统版本彼此自洽
            for key in (
                "impersonate",
                "pc_libra_divert",
                "browser_language",
                "browser_platform",
                "browser_name",
                "browser_version",
                "engine_name",
                "engine_version",
                "os_name",
                "os_version",
            ):
                if profile.get(key):
                    info[key] = profile[key]
        return info

    def _browser_info_tiktok(self, profile: dict | None) -> dict:
        cfg = self.config
        ua = str(
            cfg.get("browser_info_tiktok_browser_version")
            or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        )
        impersonate = str(cfg.get("browser_info_tiktok_impersonate") or "chrome146")
        platform = str(cfg.get("browser_info_tiktok_browser_platform") or "MacIntel")

        if profile:
            impersonate = profile["impersonate"]
            # TikTok 的 browser_version 是完整 UA 串，仅让其中的浏览器版本号与
            # TLS 指纹保持一致，不改变其结构，避免影响内核的签名参数。
            version = profile["browser_version"].split(".")[0]
            new_ua = re_sub(r"Chrome/\d+\.0\.0\.0", f"Chrome/{version}.0.0.0", ua)
            if new_ua == ua and "Chrome/" not in ua:
                new_ua = profile["ua"]
            ua = new_ua

        return {
            "impersonate": impersonate,
            "app_language": str(cfg.get("browser_info_tiktok_app_language") or "zh-Hans"),
            "browser_language": str(cfg.get("browser_info_tiktok_browser_language") or "zh-CN"),
            "browser_name": str(cfg.get("browser_info_tiktok_browser_name") or "Mozilla"),
            "browser_platform": platform,
            "browser_version": ua,
            "language": str(cfg.get("browser_info_tiktok_language") or "zh-Hans"),
            "os": str(cfg.get("browser_info_tiktok_os") or "mac"),
            "priority_region": str(cfg.get("browser_info_tiktok_priority_region") or "US"),
            "region": str(cfg.get("browser_info_tiktok_region") or "US"),
            "tz_name": str(cfg.get("browser_info_tiktok_tz_name") or "Asia/Shanghai"),
            "webcast_language": str(
                cfg.get("browser_info_tiktok_webcast_language") or "zh-Hans"
            ),
            "device_id": str(cfg.get("browser_info_tiktok_device_id") or ""),
        }
