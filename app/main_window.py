"""主窗口。

布局（严格按要求）：

    ┌───────────────────────────────────────────────────────────┐
    │ 工具栏：开始 / 停止 / 保存 / 重载 / 恢复默认 / 打开目录 …   │
    ├───────────────────────────┬───────────────────────────────┤
    │  设置区（左半屏）          │  日志区（右半屏）              │
    │  ┌ 抖音 ┬ TikTok ┐        │                               │
    │  │ Cookie            │    │                               │
    │  │ 下载类型           │    │                               │
    │  │ 链接传入方式        │    │                               │
    │  │ 其它全部参数        │    │                               │
    ├───────────────────────────┴───────────────────────────────┤
    │ 进度条 + 状态信息                                          │
    └───────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from re import compile as re_compile
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFontMetrics, QKeySequence
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .about_dialog import AboutDialog
from .config_store import ConfigStore
from .engine import EngineWorker, TaskRequest, normalize_cookie
from .field_spec import PLATFORM_NAMES
from .legacy_import import DEFAULT_LEGACY_DB, import_records
from .link_analysis import MODE_NAMES, URL_PATTERN, analyse
from .log_panel import LogPanel
from .paths import (
    APP_ROOT,
    CONFIG_FILE,
    DOWNLOADS_DIR,
    RECORD_DB,
    UPSTREAM_ROOT,
    VOLUME_DIR,
)
from .settings_panel import SettingsPanel
from .stats import TYPE_ORDER, format_entries, format_chips

__all__ = ["MainWindow"]

#: 内核 settings.json 顶层键 -> GUI 配置键
_UPSTREAM_KEY_MAP: dict[str, str] = {
    "cookie": "cookie",
    "cookie_tiktok": "cookie_tiktok",
    "root": "root",
    "folder_name": "folder_name",
    "name_format": "name_format",
    "desc_length": "desc_length",
    "name_length": "name_length",
    "date_format": "date_format",
    "split": "split",
    "folder_mode": "folder_mode",
    "music": "music",
    "truncate": "truncate",
    "storage_format": "storage_format",
    "dynamic_cover": "dynamic_cover",
    "static_cover": "static_cover",
    "proxy": "proxy",
    "proxy_tiktok": "proxy_tiktok",
    "download": "download",
    "max_size": "max_size",
    "chunk": "chunk",
    "timeout": "timeout",
    "max_retry": "max_retry",
    "max_pages": "max_pages",
    "ffmpeg": "ffmpeg",
    "live_qualities": "live_qualities",
    "original_quality": "original_quality",
    "douyin_platform": "douyin_platform",
    "tiktok_platform": "tiktok_platform",
}

#: (内核 settings.json 块名, 块内键) -> GUI 配置键
_UPSTREAM_BROWSER_MAP: dict[tuple[str, str], str] = {
    ("browser_info", "impersonate"): "browser_info_impersonate",
    ("browser_info", "pc_libra_divert"): "browser_info_pc_libra_divert",
    ("browser_info", "browser_language"): "browser_info_browser_language",
    ("browser_info", "browser_platform"): "browser_info_browser_platform",
    ("browser_info", "browser_name"): "browser_info_browser_name",
    ("browser_info", "browser_version"): "browser_info_browser_version",
    ("browser_info", "engine_name"): "browser_info_engine_name",
    ("browser_info", "engine_version"): "browser_info_engine_version",
    ("browser_info", "os_name"): "browser_info_os_name",
    ("browser_info", "os_version"): "browser_info_os_version",
    ("browser_info", "webid"): "browser_info_webid",
    ("browser_info_tiktok", "impersonate"): "browser_info_tiktok_impersonate",
    ("browser_info_tiktok", "app_language"): "browser_info_tiktok_app_language",
    ("browser_info_tiktok", "browser_language"): "browser_info_tiktok_browser_language",
    ("browser_info_tiktok", "browser_name"): "browser_info_tiktok_browser_name",
    ("browser_info_tiktok", "browser_platform"): "browser_info_tiktok_browser_platform",
    ("browser_info_tiktok", "browser_version"): "browser_info_tiktok_browser_version",
    ("browser_info_tiktok", "language"): "browser_info_tiktok_language",
    ("browser_info_tiktok", "os"): "browser_info_tiktok_os",
    ("browser_info_tiktok", "priority_region"): "browser_info_tiktok_priority_region",
    ("browser_info_tiktok", "region"): "browser_info_tiktok_region",
    ("browser_info_tiktok", "tz_name"): "browser_info_tiktok_tz_name",
    ("browser_info_tiktok", "webcast_language"): "browser_info_tiktok_webcast_language",
    ("browser_info_tiktok", "device_id"): "browser_info_tiktok_device_id",
}

#: URL 提取正则（与内核 Requester 一致，统一由 link_analysis 提供，避免两处漂移）
_URL_PATTERN = URL_PATTERN

#: 裸标识符（sec_user_id / 作品 ID / 合集 ID），用于无 URL 时直接填写 ID 的场景
_BARE_IDENTIFIER = re_compile(r"^[A-Za-z0-9_\-]{8,}$")

APP_TITLE = "DouK-Downloader GUI · 抖音 / TikTok 作品采集工具"

#: 计数栏尺寸与配色
_ACCOUNT_CHIP_WIDTH = 142
_COUNTER_BAR_HEIGHT = 34
_TYPE_CHIP_MIN_WIDTH = 66
_COLOR_LABEL = "#1f2329"
_COLOR_DOWNLOAD = "#07c160"   # 已下载：绿色
_COLOR_SKIP = "#e34d59"       # 跳过：红色
_COLOR_MUTED = "#c9cdd4"      # 数值为 0 时置灰
_COLOR_SEP = "#dcdfe6"


def _pair_html(label: str, download: int, skip: int) -> str:
    """类型计数项：``名称：下载数 | 跳过数``，下载为绿色、跳过为红色。"""
    download_color = _COLOR_DOWNLOAD if download else _COLOR_MUTED
    skip_color = _COLOR_SKIP if skip else _COLOR_MUTED
    return (
        f'<span style="color:{_COLOR_LABEL}">{label}：</span>'
        f'<span style="color:{download_color}">{download}</span>'
        f'<span style="color:{_COLOR_SEP}"> | </span>'
        f'<span style="color:{skip_color}">{skip}</span>'
    )


def _repolish(widget) -> None:
    """属性变化后刷新样式（QSS 属性选择器不会自动重绘）。"""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


class MainWindow(QMainWindow):
    """应用主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1480, 900)
        self.setMinimumSize(1120, 680)

        self.store = ConfigStore()
        self.config: dict[str, Any] = self.store.load()
        self.worker: EngineWorker | None = None
        self.panels: dict[str, SettingsPanel] = {}
        self._tab_order = ["douyin", "tiktok"]
        self._active_platform = "douyin"

        self._build_ui()
        self._build_actions()
        self._load_into_ui()

    # ------------------------------------------------------------------ #
    # 界面搭建
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("RootWidget")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self.tabs = QTabWidget()
        for platform in self._tab_order:
            panel = SettingsPanel(platform)
            panel.changed.connect(self._on_settings_changed)
            self.panels[platform] = panel
            self.tabs.addTab(panel, PLATFORM_NAMES[platform])
        self.tabs.currentChanged.connect(self._on_tab_changed)
        splitter.addWidget(self.tabs)

        self.log_panel = LogPanel()
        splitter.addWidget(self.log_panel)

        # 设置区 : 日志区 = 40% : 60%
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        self.splitter = splitter
        self._apply_splitter_ratio()
        layout.addWidget(splitter, 1)

        layout.addWidget(self._build_footer())
        self.statusBar().showMessage("就绪")

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("Card")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)

        self.start_button = QPushButton("开始任务")
        self.start_button.setObjectName("Primary")
        self.start_button.setMinimumWidth(110)
        self.start_button.clicked.connect(self._on_start)
        row.addWidget(self.start_button)

        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("Danger")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._on_stop)
        row.addWidget(self.stop_button)

        row.addWidget(_separator())

        save_btn = QPushButton("保存配置")
        save_btn.clicked.connect(self._on_save)
        row.addWidget(save_btn)

        reload_btn = QPushButton("重新载入")
        reload_btn.clicked.connect(self._on_reload)
        row.addWidget(reload_btn)

        reset_btn = QPushButton("恢复默认")
        reset_btn.clicked.connect(self._on_reset)
        row.addWidget(reset_btn)

        import_btn = QPushButton("导入内核配置")
        import_btn.setToolTip("从内核 settings.json 导入 Cookie 与各项参数，便于从命令行版本迁移")
        import_btn.clicked.connect(self._on_import_upstream)
        row.addWidget(import_btn)

        record_btn = QPushButton("导入下载记录")
        record_btn.setToolTip(
            "从旧版内核的 DouK-Downloader.db 导入已下载作品记录，避免重复下载"
        )
        record_btn.clicked.connect(self._on_import_records)
        row.addWidget(record_btn)

        row.addWidget(_separator())

        open_dl = QPushButton("打开下载目录")
        open_dl.clicked.connect(self._open_download_dir)
        row.addWidget(open_dl)

        open_cfg = QPushButton("打开配置目录")
        open_cfg.clicked.connect(lambda: self._open_path(CONFIG_FILE.parent))
        row.addWidget(open_cfg)

        row.addWidget(_separator())

        about_btn = QPushButton("关于")
        about_btn.clicked.connect(self._on_about)
        row.addWidget(about_btn)

        row.addStretch(1)

        self.dirty_label = QLabel("")
        self.dirty_label.setObjectName("CardHint")
        row.addWidget(self.dirty_label)

        return bar

    def _build_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("Card")
        column = QVBoxLayout(footer)
        column.setContentsMargins(10, 8, 10, 8)
        column.setSpacing(6)

        # ---- 第一行：账号计数 + 进度条 + 阶段 + 自动保存 ---- #
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.account_chip = QLabel("账号数量 0/0")
        self.account_chip.setObjectName("CounterChip")
        self.account_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.account_chip.setFixedWidth(_ACCOUNT_CHIP_WIDTH)
        self.account_chip.setToolTip("本次已处理 / 待处理的账号（合集）链接数量")
        row.addWidget(self.account_chip, 0)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMinimumWidth(200)
        row.addWidget(self.progress, 1)

        self.phase_label = QLabel("空闲")
        self.phase_label.setObjectName("CardHint")
        self.phase_label.setMinimumWidth(220)
        row.addWidget(self.phase_label, 0)

        self.stats_label = QLabel("")
        self.stats_label.setObjectName("CardHint")
        row.addWidget(self.stats_label, 0)

        self.autosave = QCheckBox("退出时自动保存配置")
        self.autosave.setChecked(True)
        row.addWidget(self.autosave, 0)

        column.addLayout(row)

        # ---- 第二行：分类计数栏（横向可滚动，窄窗口下不截断） ---- #
        column.addWidget(self._build_counter_bar())
        return footer

    def _build_counter_bar(self) -> QWidget:
        """进度条下方的实时计数栏（按类型汇总下载 / 跳过数量）。"""
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.counter_chips: dict[str, QLabel] = {}
        for name in TYPE_ORDER:
            chip = QLabel("")
            chip.setObjectName("CounterChip")
            chip.setTextFormat(Qt.TextFormat.RichText)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setToolTip(self._chip_tooltip(name))
            chip.setMinimumWidth(self._type_chip_width())
            # stretch=0：按自然宽度紧凑排布（stretch=1 会被拉伸填满整行，
            # 使最小宽度失效，看起来就没变短）
            layout.addWidget(chip, 0)
            self.counter_chips[name] = chip

        layout.addStretch(1)

        legend = QLabel("计数说明：绿色数字为已下载计数，红色数字为跳过计数。")
        legend.setObjectName("CardHint")
        layout.addWidget(legend, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFixedHeight(_COUNTER_BAR_HEIGHT)
        scroll.setWidget(holder)
        self.counter_scroll = scroll
        return scroll

    def _type_chip_width(self) -> int:
        """文件类型计数项的宽度：贴合内容，约为加宽版本的一半。"""
        metrics = QFontMetrics(self.font())
        natural = metrics.horizontalAdvance("动图： 000 | 000") + 16  # 含内边距与边框
        return max(_TYPE_CHIP_MIN_WIDTH, natural)

    @staticmethod
    def _chip_tooltip(name: str) -> str:
        return f"{name}：绿色数字为已下载文件数，红色数字为已跳过文件数"

    def _on_stats(self, snapshot: dict) -> None:
        """刷新计数栏。"""
        if not hasattr(self, "counter_chips"):
            return

        entries = format_entries(snapshot)
        by_key = {entry["key"]: entry for entry in entries}

        # 账号固定在进度条左侧
        account = by_key.get("账号")
        if account:
            self.account_chip.setText(f"账号数量 {account['value']}")
            self.account_chip.setProperty("zero", _is_zero(str(account["value"])))
        else:
            self.account_chip.setText("账号数量 —")
            self.account_chip.setProperty("zero", True)
        _repolish(self.account_chip)

        for name, chip in self.counter_chips.items():
            entry = by_key.get(name)
            if entry is not None and entry["kind"] == "pair":
                chip.setText(_pair_html(name, entry["download"], entry["skip"]))
            else:
                chip.setText(_pair_html(name, 0, 0))

    def _apply_splitter_ratio(self, left_ratio: float = 0.40) -> None:
        """设置区 : 日志区 = 40% : 60%。"""
        total = self.splitter.width() or self.width() or 1480
        if total <= 0:
            return
        left = max(360, int(total * left_ratio))
        self.splitter.setSizes([left, max(320, total - left)])

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 回调
        super().showEvent(event)
        # 首次显示时按 40/60 分配；之后尊重用户的拖动结果
        if not getattr(self, "_splitter_ready", False):
            self._splitter_ready = True
            self._apply_splitter_ratio()

    def _build_actions(self) -> None:
        start = QAction("开始任务", self)
        start.setShortcut(QKeySequence("Ctrl+R"))
        start.triggered.connect(self._on_start)
        save = QAction("保存配置", self)
        save.setShortcut(QKeySequence("Ctrl+S"))
        save.triggered.connect(self._on_save)
        stop = QAction("停止任务", self)
        stop.setShortcut(QKeySequence("Ctrl+."))
        stop.triggered.connect(self._on_stop)
        self.addAction(start)
        self.addAction(save)
        self.addAction(stop)

    # ------------------------------------------------------------------ #
    # 配置读写
    # ------------------------------------------------------------------ #
    def _load_into_ui(self) -> None:
        for panel in self.panels.values():
            panel.load(self.config)
        self._active_platform = self._tab_order[self.tabs.currentIndex()]
        self._mark_clean()

    def _collect_config(self) -> None:
        """把两个分页的控件值汇总到共享配置，当前分页的值最后写入以确保优先。"""
        for platform, panel in self.panels.items():
            if platform == self._active_platform:
                continue
            panel.commit(self.config)
        self.panels[self._active_platform].commit(self.config)

    def _on_tab_changed(self, index: int) -> None:
        new_platform = self._tab_order[index]
        if new_platform == self._active_platform:
            return
        # 仅提交「正在离开」的分页，避免另一分页的旧值覆盖新值
        self.panels[self._active_platform].commit(self.config)
        self._active_platform = new_platform
        self.panels[new_platform].load(self.config)
        self.statusBar().showMessage(f"已切换到 {PLATFORM_NAMES[new_platform]} 设置", 3000)

    def _on_settings_changed(self) -> None:
        self.dirty_label.setText("● 配置已修改（未保存）")

    def _mark_clean(self) -> None:
        self.dirty_label.setText("")

    def _on_save(self) -> None:
        self._collect_config()
        try:
            path = self.store.save(self.config)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._mark_clean()
        self.log_panel.append("success", f"配置已保存：{path}")
        self.statusBar().showMessage("配置已保存", 3000)

    def _on_reload(self) -> None:
        if QMessageBox.question(
            self, "重新载入", "将放弃当前未保存的修改并从磁盘重新载入配置，是否继续？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.config = self.store.load()
        self._load_into_ui()
        self.log_panel.append("info", "已从配置文件重新载入参数。")

    def _on_reset(self) -> None:
        if QMessageBox.question(
            self, "恢复默认", "将把所有参数恢复为默认值（不会立即写盘），是否继续？"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.config = self.store.reset()
        self._load_into_ui()
        self.log_panel.append("warning", "所有参数已恢复为默认值，如需生效请点击「保存配置」。")

    def _on_import_records(self) -> None:
        """把旧版内核的下载记录合并到本项目（增量、不覆盖、自动备份）。"""
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.warning(
                self,
                "任务进行中",
                "任务正在使用下载记录数据库，请先停止任务再导入。",
            )
            return

        start_dir = DEFAULT_LEGACY_DB.parent
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择旧版内核的 DouK-Downloader.db",
            str(start_dir) if start_dir.is_dir() else str(APP_ROOT),
            "数据库文件 (*.db);;所有文件 (*.*)",
        )
        if not path:
            return

        try:
            result = import_records(Path(path), RECORD_DB, include_mapping=True)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "导入失败", f"{type(exc).__name__}: {exc}"
            )
            return

        level = "warning" if result.warnings else "success"
        for line in result.summary().splitlines():
            self.log_panel.append(level, f"[导入下载记录] {line}")
        QMessageBox.information(
            self,
            "导入完成",
            result.summary()
            + "\n\n导入后，「下载前预过滤」会直接跳过这些已下载作品，不再消耗接口请求。",
        )

    def _on_import_upstream(self) -> None:
        """从内核 settings.json 导入参数（便于从命令行版本迁移）。"""
        default_dir = VOLUME_DIR
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择内核 settings.json",
            str(default_dir) if default_dir.is_dir() else str(APP_ROOT),
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "导入失败", f"无法解析该文件：\n{exc}")
            return
        if not isinstance(payload, dict):
            QMessageBox.critical(self, "导入失败", "文件内容不是 JSON 对象。")
            return

        imported: list[str] = []
        for upstream_key, gui_key in _UPSTREAM_KEY_MAP.items():
            if upstream_key not in payload:
                continue
            value = payload[upstream_key]
            if value is None:
                continue
            if gui_key in ("cookie", "cookie_tiktok"):
                value = normalize_cookie(str(value)) if not isinstance(value, dict) else (
                    "; ".join(f"{k}={v}" for k, v in value.items() if v not in (None, ""))
                )
            elif gui_key == "name_format" and isinstance(value, str):
                value = value.split()
            elif gui_key == "run_command" and isinstance(value, list):
                value = " ".join(value)
            self.config[gui_key] = value
            imported.append(gui_key)

        for (block, sub_key), gui_key in _UPSTREAM_BROWSER_MAP.items():
            block_value = payload.get(block)
            if isinstance(block_value, dict) and sub_key in block_value:
                self.config[gui_key] = block_value[sub_key]
                imported.append(gui_key)

        self._load_into_ui()
        self.log_panel.append(
            "success",
            f"已从 {path} 导入 {len(set(imported))} 项参数。"
            "请核对「保存根目录」是否为当前系统的有效路径（旧配置可能来自其他系统）。",
        )
        if imported:
            QMessageBox.information(
                self,
                "导入完成",
                f"共导入 {len(set(imported))} 项参数。\n\n"
                "注意：\n"
                "1. 旧配置中的“保存根目录”可能来自 macOS / 其他电脑，请改为本机有效路径；\n"
                "2. 导入结果尚未写盘，确认无误后请点击「保存配置」。",
            )
        else:
            QMessageBox.warning(self, "未导入任何参数", "该文件中没有可识别的参数项。")

    # ------------------------------------------------------------------ #
    # 任务执行
    # ------------------------------------------------------------------ #
    def _on_start(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "任务进行中", "已有任务正在运行，请先停止或等待其结束。")
            return

        self._collect_config()
        platform = self._active_platform
        name = PLATFORM_NAMES[platform]

        if not self.config.get(f"{platform}_platform", True):
            QMessageBox.warning(
                self, "平台已停用",
                f"当前分页对应平台「{name}」在“平台开关”中被停用，请先启用后再开始任务。",
            )
            return

        request = TaskRequest(
            platform=platform,
            mode=str(self.config.get(f"task_mode{'' if platform == 'douyin' else '_tiktok'}") or "detail"),
            account_tab=str(self.config.get(f"account_tab{'' if platform == 'douyin' else '_tiktok'}") or "post"),
        )

        try:
            request.links = self._resolve_links(platform, request.mode)
        except ValueError as exc:
            QMessageBox.warning(self, "链接无效", str(exc))
            return
        if not request.links:
            QMessageBox.warning(
                self, "没有待处理链接",
                "请先粘贴作品链接，或选择一个包含链接的本地 txt 文件。",
            )
            return

        if not self._confirm_link_mode(platform, request):
            return

        cookie = str(self.config.get("cookie" if platform == "douyin" else "cookie_tiktok") or "").strip()
        if not cookie:
            if QMessageBox.question(
                self,
                "Cookie 为空",
                f"未填写 {name} Cookie，程序在执行账号类接口时可能返回空数据或被风控。\n"
                "是否仍然继续？",
            ) != QMessageBox.StandardButton.Yes:
                return

        if request.mode == "live" and not str(self.config.get("ffmpeg") or "").strip():
            if QMessageBox.question(
                self,
                "未配置 FFmpeg",
                "直播模式需要 FFmpeg 才能录制。当前未填写 FFmpeg 路径，"
                "程序将只解析并打印拉流地址。是否继续？",
            ) != QMessageBox.StandardButton.Yes:
                return

        try:
            self.store.save(self.config)
            self._mark_clean()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "保存配置失败", str(exc))

        self._set_running(True)
        self.progress.setRange(0, 0)
        self.stats_label.setText("")
        self._reset_counters()
        self.phase_label.setText(f"正在启动：{request.title}")
        self.log_panel.append("system", f"启动任务：{request.title}（共 {len(request.links)} 条输入）")

        worker = EngineWorker(self.config, request)
        worker.signals.message.connect(self.log_panel.append)
        worker.signals.phase.connect(self.phase_label.setText)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.stats.connect(self._on_stats)
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self.worker = worker
        worker.start()

    def _resolve_links(self, platform: str, mode: str) -> list[str]:
        suffix = "" if platform == "douyin" else "_tiktok"
        source = str(self.config.get(f"link_source{suffix}") or "paste")

        if source == "file":
            raw_path = str(self.config.get(f"link_file{suffix}") or "").strip()
            if not raw_path:
                raise ValueError("未选择 txt 文件，请在设置区选择文件或改用粘贴模式。")
            path = Path(raw_path)
            if not path.is_file():
                raise ValueError(f"文件不存在：{raw_path}")
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                try:
                    text = path.read_text(encoding="gbk")
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(f"无法解析文件编码：{exc}") from exc
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"读取文件失败：{exc}") from exc
            self.log_panel.append("info", f"已读取 txt 文件：{path}")
        else:
            text = str(self.config.get(f"link_text{suffix}") or "")

        return _split_links(text, mode)

    def _confirm_link_mode(self, platform: str, request: TaskRequest) -> bool:
        """启动前检查「链接类型」与「下载类型」是否匹配。

        典型误用：把账号主页链接放进「批量下载链接作品」模式 —— 该模式只识别
        19 位作品 ID，账号链接里没有，于是会白跑一轮链接解析（每条一次请求、
        按反爬间隔等待，可能十几分钟）最后才报解析失败。

        :return: True 表示继续启动，False 表示用户取消
        """
        analysis = analyse(request.links, platform)
        advice = analysis.mismatch_message(request.mode)
        self.log_panel.append(
            "info",
            f"链接类型检查：共 {analysis.total} 条，{analysis.describe()}",
        )
        if not advice:
            return True

        dialog = QMessageBox(self)
        dialog.setWindowTitle("下载类型与链接不匹配")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(advice)
        dialog.setTextFormat(Qt.TextFormat.PlainText)

        switch_button = None
        suggested = analysis.suggested_mode
        if suggested and suggested != request.mode:
            switch_button = dialog.addButton(
                f"改用「{MODE_NAMES.get(suggested, suggested)}」",
                QMessageBox.ButtonRole.AcceptRole,
            )
        keep_button = dialog.addButton("仍按当前模式继续", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(switch_button or keep_button)
        dialog.exec()

        clicked = dialog.clickedButton()
        if clicked is cancel_button:
            self.log_panel.append("warning", "已取消启动：下载类型与链接不匹配。")
            return False
        if switch_button is not None and clicked is switch_button and suggested:
            request.mode = suggested
            mode_key = "task_mode" if platform == "douyin" else "task_mode_tiktok"
            panel = self.panels[platform]
            if mode_key in panel.editors:
                panel.editors[mode_key].set_value(suggested)
                panel.refresh_visibility()
            self.config[mode_key] = suggested
            self.log_panel.append(
                "success", f"已切换下载类型为「{MODE_NAMES.get(suggested, suggested)}」。"
            )
        else:
            self.log_panel.append("warning", "已按当前下载类型继续（可能存在大量无效链接）。")
        return True

    def _on_stop(self) -> None:
        if self.worker is None or not self.worker.isRunning():
            return
        if QMessageBox.question(
            self, "停止任务", "确定要停止当前任务吗？已下载的文件会保留。"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.phase_label.setText("正在停止…")
        self.log_panel.append("warning", "已请求停止任务，等待当前操作安全退出……")
        self.worker.stop()

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.setRange(0, 0)
            return
        self.progress.setRange(0, total)
        self.progress.setValue(min(done, total))

    def _on_finished(self, stats: dict) -> None:
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.stats_label.setText(
            " | ".join(f"{k}：{v}" for k, v in stats.items() if k not in ("状态",))
        )
        self.phase_label.setText(str(stats.get("状态", "已完成")))

    def _on_failed(self, message: str) -> None:
        self.phase_label.setText("任务失败")
        QMessageBox.critical(
            self,
            "任务失败",
            f"任务执行过程中出现未处理的异常：\n{message}\n\n"
            "详细信息请查看右侧日志区，或导出日志后反馈。",
        )

    def _on_worker_finished(self) -> None:
        self._set_running(False)
        self.statusBar().showMessage("任务结束", 5000)
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.tabs.setEnabled(not running)

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _open_download_dir(self) -> None:
        target = str(self.config.get("root") or "").strip()
        path = Path(target) if target else DOWNLOADS_DIR
        self._open_path(path)

    def _open_path(self, path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "打开失败", f"{path}\n{exc}")

    def _on_about(self) -> None:
        dialog = AboutDialog(self)
        dialog.exec()

    def _reset_counters(self) -> None:
        """开始新任务前把计数栏清零。"""
        self._on_stats({})

    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 回调
        if self.worker is not None and self.worker.isRunning():
            if QMessageBox.question(
                self, "退出", "任务仍在运行，退出将中断任务。确定要退出吗？"
            ) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.stop()
            self.worker.wait(5000)
        if self.autosave.isChecked():
            try:
                self._collect_config()
                self.store.save(self.config)
            except Exception:  # noqa: BLE001
                pass
        event.accept()


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setStyleSheet("color: #e6e8eb; background: #e6e8eb; max-width: 1px;")
    return line


def _is_zero(value: str) -> bool:
    """判断形如 ``12/8`` / ``0`` / ``0/0`` 的计数是否全为 0。"""
    parts = [p.strip() for p in str(value).split("/")]
    return all(p in ("", "0") for p in parts)


def _split_links(text: str, mode: str = "detail") -> list[str]:
    """把用户输入拆分成待处理条目。

    - 所有模式都优先从每行里提取真实 URL（一行多链接会拆开），
      因此 ``#博主昵称`` 这类注释行、以及分享文案里的说明文字都会被正确忽略；
    - ``detail`` 模式只能处理含 19 位作品 ID 的链接，因此不再保留无链接的行；
    - 其它模式额外保留裸标识符（sec_user_id / 作品 ID），兼容直接填 ID 的场景。
    """
    result: list[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        urls = _URL_PATTERN.findall(line)
        if urls:
            result.extend(urls)
        elif mode != "detail" and _BARE_IDENTIFIER.match(line):
            result.append(line)
    # 去重且保持顺序
    return list(dict.fromkeys(result))
