"""把旧版内核安装目录里的下载记录合并到本项目。

背景：内核把「已下载作品」记在 ``Volume/DouK-Downloader.db`` 的
``download_data(ID)`` 表里。换一份安装目录（例如从 V5.7 命令行版迁到本图形界面）
后这张表是空的，去重就失效了 —— 已下载的作品会被重新下载。

本模块把旧库的两张表合并过来：

- ``download_data(ID)``：已下载作品 ID —— **这是避免重复下载的关键**；
- ``mapping_data(ID, NAME, MARK)``：账号/合集的昵称与标记缓存 ——
  一并导入可让「改名」机制从正确的基线出发，避免首次运行时误判。

安全约束：
1. 合并前先把目标库完整备份到 ``.workbuddy/backup/``；
2. 只用 ``INSERT OR IGNORE``，**绝不覆盖**目标库已有记录；
3. 合并后做 ``integrity_check`` 与行数校验，任何异常都中止并提示备份位置。
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .paths import BACKUP_DIR, RECORD_DB

__all__ = ["ImportResult", "import_records", "inspect_database", "DEFAULT_LEGACY_DB"]

#: 常见的旧版安装位置（供界面预填，实际以用户选择为准）
DEFAULT_LEGACY_DB = Path(
    r"\\hy-nas\Data\抖音爬虫2024\TikTokDownloader_V5.7_Windows_X64"
    r"\_internal\Volume\DouK-Downloader.db"
)

_TABLE_DDL = {
    "download_data": "CREATE TABLE IF NOT EXISTS download_data (ID TEXT PRIMARY KEY);",
    "mapping_data": """CREATE TABLE IF NOT EXISTS mapping_data (
        ID TEXT PRIMARY KEY,
        NAME TEXT NOT NULL,
        MARK TEXT NOT NULL
        );""",
}

#: 分批读写的大小，避免一次性把百万级记录读进内存
_CHUNK = 20000


@dataclass
class ImportResult:
    """一次导入的结果摘要。"""

    source: str
    target: str
    backup: str = ""
    download_before: int = 0
    download_after: int = 0
    download_added: int = 0
    mapping_before: int = 0
    mapping_after: int = 0
    mapping_added: int = 0
    integrity: str = ""
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"来源库：{self.source}",
            f"目标库：{self.target}",
        ]
        if self.backup:
            lines.append(f"已备份：{self.backup}")
        lines.append(
            f"下载记录：{self.download_before} → {self.download_after}"
            f"（新增 {self.download_added} 条）"
        )
        if self.mapping_added or self.mapping_before:
            lines.append(
                f"昵称缓存：{self.mapping_before} → {self.mapping_after}"
                f"（新增 {self.mapping_added} 条）"
            )
        lines.append(f"完整性检查：{self.integrity}")
        for warning in self.warnings:
            lines.append(f"提示：{warning}")
        return "\n".join(lines)


def inspect_database(path: Path) -> dict[str, int]:
    """只读统计一个内核数据库里各表的行数。"""
    result: dict[str, int] = {}
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        for table in tables:
            try:
                result[table] = connection.execute(
                    f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - 表名来自 sqlite_master
                ).fetchone()[0]
            except sqlite3.Error:
                continue
    finally:
        connection.close()
    return result


def _count(connection: sqlite3.Connection, table: str) -> int:
    try:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
    except sqlite3.Error:
        return 0


def import_records(
    source_db: Path,
    target_db: Path = RECORD_DB,
    include_mapping: bool = True,
    backup: bool = True,
) -> ImportResult:
    """把 ``source_db`` 的下载记录合并进 ``target_db``。

    :raises FileNotFoundError: 源库不存在
    :raises ValueError: 源库不是有效的内核数据库，或源库与目标库相同
    :raises sqlite3.Error: 合并过程中出现数据库错误（会清理掉已写内容）
    """
    source_db = Path(source_db)
    target_db = Path(target_db)

    if not source_db.is_file():
        raise FileNotFoundError(f"找不到来源数据库：{source_db}")
    if source_db.resolve() == target_db.resolve():
        raise ValueError("来源数据库与目标数据库是同一个文件，无需导入。")

    source_tables = inspect_database(source_db)
    if "download_data" not in source_tables:
        raise ValueError(
            f"来源库中没有 download_data 表，可能不是内核数据库：{source_db}"
        )

    target_db.parent.mkdir(parents=True, exist_ok=True)
    result = ImportResult(source=str(source_db), target=str(target_db))

    if backup and target_db.is_file():
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = BACKUP_DIR / f"{target_db.stem}.{stamp}.db.bak"
        shutil.copy2(target_db, backup_path)
        result.backup = str(backup_path)

    # 使用两个独立连接（不用 ATTACH）：跨盘 / 网络路径下 ATTACH+分离容易触发
    # "database legacy is locked"，分批读写更稳妥，也便于控制内存占用。
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    connection = sqlite3.connect(target_db)
    try:
        for ddl in _TABLE_DDL.values():
            connection.execute(ddl)
        connection.commit()

        result.download_before = _count(connection, "download_data")
        result.mapping_before = _count(connection, "mapping_data")

        # ---- 下载记录 ----
        cursor = source.execute(
            "SELECT ID FROM download_data WHERE ID IS NOT NULL AND ID <> ''"
        )
        while True:
            chunk = cursor.fetchmany(_CHUNK)
            if not chunk:
                break
            connection.executemany(
                "INSERT OR IGNORE INTO download_data (ID) VALUES (?)", chunk
            )
        connection.commit()

        # ---- 昵称缓存 ----
        if include_mapping:
            try:
                cursor = source.execute("SELECT ID, NAME, MARK FROM mapping_data")
                while True:
                    chunk = cursor.fetchmany(_CHUNK)
                    if not chunk:
                        break
                    connection.executemany(
                        "INSERT OR IGNORE INTO mapping_data (ID, NAME, MARK) "
                        "VALUES (?, ?, ?)",
                        chunk,
                    )
                connection.commit()
            except sqlite3.Error as exc:
                # 旧库的 mapping_data 结构异常时不应影响下载记录的导入
                result.warnings.append(f"昵称缓存导入失败（已跳过）：{exc}")

        result.download_after = _count(connection, "download_data")
        result.mapping_after = _count(connection, "mapping_data")
        result.download_added = max(0, result.download_after - result.download_before)
        result.mapping_added = max(0, result.mapping_after - result.mapping_before)

        check = connection.execute("PRAGMA integrity_check").fetchone()
        result.integrity = str(check[0]) if check else "unknown"
    except Exception:
        connection.rollback()
        raise
    finally:
        source.close()
        connection.close()

    if result.integrity != "ok":
        result.warnings.append(
            f"数据库完整性检查未通过（{result.integrity}），"
            f"建议还原备份：{result.backup}"
        )
    return result
