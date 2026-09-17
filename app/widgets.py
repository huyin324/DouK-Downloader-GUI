"""通用界面组件：带 “?” 帮助图标的参数编辑器、分区卡片、帮助弹窗。

本模块只负责“单个参数怎么呈现、怎么取值、怎么设置值”，
具体有哪些参数由 :mod:`app.field_spec` 声明，排布由
:mod:`app.settings_panel` 决定。
"""

from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .field_spec import Field
from .theme import COLORS

__all__ = [
    "HelpDialog",
    "FieldEditor",
    "SectionCard",
    "PathPicker",
    "MultiChoiceBox",
]


# --------------------------------------------------------------------------- #
# 帮助弹窗
# --------------------------------------------------------------------------- #
class HelpDialog(QDialog):
    """参数说明弹窗：展示参数描述与示例。"""

    def __init__(self, field: Field, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"参数说明 · {field.label}")
        self.setMinimumWidth(520)
        self.setStyleSheet(
            f"""
            QDialog {{ background: #ffffff; }}
            QLabel#HelpTitle {{ font-size: 14px; font-weight: 700; color: #1f2329; }}
            QLabel#HelpKey {{ color: {COLORS["muted"]}; font-size: 11px; }}
            QLabel#BlockTitle {{
                font-size: 12px; font-weight: 700; color: {COLORS["accent_pressed"]};
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel(field.label)
        title.setObjectName("HelpTitle")
        layout.addWidget(title)

        key_text = field.upstream or (field.key + "（界面专用）")
        key_label = QLabel(f"配置键：{key_text}")
        key_label.setObjectName("HelpKey")
        layout.addWidget(key_label)
        layout.addWidget(_divider())

        layout.addWidget(_block_title("功能说明"))
        desc = QTextBrowser()
        desc.setOpenExternalLinks(True)
        desc.setPlainText(field.help_desc or "暂无说明。")
        desc.setMinimumHeight(110)
        desc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(desc)

        if field.help_example:
            layout.addWidget(_block_title("示例 / 取值参考"))
            example = QTextBrowser()
            example.setPlainText(field.help_example)
            mono = QFont("Consolas")
            mono.setStyleHint(QFont.StyleHint.Monospace)
            mono.setPointSize(9)
            example.setFont(mono)
            example.setMinimumHeight(110)
            layout.addWidget(example)

        if field.choices:
            layout.addWidget(_block_title("可选值"))
            items = "\n".join(f"• {label}  →  {value!r}" for label, value in field.choices)
            choice_browser = QTextBrowser()
            choice_browser.setPlainText(items)
            choice_browser.setMinimumHeight(80)
            layout.addWidget(choice_browser)

        if field.minimum is not None or field.maximum is not None:
            layout.addWidget(_block_title("取值范围"))
            lo = "不限" if field.minimum is None else field.minimum
            hi = "不限" if field.maximum is None else field.maximum
            rng = QLabel(f"最小值：{lo}      最大值：{hi}")
            rng.setObjectName("HelpKey")
            layout.addWidget(rng)

        layout.addStretch(1)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("关闭")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._center_on_cursor()

    def _center_on_cursor(self) -> None:
        pos = QCursor.pos()
        self.move(max(0, pos.x() - 260), max(0, pos.y() - 120))


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #e6e8eb; background: #e6e8eb; max-height: 1px;")
    return line


def _block_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("BlockTitle")
    return label


# --------------------------------------------------------------------------- #
# 路径选择器
# --------------------------------------------------------------------------- #
class PathPicker(QWidget):
    """文本框 + 浏览按钮。"""

    def __init__(
        self,
        mode: str,
        placeholder: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode  # "file" | "dir" | "save"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        layout.addWidget(self.edit, 1)

        browse = QPushButton("浏览…")
        browse.setFixedWidth(64)
        browse.clicked.connect(self._browse)
        layout.addWidget(browse, 0)

        open_btn = QPushButton("打开")
        open_btn.setFixedWidth(50)
        open_btn.clicked.connect(self._open)
        layout.addWidget(open_btn, 0)

    def _browse(self) -> None:
        if self.mode == "file":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择文件",
                self.edit.text() or "",
                "所有文件 (*.*);;文本文件 (*.txt)",
            )
        else:
            path = QFileDialog.getExistingDirectory(
                self, "选择目录", self.edit.text() or ""
            )
        if path:
            self.edit.setText(path)

    def _open(self) -> None:
        from os import startfile
        from pathlib import Path

        target = self.edit.text().strip()
        if not target:
            return
        p = Path(target)
        try:
            if self.mode == "file" and p.is_file():
                startfile(str(p))
            elif self.mode != "file" and p.is_dir():
                startfile(str(p))
            elif p.parent.is_dir():
                startfile(str(p.parent))
        except Exception:
            pass

    def value(self) -> str:
        return self.edit.text().strip()

    def set_value(self, value: Any) -> None:
        self.edit.setText("" if value is None else str(value))


# --------------------------------------------------------------------------- #
# 多选（复选）控件
# --------------------------------------------------------------------------- #
class MultiChoiceBox(QWidget):
    """横向排列的复选组，**勾选顺序即取值顺序**。

    用于“文件名组成”这类顺序敏感的多选参数：用户勾选的先后顺序决定拼接顺序，
    取消后再重新勾选即可调整位置。其他顺序无关的多选参数（如指纹池）不受影响。
    """

    changed = pyqtSignal()

    def __init__(
        self,
        choices: tuple[tuple[str, Any], ...] | list[tuple[str, Any]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._boxes: list[tuple[QCheckBox, Any]] = []
        self._order: list[Any] = []
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(2)
        per_row = 3
        for index, (label, value) in enumerate(choices):
            box = QCheckBox(label)
            box.stateChanged.connect(lambda _state, v=value: self._on_toggle(v))
            layout.addWidget(box, index // per_row, index % per_row)
            self._boxes.append((box, value))

    def _on_toggle(self, value: Any) -> None:
        checked_now = {v: b.isChecked() for b, v in self._boxes}
        if checked_now.get(value):
            if value not in self._order:
                self._order.append(value)
        elif value in self._order:
            self._order.remove(value)
        self.changed.emit()

    def value(self) -> list[Any]:
        checked = {v for box, v in self._boxes if box.isChecked()}
        ordered = [v for v in self._order if v in checked]
        # 兜底：不在顺序表里的已勾选项按定义顺序补到末尾
        for _box, value in self._boxes:
            if value in checked and value not in ordered:
                ordered.append(value)
        return ordered

    def set_value(self, values: Any) -> None:
        if isinstance(values, str):
            values = [v.strip() for v in values.replace(",", " ").split() if v.strip()]
        values = list(values or [])
        known = [value for _box, value in self._boxes]
        # 传入顺序即初始拼接顺序（例如从配置读回的 name_format）
        self._order = [value for value in values if value in known]
        for box, value in self._boxes:
            box.blockSignals(True)
            box.setChecked(value in values)
            box.blockSignals(False)

    def order_hint(self) -> str:
        return "、".join(str(v) for v in self.value())


# --------------------------------------------------------------------------- #
# 单个参数编辑器
# --------------------------------------------------------------------------- #
class FieldEditor(QWidget):
    """一个参数项：标签 + “?” 帮助图标 + 输入控件。"""

    changed = pyqtSignal()

    def __init__(self, field: Field, value: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.field = field
        self._getter: Callable[[], Any]
        self._setter: Callable[[Any], None]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(3)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(5)

        label = QLabel(field.label)
        label.setObjectName("FieldLabel")
        if field.upstream:
            label.setToolTip(f"§ {field.upstream}")
        header.addWidget(label, 0)

        help_button = QPushButton("?")
        help_button.setObjectName("HelpButton")
        help_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        help_button.setToolTip("点击查看该参数的说明与示例")
        help_button.clicked.connect(self._show_help)
        header.addWidget(help_button, 0)
        header.addStretch(1)

        self.action_area = header  # 供外部插入“粘贴 / 清空”等操作按钮
        root.addLayout(header)

        editor, getter, setter = self._build_editor(field, value)
        self.editor = editor
        root.addWidget(editor)
        self._getter = getter
        self._setter = setter

    # ------------------------------------------------------------------ #
    def _show_help(self) -> None:
        dialog = HelpDialog(self.field, self.window())
        dialog.exec()

    def add_action_button(self, button: QPushButton) -> None:
        """在标签行右侧追加一个动作按钮。"""
        button.setObjectName("LinkButton")
        button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.action_area.addWidget(button, 0)

    # ------------------------------------------------------------------ #
    def _build_editor(
        self, field: Field, value: Any
    ) -> tuple[QWidget, Callable[[], Any], Callable[[Any], None]]:
        kind = field.kind

        if kind == "bool":
            widget = QCheckBox("启用")
            widget.setChecked(bool(value if value is not None else field.default))
            widget.stateChanged.connect(lambda *_: self.changed.emit())

            def getter() -> bool:
                return widget.isChecked()

            def setter(v: Any) -> None:
                widget.blockSignals(True)
                widget.setChecked(bool(v))
                widget.blockSignals(False)

            return widget, getter, setter

        if kind == "int":
            # QSpinBox 只支持 int32，这里做一次钳制，避免规格中写入超大上限时崩溃
            _INT32_MIN, _INT32_MAX = -2147483648, 2147483647
            lower = int(field.minimum) if field.minimum is not None else _INT32_MIN
            upper = int(field.maximum) if field.maximum is not None else _INT32_MAX
            lower = max(_INT32_MIN, min(lower, _INT32_MAX))
            upper = max(_INT32_MIN, min(upper, _INT32_MAX))
            if upper < lower:
                upper = lower
            widget = QSpinBox()
            widget.setRange(lower, upper)
            if field.step:
                widget.setSingleStep(max(1, int(field.step)))
            widget.setValue(max(lower, min(int(value if value is not None else field.default), upper)))
            if field.suffix:
                widget.setSuffix(field.suffix)
            widget.valueChanged.connect(lambda *_: self.changed.emit())

            def getter() -> int:
                return widget.value()

            def setter(v: Any) -> None:
                widget.blockSignals(True)
                widget.setValue(int(v))
                widget.blockSignals(False)

            return widget, getter, setter

        if kind == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(field.decimals or 2)
            widget.setRange(
                float(field.minimum if field.minimum is not None else -1e12),
                float(field.maximum if field.maximum is not None else 1e12),
            )
            if field.step:
                widget.setSingleStep(float(field.step))
            widget.setValue(float(value if value is not None else field.default))
            widget.valueChanged.connect(lambda *_: self.changed.emit())

            def getter() -> float:
                return widget.value()

            def setter(v: Any) -> None:
                widget.blockSignals(True)
                widget.setValue(float(v))
                widget.blockSignals(False)

            return widget, getter, setter

        if kind == "choice":
            widget = QComboBox()
            for label, val in field.choices:
                widget.addItem(label, val)
            index = widget.findData(value if value is not None else field.default)
            widget.setCurrentIndex(max(0, index))
            widget.currentIndexChanged.connect(lambda *_: self.changed.emit())

            def getter() -> Any:
                return widget.currentData()

            def setter(v: Any) -> None:
                widget.blockSignals(True)
                widget.setCurrentIndex(max(0, widget.findData(v)))
                widget.blockSignals(False)

            return widget, getter, setter

        if kind == "multichoice":
            widget = MultiChoiceBox(field.choices)
            widget.set_value(value if value is not None else field.default)
            widget.changed.connect(lambda: self.changed.emit())

            def getter() -> list:
                return widget.value()

            def setter(v: Any) -> None:
                widget.set_value(v)

            return widget, getter, setter

        if kind == "textblock":
            widget = QPlainTextEdit()
            widget.setPlaceholderText(field.placeholder)
            widget.setPlainText("" if value is None else str(value))
            widget.setFixedHeight(max(52, (field.rows or 4) * 20))
            mono = QFont("Consolas")
            mono.setStyleHint(QFont.StyleHint.Monospace)
            mono.setPointSize(9)
            widget.setFont(mono)
            widget.textChanged.connect(lambda: self.changed.emit())

            def getter() -> str:
                return widget.toPlainText()

            def setter(v: Any) -> None:
                widget.blockSignals(True)
                widget.setPlainText("" if v is None else str(v))
                widget.blockSignals(False)

            return widget, getter, setter

        if kind in ("openfile", "directory"):
            widget = PathPicker(
                "file" if kind == "openfile" else "dir",
                field.placeholder,
            )
            widget.set_value(value if value is not None else field.default)
            widget.edit.textChanged.connect(lambda *_: self.changed.emit())

            def getter() -> str:
                return widget.value()

            def setter(v: Any) -> None:
                widget.set_value(v)

            return widget, getter, setter

        # 默认：单行文本
        widget = QLineEdit()
        widget.setPlaceholderText(field.placeholder)
        widget.setText("" if value is None else str(value))
        widget.textChanged.connect(lambda *_: self.changed.emit())

        def getter() -> str:
            return widget.text().strip()

        def setter(v: Any) -> None:
            widget.blockSignals(True)
            widget.setText("" if v is None else str(v))
            widget.blockSignals(False)

        return widget, getter, setter

    # ------------------------------------------------------------------ #
    def value(self) -> Any:
        return self._getter()

    def set_value(self, value: Any) -> None:
        self._setter(value)

    def focus_editor(self) -> None:
        try:
            self.editor.setFocus()  # type: ignore[attr-defined]
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 分区卡片
# --------------------------------------------------------------------------- #
class SectionCard(QFrame):
    """一个设置板块：标题 + 若干参数行。"""

    def __init__(
        self,
        title: str,
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._rows = QVBoxLayout()
        self._rows.setContentsMargins(10, 6, 10, 8)
        self._rows.setSpacing(4)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        header.addWidget(title_label, 0)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("CardHint")
            header.addWidget(hint_label, 0)
        header.addStretch(1)
        outer.addLayout(header)
        outer.addLayout(self._rows)

    def add_widget(self, widget: QWidget) -> None:
        self._rows.addWidget(widget)

    def insert_after(self, anchor: QWidget, widget: QWidget) -> None:
        """把 ``widget`` 插到 ``anchor`` 的下方。"""
        index = self._rows.indexOf(anchor)
        if index < 0:
            self._rows.addWidget(widget)
            return
        self._rows.insertWidget(index + 1, widget)

    def add_note(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("CardHint")
        label.setWordWrap(True)
        self._rows.addWidget(label)

    def add_stretch(self) -> None:
        self._rows.addStretch(1)


def make_scroll_area(inner: QWidget) -> QScrollArea:
    """把控件包进可滚动的容器。"""
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(inner)
    return area
