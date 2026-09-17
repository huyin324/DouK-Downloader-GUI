"""一条命令打包成单个 exe。

用法::

    .venv\\Scripts\\python.exe build_exe.py

产出：``dist/DouK-Downloader-GUI.exe``（单文件，双击即用，无需安装 Python）。

脚本会依次完成：
1. 清理 ``upstream`` 下的 ``__pycache__``（避免把 .pyc 当资源塞进包里）；
2. 调用 PyInstaller（配置见 ``build.spec``）；
3. 把内核数据目录（含下载记录数据库与 settings.json）复制到 exe 所在目录，
   这样打包版能直接沿用已有的下载记录；
4. 提示自检方式。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
EXE_NAME = "DouK-Downloader-GUI.exe"


def step(message: str) -> None:
    print(f"\n=== {message} ===")


def clean_pycache() -> None:
    step("清理 __pycache__")
    removed = 0
    for directory in list((ROOT / "upstream").rglob("__pycache__")) + list(
        (ROOT / "app").rglob("__pycache__")
    ):
        shutil.rmtree(directory, ignore_errors=True)
        removed += 1
    print(f"已清理 {removed} 个 __pycache__ 目录")


def run_pyinstaller() -> None:
    step("PyInstaller 打包（约 1~3 分钟）")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "build.spec",
        "--noconfirm",
        "--distpath",
        str(DIST),
        "--workpath",
        str(ROOT / "build" / "pyinstaller"),
    ]
    result = subprocess.run(command, cwd=str(ROOT), check=False)
    if result.returncode != 0:
        raise SystemExit(f"打包失败，退出码 {result.returncode}")


def seed_volume() -> None:
    """把内核数据目录复制到 exe 同目录（已有则不覆盖）。"""
    step("准备内核数据目录")
    source = ROOT / "upstream" / "Volume"
    target = DIST / "Volume"
    if not source.is_dir():
        print("未找到 upstream/Volume，跳过（首次运行会自动创建）")
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name == "Cache":
            continue
        destination = target / item.name
        if destination.exists():
            print(f"  已存在，跳过：{item.name}")
            continue
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
        print(f"  已复制：{item.name}")


def seed_config() -> None:
    """把当前界面配置（含 Cookie）带到 exe 同目录，免得打包版重新填一遍。"""
    step("准备界面配置")
    source = ROOT / "config" / "gui_settings.json"
    if not source.is_file():
        print("未找到 config/gui_settings.json，跳过（首次运行会自动创建）")
        return
    destination = DIST / "config" / source.name
    if destination.exists():
        print("  已存在，跳过：gui_settings.json")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    print("  已复制：gui_settings.json（含 Cookie 等凭据，请勿外发 dist 目录）")


def report() -> None:
    exe = DIST / EXE_NAME
    step("完成")
    if not exe.is_file():
        raise SystemExit("未找到生成的 exe")
    size_mb = exe.stat().st_size / 1024 / 1024
    print(f"可执行文件：{exe}")
    print(f"体积：{size_mb:.1f} MB")
    print()
    print("自检（验证内核与依赖是否完整）：")
    print(f"    cd dist && {EXE_NAME} --selftest")
    print("    报告会写入 dist/selftest_report.txt")
    print()
    print("说明：配置、下载记录、数据库都会写在 exe 所在目录，")
    print("      把整个 dist 目录复制到任意位置（或移动 exe）即可换机使用。")


def main() -> int:
    clean_pycache()
    run_pyinstaller()
    seed_volume()
    seed_config()
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
