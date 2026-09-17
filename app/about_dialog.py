"""「关于」对话框。

包含四部分：
    1. 本 GUI 工具的项目信息（作者 / 邮箱）
    2. 上游原项目信息（名称 / 作者 / 地址 / 文档 / 许可）
    3. 免责声明（沿用上游声明，另附本外壳的补充说明）
    4. 捐赠入口，下方横向排列微信与支付宝收款码
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .paths import APP_ROOT, ensure_upstream_on_path

__all__ = ["AboutDialog"]

# ---- 本 GUI 工具信息 ------------------------------------------------------ #
GUI_AUTHOR = "HuYin"
GUI_EMAIL = "aihuyin@qq.com"
GUI_VERSION = "V1.0"

# ---- 上游项目信息（读取内核常量失败时的兜底值） ---------------------------- #
_FALLBACK_PROJECT = {
    "name": "DouK-Downloader（TikTokDownloader）",
    "author": "JoeanAmier",
    "repository": "https://github.com/JoeanAmier/TikTokDownloader",
    "documentation": "https://github.com/JoeanAmier/TikTokDownloader/wiki/Documentation",
    "licence": "GNU General Public License v3.0",
    "version": "V5.8",
}

_FALLBACK_DISCLAIMER = (
    "本图形界面仅是对开源项目 DouK-Downloader 的界面封装，未改变其功能与用途。\n"
    "使用者在使用本项目时必须严格遵守 GNU General Public License v3.0，"
    "并自行研究相关法律法规，确保使用行为合法合规。\n"
    "本项目不参与、不支持、不认可任何非法内容的获取或分发，"
    "不对使用者涉及的数据收集、存储、传输等处理活动的合规性承担责任。\n"
    "使用者不得利用本工具从事任何侵犯知识产权的行为。\n"
    "任何因使用本项目产生的风险与法律责任，均由使用者自行承担。"
)

#: 收款码图片（放在项目根目录）
QR_CODES = (
    ("微信收款码", "微信收款码.JPG"),
    ("支付宝收款码", "支付宝收款码.JPG"),
)

_QR_HEIGHT = 190


def _project_info() -> dict:
    """尽量从内核常量读取原项目信息，失败则用兜底值。"""
    info = dict(_FALLBACK_PROJECT)
    try:
        ensure_upstream_on_path()
        from src.custom.internal import (  # noqa: PLC0415
            DOCUMENTATION_URL,
            LICENCE,
            PROJECT_NAME,
            REPOSITORY,
            __VERSION__,
        )

        info.update(
            {
                "name": f"DouK-Downloader（TikTokDownloader） {PROJECT_NAME}",
                "repository": REPOSITORY,
                "documentation": DOCUMENTATION_URL,
                "licence": LICENCE,
                "version": __VERSION__,
            }
        )
    except Exception:  # noqa: BLE001
        pass
    return info


def _disclaimer_text() -> str:
    """上游免责声明（完整版）。"""
    try:
        ensure_upstream_on_path()
        from src.custom.internal import DISCLAIMER_TEXT  # noqa: PLC0415

        return str(DISCLAIMER_TEXT)
    except Exception:  # noqa: BLE001
        return _FALLBACK_DISCLAIMER


class AboutDialog(QDialog):
    """关于窗口。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("关于 · DouK-Downloader GUI")
        self.setMinimumSize(680, 560)
        self.resize(700, 820)
        self.setStyleSheet(
            """
            QDialog { background: #ffffff; }
            QScrollArea { border: none; background: transparent; }
            QWidget#AboutBody { background: #ffffff; }
            QLabel#AboutTitle { font-size: 16px; font-weight: 600; color: #1f2329; }
            QLabel#AboutSub { color: #8a919f; font-size: 11px; }
            QLabel#AboutSection { font-size: 13px; font-weight: 600; color: #07c160; }
            QLabel#AboutKey { color: #8a919f; }
            QLabel#AboutValue { color: #1f2329; }
            QLabel#AboutQrCaption { color: #4e5969; font-size: 11px; }
            QLabel#AboutDonate { color: #1f2329; }
            QFrame#AboutCard {
                background: #fcfcfd;
                border: 1px solid #e6e8eb;
                border-radius: 8px;
            }
            QTextBrowser {
                background: #fcfcfd;
                border: 1px solid #e6e8eb;
                border-radius: 6px;
                padding: 6px;
                color: #4e5969;
            }
            """
        )

        # 内容放进滚动区，保证窗口拉小时也不会挤压重叠
        body = QWidget()
        body.setObjectName("AboutBody")
        content = QVBoxLayout(body)
        content.setContentsMargins(18, 16, 18, 12)
        content.setSpacing(10)

        # ---------------- 标题 ---------------- #
        title = QLabel("DouK-Downloader GUI")
        title.setObjectName("AboutTitle")
        content.addWidget(title)
        subtitle = QLabel(
            "抖音 / TikTok 作品下载与数据采集工具的图形界面外壳（Python + PyQt6）"
        )
        subtitle.setObjectName("AboutSub")
        subtitle.setWordWrap(True)
        content.addWidget(subtitle)
        content.addWidget(_divider())

        # ---------------- 项目信息 ---------------- #
        content.addWidget(_section("项目信息"))
        card = _card()
        card_body = QVBoxLayout(card)
        card_body.setContentsMargins(12, 10, 12, 10)
        card_body.setSpacing(5)
        card_body.addLayout(_kv_row("GUI 工具作者", GUI_AUTHOR))
        card_body.addLayout(_kv_row("联系邮箱", GUI_EMAIL, link=f"mailto:{GUI_EMAIL}"))
        card_body.addLayout(_kv_row("界面版本", GUI_VERSION))
        card_body.addLayout(_kv_row("技术栈", "Python 3.12+ / PyQt6"))
        content.addWidget(card)

        # ---------------- 原项目信息 ---------------- #
        project = _project_info()
        content.addWidget(_section("原项目信息"))
        project_card = _card()
        project_body = QVBoxLayout(project_card)
        project_body.setContentsMargins(12, 10, 12, 10)
        project_body.setSpacing(5)
        project_body.addLayout(_kv_row("项目名称", project["name"]))
        project_body.addLayout(_kv_row("项目作者", project["author"]))
        project_body.addLayout(
            _kv_row("项目地址", project["repository"], link=project["repository"])
        )
        project_body.addLayout(
            _kv_row("项目文档", project["documentation"], link=project["documentation"])
        )
        project_body.addLayout(_kv_row("开源许可", project["licence"]))
        content.addWidget(project_card)

        note = QLabel(
            "本图形界面仅是对上述开源项目的界面封装，内核源码未作改动，"
            "所有下载与解析逻辑均来自原项目；本外壳同样以 GPL-3.0 发布。"
        )
        note.setObjectName("AboutSub")
        note.setWordWrap(True)
        content.addWidget(note)

        # ---------------- 免责声明 ---------------- #
        content.addWidget(_section("免责声明"))
        disclaimer = QTextBrowser()
        disclaimer.setPlainText(
            _disclaimer_text()
            + "\n\n──────── 本图形界面外壳的补充说明 ────────\n"
            "1. 本外壳不改变内核的功能与用途，仅提供参数配置、日志展示与运行时增强。\n"
            "2. 使用者应自行确保使用行为符合当地法律法规及平台服务条款。\n"
            "3. 因使用本工具产生的任何风险与后果，均由使用者自行承担。"
        )
        disclaimer.setFixedHeight(190)
        disclaimer.setOpenExternalLinks(True)
        content.addWidget(disclaimer)

        # ---------------- 捐赠 ---------------- #
        content.addWidget(_section("捐赠"))
        donate = QLabel("如此工具对您有些许价值，您可以进行打赏，万分感谢！")
        donate.setObjectName("AboutDonate")
        donate.setWordWrap(True)
        content.addWidget(donate)

        qr_row = QHBoxLayout()
        qr_row.setContentsMargins(0, 4, 0, 0)
        qr_row.setSpacing(30)
        qr_row.addStretch(1)
        for caption, filename in QR_CODES:
            qr_row.addWidget(self._build_qr(APP_ROOT / filename, caption))
        qr_row.addStretch(1)
        content.addLayout(qr_row)
        content.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(body)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(scroll, 1)

        # ---------------- 按钮 ---------------- #
        footer = QWidget()
        buttons = QHBoxLayout(footer)
        buttons.setContentsMargins(18, 8, 18, 14)
        buttons.addStretch(1)
        close = QPushButton("关闭")
        close.setObjectName("Primary")
        close.setAutoDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addWidget(footer)
        close.setFocus()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_qr(path: Path, caption: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path)) if path.is_file() else QPixmap()
        if not pixmap.isNull():
            image.setPixmap(
                pixmap.scaledToHeight(
                    _QR_HEIGHT, Qt.TransformationMode.SmoothTransformation
                )
            )
            image.setToolTip(f"点击查看原图：{path.name}")
            image.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            image.mousePressEvent = lambda _event, p=path: _open_path(p)  # type: ignore[method-assign]
        else:
            image.setText("二维码文件缺失")
            image.setObjectName("AboutSub")
            image.setMinimumSize(120, _QR_HEIGHT)
        layout.addWidget(image, 0, Qt.AlignmentFlag.AlignHCenter)

        label = QLabel(caption)
        label.setObjectName("AboutQrCaption")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        return box


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("AboutSection")
    return label


def _card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("AboutCard")
    return frame


def _kv_row(key: str, value: str, link: str = "") -> QHBoxLayout:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)

    key_label = QLabel(f"{key}：")
    key_label.setObjectName("AboutKey")
    key_label.setFixedWidth(84)
    key_label.setAlignment(
        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
    )
    row.addWidget(key_label)

    if link:
        value_label = QLabel(f'<a href="{link}" style="color:#07c160;">{value}</a>')
        value_label.setOpenExternalLinks(True)
        value_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        value_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    else:
        value_label = QLabel(value)
    value_label.setObjectName("AboutValue")
    value_label.setWordWrap(True)
    value_label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse
    )
    row.addWidget(value_label, 1)
    return row


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #e6e8eb; background: #e6e8eb; max-height: 1px;")
    return line


def _open_url(url: str) -> None:
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtCore import QUrl

    QDesktopServices.openUrl(QUrl(url))


def _open_path(path: Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        _open_url(path.as_uri())
