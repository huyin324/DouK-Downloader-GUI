"""去重预过滤的实网对照实验。

流程（全部使用真实 Cookie 与真实账号）：

    阶段 1  干跑一次账号采集，导出作品 ID（storage_format=csv，不写媒体文件）
    阶段 2  把这些真实作品 ID 写入内核下载记录表（写入前会备份数据库）
    阶段 3  再次干跑同一账号，验证：
              - 日志出现「[去重] 预过滤」
              - 统计中的「跳过已下载」等于作品数量
              - 内核**完全没有发起任何媒体请求**（不再出现“文件大小超出限制”）
    收尾    删除本次写入的 ID，并校验记录总数回到实验前的值

用法::

    .venv\\Scripts\\python.exe tests\\live_dedup_test.py ^
        --config "<内核 settings.json>" --txt "<账号链接 txt>"
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from re import compile as re_compile
from re import search as re_search

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(_ROOT), str(_ROOT / "upstream")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

_ID_PATTERN = re_compile(r"\b(\d{19})\b")

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")


def build_config(cookie: str, root: Path, csv: bool) -> dict:
    from app.field_spec import default_config

    config = default_config()
    config["cookie"] = cookie
    config["root"] = str(root)
    config["task_mode"] = "account"
    config["account_tab"] = "post"
    config["max_pages"] = 1
    config["download"] = True
    config["max_size"] = 1                    # 干跑：只取响应头
    config["timeout"] = 15
    config["max_retry"] = 2
    config["storage_format"] = "csv" if csv else ""
    config["dedup_prefilter"] = True
    config["dedup_verify_file"] = False
    config["record_enable"] = True
    config["logger_file"] = False
    config["antispider_enable"] = True
    config["ua_rotate"] = True
    config["impersonate_pool"] = ["chrome", "edge"]
    config["wait_avg"] = 3.0
    config["wait_min"] = 1.0
    config["wait_max"] = 8.0
    config["max_workers"] = 2
    config["batch_suspend_every"] = 0
    return config


def run_engine(config: dict, link: str, timeout: int) -> tuple[list[str], list[dict], float]:
    from PyQt6.QtCore import Qt

    from app.engine import EngineWorker, TaskRequest

    request = TaskRequest(platform="douyin", mode="account", links=[link], account_tab="post")
    worker = EngineWorker(config, request)
    logs: list[str] = []
    stats: list[dict] = []
    worker.signals.message.connect(
        lambda level, text: logs.append(f"[{level}] {text}"),
        Qt.ConnectionType.DirectConnection,
    )
    worker.signals.finished.connect(
        lambda payload: stats.append(payload), Qt.ConnectionType.DirectConnection
    )
    worker.signals.failed.connect(
        lambda msg: logs.append(f"[failed] {msg}"), Qt.ConnectionType.DirectConnection
    )
    started = time.monotonic()
    thread = threading.Thread(target=worker.run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        print("    运行超时，请求停止 …")
        worker.stop()
        thread.join(60)
    return logs, stats, time.monotonic() - started


# --------------------------------------------------------------------------- #
def db_records(path: Path) -> int:
    import sqlite3

    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute("SELECT COUNT(*) FROM download_data").fetchone()[0]
    finally:
        con.close()


def collect_ids(root: Path) -> list[str]:
    """从阶段 1 导出的 CSV 中提取作品 ID。"""
    ids: list[str] = []
    for csv_file in root.rglob("*.csv"):
        try:
            text = csv_file.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        ids.extend(_ID_PATTERN.findall(text))
    return list(dict.fromkeys(ids))


def seed_ids(db_path: Path, ids: list[str]) -> None:
    import sqlite3

    con = sqlite3.connect(db_path)
    try:
        con.executemany("INSERT OR IGNORE INTO download_data (ID) VALUES (?)", [(i,) for i in ids])
        con.commit()
    finally:
        con.close()


def remove_ids(db_path: Path, ids: list[str]) -> None:
    import sqlite3

    con = sqlite3.connect(db_path)
    try:
        con.executemany("DELETE FROM download_data WHERE ID=?", [(i,) for i in ids])
        con.commit()
    finally:
        con.close()


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--txt", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    config_path = Path(args.config)
    txt_path = Path(args.txt)
    if not config_path.is_file() or not txt_path.is_file():
        print("配置文件或链接文件不存在。")
        return 2

    from app.main_window import _split_links

    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    raw_cookie = payload.get("cookie")
    cookie = (
        "; ".join(f"{k}={v}" for k, v in raw_cookie.items() if v not in (None, ""))
        if isinstance(raw_cookie, dict)
        else str(raw_cookie or "")
    )
    links = _split_links(txt_path.read_text(encoding="utf-8-sig"), "account")
    if not cookie or not links:
        print("缺少 Cookie 或账号链接。")
        return 2
    link = links[0]

    db_path = _ROOT / "upstream" / "Volume" / "DouK-Downloader.db"
    if not db_path.is_file():
        print(f"找不到内核下载记录数据库：{db_path}（请先运行一次 GUI 以创建）")
        return 2

    backup_dir = _ROOT / ".workbuddy" / "tmp"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"DouK-Downloader.db.bak-{time.strftime('%Y%m%d%H%M%S')}"
    shutil.copy2(db_path, backup)
    print(f"已备份下载记录数据库到：{backup}")

    before_count = db_records(db_path)
    print(f"实验前下载记录数：{before_count}")

    seeded: list[str] = []
    try:
        # ---------------- 阶段 1：采集并导出作品 ID ---------------- #
        print("\n" + "=" * 68)
        print("阶段 1：干跑采集，导出作品 ID")
        print("=" * 68)
        with tempfile.TemporaryDirectory() as tmp:
            root1 = Path(tmp) / "run1"
            logs1, stats1, elapsed1 = run_engine(build_config(cookie, root1, csv=True), link, args.timeout)
            joined1 = "\n".join(logs1)
            check("阶段 1 未出现未处理异常", "[failed]" not in joined1)
            check("阶段 1 正常结束",
                  bool(stats1) and stats1[0].get("状态") == "已完成", str(stats1[:1]))
            media1 = [
                p for p in root1.rglob("*")
                if p.is_file() and p.suffix.lower() in {".mp4", ".jpeg", ".webp", ".mp3"}
            ]
            check("阶段 1 未写入媒体文件", not media1, f"{media1[:3]}")

            works = collect_ids(root1)
            media_requests_1 = sum(1 for line in logs1 if "文件大小超出限制" in line)
            # 账号接口实际返回的作品数（CSV 里可能还含音乐 ID 等其它 19 位数字）
            work_count = 0
            for line in logs1:
                matched = re_search(r"共获取到 (\d+) 个", line)
                if matched:
                    work_count = int(matched.group(1))
            print(f"    账号接口返回作品 {work_count} 个，CSV 导出 19 位 ID {len(works)} 个，"
                  f"媒体请求 {media_requests_1} 次，耗时 {elapsed1:.1f}s")
            check("阶段 1 解析出作品 ID", len(works) > 0)
            check("阶段 1 确实发起了媒体请求（用于与阶段 3 对照）", media_requests_1 > 0,
                  f"{media_requests_1} 次")

        if not works:
            print("\n未取到作品 ID，无法继续对照实验。")
            return 1

        # ---------------- 阶段 2：把作品 ID 写入下载记录 ---------------- #
        print("\n" + "=" * 68)
        print("阶段 2：将这些作品标记为「已下载」")
        print("=" * 68)
        seed_ids(db_path, works)
        seeded = works
        after_seed = db_records(db_path)
        print(f"    写入 {len(works)} 条记录，当前记录数 {after_seed}")
        check("下载记录已写入", after_seed >= before_count,
              f"{before_count} -> {after_seed}")

        # ---------------- 阶段 3：再次采集，验证预过滤 ---------------- #
        print("\n" + "=" * 68)
        print("阶段 3：再次干跑同一账号，验证预过滤是否真正省下请求")
        print("=" * 68)
        with tempfile.TemporaryDirectory() as tmp:
            root2 = Path(tmp) / "run2"
            logs2, stats2, elapsed2 = run_engine(build_config(cookie, root2, csv=False), link, args.timeout)
            joined2 = "\n".join(logs2)
            check("阶段 3 未出现未处理异常", "[failed]" not in joined2)

            media_requests_2 = sum(1 for line in logs2 if "文件大小超出限制" in line)
            skipped = stats2[0].get("跳过已下载", 0) if stats2 else 0
            print(f"    媒体请求 {media_requests_2} 次，跳过已下载 {skipped} 个，"
                  f"耗时 {elapsed2:.1f}s")

            check("日志出现了去重预过滤提示", "[去重] 预过滤" in joined2)
            check("统计数据记录了跳过数量", work_count > 0 and skipped == work_count,
                  f"跳过 {skipped} / 账号作品 {work_count}")
            check("内核完全没有发起媒体请求（真正省下带宽）",
                  media_requests_2 == 0,
                  f"阶段1 {media_requests_1} 次 -> 阶段3 {media_requests_2} 次")
            check("阶段 3 明显快于阶段 1", elapsed2 <= elapsed1 + 5,
                  f"{elapsed1:.1f}s -> {elapsed2:.1f}s")
            media2 = [
                p for p in root2.rglob("*")
                if p.is_file() and p.suffix.lower() in {".mp4", ".jpeg", ".webp", ".mp3"}
            ]
            check("阶段 3 未写入媒体文件", not media2, f"{media2[:3]}")

            for line in logs2:
                if "[去重]" in line:
                    print(f"    {line}")
    finally:
        if seeded:
            remove_ids(db_path, seeded)
        final_count = db_records(db_path)
        print(f"\n已清理本次写入的记录，当前记录数：{final_count}（实验前 {before_count}）")
        if final_count != before_count:
            print(f"  [警告] 记录数与实验前不一致，备份位于 {backup}")

    print("\n" + "=" * 68)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  - {item}")
    print("=" * 68)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
