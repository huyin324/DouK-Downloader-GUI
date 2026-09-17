"""上游「昵称 / 标记变更」改名机制探针。

用**真实**的 ``src.manager.Database`` + ``src.manager.Cache``（aiosqlite 真库、
真表结构）复现四种场景，确认历史文件夹与作品文件名到底会怎么变。

只依赖内核模块，不联网、不下载任何文件。

用法::

    .venv\\Scripts\\python.exe tests\\cache_rename_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(_ROOT), str(_ROOT / "upstream")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")


class StubConsole:
    """替身控制台：input 返回真值哨兵，与 GUI 下的 QtConsole 行为一致。"""

    def __init__(self) -> None:
        self.inputs: list[str] = []

    def print(self, *args, **kwargs) -> None:
        pass

    info = warning = error = debug = print

    def input(self, prompt="", *args, **kwargs) -> str:
        self.inputs.append(str(prompt))
        return "skip"


class StubLogger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, text: str, output: bool = True, **kwargs) -> None:
        self.lines.append(str(text))

    warning = error = debug = info


def make_parameter(root: Path, console, logger) -> SimpleNamespace:
    return SimpleNamespace(root=root, console=console, logger=logger)


WORK_FILES = (
    "2026-01-01 10.00.00-视频-旧昵称-作品甲.mp4",
    "2026-01-02 11.00.00-图集-旧昵称-作品乙_1.jpeg",
    "2026-01-02 11.00.00-图集-旧昵称-作品乙_2.jpeg",
)


def seed_account_folder(root: Path, folder: str) -> Path:
    path = root / folder
    path.mkdir(parents=True, exist_ok=True)
    for name in WORK_FILES:
        (path / name).write_bytes(b"x")
    return path


def listing(root: Path) -> tuple[list[str], list[str]]:
    """返回 (文件夹名列表, 全部文件名列表)。"""
    folders = sorted(p.name for p in root.iterdir() if p.is_dir())
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(path.name)
    return folders, files


def tree(root: Path) -> dict[str, list[str]]:
    """返回 {文件夹名: [子项名...]}，用于在临时目录销毁前快照目录结构。"""
    result: dict[str, list[str]] = {}
    for path in sorted(root.iterdir()):
        if path.is_dir():
            result[path.name] = sorted(child.name for child in path.iterdir())
    return result


async def scenario(
    label: str,
    *,
    solo_mode: bool,
    cache_mark: bool,
    cache_name: bool,
    old_name: str,
    old_mark: str,
    new_name: str,
    new_mark: str,
    folder_template: str = "UID123_{who}_发布作品",
    apply_fix: bool = False,
    restore: bool = False,
) -> dict:
    """跑一次 update_cache，返回现场信息。"""
    from src.manager import Cache, Database

    if restore:
        from app.upstream_fixes import uninstall

        uninstall()
    if apply_fix:
        from app.upstream_fixes import install

        install({"fix_cache_rename": True, "rename_account_folder": True})

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        root = tmp_path / "downloads"
        root.mkdir()

        console, logger = StubConsole(), StubLogger()

        database = Database()
        database.file = tmp_path / "probe.db"
        await database.__aenter__()
        try:
            # 造出「上次运行」留下的现场：文件夹用旧值命名，mapping_data 记录旧值
            who = old_mark or old_name
            folder = folder_template.format(who=who)
            if solo_mode:
                work_dir = root / folder / "旧昵称-作品甲"
                work_dir.mkdir(parents=True, exist_ok=True)
                for name in WORK_FILES[:1]:
                    (work_dir / name).write_bytes(b"x")
                (root / folder / ("图集-旧昵称-作品乙")).mkdir(exist_ok=True)
                for name in WORK_FILES[1:]:
                    (root / folder / "图集-旧昵称-作品乙" / name).write_bytes(b"x")
            else:
                seed_account_folder(root, folder)

            await database.update_mapping_data("123", old_name, old_mark)

            cache = Cache(
                make_parameter(root, console, logger),
                database,
                cache_mark,
                cache_name,
            )

            before_folders, before_files = listing(root)
            error = ""
            try:
                await cache.update_cache(
                    solo_mode, "UID", "发布作品", "123", new_name, new_mark
                )
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"

            after_folders, after_files = listing(root)
            row = await database.read_mapping_data("123")
            return {
                "label": label,
                "error": error,
                "root": root,
                "tree": tree(root),
                "before_folders": before_folders,
                "after_folders": after_folders,
                "before_files": before_files,
                "after_files": after_files,
                "mapping": dict(row) if row else {},
                "console_inputs": console.inputs,
                "logger": logger.lines,
            }
        finally:
            await database.close()


def report(result: dict) -> None:
    print(f"\n--- {result['label']} ---")
    if result["error"]:
        print(f"  异常：{result['error']}")
    print(f"  改名前后文件夹：{result['before_folders']} -> {result['after_folders']}")
    new_files = [f for f in result["after_files"] if "新昵称" in f]
    old_files = [f for f in result["after_files"] if "旧昵称" in f]
    print(f"  文件名含「新昵称」：{len(new_files)} 个 / 仍含「旧昵称」：{len(old_files)} 个")
    if result["tree"]:
        print(f"  目录结构：{result['tree']}")
    print(f"  mapping_data 现有记录：{result['mapping']}")
    if result["console_inputs"]:
        print(f"  触发了 {len(result['console_inputs'])} 次交互式询问（GUI 下自动跳过）")


async def main() -> int:
    print("=" * 72)
    print("上游「昵称 / 标记变更」改名机制探针")
    print("=" * 72)

    # 场景 1：默认配置（name_format 含 nickname），仅昵称变化，mark 为空，平铺模式
    r1 = await scenario(
        "场景1 仅昵称变化（mark 为空、平铺模式、name_format 含 nickname）",
        solo_mode=False, cache_mark=False, cache_name=True,
        old_name="旧昵称", old_mark="", new_name="新昵称", new_mark="",
    )
    report(r1)
    check("场景1 复现上游缺陷（抛 FileNotFoundError，账号处理被中断）",
          "FileNotFoundError" in r1["error"], r1["error"] or "未复现")
    check("场景1 异常导致文件一个都没改成名",
          not [f for f in r1["after_files"] if "新昵称" in f], str(r1["after_files"]))
    check("场景1 异常也导致 mapping_data 未更新",
          r1["mapping"].get("NAME") == "旧昵称", str(r1["mapping"]))

    # 场景 2：仅昵称变化，但 name_format 不含 nickname
    r2 = await scenario(
        "场景2 仅昵称变化（name_format 不含 nickname）",
        solo_mode=False, cache_mark=False, cache_name=False,
        old_name="旧昵称", old_mark="", new_name="新昵称", new_mark="",
    )
    report(r2)
    check("场景2 未抛异常", not r2["error"], r2["error"])
    check("场景2 完全不改名（未启用昵称缓存改名）",
          r2["before_files"] == r2["after_files"])
    check("场景2 仍会更新 mapping_data",
          r2["mapping"].get("NAME") == "新昵称", str(r2["mapping"]))

    # 场景 3：mark 从空变为 ABC（name_format 含 mark）
    r3 = await scenario(
        "场景3 mark 由空变为 ABC（name_format 含 nickname + mark）",
        solo_mode=False, cache_mark=True, cache_name=True,
        old_name="旧昵称", old_mark="", new_name="旧昵称", new_mark="ABC",
    )
    report(r3)
    check("场景3 未抛异常", not r3["error"], r3["error"])
    check("场景3 文件夹已按 mark 改名",
          r3["after_folders"] == ["UID123_ABC_发布作品"], str(r3["after_folders"]))

    # 场景 4：folder_mode=True（每个作品一个子文件夹），仅昵称变化
    r4 = await scenario(
        "场景4 仅昵称变化（folder_mode=True，作品独立子文件夹）",
        solo_mode=True, cache_mark=False, cache_name=True,
        old_name="旧昵称", old_mark="", new_name="新昵称", new_mark="",
    )
    report(r4)
    check("场景4 同样复现缺陷（folder_mode=True 亦然）",
          "FileNotFoundError" in r4["error"], r4["error"] or "未复现")

    # ---------------- 打补丁后的对照 ---------------- #
    print("\n" + "-" * 72)
    print("以下为启用本项目运行时修复后的结果")
    print("-" * 72)

    r5 = await scenario(
        "场景5 仅昵称变化（已启用修复）",
        solo_mode=False, cache_mark=False, cache_name=True,
        old_name="旧昵称", old_mark="", new_name="新昵称", new_mark="",
        apply_fix=True,
    )
    report(r5)
    check("场景5 不再抛异常", not r5["error"], r5["error"])
    check("场景5 文件夹已按新昵称重命名",
          r5["after_folders"] == ["UID123_新昵称_发布作品"], str(r5["after_folders"]))
    renamed = [f for f in r5["after_files"] if "新昵称" in f]
    check("场景5 全部 3 个作品文件名都已替换为新昵称",
          len(renamed) == 3, f"{len(renamed)}/3")
    check("场景5 没有残留旧昵称的文件",
          not [f for f in r5["after_files"] if "旧昵称" in f],
          str(r5["after_files"]))
    check("场景5 mapping_data 已更新",
          r5["mapping"].get("NAME") == "新昵称", str(r5["mapping"]))
    check("场景5 未出现重复目录", len(r5["after_folders"]) == 1, str(r5["after_folders"]))

    r6 = await scenario(
        "场景6 仅昵称变化 + folder_mode=True（已启用修复）",
        solo_mode=True, cache_mark=False, cache_name=True,
        old_name="旧昵称", old_mark="", new_name="新昵称", new_mark="",
        apply_fix=True,
    )
    report(r6)
    check("场景6 不再抛异常", not r6["error"], r6["error"])
    check("场景6 文件夹已按新昵称重命名",
          r6["after_folders"] == ["UID123_新昵称_发布作品"], str(r6["after_folders"]))
    subfolders = sorted(
        name for children in r6["tree"].values() for name in children
    )
    check("场景6 作品子文件夹也完成改名",
          len(subfolders) == 2 and all("新昵称" in s for s in subfolders),
          str(r6["tree"]))

    r7 = await scenario(
        "场景7 卸载修复后行为回到upstream原始状态",
        solo_mode=False, cache_mark=False, cache_name=True,
        old_name="旧昵称", old_mark="", new_name="新昵称", new_mark="",
        restore=True,
    )
    report(r7)
    check("场景7 卸载修复后重新复现上游异常", bool(r7["error"]), r7["error"] or "未复现")

    print("\n" + "=" * 72)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  - {item}")
    print("=" * 72)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
