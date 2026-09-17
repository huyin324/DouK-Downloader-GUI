"""把旧版内核安装目录的下载记录导入本项目（避免重复下载）。

用法::

    # 使用默认的旧版目录
    .venv\\Scripts\\python.exe import_legacy_records.py

    # 指定来源数据库
    .venv\\Scripts\\python.exe import_legacy_records.py --source "D:\\old\\Volume\\DouK-Downloader.db"

    # 只看来源库内容，不做任何写入
    .venv\\Scripts\\python.exe import_legacy_records.py --inspect

导入是**增量且不覆盖**的（``INSERT OR IGNORE``），可以反复执行。
写入前会自动把目标数据库备份到 ``.workbuddy/backup/``。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from app.legacy_import import DEFAULT_LEGACY_DB, import_records, inspect_database
    from app.paths import RECORD_DB

    parser = argparse.ArgumentParser(
        description="把旧版内核的下载记录合并到本项目",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        default=str(DEFAULT_LEGACY_DB),
        help="旧版内核的 DouK-Downloader.db 路径",
    )
    parser.add_argument(
        "--target",
        default=str(RECORD_DB),
        help="本项目的 DouK-Downloader.db 路径（默认即可）",
    )
    parser.add_argument(
        "--no-mapping",
        action="store_true",
        help="只导入作品下载记录，不导入账号昵称缓存",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="只统计来源库内容，不写入任何数据",
    )
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)

    print("=" * 68)
    print("下载记录导入工具")
    print("=" * 68)
    print(f"来源库：{source}")
    print(f"目标库：{target}")
    print()

    if not source.is_file():
        print(f"[错误] 找不到来源数据库：{source}")
        return 2

    try:
        source_tables = inspect_database(source)
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] 无法读取来源数据库：{exc}")
        return 2

    print("来源库内容：")
    for table, count in sorted(source_tables.items()):
        print(f"    {table:<16} {count} 行")
    if "download_data" not in source_tables:
        print("[错误] 来源库中没有 download_data 表，可能不是内核数据库。")
        return 2

    if args.inspect:
        print("\n已按要求只做检查，未写入任何数据。")
        return 0

    if target.is_file():
        print("\n目标库现状：")
        for table, count in sorted(inspect_database(target).items()):
            print(f"    {table:<16} {count} 行")

    try:
        result = import_records(
            source,
            target,
            include_mapping=not args.no_mapping,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"\n[错误] 导入失败：{type(exc).__name__}: {exc}")
        return 1

    print("\n" + "-" * 68)
    print("导入完成")
    print("-" * 68)
    print(result.summary())
    print()
    print(
        "说明：download_data 是「已下载作品 ID」表，导入后图形界面的"
        "「下载前预过滤」即可直接跳过这些作品，不会再消耗任何接口请求。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
