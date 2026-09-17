"""去重预过滤性能基准（使用真实下载记录数据库）。

用法::

    .venv\\Scripts\\python.exe tests\\benchmark_dedup.py <DouK-Downloader.db 路径>

脚本只读原始数据库的下载记录，并把它们写入一个临时数据库用于测试，
不会修改传入的数据库文件。
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(_ROOT), str(_ROOT / "upstream")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


async def run(db_path: Path) -> int:
    import aiosqlite

    from app.dedup import DedupManager

    # 读取真实记录
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        recorded = [
            row[0] for row in source.execute("SELECT ID FROM download_data").fetchall()
        ]
    finally:
        source.close()

    if not recorded:
        print("数据库中没有下载记录，无法进行基准测试。")
        return 1

    print(f"真实下载记录：{len(recorded)} 条")

    with tempfile.TemporaryDirectory() as tmp:
        work_db = Path(tmp) / "bench.db"
        conn = await aiosqlite.connect(work_db)
        try:
            await conn.execute("CREATE TABLE download_data (ID TEXT PRIMARY KEY)")
            await conn.executemany(
                "INSERT INTO download_data (ID) VALUES (?)", [(i,) for i in recorded]
            )
            await conn.commit()
            cursor = await conn.cursor()

            class FakeDB:
                def __init__(self, cur):
                    self.cursor = cur

            logs: list[str] = []
            manager = DedupManager(
                FakeDB(cursor),
                Path(tmp) / "downloads",
                {"dedup_prefilter": True, "dedup_skip_log": False, "record_enable": True},
                logs.append,
            )

            # --- 场景 1：全部命中（最坏情况下的最大值查询） ---
            start = time.perf_counter()
            kept, skipped = await manager.filter_ids(recorded)
            hit_all = time.perf_counter() - start
            print(
                f"[场景1] 传入 {len(recorded)} 条（全部已下载）"
                f" -> 跳过 {len(skipped)}，待处理 {len(kept)}，"
                f"耗时 {hit_all * 1000:.0f} ms"
            )
            assert kept == [] and len(skipped) == len(recorded), "全部命中场景结果错误"

            # --- 场景 2：半命中（混合新老作品） ---
            half = recorded[: len(recorded) // 2]
            fresh = [f"{9000000000000000000 + i}" for i in range(len(recorded) // 2)]
            mixed = half + fresh
            manager2 = DedupManager(
                FakeDB(cursor),
                Path(tmp) / "downloads",
                {"dedup_prefilter": True, "dedup_skip_log": False, "record_enable": True},
                logs.append,
            )
            start = time.perf_counter()
            kept2, skipped2 = await manager2.filter_ids(mixed)
            hit_half = time.perf_counter() - start
            print(
                f"[场景2] 传入 {len(mixed)} 条（一半已下载）"
                f" -> 跳过 {len(skipped2)}，待处理 {len(kept2)}，"
                f"耗时 {hit_half * 1000:.0f} ms"
            )
            assert len(kept2) == len(fresh) and len(skipped2) == len(half), "半命中场景结果错误"

            # --- 场景 3：全部未命中 ---
            manager3 = DedupManager(
                FakeDB(cursor),
                Path(tmp) / "downloads",
                {"dedup_prefilter": True, "dedup_skip_log": False, "record_enable": True},
                logs.append,
            )
            start = time.perf_counter()
            kept3, skipped3 = await manager3.filter_ids(fresh)
            miss_all = time.perf_counter() - start
            print(
                f"[场景3] 传入 {len(fresh)} 条（全部未下载）"
                f" -> 跳过 {len(skipped3)}，待处理 {len(kept3)}，"
                f"耗时 {miss_all * 1000:.0f} ms"
            )
            assert skipped3 == [] and len(kept3) == len(fresh), "未命中场景结果错误"

            # --- 对比：若不预过滤，将产生多少次详情请求 ---
            print()
            print("对比（假设平均每个作品 detail 请求耗时 0.5 s）：")
            print(
                f"  不预过滤：{len(recorded)} 次请求，"
                f"约 {len(recorded) * 0.5 / 60:.0f} 分钟，额外流量 {len(recorded) * 0.05:.0f} MB"
            )
            print(
                f"  已预过滤：0 次请求，0 分钟，"
                f"预过滤本身耗时 {hit_all * 1000:.0f} ms"
            )
            print(
                f"  场景2 收益：省下 {len(skipped2)} 次请求，"
                f"约 {len(skipped2) * 0.5 / 60:.1f} 分钟"
            )
        finally:
            await conn.close()

    print()
    print("基准测试通过。")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    db_path = Path(sys.argv[1])
    if not db_path.is_file():
        print(f"文件不存在：{db_path}")
        return 2
    return asyncio.run(run(db_path))


if __name__ == "__main__":
    raise SystemExit(main())
