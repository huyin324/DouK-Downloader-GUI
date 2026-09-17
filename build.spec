# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：把 GUI + 内核打包成单个 exe。

用法::

    .venv\\Scripts\\python.exe -m PyInstaller build.spec --noconfirm

产出：``dist/DouK-Downloader-GUI.exe``（单文件，无需安装 Python）。

说明：
- 内核源码 ``upstream/src`` 以**数据文件**形式打进包内（不是作为模块编译），
  运行时由 ``app.paths.ensure_upstream_on_path()`` 把 ``upstream`` 加入 sys.path
  后再 ``import src.xxx``，因此内核源码保持零改动。
- 需要持久化的文件（配置、数据库、下载目录）**不会**写在临时解压目录，
  而是写在 exe 所在目录（与内核 ``internal.ROOT`` 的取值一致）。
"""

from pathlib import Path

ROOT = Path(SPECPATH)

# ---------- 需要一起打包的非代码资源 ---------- #
datas = [
    # 内核源码与资源
    (str(ROOT / "upstream" / "src"), "upstream/src"),
    (str(ROOT / "upstream" / "locale"), "upstream/locale"),
    (str(ROOT / "upstream" / "static" / "images"), "upstream/static/images"),
    # GUI 资源
    (str(ROOT / "app" / "assets"), "app/assets"),
]

# 图标与收款码（缺失时自动跳过，不影响打包）
for name in ("icon.svg", "微信收款码.JPG", "支付宝收款码.JPG"):
    candidate = ROOT / name
    if candidate.is_file():
        datas.append((str(candidate), "."))

hiddenimports = [
    # PyQt6：SVG 图标（app/assets/check.svg、窗口图标）需要 SVG 图像插件
    "PyQt6.QtSvg",
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    # 内核用到的三方库（部分为动态导入，静态分析扫不到）
    "curl_cffi",
    "curl_cffi.requests",
    "emoji",
    "lxml",
    "lxml.etree",
    "openpyxl",
    "pydantic",
    "pydantic.deprecated.decorator",
    "pyperclip",
    "rich",
    "aiofiles",
    "aiosqlite",
    # 内核源码是以数据文件形式打包的，PyInstaller 分析不到它的导入，
    # 因此下面这些必须显式声明（src/application/__init__.py -> TikTokDownloader
    # -> main_server 会静态导入 fastapi / uvicorn，缺了启动任务就报错）
    "fastapi",
    "uvicorn",
    "uvicorn.protocols.http",
    "uvicorn.lifespan.on",
    "starlette",
    "starlette.responses",
    "anyio",
    "pydantic",
    "pydantic.deprecated.decorator",
]

# 内核在模块导入期不会被静态分析覆盖的部分，按需整体收集
try:  # pragma: no cover - 依赖安装情况不同
    from PyInstaller.utils.hooks import collect_all

    for _pkg in ("curl_cffi",):
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        hiddenimports += _h
except Exception:  # pragma: no cover
    pass

excludes = [
    # 用不到的重型依赖，减小体积
    "tkinter",
    "unittest",
    "pydoc",
    "doctest",
    "IPython",
    "notebook",
    "pytest",
    "PIL",
    "matplotlib",
    "scipy",
]
# 注意：不能排除 fastapi / uvicorn / starlette。
# ``src/application/__init__.py`` -> TikTokDownloader -> main_server 会静态导入它们，
# 而引擎是通过 ``from src.application.main_terminal import TikTok`` 进入的，
# 排除后打包版一启动任务就会 ModuleNotFoundError。

block_cipher = None

a = Analysis(
    [str(ROOT / "run.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DouK-Downloader-GUI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 图形界面，不弹控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # 需要 ico 图标时可改为 "icon.ico"
)
