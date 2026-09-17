"""对上游缺陷的运行时修复（不修改 upstream 源码）。

════════════════════════════════════════════════════════════════════════
缺陷：博主改昵称后，历史文件夹与作品文件名的改名逻辑失效
════════════════════════════════════════════════════════════════════════

上游 ``src/manager/cache.py::Cache`` 负责「昵称 / 标记变更后重命名历史文件」，
但在默认配置下不可用，实测（见 ``tests/cache_rename_test.py``）会直接抛异常：

    FileNotFoundError: [WinError 3] 系统找不到指定的路径:  ...\\UID123__发布作品

根因有两处：

1. ``__scan_file()`` 定位目录时用的是
   ``f"{prefix}{id_}_{mark}_{suffix}"``（原样使用 mark），
   而 ``__check_file()`` 判断目录存在用的是
   ``f"{prefix}{id_}_{data['mark'] or data['name']}_{suffix}"``（mark 为空时回退昵称）。
   两者不一致 —— mark 为空（默认值）时，前者会算出
   ``UID123__发布作品``（双下划线）这种不存在的路径，``iterdir()`` 直接抛
   ``FileNotFoundError``，异常向上传播并**中断该账号的整个处理流程**。

2. ``__batch_rename()`` 用 ``break`` 而不是 ``continue`` 跳过不匹配的文件。
   由于 ``iterdir()`` 的返回顺序不确定，只要第一个文件不含旧值，
   后面的文件就全都不会被改名。

另外附带两点改进：

3. 旧值为空字符串时，``str.replace("", new, 1)`` 会把新值**插到文件名最前面**，
   因此必须在旧值为空时跳过文件改名。

4. 昵称变化时上游**只改文件名、不改文件夹名**。而下载阶段
   ``Downloader.storage_folder()`` 会按新昵称 ``mkdir``，
   于是同一个账号会分裂出「旧昵称文件夹（内含已按新昵称改名的文件）」
   和「新昵称空文件夹」两份目录。本模块可在昵称变化时同步重命名账号文件夹，
   避免目录重复（可用 ``rename_account_folder`` 开关关闭）。

════════════════════════════════════════════════════════════════════════

所有修复都是运行时的、可关闭的；关闭后完全回到上游原始行为。
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["install", "uninstall", "resolve_account_folder", "describe"]

#: 首次安装时保存的上游原始方法，供 uninstall() 完整还原
_ORIGINALS: dict[str, Any] = {}

_PATCHED_NAMES = (
    "_Cache__check_file",
    "_Cache__scan_file",
    "_Cache__batch_rename",
)


def _row(data: Any, key: str) -> str:
    """从 mapping_data 的行对象里取值（兼容大小写与缺失）。"""
    for candidate in (key, key.upper(), key.lower()):
        try:
            value = data[candidate]
        except (KeyError, IndexError, TypeError):
            continue
        if value is not None:
            return str(value)
    return ""


def _folder_name(prefix: str, id_: str, who: str, suffix: str) -> str:
    return f"{prefix}{id_}_{who}_{suffix}"


def resolve_account_folder(
    root: Any,
    prefix: str,
    suffix: str,
    id_: str,
    mark: str,
    name: str,
) -> Any | None:
    """按优先级定位已存在的账号 / 合集文件夹。

    依次尝试：
        1. ``{prefix}{id}_{mark}_{suffix}`` —— 标记变化后已改名成的目标目录；
        2. ``{prefix}{id}_{name}_{suffix}`` —— 未改名时的原目录；
        3. 以上都不存在时，在本级目录里模糊匹配 ``{prefix}{id}_*_{suffix}``，
           兼容历史上因昵称提取失败而生成的各种异常目录名。
    """
    candidates = [
        _folder_name(prefix, id_, mark, suffix) if mark else "",
        _folder_name(prefix, id_, name, suffix),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = root.joinpath(candidate)
        if path.is_dir():
            return path

    # 兜底：模糊匹配本账号的目录（按修改时间取最新）
    try:
        pattern = f"{prefix}{id_}_*_{suffix}"
        matches = sorted(
            (p for p in root.glob(pattern) if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]
    except Exception:  # noqa: BLE001
        pass
    return None


def install(config: dict, notify: Callable[[str], None] | None = None) -> list[str]:
    """安装缓存改名相关的运行时修复，返回已应用项说明。"""
    if not config.get("fix_cache_rename", True):
        return ["缓存改名修复：未启用（沿用上游原始行为）"]

    from src.manager import Cache

    rename_account_folder = bool(config.get("rename_account_folder", True))
    applied: list[str] = []

    def _log(text: str) -> None:
        if notify is not None:
            notify(text)

    # ------------------------------------------------------------------ #
    def check_file(
        self: Any,
        solo_mode: bool,
        prefix: str,
        suffix: str,
        id_: str,
        name: str,
        mark: str,
        data: Any,
    ) -> None:
        """替换 ``Cache.__check_file``：修正目录定位，并可选同步重命名账号文件夹。"""
        old_name = _row(data, "name")
        old_mark = _row(data, "mark")

        folder = self.root.joinpath(_folder_name(prefix, id_, old_mark or old_name, suffix))
        if not folder.is_dir():
            self.log.info(f"{folder} 文件夹不存在，自动跳过", False)
            return

        # ---- 标记（mark）变化：目录名以 mark 为准 ---- #
        if old_mark != mark:
            target_name = _folder_name(prefix, id_, mark or name, suffix)
            target = self.root.joinpath(target_name)
            if target != folder and not target.exists():
                _rename(self, folder, target, "文件夹")
            if target.is_dir():
                folder = target
            if self.mark:
                scan_file(self, solo_mode, prefix, suffix, id_, name, mark, data, key="mark")

        # ---- 昵称变化：可选同步重命名账号文件夹，避免目录重复 ---- #
        if old_name != name and self.name:
            if rename_account_folder and not mark:
                target = self.root.joinpath(_folder_name(prefix, id_, name, suffix))
                if not target.exists() and folder.is_dir():
                    _rename(self, folder, target, "文件夹")
                    if target.is_dir():
                        _log(f"[改名] 账号文件夹已按新昵称更新：{folder.name} → {target.name}")
                        folder = target
            scan_file(self, solo_mode, prefix, suffix, id_, name, mark, data, key="name")

    # ------------------------------------------------------------------ #
    def scan_file(
        self: Any,
        solo_mode: bool,
        prefix: str,
        suffix: str,
        id_: str,
        name: str,
        mark: str,
        data: Any,
        key: str = "name",
    ) -> None:
        """替换 ``Cache.__scan_file``：安全定位目录 + 先物化列表再改名。"""
        root = resolve_account_folder(
            self.root, prefix, suffix, id_, mark, _row(data, key)
        ) or resolve_account_folder(
            self.root, prefix, suffix, id_, mark, _row(data, "name")
        )
        if root is None:
            self.log.info(
                f"{_folder_name(prefix, id_, mark or _row(data, 'name'), suffix)} "
                f"文件夹不存在，跳过文件改名",
                False,
            )
            return

        items = list(root.iterdir())  # 先物化，避免边改名边迭代同一目录
        if solo_mode:
            for item in items:
                if not item.is_dir():
                    continue
                renamed = self._Cache__rename_works_folder(item, mark, name, key, data)
                batch_rename(
                    self, renamed, list(renamed.iterdir()), mark, name, key, data
                )
        else:
            batch_rename(self, root, items, mark, name, key, data)

    # ------------------------------------------------------------------ #
    def batch_rename(
        self: Any,
        root: Any,
        files: list,
        mark: str,
        name: str,
        key: str,
        data: Any,
    ) -> None:
        """替换 ``Cache.__batch_rename``：用 continue 替代 break，并跳过空旧值。"""
        old_value = _row(data, key)
        if not old_value:
            # 旧值为空时 replace("", new, 1) 会把新值插到文件名最前面，必须跳过
            return
        for old_file in files:
            if not getattr(old_file, "is_file", lambda: False)():
                continue
            if old_value not in old_file.name:
                continue
            self._Cache__rename_file(root, old_file, old_value, mark, name, key)

    # ------------------------------------------------------------------ #
    def _rename(cache: Any, old_: Any, new_: Any, type_: str) -> None:
        """调用上游的 rename（自带占用重试与交互规避），返回前不依赖其返回值。"""
        try:
            cache._Cache__rename(old_, new_, type_)
        except Exception as exc:  # noqa: BLE001
            _log(f"[改名] {type_} {old_} → {new_} 失败：{exc!r}")

    # 首次安装前记录上游原始实现，保证 uninstall() 能完整还原
    for name in _PATCHED_NAMES:
        if name not in _ORIGINALS:
            _ORIGINALS[name] = getattr(Cache, name, None)

    Cache._Cache__check_file = check_file
    Cache._Cache__scan_file = scan_file
    Cache._Cache__batch_rename = batch_rename

    applied.append("缓存改名修复：已修正目录定位（消除 FileNotFoundError）")
    applied.append("缓存改名修复：文件改名改为遍历全部匹配项，不再因目录顺序中断")
    if rename_account_folder:
        applied.append("缓存改名修复：昵称变化时同步重命名账号文件夹（可关闭）")
    return applied


def uninstall() -> bool:
    """还原上游原始实现（主要用于自测中对照验证，运行时一般不需要调用）。"""
    from src.manager import Cache

    if not _ORIGINALS:
        return False
    for name, func in _ORIGINALS.items():
        if func is None:
            continue
        setattr(Cache, name, func)
    return True


def describe(lines: list[str]) -> list[str]:
    header = "上游缺陷运行时修复："
    return [header, *[f"  · {line}" for line in lines]]
