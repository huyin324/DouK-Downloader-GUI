"""文件名参考预览。

本模块**逐行复刻**上游的命名算法，保证界面里显示的参考文件名与最终落盘的文件名一致：

1. ``Downloader.batch_processing()`` 先对作品描述做一次截断：
     ``item["desc"] = beautify_string(item["desc"], self.desc_length)``
2. ``Downloader.generate_detail_name()`` 再拼接、清洗、整体截断：
     ``beautify_string(cleaner.filter_name(split.join(...), id), name_length)``
3. ``Cleaner.filter_name()`` 会把 ``:`` 替换成 ``.``（所以时间是 10.22.46 而非 10:22:46），
   并移除 Windows 非法字符、控制字符与连续空白。

为了不在界面层导入内核，这里用纯标准库重写了同样的算法
（``is_chinese_char`` 按 CJK 记 2 个宽度、其它字符记 1 个宽度）。
"""

from __future__ import annotations

from datetime import datetime
from re import compile as re_compile
from time import localtime, strftime
from typing import Any
from unicodedata import name as unicode_name

__all__ = [
    "build_filename",
    "sample_values",
    "SAMPLE_VALUES",
    "EXTENSION_BY_TYPE",
    "SPECIAL_KEYS",
    "beautify_string",
    "filter_name",
    "truncate_string",
    "is_chinese_char",
]

#: 参考用的示例值（与字段 key 对应）
SAMPLE_VALUES: dict[str, str] = {
    "id": "7300000000000000000",
    "desc": "今天天气不错",
    "create_time": "2026-09-17 10:22:46",
    "nickname": "某某某",
    "uid": "100447080410",
    "mark": "我的标记",
    "type": "视频",
}

#: 作品类型 -> 参考扩展名（真实扩展名由响应头的 Content-Type 决定）
EXTENSION_BY_TYPE: dict[str, str] = {
    "视频": "mp4",
    "图集": "jpeg",
    "实况": "mp4",
    "音乐": "mp3",
}

#: 这些 key 的值来自运行时上下文，无法从配置推断，需要额外说明
SPECIAL_KEYS: dict[str, str] = {
    "mark": "只在该账号的配置里填写了“标记”时才有值，否则为空",
    "create_time": "按“时间格式”参数实时生成",
    "desc": "按“描述最大长度”参数截断",
}

_CONTROL = re_compile(r"[\x00-\x1F\x7F]")

#: 与 Cleaner.default_rule() 在 Windows / macOS 下的规则一致
_ILLEGAL = {
    "/": "",
    "\\": "",
    "|": "",
    "<": "",
    ">": "",
    '"': "",
    "?": "",
    ":": "",
    "*": "",
    "\x00": "",
    "\t": "",
    "\n": "",
    "\r": "",
    "\x0b": "",
    "\x0c": "",
}

try:  # emoji 是内核依赖，已随环境安装；缺失时降级为不处理
    from emoji import replace_emoji as _replace_emoji
except Exception:  # noqa: BLE001

    def _replace_emoji(text: str) -> str:
        return text


# --------------------------------------------------------------------------- #
# 与上游 tools/truncate.py 等价
# --------------------------------------------------------------------------- #
def is_chinese_char(char: str) -> bool:
    return "CJK" in unicode_name(char, "")


def truncate_string(text: str, length: int = 64) -> str:
    count = 0
    result = ""
    for char in text:
        count += 2 if is_chinese_char(char) else 1
        if count > length:
            break
        result += char
    return result


def beautify_string(text: str, length: int = 64) -> str:
    """超长时保留首尾并加省略号（与上游完全一致：CJK 记 2，其它记 1）。"""
    count = 0
    for char in text:
        count += 2 if is_chinese_char(char) else 1
        if count > length:
            break
    else:
        return text
    length //= 2
    start = truncate_string(text, length)
    end = truncate_string(text[::-1], length)[::-1]
    return f"{start}...{end}"


# --------------------------------------------------------------------------- #
# 与上游 tools/cleaner.py::Cleaner.filter_name 等价
# --------------------------------------------------------------------------- #
def filter_name(text: str, default: str = "") -> str:
    text = text.replace(":", ".")
    text = _CONTROL.sub("", text)
    for key, value in _ILLEGAL.items():
        text = text.replace(key, value)
    text = _replace_emoji(text)
    text = " ".join(text.split())
    text = text.strip().strip(".")
    return text or default


# --------------------------------------------------------------------------- #
def sample_values(
    config: dict[str, Any], now: datetime | None = None
) -> dict[str, str]:
    """构造参考用的字段样本（``create_time`` 按配置的时间格式实时生成）。"""
    samples = dict(SAMPLE_VALUES)
    moment = now or datetime.now()
    date_format = str(config.get("date_format") or "%Y-%m-%d %H:%M:%S")
    try:
        samples["create_time"] = strftime(date_format, moment.timetuple())
    except ValueError:
        # 时间格式非法时上游会回退默认值，这里保持一致
        samples["create_time"] = strftime("%Y-%m-%d %H:%M:%S", moment.timetuple())
    return samples


def compose_name(config: dict[str, Any], samples: dict[str, str]) -> str:
    """按上游顺序完成「截断描述 → 拼接 → 清洗 → 整体截断」，返回不含扩展名的文件名。"""
    keys = list(config.get("name_format") or [])
    if not keys:
        return ""

    split = str(config.get("split") or "-")
    desc_length = _as_int(config.get("desc_length"), 64)
    name_length = _as_int(config.get("name_length"), 128)

    # 步骤 1：上游先按 desc_length 截断作品描述
    description = beautify_string(samples.get("desc", ""), desc_length)

    # 步骤 2：按 name_format 顺序拼接
    raw = split.join(
        description if key == "desc" else samples.get(key, "") for key in keys
    )

    # 步骤 3：清洗 + 按 name_length 整体截断（清洗后为空则回退作品 ID）
    return beautify_string(filter_name(raw, samples.get("id", "")), name_length)


def build_filename(config: dict[str, Any], now: datetime | None = None) -> str:
    """根据当前配置生成参考文件名（扩展名按作品类型给出常规取值）。

    :param config: GUI 配置字典，需要 name_format / split / desc_length /
        name_length / date_format
    :param now: 用于生成示例时间的时刻，默认当前时间
    """
    samples = sample_values(config, now)
    name = compose_name(config, samples)
    if not name:
        return ""
    extension = EXTENSION_BY_TYPE.get(samples.get("type", ""), "mp4")
    return f"{name}.{extension}"


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
