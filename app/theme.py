"""界面主题（扁平化 / 现代化）。

配色约定：
    - 主强调色  #07c160（微信绿），悬停 #06ad56，按下 #059c4d
    - 危险色    #e34d59
    - 禁用色    #c9cdd4
    - 浅色主题：浅底 + 深色文字
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["COLORS", "LIGHT_QSS", "DARK_QSS", "build_qss", "level_color"]

#: 勾选图标（SVG，白色对勾）。QSS 的 url() 需要 POSIX 风格路径
_ASSET_DIR = Path(__file__).resolve().parent / "assets"
CHECK_ICON = (_ASSET_DIR / "check.svg").as_posix()

COLORS = {
    "accent": "#07c160",
    "accent_hover": "#06ad56",
    "accent_pressed": "#059c4d",
    "accent_soft": "#e8f9ef",
    "danger": "#e34d59",
    "warning": "#f5a623",
    "info": "#2f88ff",
    "muted": "#8a919f",
    "disabled": "#c9cdd4",
}

# 日志级别 -> 颜色
_LEVEL_COLORS_LIGHT = {
    "info": "#1f9c53",
    "success": "#07c160",
    "warning": "#c47b12",
    "error": "#d0342c",
    "debug": "#8a919f",
    "normal": "#2b2f36",
    "system": "#2f88ff",
}

_LEVEL_COLORS_DARK = {
    "info": "#5fd68a",
    "success": "#07c160",
    "warning": "#e8b339",
    "error": "#ff6b63",
    "debug": "#9aa0aa",
    "normal": "#e6e8eb",
    "system": "#6aa9ff",
}


def level_color(level: str, dark: bool = False) -> str:
    """返回日志级别对应的文字颜色。"""
    table = _LEVEL_COLORS_DARK if dark else _LEVEL_COLORS_LIGHT
    return table.get(level, table["normal"])


LIGHT_QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 12px;
    outline: none;
}}
QWidget#RootWidget {{
    background: #f4f5f7;
}}
QFrame#Card {{
    background: #ffffff;
    border: 1px solid #e6e8eb;
    border-radius: 8px;
}}
QLabel#CardTitle {{
    font-size: 13px;
    font-weight: 600;
    color: #1f2329;
    padding: 2px 0 2px 0;
}}
QLabel#CardHint {{
    color: #8a919f;
    font-size: 11px;
}}
QLabel#FileNamePreview {{
    background: #f7f8fa;
    border: 1px dashed #d5d9e0;
    border-radius: 5px;
    padding: 7px 9px;
    color: #085041;
    font-family: "Consolas", "Microsoft YaHei UI", monospace;
}}
QLabel#CounterChip {{
    background: #f2f3f5;
    border: 1px solid #e6e8eb;
    border-radius: 4px;
    padding: 2px 8px;
    color: #1f2329;
    font-size: 11px;
}}
QLabel#CounterChip[zero="true"] {{
    background: #fafbfc;
    border-color: #eef0f3;
    color: #b4b2a9;
}}
QLabel#FieldLabel {{
    color: #1f2329;
}}
QLabel#SectionBadge {{
    background: {COLORS["accent_soft"]};
    color: {COLORS["accent_pressed"]};
    border-radius: 3px;
    padding: 1px 6px;
    font-size: 11px;
}}

/* ---------- 主按钮 ---------- */
QPushButton {{
    background: #ffffff;
    color: #1f2329;
    border: 1px solid #dcdfe6;
    border-radius: 5px;
    padding: 5px 14px;
    min-height: 20px;
}}
QPushButton:hover {{
    border-color: {COLORS["accent"]};
    color: {COLORS["accent_pressed"]};
}}
QPushButton:pressed {{
    background: {COLORS["accent_soft"]};
}}
QPushButton:disabled {{
    color: {COLORS["disabled"]};
    border-color: #ebedf0;
    background: #f7f8fa;
}}
QPushButton#Primary {{
    background: {COLORS["accent"]};
    color: #ffffff;
    border: 1px solid {COLORS["accent"]};
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {COLORS["accent_hover"]};
    border-color: {COLORS["accent_hover"]};
}}
QPushButton#Primary:pressed {{
    background: {COLORS["accent_pressed"]};
}}
QPushButton#Primary:disabled {{
    background: {COLORS["disabled"]};
    border-color: {COLORS["disabled"]};
    color: #ffffff;
}}
QPushButton#Danger {{
    background: #ffffff;
    color: {COLORS["danger"]};
    border: 1px solid {COLORS["danger"]};
    font-weight: 600;
}}
QPushButton#Danger:hover {{
    background: #fdecee;
}}
QPushButton#Danger:disabled {{
    color: {COLORS["disabled"]};
    border-color: #ebedf0;
}}
QPushButton#HelpButton {{
    background: transparent;
    color: {COLORS["muted"]};
    border: 1px solid #d5d9e0;
    border-radius: 8px;
    padding: 0;
    min-width: 16px;
    max-width: 16px;
    min-height: 16px;
    max-height: 16px;
    font-size: 11px;
    font-weight: 700;
}}
QPushButton#HelpButton:hover {{
    background: {COLORS["accent"]};
    color: #ffffff;
    border-color: {COLORS["accent"]};
}}
QPushButton#LinkButton {{
    background: transparent;
    border: none;
    color: {COLORS["info"]};
    padding: 0 4px;
    text-decoration: underline;
}}
QPushButton#LinkButton:hover {{
    color: {COLORS["accent_pressed"]};
}}

/* ---------- 输入控件 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #ffffff;
    border: 1px solid #dcdfe6;
    border-radius: 5px;
    padding: 4px 7px;
    color: #1f2329;
    selection-background-color: {COLORS["accent"]};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {COLORS["accent"]};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background: #f7f8fa;
    color: {COLORS["disabled"]};
}}
QLineEdit[readOnly="true"] {{
    background: #f7f8fa;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 15px;
    border: none;
    background: transparent;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid #dcdfe6;
    selection-background-color: {COLORS["accent_soft"]};
    selection-color: #1f2329;
    outline: none;
}}

/* ---------- 勾选框 ---------- */
QCheckBox {{
    color: #1f2329;
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 3px;
}}
/* 未选中：纯白底 + 灰边；显式 image: none 以屏蔽 Fusion 风格自带的指示符 */
QCheckBox::indicator:unchecked {{
    background: #ffffff;
    border: 1px solid #c9cdd4;
    image: none;
}}
QCheckBox::indicator:unchecked:hover {{
    border-color: {COLORS["accent"]};
    image: none;
}}
/* 选中：实心强调色 + 白色对勾 */
QCheckBox::indicator:checked {{
    background: {COLORS["accent"]};
    border: 1px solid {COLORS["accent"]};
    image: url("{CHECK_ICON}");
}}
QCheckBox::indicator:checked:hover {{
    background: {COLORS["accent_hover"]};
    border-color: {COLORS["accent_hover"]};
    image: url("{CHECK_ICON}");
}}
QCheckBox::indicator:unchecked:disabled {{
    background: #f2f3f5;
    border-color: #e5e6eb;
    image: none;
}}
QCheckBox::indicator:checked:disabled {{
    background: {COLORS["disabled"]};
    border-color: {COLORS["disabled"]};
    image: url("{CHECK_ICON}");
}}
QRadioButton {{
    color: #1f2329;
    spacing: 6px;
}}
QRadioButton::indicator:unchecked {{
    width: 14px;
    height: 14px;
    border: 1px solid #c9cdd4;
    border-radius: 7px;
    background: #ffffff;
    image: none;
}}
QRadioButton::indicator:checked {{
    width: 14px;
    height: 14px;
    border: 4px solid {COLORS["accent"]};
    border-radius: 7px;
    background: #ffffff;
    image: none;
}}

/* ---------- 选项卡 ---------- */
QTabWidget::pane {{
    border: 1px solid #e6e8eb;
    border-radius: 8px;
    background: #ffffff;
    top: -1px;
}}
QTabBar::tab {{
    background: #eef0f3;
    color: #4e5969;
    border: 1px solid #e6e8eb;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 22px;
    margin-right: 2px;
    font-weight: 600;
}}
QTabBar::tab:hover {{
    color: {COLORS["accent_pressed"]};
}}
QTabBar::tab:selected {{
    background: #ffffff;
    color: {COLORS["accent_pressed"]};
    border-bottom: 2px solid {COLORS["accent"]};
}}

/* ---------- 分组框 ---------- */
QGroupBox {{
    border: 1px solid #e6e8eb;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
    background: #fcfcfd;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #4e5969;
}}

/* ---------- 滚动区 ---------- */
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #d0d4da;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS["accent"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 9px;
}}
QScrollBar::handle:horizontal {{
    background: #d0d4da;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0;
    background: transparent;
}}

/* ---------- 其他 ---------- */
QSplitter::handle {{
    background: #e6e8eb;
}}
QSplitter::handle:horizontal {{
    width: 4px;
}}
QProgressBar {{
    border: none;
    border-radius: 3px;
    background: #eef0f3;
    height: 6px;
    text-align: center;
    color: #1f2329;
}}
QProgressBar::chunk {{
    background: {COLORS["accent"]};
    border-radius: 3px;
}}
QStatusBar {{
    background: #ffffff;
    border-top: 1px solid #e6e8eb;
    color: #4e5969;
}}
QToolTip {{
    background: #2b2f36;
    color: #ffffff;
    border: none;
    padding: 4px 7px;
    border-radius: 4px;
}}
QMenu {{
    background: #ffffff;
    border: 1px solid #e6e8eb;
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 22px 5px 14px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {COLORS["accent_soft"]};
    color: {COLORS["accent_pressed"]};
}}
QTextBrowser {{
    background: #ffffff;
    border: 1px solid #e6e8eb;
    border-radius: 6px;
    padding: 6px;
}}
"""

DARK_QSS = LIGHT_QSS.replace("#f4f5f7", "#17181a").replace(
    "#ffffff", "#202225"
).replace("#fcfcfd", "#1c1d20").replace("#f7f8fa", "#26282c").replace(
    "#eef0f3", "#26282c"
).replace("#e6e8eb", "#33363b").replace("#dcdfe6", "#3d4148").replace(
    "#ebedf0", "#33363b"
).replace("#1f2329", "#e6e8eb").replace("#2b2f36", "#e6e8eb").replace(
    "#4e5969", "#b6bcc6"
).replace("#8a919f", "#9aa0aa").replace("#d0d4da", "#4a4e55").replace(
    "#d5d9e0", "#4a4e55"
)


def build_qss(dark: bool = False) -> str:
    """按主题返回样式表。"""
    return DARK_QSS if dark else LIGHT_QSS
