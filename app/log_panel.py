"""右侧日志显示区。"""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import level_color

__all__ = ["LogPanel"]

_MAX_BLOCKS = 8000

_LEVEL_FILTERS = (
    ("全部", None),
    ("仅信息", ("info", "success", "system")),
    ("仅警告", ("warning",)),
    ("仅错误", ("error",)),
)


class LogPanel(QWidget):
    """带级别着色、过滤与导出的日志面板。"""

    def __init__(self, dark: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.dark = dark
        self._records: list[tuple[str, str, str]] = []  # (时间, 级别, 文本)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ---------------- 标题栏 ----------------
        header = QFrame()
        header.setObjectName("Card")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(8)

        title = QLabel("运行日志")
        title.setObjectName("CardTitle")
        header_layout.addWidget(title, 0)

        self.counter = QLabel("共 0 条")
        self.counter.setObjectName("CardHint")
        header_layout.addWidget(self.counter, 0)
        header_layout.addStretch(1)

        header_layout.addWidget(QLabel("级别："))
        self.filter_box = QComboBox()
        for label, _value in _LEVEL_FILTERS:
            self.filter_box.addItem(label)
        self.filter_box.setFixedWidth(96)
        header_layout.addWidget(self.filter_box)

        self.autoscroll = QCheckBox("自动滚动")
        self.autoscroll.setChecked(True)
        header_layout.addWidget(self.autoscroll)

        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear)
        header_layout.addWidget(clear_btn)

        export_btn = QPushButton("导出日志")
        export_btn.clicked.connect(self.export)
        header_layout.addWidget(export_btn)

        layout.addWidget(header)

        # ---------------- 日志正文 ----------------
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(_MAX_BLOCKS)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.view.setPlaceholderText(
            "这里会实时显示采集过程日志。\n"
            "点击左上角「开始任务」后，上游内核的全部输出都会转发到此处。"
        )
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(9)
        self.view.setFont(mono)
        layout.addWidget(self.view, 1)

        self.filter_box.currentIndexChanged.connect(self._rerender)

    # ------------------------------------------------------------------ #
    def append(self, level: str, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._records.append((stamp, level, text))
        if len(self._records) > _MAX_BLOCKS:
            del self._records[: len(self._records) - _MAX_BLOCKS]
        self.counter.setText(f"共 {len(self._records)} 条")
        if self._visible(level):
            self._append_html(stamp, level, text)

    def _visible(self, level: str) -> bool:
        allowed = _LEVEL_FILTERS[self.filter_box.currentIndex()][1]
        return allowed is None or level in allowed

    def _append_html(self, stamp: str, level: str, text: str) -> None:
        color = level_color(level, self.dark)
        muted = "#9aa0aa" if self.dark else "#8a919f"
        body = escape(text).replace("  ", "&nbsp;&nbsp;").replace("\n", "<br/>")
        html = (
            f'<span style="color:{muted}">[{stamp}]</span> '
            f'<span style="color:{color}">{body}</span>'
        )
        self.view.appendHtml(html)
        if self.autoscroll.isChecked():
            self.view.moveCursor(QTextCursor.MoveOperation.End)

    def _rerender(self) -> None:
        self.view.clear()
        for stamp, level, text in self._records:
            if self._visible(level):
                self._append_html(stamp, level, text)

    # ------------------------------------------------------------------ #
    def clear(self) -> None:
        self._records.clear()
        self.view.clear()
        self.counter.setText("共 0 条")

    def export(self) -> None:
        if not self._records:
            QMessageBox.information(self, "没有日志", "当前没有可导出的日志内容。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "导出日志",
            f"DouK-GUI-{datetime.now():%Y%m%d-%H%M%S}.log",
            "日志文件 (*.log);;文本文件 (*.txt)",
        )
        if not path:
            return
        try:
            Path(path).write_text(
                "\n".join(f"[{s}][{lv.upper()}] {t}" for s, lv, t in self._records),
                encoding="utf-8",
            )
            QMessageBox.information(self, "导出成功", f"日志已保存至：\n{path}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导出失败", str(exc))
