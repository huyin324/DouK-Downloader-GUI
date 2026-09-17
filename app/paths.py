"""路径与运行环境定义。

本模块负责：
1. 解析 GUI 工程根目录与上游 DouK-Downloader 内核目录；
2. 把上游目录加入 sys.path，使 ``import src.xxx`` 可用（上游自身使用绝对导入）；
3. 提供 GUI 配置文件的落盘位置。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = [
    "APP_ROOT",
    "DATA_ROOT",
    "UPSTREAM_ROOT",
    "CONFIG_DIR",
    "CONFIG_FILE",
    "DOWNLOADS_DIR",
    "VOLUME_DIR",
    "RECORD_DB",
    "BACKUP_DIR",
    "IS_FROZEN",
    "ensure_upstream_on_path",
    "app_icon_path",
]

#: 是否运行在 PyInstaller 打包出的可执行文件中
IS_FROZEN: bool = bool(getattr(sys, "frozen", False))

# 只读的代码与资源根目录。
# 打包后为 PyInstaller 的临时解压目录 ``_MEIPASS``（程序退出即删除），
# 因此**任何需要持久化的文件都不能写在这里**。
APP_ROOT: Path = (
    Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)).resolve()
    if IS_FROZEN
    else Path(__file__).resolve().parent.parent
)

# 上游 DouK-Downloader 内核目录（只读资源）
UPSTREAM_ROOT: Path = APP_ROOT / "upstream"

# --------------------------------------------------------------------------- #
# 可写的数据根目录
# --------------------------------------------------------------------------- #
# 必须与内核自身的取值保持一致：``src/custom/internal.py`` 在冻结运行时
# 把 ROOT 定义为 ``Path(sys.executable).resolve().parent``，否则为仓库根目录。
# 若两者不一致，GUI 读写的下载记录数据库将与内核实际使用的不是同一个文件。


def _runtime_root() -> Path:
    """GUI 自身数据的可写根目录（配置、备份、默认下载目录）。"""
    if not IS_FROZEN:
        return APP_ROOT
    override = os.environ.get("DOUK_DATA_DIR", "").strip()
    if override:
        return Path(override)
    return Path(sys.executable).resolve().parent


def _kernel_root() -> Path:
    """内核数据根目录，必须与 ``src/custom/internal.py`` 的 ROOT 完全一致。

    - 源码运行：``upstream``（``internal.py`` 的上三级目录）
    - 冻结运行：exe 所在目录

    两者若不一致，GUI 读写的下载记录数据库会与内核实际使用的不是同一个文件。
    """
    if IS_FROZEN:
        return _runtime_root()
    return UPSTREAM_ROOT


DATA_ROOT: Path = _runtime_root()

# 内核数据根目录（settings.json / DouK-Downloader.db / Cache 都在这里）
KERNEL_ROOT: Path = _kernel_root()

# GUI 自身的配置文件目录
CONFIG_DIR: Path = DATA_ROOT / "config"
CONFIG_FILE: Path = CONFIG_DIR / "gui_settings.json"

# 默认下载根目录
DOWNLOADS_DIR: Path = DATA_ROOT / "Downloads"

# 内核数据目录
VOLUME_DIR: Path = KERNEL_ROOT / "Volume"

# 内核的下载记录数据库（download_data / mapping_data 两张表）
RECORD_DB: Path = VOLUME_DIR / "DouK-Downloader.db"

# 备份目录：改动数据库前先在此留一份
BACKUP_DIR: Path = (
    DATA_ROOT / "backup" if IS_FROZEN else APP_ROOT / ".workbuddy" / "backup"
)


def app_icon_path() -> Path | None:
    """返回可用的应用图标路径。

    优先使用项目根目录的 ``icon.svg``，其次回退到内核自带的图标资源。
    两者都不存在时返回 None（界面会使用系统默认图标）。
    """
    candidates = (
        APP_ROOT / "icon.svg",
        UPSTREAM_ROOT / "static" / "images" / "DouK-Downloader.png",
        UPSTREAM_ROOT / "static" / "images" / "DouK-Downloader.ico",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ensure_upstream_on_path() -> Path:
    """把上游目录加入 sys.path 并返回该目录。

    上游代码使用 ``from src.xxx import ...`` 形式的绝对导入，
    因此 ``upstream`` 目录必须作为顶层包搜索路径存在。
    """
    path = str(UPSTREAM_ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)
    return UPSTREAM_ROOT
