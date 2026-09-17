"""DouK-Downloader GUI 启动入口。

    用法::

    python run.py              # 启动图形界面
    python run.py --selftest   # 自检（结果写入 selftest_report.txt）

依赖：PyQt6 以及 ``requirements.txt`` 中列出的全部内核依赖。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证 ``import app.xxx`` 可用（不依赖当前工作目录）
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.paths import ensure_upstream_on_path  # noqa: E402

ensure_upstream_on_path()

if "--selftest" in sys.argv[1:]:
    from app.selftest import run_selftest

    raise SystemExit(run_selftest())


def main() -> int:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    from app.fonts import ensure_cjk_font
    from app.main_window import MainWindow
    from app.paths import app_icon_path
    from app.theme import build_qss

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = QApplication(sys.argv)
    application.setApplicationName("DouK-Downloader GUI")
    application.setOrganizationName("DouK-Downloader GUI")
    application.setStyle("Fusion")

    icon_path = app_icon_path()
    if icon_path is not None:
        application.setWindowIcon(QIcon(str(icon_path)))

    ensure_cjk_font(application)
    application.setStyleSheet(build_qss(False))

    window = MainWindow()
    if icon_path is not None:
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
