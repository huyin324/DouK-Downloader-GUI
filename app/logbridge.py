"""日志桥接：把上游内核的 Rich 控制台输出转发到 Qt 界面。

上游内核的所有日志最终都会经过 ``ColorfulConsole.print(...)``，
因此只需要继承该类并把输出改写为 Qt 信号，即可在不改动内核代码的前提下
捕获全部日志（包括 ``BaseLogger`` / ``LoggerManager`` 产生的日志）。
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal
from rich.text import Text

__all__ = ["LogBus", "QtConsole", "style_to_level"]

# 上游 custom/static.py 中定义的样式常量（避免直接依赖内核导入顺序）
_STYLE_LEVEL = (
    ("bright_red", "error"),
    ("bright_yellow", "warning"),
    ("bright_green", "info"),
    ("dark_orange", "debug"),
    ("#fff200", "system"),
    ("turquoise2", "system"),
)


def style_to_level(style: Any) -> str:
    """把 Rich 样式描述映射为界面日志级别。"""
    if style is None:
        return "normal"
    text = str(style).lower()
    for token, level in _STYLE_LEVEL:
        if token in text:
            return level
    return "normal"


def _render(arg: Any) -> str:
    """把 Rich 打印参数渲染为纯文本（去掉标记）。"""
    if isinstance(arg, str):
        try:
            return Text.from_markup(arg).plain
        except Exception:
            return arg
    if isinstance(arg, Text):
        return arg.plain
    return str(arg)


class LogBus(QObject):
    """日志信号总线。

    ``message`` 携带 (级别, 文本)，由主线程的日志面板消费。
    """

    message = pyqtSignal(str, str)


class QtConsole:
    """延迟构造的 ``ColorfulConsole`` 子类工厂。

    上游内核通过 ``from src.tools import ColorfulConsole`` 导入，
    这里在运行时动态生成子类，避免在界面线程之外提前导入内核模块。
    """

    _cls = None

    @classmethod
    def build(cls, bus: LogBus, debug: bool = False, listener=None):
        """构造彩色控制台。

        :param bus: 具备 ``message`` 信号的对象，日志会转发到它
        :param debug: 是否输出 debug 级日志
        :param listener: 可选回调 ``listener(level, text)``，
            在**打印的线程内同步调用**。用于顺带消费日志做实时统计等，
            因为内核输出并不经过上层的日志包装函数。
        """
        if cls._cls is None:
            from src.tools import ColorfulConsole as _BaseConsole

            class _QtConsole(_BaseConsole):  # type: ignore[misc, valid-type]
                """把 print / input 重定向到 Qt 的彩色控制台。

                注意：Rich 的 ``Console.__init__`` 全部参数都是 keyword-only，
                因此这里不能向 ``super().__init__`` 传递任何位置参数。
                """

                def __init__(self, bus, *, debug: bool = False, listener=None, **kwargs):
                    kwargs.setdefault("quiet", True)
                    super().__init__(debug=debug, **kwargs)
                    self.bus = bus
                    self.listener = listener
                    #: 记录被拦截的交互式输入，便于事后审计
                    self.input_history: list[str] = []

                # ------------------------------------------------------ #
                def print(self, *args, style=None, highlight=False, **kwargs):  # noqa: A003
                    # 进度条等 Live 渲染会传入 end="" / transient 等参数，直接丢弃
                    if kwargs.get("end") == "":
                        return
                    text = " ".join(_render(a) for a in args)
                    text = text.rstrip()
                    if not text:
                        return
                    if self.listener is not None:
                        try:
                            self.listener(style_to_level(style), text)
                        except Exception:
                            pass
                    level = style_to_level(style)
                    try:
                        self.bus.message.emit(level, text)
                    except RuntimeError:
                        # 界面已销毁
                        pass

                def info(self, *args, highlight=False, **kwargs):
                    self.print(*args, style="bright_green", highlight=highlight, **kwargs)

                def warning(self, *args, highlight=False, **kwargs):
                    self.print(*args, style="bright_yellow", highlight=highlight, **kwargs)

                def error(self, *args, highlight=False, **kwargs):
                    self.print(*args, style="bright_red", highlight=highlight, **kwargs)

                def debug(self, *args, highlight=False, **kwargs):
                    if self.debug_mode:
                        self.print(*args, style="dark_orange", highlight=highlight, **kwargs)

                def input(self, prompt="", style="", *args, **kwargs):  # noqa: A003
                    """图形界面下不存在终端交互。

                    返回哨兵值 "skip"：上游的 ``retry_limited`` 收到非空字符串会
                    安全跳过；``_choice_live_quality`` 解析失败会安全放弃直播下载。
                    """
                    self.input_history.append(str(prompt))
                    self.bus.message.emit(
                        "warning",
                        f"[交互请求已自动跳过] {_render(str(prompt))}".rstrip(),
                    )
                    return "skip"

            cls._cls = _QtConsole
        return cls._cls(bus, debug=debug, listener=listener)
