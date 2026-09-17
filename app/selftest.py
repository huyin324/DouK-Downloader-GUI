"""打包后的自检。

单文件 exe 无法像源码那样方便地排查问题，因此内置一个自检模式::

    DouK-Downloader-GUI.exe --selftest

它会把结果写到 exe 所在目录的 ``selftest_report.txt``，并返回 0 / 1 作为退出码。
覆盖打包场景最容易出问题的几处：内核源码是否随包、可写目录是否可用、
``curl_cffi`` 等二进制依赖是否完整、Qt 的 SVG 插件是否可用。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

__all__ = ["run_selftest"]

REPORT_NAME = "selftest_report.txt"


def run_selftest(report_path: str | os.PathLike[str] | None = None) -> int:
    """执行自检，返回 0 表示全部通过。"""
    lines: list[str] = []
    failures = 0

    def check(name: str, action: Callable[[], str]) -> None:
        nonlocal failures
        try:
            detail = action()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            lines.append(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        else:
            lines.append(f"[ OK ] {name}: {detail}")

    from .paths import (
        APP_ROOT,
        DATA_ROOT,
        IS_FROZEN,
        RECORD_DB,
        UPSTREAM_ROOT,
        VOLUME_DIR,
        app_icon_path,
    )

    lines.append("DouK-Downloader GUI 自检报告")
    lines.append(f"时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append(f"可执行文件：{Path(sys.executable).resolve()}")
    lines.append(f"冻结运行：{IS_FROZEN}   临时资源目录：{APP_ROOT}")
    lines.append(f"数据目录（可写）：{DATA_ROOT}")
    lines.append("")

    # 1. 内核源码是否随包
    def _kernel_source() -> str:
        src_dir = UPSTREAM_ROOT / "src"
        if not src_dir.is_dir():
            raise FileNotFoundError(f"缺少内核源码目录：{src_dir}")
        count = len(list(src_dir.rglob("*.py")))
        return f"{src_dir}（{count} 个 .py 文件）"

    check("内核源码随包", _kernel_source)

    # 2. 可写目录（下载记录数据库必须能持久化）
    def _writable() -> str:
        VOLUME_DIR.mkdir(parents=True, exist_ok=True)
        probe = VOLUME_DIR / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return f"{VOLUME_DIR} 可写（数据库：{RECORD_DB.name}）"

    check("数据目录可写", _writable)

    # 3. 内核常量导入（会触发 src.custom.internal，同时创建 Volume）
    def _kernel_import() -> str:
        from src.custom.internal import __VERSION__, PROJECT_NAME

        return f"{PROJECT_NAME}（内部版本 {__VERSION__}）"

    check("内核模块导入", _kernel_import)

    # 4. 二进制依赖 curl_cffi（打包最容易丢失 .pyd / DLL）
    def _curl_cffi() -> str:
        from curl_cffi import requests

        session = requests.Session(impersonate="chrome")
        session.close()
        import curl_cffi

        return f"curl-cffi {curl_cffi.__version__} 可用"

    check("curl_cffi 可用", _curl_cffi)

    # 5. 内核核心依赖
    for module_name in ("aiofiles", "aiosqlite", "emoji", "lxml", "openpyxl",
                        "pyperclip", "rich"):
        check(
            f"依赖 {module_name}",
            lambda _name=module_name: f"{__import__(_name).__name__} 已加载",
        )

    # 6. 下载管理器（会导入 src/downloader/download 与 Database）
    def _manager() -> str:
        from src.downloader.download import Downloader
        from src.manager import Database

        return f"{Database.__name__} / {Downloader.__name__} 已加载"

    check("内核下载与数据库模块", _manager)

    # 7. 引擎真正进入内核的入口（打包时最容易漏依赖的一环）
    #    src/application/__init__.py -> TikTokDownloader -> main_server -> fastapi
    def _entry() -> str:
        from src.application.main_terminal import TikTok

        return f"{TikTok.__name__} 已加载（含 Web API 依赖链）"

    check("内核主程序入口", _entry)

    # 8. 按引擎的方式真正初始化一次内核（Settings -> Database -> Parameter -> TikTok）
    def _kernel_init() -> str:
        import asyncio

        from PyQt6.QtCore import QObject, pyqtSignal

        from .logbridge import QtConsole

        class _Bus(QObject):
            message = pyqtSignal(str, str)
            phase = pyqtSignal(str)
            progress = pyqtSignal(int, int)

        bus = _Bus()
        bus.message.connect(lambda *_: None)
        console = QtConsole.build(bus)

        from src.application.main_terminal import TikTok
        from src.config import Parameter, Settings
        from src.custom import VOLUME
        from src.manager import Database, DownloadRecorder
        from src.module import Cookie
        from src.record import BaseLogger

        async def _build() -> str:
            settings = Settings(VOLUME, console)
            database = Database()
            await database.__aenter__()
            try:
                recorder = DownloadRecorder(database, True, console)
                parameter = Parameter(
                    settings,
                    Cookie(settings, console),
                    logger=BaseLogger,
                    console=console,
                    **settings.read(),
                    recorder=recorder,
                )
                TikTok(parameter, database, server_mode=True)
            finally:
                await database.__aexit__(None, None, None)
            return f"内核初始化成功（{TikTok.__name__}，数据目录 {VOLUME}）"

        return asyncio.run(_build())

    check("内核初始化", _kernel_init)

    # 9. 下载记录数据库可读（验证 sqlite 与持久化目录一致）
    def _records() -> str:
        import sqlite3

        if not RECORD_DB.is_file():
            return "数据库尚未创建（首次运行会自动建立）"
        connection = sqlite3.connect(f"file:{RECORD_DB}?mode=ro", uri=True)
        try:
            count = connection.execute("SELECT count(*) FROM download_data").fetchone()[0]
        finally:
            connection.close()
        return f"{RECORD_DB.name}：{count} 条下载记录"

    check("下载记录数据库", _records)

    # 10. 可选：真实网络请求（验证证书库与 TLS 在包内可用）
    if "--network" in sys.argv[1:]:

        def _network() -> str:
            from curl_cffi import requests

            response = requests.get(
                "https://www.baidu.com", timeout=15, impersonate="chrome"
            )
            return f"HTTPS 请求成功：HTTP {response.status_code}"

        check("网络请求（curl_cffi + 证书库）", _network)

    # 7. Qt 与 SVG 资源
    def _qt() -> str:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([sys.argv[0]])
        icon_path = app_icon_path()
        if icon_path is None:
            raise FileNotFoundError("未找到窗口图标资源")
        icon = QIcon(str(icon_path))
        if icon.isNull():
            raise ValueError(f"图标无法解析（缺少 SVG 插件？）：{icon_path}")
        from .theme import CHECK_ICON

        if not Path(CHECK_ICON).is_file():
            raise FileNotFoundError(f"缺少勾选图标资源：{CHECK_ICON}")
        return f"Qt 启动正常，SVG 资源可用（{Path(icon_path).name} / check.svg）"

    check("Qt 与 SVG 资源", _qt)

    # 8. 主窗口构建（离屏渲染，验证 QSS 与全部控件）
    def _window() -> str:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        from .fonts import ensure_cjk_font
        from .main_window import MainWindow
        from .theme import build_qss

        app = QApplication.instance() or QApplication([sys.argv[0]])
        app.setStyle("Fusion")
        ensure_cjk_font(app)
        app.setStyleSheet(build_qss(False))
        window = MainWindow()
        platform_count = len(window.panels)
        window.autosave.setChecked(False)
        window.close()
        return f"主窗口构建成功（{platform_count} 个平台分页）"

    check("主窗口构建", _window)

    lines.append("")
    lines.append(f"结果：{'全部通过' if not failures else f'{failures} 项失败'}")
    text = "\n".join(lines) + "\n"

    target = Path(report_path) if report_path else Path(sys.executable).resolve().parent / REPORT_NAME
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text, end="")
    return 0 if not failures else 1
