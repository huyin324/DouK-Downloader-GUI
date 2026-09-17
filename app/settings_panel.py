"""左侧设置区：抖音 / TikTok 双分页参数面板。

每个分页内部严格按需求排列：

    1. 首行 Cookie
    2. 下载类型选择
    3. 链接传入方式（粘贴链接 / 从本地 txt 读取）
    4. 其余全部参数（下载内容、命名、网络、反爬虫、去重、平台开关、高级）

两个分页共享“通用”参数：切换分页时由主窗口执行
``commit()`` -> 切换 -> ``load()``，从而保证同一份通用配置在两个分页里显示一致。
"""

from __future__ import annotations

from pathlib import Path
from re import compile as re_compile
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .field_spec import Field, SECTION_HINTS, SECTIONS, fields_for
from .naming_preview import build_filename
from .widgets import FieldEditor, SectionCard

__all__ = ["SettingsPanel"]

_COOKIE_KEYS = re_compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+=([^;\s][^;]*)")
_URL_PATTERN = re_compile(r"https?://[^\s\"<>\\^`{|}，。；！？、【】《》]+")


class SettingsPanel(QWidget):
    """单个平台分页的全部设置项。"""

    changed = pyqtSignal()

    def __init__(self, platform: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.platform = platform
        self.editors: dict[str, FieldEditor] = {}
        self._fields: dict[str, Field] = {}
        self.cards: dict[str, SectionCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        self._body = QVBoxLayout(container)
        self._body.setContentsMargins(8, 8, 8, 12)
        self._body.setSpacing(8)

        for section_id, title, hint in SECTIONS:
            fields = fields_for(platform, section_id)
            if not fields:
                continue
            card = SectionCard(title, SECTION_HINTS.get(section_id, hint))
            self.cards[section_id] = card
            for item in fields:
                editor = FieldEditor(item, item.default)
                editor.changed.connect(self.changed.emit)
                self.editors[item.key] = editor
                self._fields[item.key] = item
                card.add_widget(editor)

            if section_id == "task":
                self._decorate_task_card(card)
            elif section_id == "naming":
                self._decorate_naming_card(card)
            elif section_id == "antispider":
                card.add_note(
                    "说明：以上参数仅在“启用反爬虫增强”开启时生效；"
                    "关闭后完全沿用内核默认的请求节奏与指纹。"
                )

            self._body.addWidget(card)

        self._body.addStretch(1)
        area.setWidget(container)
        outer.addWidget(area)

        self._connect_dependencies()

    # ------------------------------------------------------------------ #
    # 任务卡片的附加交互
    # ------------------------------------------------------------------ #
    def _decorate_task_card(self, card: SectionCard) -> None:
        cookie_key = "cookie" if self.platform == "douyin" else "cookie_tiktok"
        text_key = "link_text" if self.platform == "douyin" else "link_text_tiktok"
        file_key = "link_file" if self.platform == "douyin" else "link_file_tiktok"

        cookie_editor = self.editors[cookie_key]
        paste_btn = QPushButton("从剪贴板粘贴")
        paste_btn.clicked.connect(lambda: self._paste_cookie(cookie_key))
        cookie_editor.add_action_button(paste_btn)

        check_btn = QPushButton("校验登录状态")
        check_btn.clicked.connect(lambda: self._check_cookie(cookie_key))
        cookie_editor.add_action_button(check_btn)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(lambda: self._clear_cookie(cookie_key))
        cookie_editor.add_action_button(clear_btn)

        text_editor = self.editors[text_key]
        fill_btn = QPushButton("从剪贴板追加")
        fill_btn.clicked.connect(lambda: self._append_clipboard(text_key))
        text_editor.add_action_button(fill_btn)

        file_editor = self.editors[file_key]
        preview_btn = QPushButton("解析文件内容")
        preview_btn.clicked.connect(lambda: self._preview_file(file_key))
        file_editor.add_action_button(preview_btn)

        # 链接识别状态提示
        self.link_status = QLabel("")
        self.link_status.setObjectName("CardHint")
        self.link_status.setWordWrap(True)

        self.unified_note = QLabel("")
        self.unified_note.setObjectName("CardHint")
        self.unified_note.setWordWrap(True)
        card.add_widget(self.unified_note)
        # 文本框与文件选择互斥显示（由 refresh_visibility 统一控制）
        card.add_widget(self.link_status)

    def _paste_cookie(self, key: str) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            QMessageBox.information(self, "剪贴板为空", "剪贴板中没有任何文本内容。")
            return
        self.editors[key].set_value(text)
        self._check_cookie(key)

    def _clear_cookie(self, key: str) -> None:
        self.editors[key].set_value("")

    def _check_cookie(self, key: str) -> None:
        value = str(self.editors[key].value() or "").strip()
        if not value:
            QMessageBox.warning(self, "Cookie 为空", "请先填写 Cookie 再执行校验。")
            return
        pairs = _COOKIE_KEYS.findall(value)
        name = "抖音" if self.platform == "douyin" else "TikTok"
        state_key = "sessionid_ss" if self.platform == "douyin" else "sessionid"
        logged_in = state_key in value
        important = ("msToken", "ttwid", "odin_tt", "passport_csrf_token", "sessionid", "uifid")
        missing = [k for k in important if k not in value]

        lines = [
            f"共解析到 {len(pairs)} 个键值对。",
            f"登录标识 {state_key}：{'存在，Cookie 已登录' if logged_in else '缺失，Cookie 未登录'}",
        ]
        if missing:
            lines.append("未包含的常见字段：" + "、".join(missing))
        if not logged_in:
            lines.append(
                "提示：缺少登录标识时，账号类接口与部分作品详情可能返回空数据。"
            )
        QMessageBox.information(self, f"{name} Cookie 校验结果", "\n".join(lines))
        self.changed.emit()

    def _append_clipboard(self, key: str) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if not text:
            return
        editor = self.editors[key]
        current = str(editor.value() or "").rstrip()
        editor.set_value(f"{current}\n{text}".strip())
        self._update_link_status()

    def _preview_file(self, key: str) -> None:
        raw = str(self.editors[key].value() or "").strip()
        if not raw:
            QMessageBox.warning(self, "未选择文件", "请先选择本地 txt 文本文件。")
            return
        path = Path(raw)
        if not path.is_file():
            QMessageBox.warning(self, "文件不存在", f"找不到文件：{raw}")
            return
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="gbk")
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "读取失败", f"无法解析文件编码：{exc}")
                return
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "读取失败", f"{exc}")
            return

        urls = _URL_PATTERN.findall(content)
        lines = [ln for ln in content.splitlines() if ln.strip()]
        preview = "\n".join(lines[:15])
        QMessageBox.information(
            self,
            "文件解析结果",
            f"文件：{path}\n"
            f"有效行数：{len(lines)}\n"
            f"可识别链接：{len(urls)}\n\n"
            f"内容预览（前 15 行）：\n{preview}",
        )
        self.changed.emit()

    # ------------------------------------------------------------------ #
    # 文件命名参考预览
    # ------------------------------------------------------------------ #
    def _decorate_naming_card(self, card: SectionCard) -> None:
        if "name_format" not in self.editors:
            return

        self.preview_caption = QLabel("")
        self.preview_caption.setObjectName("CardHint")
        self.preview_caption.setWordWrap(True)

        self.filename_preview = QLabel("")
        self.filename_preview.setObjectName("FileNamePreview")
        self.filename_preview.setWordWrap(True)
        self.filename_preview.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.filename_preview.setToolTip("可直接选中复制，用于提前核对命名规则")

        anchor = self.editors["name_format"]
        card.insert_after(anchor, self.preview_caption)
        card.insert_after(self.preview_caption, self.filename_preview)

        for key in ("name_format", "split", "desc_length", "name_length", "date_format"):
            if key in self.editors:
                self.editors[key].changed.connect(self._update_filename_preview)
        self._update_filename_preview()

    def _update_filename_preview(self) -> None:
        if not hasattr(self, "filename_preview"):
            return
        config = {key: editor.value() for key, editor in self.editors.items()}
        filename = build_filename(config)
        self.filename_preview.setText(
            filename or "（尚未勾选任何“文件名组成”元素）"
        )

        keys = list(config.get("name_format") or [])
        spec = self._fields.get("name_format")
        labels = {value: label for label, value in (spec.choices if spec else ())}
        order_text = " → ".join(labels.get(key, str(key)) for key in keys)
        caption = (
            "参考文件名：按“文件名组成”的勾选顺序、用“文件名分隔符”拼接后实时生成。"
            "时间为当前时刻，其余为示例值；“:”会被替换为“.”，非法字符会被移除。"
        )
        if order_text:
            caption += f"　当前拼接顺序：{order_text}"
        if "mark" in keys:
            caption += "　注意：“自定义标记”仅在账号配置里填写过标记时才有值，否则该段为空。"
        if "id" not in keys and "desc" not in keys:
            caption += "　提示：勾选“作品 ID”或“作品描述”可避免不同作品重名。"
        self.preview_caption.setText(caption)

    # ------------------------------------------------------------------ #
    # 联动显示
    # ------------------------------------------------------------------ #
    def _connect_dependencies(self) -> None:
        mode_key = "task_mode" if self.platform == "douyin" else "task_mode_tiktok"
        source_key = "link_source" if self.platform == "douyin" else "link_source_tiktok"

        if mode_key in self.editors:
            self.editors[mode_key].changed.connect(self.refresh_visibility)
        if source_key in self.editors:
            self.editors[source_key].changed.connect(self.refresh_visibility)

    def refresh_visibility(self) -> None:
        mode_key = "task_mode" if self.platform == "douyin" else "task_mode_tiktok"
        tab_key = "account_tab" if self.platform == "douyin" else "account_tab_tiktok"
        source_key = "link_source" if self.platform == "douyin" else "link_source_tiktok"
        text_key = "link_text" if self.platform == "douyin" else "link_text_tiktok"
        file_key = "link_file" if self.platform == "douyin" else "link_file_tiktok"

        mode = self.editors[mode_key].value() if mode_key in self.editors else "detail"
        source = self.editors[source_key].value() if source_key in self.editors else "paste"

        # 账号作品类型：仅账号模式需要
        if tab_key in self.editors:
            self.editors[tab_key].setVisible(mode == "account")

        # 链接来源：直播模式下提示不同
        self.editors[text_key].setVisible(source == "paste")
        self.editors[file_key].setVisible(source == "file")

        hints = {
            "detail": "当前模式：批量下载链接作品。可粘贴作品链接或分享文案，程序自动提取 19 位作品 ID。",
            "account": "当前模式：批量下载账号作品。请填写账号主页链接，并在上方选择要采集的列表类型。",
            "mix": "当前模式：批量下载合集作品。可填写合集链接，也可填写合集内任意作品链接。",
            "live": "当前模式：获取直播拉流地址。需要配置有效的 FFmpeg 与直播清晰度才能自动录制。",
        }
        if hasattr(self, "unified_note"):
            self.unified_note.setText(hints.get(mode, ""))
        self._update_link_status()
        self._update_filename_preview()

    def _update_link_status(self) -> None:
        if not hasattr(self, "link_status"):
            return
        source_key = "link_source" if self.platform == "douyin" else "link_source_tiktok"
        text_key = "link_text" if self.platform == "douyin" else "link_text_tiktok"
        file_key = "link_file" if self.platform == "douyin" else "link_file_tiktok"
        source = self.editors[source_key].value() if source_key in self.editors else "paste"

        if source == "paste":
            raw = str(self.editors[text_key].value() or "")
            urls = _URL_PATTERN.findall(raw)
            self.link_status.setText(
                f"已识别链接 {len(urls)} 条 / 非空行 {len([l for l in raw.splitlines() if l.strip()])} 行。"
            )
        else:
            raw = str(self.editors[file_key].value() or "").strip()
            if not raw:
                self.link_status.setText("尚未选择 txt 文件。")
            elif not Path(raw).is_file():
                self.link_status.setText(f"文件不存在：{raw}")
            else:
                self.link_status.setText(f"将读取文件：{raw}")

    # ------------------------------------------------------------------ #
    # 取值 / 赋值
    # ------------------------------------------------------------------ #
    def collect(self) -> dict[str, Any]:
        return {key: editor.value() for key, editor in self.editors.items()}

    def commit(self, config: dict) -> None:
        """把本分页的所有控件值写入共享配置字典。"""
        config.update(self.collect())

    def load(self, config: dict, keys: set[str] | None = None) -> None:
        """从共享配置字典回填控件；``keys`` 限定只回填指定键。"""
        for key, editor in self.editors.items():
            if keys is not None and key not in keys:
                continue
            if key in config:
                editor.set_value(config[key])
        self.refresh_visibility()

    def own_keys(self) -> set[str]:
        return set(self.editors.keys())
