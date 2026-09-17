"""中文字体保障。

在绝大多数 Windows 桌面环境下，Qt 会自动枚举系统字体，无需额外处理。
但在某些精简系统、容器或离屏渲染场景下，Qt 的字体数据库可能为空，
导致所有中文渲染成方框（tofu）。本模块在启动时做一次兜底：

    1. 检查字体数据库中是否存在可用的中文字体族；
    2. 若不存在，尝试直接从系统字体目录加载常见中文字体文件；
    3. 返回最终可用的字体族名，供全局样式表与 QApplication 使用。
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["CJK_FAMILIES", "ensure_cjk_font"]

#: 首选字体族（按优先级排列，与 theme.py 的 QSS 保持一致）
CJK_FAMILIES: tuple[str, ...] = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "DengXian",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "PingFang SC",
    "WenQuanYi Micro Hei",
)

#: 需要时可直接加载的字体文件（Windows 优先，其次常见 Linux 路径）
_FONT_FILES: tuple[str, ...] = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)


def _available_families() -> set[str]:
    from PyQt6.QtGui import QFontDatabase

    return set(QFontDatabase.families())


def ensure_cjk_font(application=None) -> str:
    """确保存在可用的中文字体，返回最终选用的字体族名。

    :param application: 可选的 ``QApplication``；传入时会一并设置应用默认字体。
    """
    from PyQt6.QtGui import QFont, QFontDatabase

    families = _available_families()
    for family in CJK_FAMILIES:
        if family in families:
            if application is not None:
                application.setFont(QFont(family, 9))
            return family

    # 字体数据库里没有中文字体，尝试显式加载字体文件
    loaded_any = False
    for path in _FONT_FILES:
        if not Path(path).is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id == -1:
            continue
        loaded_any = True
        names = QFontDatabase.applicationFontFamilies(font_id)
        for name in names:
            if application is not None:
                application.setFont(QFont(name, 9))
            return name

    # 全部失败：返回首选族名，让 Qt 自行回退
    if loaded_any:
        print("警告：已加载字体文件但未能解析出字体族名。", file=sys.stderr)
    else:
        print(
            "警告：未找到可用中文字体，界面中文可能显示为方框。"
            "请确认系统已安装微软雅黑等中文字体。",
            file=sys.stderr,
        )
    return CJK_FAMILIES[0]
