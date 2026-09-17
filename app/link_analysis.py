"""链接类型识别与下载类型匹配检查。

解决的问题：当用户把**账号主页链接**粘贴进「批量下载链接作品」模式时，
内核只会从链接里提取 19 位作品 ID，账号主页链接不含作品 ID，
于是会白跑一轮链接解析（每条链接一次请求，按反爬间隔等待，可能十几分钟）
最后才报「未能解析出任何作品 ID」，用户很难自己定位原因。

本模块在启动前先判定链接类型，若与所选下载类型明显不匹配，就给出可操作的建议。

纯标准库实现，不在界面层引入内核依赖。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "LinkAnalysis",
    "analyse",
    "classify_link",
    "needs_resolution",
    "split_by_resolution",
    "MODE_NAMES",
    "KIND_NAMES",
    "URL_PATTERN",
    "SHORT_LINK_PATTERN",
]

#: 下载类型 -> 中文名
MODE_NAMES: dict[str, str] = {
    "detail": "批量下载链接作品",
    "account": "批量下载账号作品",
    "mix": "批量下载合集作品",
    "live": "获取直播拉流地址",
}

#: 链接类型 -> 中文名
KIND_NAMES: dict[str, str] = {
    "work": "作品链接",
    "account": "账号主页链接",
    "mix": "合集链接",
    "live": "直播链接",
    "short": "短链（需解析后才能判断）",
    "unknown": "无法识别",
}

#: 链接类型 -> 适配的下载类型
MODE_FOR_KIND: dict[str, str] = {
    "work": "detail",
    "account": "account",
    "mix": "mix",
    "live": "live",
}

#: 与内核 ``src/link/requester.py::Requester.URL`` 完全一致的 URL 提取正则
URL_PATTERN = re.compile(r"https?://[^\s\"<>\\^`{|}，。；！？、【】《》]+")

#: 短链：**只有这类链接才必须真正发请求去解析跳转**。
#: 形如 https://v.douyin.com/xxx/ 的短链本身不含任何可用信息，
#: 内核必须请求一次拿到 302 后的真实地址才能提取作品 ID；
#: 而 https://www.douyin.com/video/7300000000000000000 这类完整链接，
#: 作品 ID 就在 URL 里，直接做正则提取即可，无需任何请求。
SHORT_LINK_PATTERN = re.compile(
    r"https?://(?:v|vt)\.douyin\.com/"
    r"|https?://(?:vt|vm)\.tiktok\.com/"
)

#: 判定占多数所需的最低比例
_DOMINANT_RATIO = 0.6

_DOUYIN_LIVE = re.compile(
    r"(live\.douyin\.com/\d+|douyin\.com/follow\?|webcast\.amemv\.com/douyin/webcast/reflow/)"
)
_DOUYIN_MIX = re.compile(
    r"(douyin\.com/collection/\d+|iesdouyin\.com/share/mix/detail/\d+)"
)
_DOUYIN_WORK = re.compile(
    r"(douyin\.com/(?:video|note|slides)/\d{19}"
    r"|iesdouyin\.com/share/(?:video|note|slides)/\d{19}"
    r"|modal_id=\d{19}"
    r"|douyin\.com/channel/\d+\?modal_id=\d{19})"
)
_DOUYIN_ACCOUNT = re.compile(
    r"(douyin\.com/user/[A-Za-z0-9_-]+|iesdouyin\.com/share/user/)"
)
_DOUYIN_SHORT = re.compile(r"(v\.douyin\.com/|iesdouyin\.com/)")

_TIKTOK_LIVE = re.compile(r"tiktok\.com/@[^/\s]+/live")
_TIKTOK_MIX = re.compile(r"tiktok\.com/@[^/\s]+/(?:playlist|collection)/")
_TIKTOK_WORK = re.compile(r"tiktok\.com/@[^/\s]+/(?:video|photo)/\d{19}")
_TIKTOK_ACCOUNT = re.compile(r"tiktok\.com/@[^/\s?]+")


def classify_link(url: str, platform: str = "douyin") -> str:
    """判断单条链接属于哪一类。

    :return: ``work`` / ``account`` / ``mix`` / ``live`` / ``short`` / ``unknown``
    """
    text = (url or "").strip()
    if not text:
        return "unknown"

    if platform == "tiktok":
        for kind, pattern in (
            ("live", _TIKTOK_LIVE),
            ("mix", _TIKTOK_MIX),
            ("work", _TIKTOK_WORK),
            ("account", _TIKTOK_ACCOUNT),
        ):
            if pattern.search(text):
                return kind
        return "unknown"

    # 抖音：live -> mix -> work -> account -> short
    # 注意把 modal_id 判定为作品（内核会从中提取作品 ID，即使它挂在账号主页后面）
    for kind, pattern in (
        ("live", _DOUYIN_LIVE),
        ("mix", _DOUYIN_MIX),
        ("work", _DOUYIN_WORK),
        ("account", _DOUYIN_ACCOUNT),
        ("short", _DOUYIN_SHORT),
    ):
        if pattern.search(text):
            return kind
    return "unknown"


@dataclass
class LinkAnalysis:
    """一批链接的类型统计与模式匹配建议。"""

    total: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    #: 占多数的链接类型（work / account / mix / live），无法判定时为 None
    dominant_kind: str | None = None
    #: 该类型适配的下载类型；无法判定时为 None
    suggested_mode: str | None = None

    @property
    def classified(self) -> int:
        """可明确归类的链接数量（不含短链与无法识别的）。"""
        return sum(self.counts.get(k, 0) for k in MODE_FOR_KIND)

    def describe(self) -> str:
        parts = [
            f"{KIND_NAMES[kind]} {self.counts[kind]} 条"
            for kind in ("work", "account", "mix", "live", "short", "unknown")
            if self.counts.get(kind)
        ]
        return "、".join(parts) if parts else "无"

    # ------------------------------------------------------------------ #
    def mismatch_message(self, mode: str) -> str:
        """返回不匹配提示；匹配时返回空字符串。"""
        if not self.total:
            return ""

        kind = self.dominant_kind
        #: 输入占多数的链接类型所适配的下载类型
        expected = MODE_FOR_KIND.get(kind or "")
        current_name = MODE_NAMES.get(mode, mode)

        # 情况一：没有任何可明确归类的链接
        if self.classified == 0 or not kind:
            if self.counts.get("short"):
                return (
                    f"检测到 {self.counts['short']} 条短链，需要在解析后才能确定类型。\n"
                    f"若解析结果为空，请确认下载类型与链接内容是否匹配。"
                )
            return (
                "提交的内容里没有识别到任何可用的链接。\n"
                "请确认已填写完整链接（需以 http:// 或 https:// 开头）。"
            )

        # 情况二：所选模式无法处理这类链接
        if expected and expected != mode:
            message = (
                f"共 {self.total} 条输入：{self.describe()}。\n\n"
                f"当前下载类型是「{current_name}」，但输入主要是"
                f"{KIND_NAMES[kind]}，该模式不会处理这类链接，"
                f"最终只会提示「未能解析出任何作品 ID」。\n\n"
                f"建议改用「{MODE_NAMES.get(expected, expected)}」。"
            )
            if mode == "detail":
                message += (
                    "\n\n补充：作品链接模式只能识别含 19 位作品 ID 的链接"
                    "（如 https://www.douyin.com/video/7300000000000000000）。"
                )
            return message

        return ""


def needs_resolution(url: str) -> bool:
    """该链接是否必须先发一次请求解析跳转才能提取作品 ID。"""
    return bool(SHORT_LINK_PATTERN.search(url or ""))


def split_by_resolution(links: list[str]) -> tuple[list[str], list[str]]:
    """把链接分成 (需解析的短链, 可直接提取的完整链接)，均保持原顺序。"""
    short: list[str] = []
    direct: list[str] = []
    for link in links:
        (short if needs_resolution(link) else direct).append(link)
    return short, direct


def analyse(links: list[str], platform: str = "douyin") -> LinkAnalysis:
    """统计一批链接的类型，并在某类占多数时给出推荐下载类型。"""
    counts: dict[str, int] = {}
    for link in links:
        kind = classify_link(link, platform)
        counts[kind] = counts.get(kind, 0) + 1

    result = LinkAnalysis(total=len(links), counts=counts)
    if result.classified:
        dominant = max(MODE_FOR_KIND, key=lambda k: counts.get(k, 0))
        if counts.get(dominant, 0) / result.classified >= _DOMINANT_RATIO:
            result.dominant_kind = dominant
            result.suggested_mode = MODE_FOR_KIND[dominant]
    return result
