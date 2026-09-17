"""反爬虫增强。

设计原则：**不修改上游源码**，全部通过运行时的模块属性替换 / 类属性替换实现。

接管的能力与落点：

===============  ==========================================================
能力             落点
===============  ==========================================================
请求节流         ``src.custom.function.get_wait_time``（``wait()`` 在调用时
                 才在模块全局查找该函数，因此替换即刻生效）
重试退避         ``src.tools.retry.Retry.retry`` / ``retry_lite``
                 （必须在 ``src.downloader`` 等模块被导入前替换，
                 否则装饰器已完成绑定）
下载并发         ``src.downloader.download.Downloader.semaphore``
批次休眠         ``src.application.main_terminal.suspend``
                 （该模块以 ``from ..custom import suspend`` 绑定了函数对象，
                  因此需要直接替换其模块属性）
指纹轮换         构造内核参数前，把一套「自洽的」浏览器指纹
                 （TLS 指纹 + UA + 平台 + 系统版本 + 内核版本）写入
                 settings 字典，保证签名用的 UA 与实际 TLS 指纹一致
===============  ==========================================================
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from importlib import import_module
from math import log
from random import choice as random_choice, lognormvariate
from re import match as re_match
from typing import Any

__all__ = [
    "Resolved",
    "resolve",
    "apply",
    "apply_after_import",
    "pick_fingerprint",
    "supported_impersonate",
    "profile_version",
    "describe",
]

# 上游默认值（antispider_enable=False 时完全回退到这些值）
UPSTREAM_DEFAULTS = {
    "wait_avg": 6.0,
    "wait_sigma": 0.5,
    "wait_min": 1.5,
    "wait_max": 33.3,
    "max_workers": 4,
}

# --------------------------------------------------------------------------- #
# 指纹画像
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Family:
    """一个浏览器指纹族的规格。"""

    name: str
    pattern: str
    browser_name: str
    engine_name: str
    engine_version: str  # 空字符串表示与 browser_version 相同
    version_kind: str  # chromium | gecko | webkit
    #: (browser_platform, os_name, os_version) 组合
    variants: tuple[tuple[str, str, str], ...]


_FAMILIES: tuple[_Family, ...] = (
    _Family(
        "chrome", r"^chrome(\d+)$", "Chrome", "Blink", "", "chromium",
        (("MacIntel", "Mac OS", "10.15.7"), ("Win32", "Windows", "10")),
    ),
    _Family(
        "edge", r"^edge(\d+)$", "Edge", "Blink", "", "chromium",
        (("Win32", "Windows", "10"),),
    ),
    _Family(
        "firefox", r"^firefox(\d+)$", "Firefox", "Gecko", "", "gecko",
        (("Win32", "Windows", "10"),),
    ),
    _Family(
        "safari", r"^safari(\d{3})$", "Safari", "WebKit", "605.1.15", "webkit",
        (("MacIntel", "Mac OS", "10.15.7"),),
    ),
)

#: 仅 Blink 内核族（其 UA 结构与内核默认值一致，改动风险最小）
_BLINK_FAMILIES = frozenset({"chrome", "edge"})

#: 无法枚举 curl_cffi 版本信息时的兜底候选
_FALLBACK_CANDIDATES: tuple[str, ...] = (
    "chrome150", "chrome146", "chrome142", "chrome136", "chrome131",
    "chrome124", "edge101", "firefox147", "safari184", "safari180",
)

_CATALOGUE: list[tuple[str, _Family, str]] | None = None


def _enumerate_browser_types() -> list[str]:
    """读取 curl_cffi 提供的指纹枚举（不同版本位于不同模块）。"""
    for module_name in ("curl_cffi.const", "curl_cffi.requests"):
        try:
            module = import_module(module_name)
            enum_cls = getattr(module, "BrowserType")
            values = [
                str(item.value) for item in enum_cls if getattr(item, "value", None)
            ]
            if values:
                return values
        except Exception:  # noqa: BLE001
            continue
    return []


def _family_of(impersonate: str) -> tuple[_Family, str] | None:
    """把 impersonate 解析为 (族, 版本数字)。无法解析时返回 None。"""
    for family in _FAMILIES:
        matched = re_match(family.pattern, impersonate)
        if matched:
            return family, matched.group(1)
    return None


def _format_version(kind: str, digits: str) -> str:
    if kind == "chromium":
        return f"{int(digits)}.0.0.0"
    if kind == "gecko":
        return f"{int(digits)}.0"
    if kind == "webkit":  # safari153 -> 15.3
        return f"{int(digits[:2])}.{int(digits[2:] or 0)}"
    return f"{int(digits)}.0.0.0"


def _catalogue() -> list[tuple[str, _Family, str]]:
    """可安全构造自洽画像的桌面指纹清单。

    自动剔除 ``*_android`` / ``*_ios`` 等移动端取值，以及
    ``chrome133a`` / ``safari2601`` 之类命名不规范、版本号无法可靠推断的取值——
    否则会出现「声称 macOS 却使用 Android 指纹」这类自相矛盾的画像，
    反而更容易被识别为异常流量。
    """
    global _CATALOGUE
    if _CATALOGUE is not None:
        return _CATALOGUE

    entries: list[tuple[str, _Family, str]] = []
    seen: set[str] = set()
    for value in _enumerate_browser_types():
        lowered = value.lower()
        if lowered in seen:
            continue
        resolved = _family_of(lowered)
        if resolved is None:
            continue
        seen.add(lowered)
        entries.append((lowered, resolved[0], resolved[1]))

    if not entries:
        for value in _FALLBACK_CANDIDATES:
            resolved = _family_of(value)
            if resolved:
                entries.append((value, resolved[0], resolved[1]))

    _CATALOGUE = entries
    return _CATALOGUE


def supported_impersonate() -> list[str]:
    """枚举可安全使用的桌面浏览器指纹（已过滤移动端与不规范的取值）。"""
    return [item[0] for item in _catalogue()]


def profile_version(impersonate: str) -> str | None:
    """返回某指纹对应的浏览器版本号字符串，例如 ``chrome146`` -> ``146.0.0.0``。"""
    resolved = _family_of(impersonate.lower())
    if resolved is None:
        return None
    family, digits = resolved
    return _format_version(family.version_kind, digits)


def _build_ua(family: _Family, version: str, variant: tuple[str, str, str]) -> str:
    platform = variant[0]
    if family.name == "Safari":
        return (
            "5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            f"(KHTML, like Gecko) Version/{version} Safari/605.1.15"
        )
    win = "Windows NT 10.0; Win64; x64"
    if family.name == "Edge":
        return (
            f"5.0 ({win}) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{version} Safari/537.36 Edg/{version}"
        )
    if family.name == "Firefox":
        return f"5.0 ({win}; rv:{version}) Gecko/20100101 Firefox/{version}"
    if platform == "MacIntel":
        return (
            "5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{version} Safari/537.36"
        )
    return (
        f"5.0 ({win}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version} Safari/537.36"
    )


def pick_fingerprint(pool: list[str] | None = None, blink_only: bool = False) -> dict:
    """随机挑选一套**自洽**的浏览器指纹。

    :param pool: 指纹族名称列表，可选 ``chrome`` / ``edge`` / ``safari`` / ``firefox``
    :param blink_only: 仅使用 Blink 内核族（Chrome / Edge）。
        用于 TikTok 平台——其请求参数内嵌完整 UA 串且 ``browser_name`` 固定为
        ``Mozilla``，改用 WebKit/Gecko 的 UA 结构会偏离内核预期，因此不做轮换。
    :return: 含 ``impersonate`` / ``browser_version`` / ``ua`` 等字段的字典，
        另附 ``desc`` 便于日志输出
    """
    families = {p.lower() for p in (pool or ["chrome", "edge", "safari"])}
    entries = [item for item in _catalogue() if item[1].name in families]
    if blink_only:
        entries = [item for item in entries if item[1].name in _BLINK_FAMILIES]
    if not entries:
        entries = [
            item for item in _catalogue() if item[1].name in _BLINK_FAMILIES
        ] or list(_catalogue())

    impersonate, family, digits = random_choice(entries)
    version = _format_version(family.version_kind, digits)
    variant = random_choice(family.variants)
    platform, os_name, os_version = variant

    return {
        "impersonate": impersonate,
        "pc_libra_divert": "Mac" if platform == "MacIntel" else "Windows",
        "browser_language": "zh-CN",
        "browser_platform": platform,
        "browser_name": family.browser_name,
        "browser_version": version,
        "engine_name": family.engine_name,
        "engine_version": family.engine_version or version,
        "os_name": os_name,
        "os_version": os_version,
        "ua": _build_ua(family, version, variant),
        "desc": f"{family.browser_name} {version} · {os_name} · TLS={impersonate}",
    }


# --------------------------------------------------------------------------- #
# 配置解析
# --------------------------------------------------------------------------- #


@dataclass
class Resolved:
    """规整后的反爬虫参数。"""

    enabled: bool = True
    wait_avg: float = UPSTREAM_DEFAULTS["wait_avg"]
    wait_sigma: float = UPSTREAM_DEFAULTS["wait_sigma"]
    wait_min: float = UPSTREAM_DEFAULTS["wait_min"]
    wait_max: float = UPSTREAM_DEFAULTS["wait_max"]
    max_workers: int = UPSTREAM_DEFAULTS["max_workers"]
    retry_backoff: float = 2.0
    retry_backoff_factor: float = 2.0
    retry_backoff_cap: float = 60.0
    suspend_every: int = 10
    suspend_seconds: float = 60.0
    inter_item_delay: float = 0.0
    applied: list[str] = field(default_factory=list)


def resolve(cfg: dict) -> Resolved:
    """把界面配置解析为 :class:`Resolved`；未启用增强时回退上游默认值。"""
    enabled = bool(cfg.get("antispider_enable", True))
    res = Resolved(enabled=enabled)
    if not enabled:
        res.suspend_every = 10          # 上游 suspend() 的硬编码行为
        res.suspend_seconds = 300.0
        return res

    def num(key: str, default: float, lo: float | None = None, hi: float | None = None):
        try:
            value = float(cfg.get(key, default))
        except (TypeError, ValueError):
            value = default
        value = value if lo is None else max(lo, value)
        value = value if hi is None else min(hi, value)
        return value

    res.wait_avg = num("wait_avg", 6.0, 0.1, 600.0)
    res.wait_sigma = num("wait_sigma", 0.5, 0.0, 3.0)
    res.wait_min = num("wait_min", 1.5, 0.0, 600.0)
    res.wait_max = num("wait_max", 33.3, 0.1, 3600.0)
    if res.wait_max < res.wait_min:
        res.wait_max = res.wait_min
    res.max_workers = int(num("max_workers", 4, 1, 32))
    res.retry_backoff = num("retry_backoff", 2.0, 0.0, 600.0)
    res.retry_backoff_factor = num("retry_backoff_factor", 2.0, 1.0, 10.0)
    res.retry_backoff_cap = num("retry_backoff_cap", 60.0, 0.1, 3600.0)
    res.suspend_every = int(num("batch_suspend_every", 10, 0, 100000))
    res.suspend_seconds = num("batch_suspend_seconds", 60.0, 0.0, 7200.0)
    res.inter_item_delay = num("inter_item_delay", 0.0, 0.0, 600.0)
    return res


# --------------------------------------------------------------------------- #
# 打补丁
# --------------------------------------------------------------------------- #


def _install_wait(res: Resolved, console) -> None:
    """接管请求节流：替换 ``src.custom.function.get_wait_time``。"""
    from src.custom import function as fn

    def get_wait_time(avg_delay: float | None = None, sigma: float | None = None) -> float:
        avg = float(avg_delay) if avg_delay else res.wait_avg
        avg = max(0.05, avg)
        sig = res.wait_sigma if sigma is None else max(0.0, float(sigma))
        mu = log(avg) - (sig**2) / 2
        return min(res.wait_max, max(res.wait_min, lognormvariate(mu, sig)))

    fn.get_wait_time = get_wait_time
    res.applied.append(
        f"请求节流：平均 {res.wait_avg:.1f}s / σ={res.wait_sigma:.2f} / "
        f"区间 {res.wait_min:.1f}~{res.wait_max:.1f}s"
    )


def _install_retry(res: Resolved, console) -> None:
    """接管重试策略：为退避等待注入指数增长。"""
    from src.tools import retry as retry_mod

    async def backoff(index: int) -> None:
        """index 从 0 开始，表示第 index+1 次重试。"""
        if res.retry_backoff <= 0:
            from src.custom import wait as upstream_wait

            await upstream_wait()
            return
        delay = min(res.retry_backoff_cap, res.retry_backoff * (res.retry_backoff_factor**index))
        if delay > 0:
            await asyncio.sleep(delay)

    def make_retry(original):
        def retry(function):
            async def inner(self, *args, **kwargs):
                finished = kwargs.pop("finished", False)
                for i in range(self.max_retry):
                    if result := await function(self, *args, **kwargs):
                        return result
                    self.log.warning(f"正在进行第 {i + 1} 次重试")
                    await backoff(i)
                if not (result := await function(self, *args, **kwargs)) and finished:
                    self.finished = True
                return result

            return inner

        return retry

    def make_retry_lite(original):
        def retry_lite(function):
            async def inner(*args, **kwargs):
                if r := await function(*args, **kwargs):
                    return r
                for i in range(retry_mod.RETRY):
                    if r := await function(*args, **kwargs):
                        return r
                    await backoff(i)
                return r

            return inner

        return retry_lite

    retry_mod.Retry.retry = staticmethod(make_retry(retry_mod.Retry.retry))
    retry_mod.Retry.retry_lite = staticmethod(make_retry_lite(retry_mod.Retry.retry_lite))
    res.applied.append(
        f"退避重试：基数 {res.retry_backoff:.1f}s / 倍数 {res.retry_backoff_factor:.1f} "
        f"/ 上限 {res.retry_backoff_cap:.0f}s"
    )


def _install_max_workers(res: Resolved) -> None:
    """接管文件下载并发数。"""
    from src.downloader.download import Downloader

    Downloader.semaphore = asyncio.Semaphore(res.max_workers)
    res.applied.append(f"文件并发下载数：{res.max_workers}")


def _install_suspend(res: Resolved, console) -> None:
    """接管批次休眠（账号 / 合集等循环中调用）。"""
    from src.application import main_terminal

    async def suspend(count: int, _console=None, *args, **kwargs) -> None:
        if not res.suspend_every or count % res.suspend_every:
            return
        if res.suspend_seconds <= 0:
            return
        (console or _console).print(
            f"已连续处理 {count} 个对象，为避免请求频率过高触发风控，"
            f"主动休眠 {res.suspend_seconds:.0f} 秒后继续……"
        )
        await asyncio.sleep(res.suspend_seconds)

    main_terminal.suspend = suspend
    if res.suspend_every:
        res.applied.append(
            f"批次休眠：每 {res.suspend_every} 个对象休眠 {res.suspend_seconds:.0f}s"
        )


def apply(cfg: dict, console) -> Resolved:
    """安装全部补丁。

    必须在导入 ``src.downloader`` / ``src.application`` 之前调用，
    否则重试装饰器已完成绑定、无法再被替换。
    """
    res = resolve(cfg)
    _install_wait(res, console)
    _install_retry(res, console)
    return res


def apply_after_import(cfg: dict, console) -> Resolved:
    """安装依赖内核业务模块的补丁（并发数、批次休眠）。"""
    res = resolve(cfg)
    _install_max_workers(res)
    _install_suspend(res, console)
    return res


def describe(res: Resolved) -> list[str]:
    """返回可直接打印到日志的说明行。"""
    header = "已启用反爬虫增强：" if res.enabled else "反爬虫增强未启用（使用内核默认策略）："
    return [header, *[f"  · {line}" for line in res.applied]]
