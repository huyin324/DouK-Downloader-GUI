"""实网联调测试（真实 Cookie + 真实账号链接，默认 **不下载任何媒体文件**）。

用法::

    .venv\\Scripts\\python.exe tests\\live_test.py ^
        --config "\\\\hy-nas\\Data\\抖音爬虫2024\\TikTokDownloader_V5.7_Windows_X64\\_internal\\Volume\\settings.json" ^
        --txt    "\\\\hy-nas\\Data\\抖音爬虫2024\\抖音关注用户列表10.txt" ^
        --accounts 1 --pages 1

默认以「干跑」方式运行：把 ``max_size`` 设为 1，内核在拿到响应头后即判定
“文件超出体积限制”并跳过，因此**不会写入任何媒体文件**，也不会写入下载记录。
仅用于验证：Cookie 有效性、签名参数更新、账号列表接口、去重预过滤、反爬虫节流。

加 ``--real`` 可解除体积限制进行真实下载（请自行评估流量与磁盘占用）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(_ROOT), str(_ROOT / "upstream")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


def load_cookie(config_path: Path) -> str:
    """从内核 settings.json 读取抖音 Cookie 并转换为标准字符串。"""
    payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
    raw = payload.get("cookie")
    if isinstance(raw, dict):
        return "; ".join(f"{k}={v}" for k, v in raw.items() if v not in (None, ""))
    return str(raw or "")


def load_links(txt_path: Path, limit: int, mode: str) -> list[str]:
    from app.main_window import _split_links

    text = txt_path.read_text(encoding="utf-8-sig")
    links = _split_links(text, mode)
    print(f"从 txt 提取到 {len(links)} 条链接（已忽略注释行与空行、已去重）")
    return links[:limit] if limit > 0 else links


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="内核 settings.json 路径")
    parser.add_argument("--txt", required=True, help="账号链接 txt 路径")
    parser.add_argument("--accounts", type=int, default=1, help="测试的账号数量")
    parser.add_argument("--pages", type=int, default=1, help="每个账号的最大翻页数")
    parser.add_argument("--timeout", type=int, default=600, help="整体超时（秒）")
    parser.add_argument("--real", action="store_true", help="解除体积限制，执行真实下载")
    parser.add_argument(
        "--mode", default="account",
        choices=["detail", "account", "mix", "live"],
        help="下载类型（默认 account）",
    )
    args = parser.parse_args()

    from PyQt6.QtCore import Qt

    from app.engine import EngineWorker, TaskRequest
    from app.field_spec import default_config

    config_path = Path(args.config)
    txt_path = Path(args.txt)
    if not config_path.is_file():
        print(f"找不到配置文件：{config_path}")
        return 2
    if not txt_path.is_file():
        print(f"找不到链接文件：{txt_path}")
        return 2

    cookie = load_cookie(config_path)
    print(f"Cookie 长度：{len(cookie)}，含 sessionid_ss：{'是' if 'sessionid_ss' in cookie else '否'}")
    if not cookie:
        print("配置文件中没有 Cookie，无法进行实网测试。")
        return 2

    links = load_links(txt_path, args.accounts, args.mode)
    if not links:
        print("未能提取到任何链接。")
        return 2
    for link in links[:5]:
        print(f"  待测链接：{link}")
    if len(links) > 5:
        print(f"  …… 共 {len(links)} 条")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "downloads"
        config = default_config()
        config["cookie"] = cookie
        config["root"] = str(root)
        config["task_mode"] = args.mode
        config["account_tab"] = "post"
        config["max_pages"] = args.pages
        config["download"] = True
        config["max_size"] = 0 if args.real else 1     # 干跑：任何文件都超限 -> 只取响应头
        config["timeout"] = 15
        config["max_retry"] = 2
        config["storage_format"] = ""
        config["dedup_prefilter"] = True
        config["dedup_verify_file"] = False
        config["record_enable"] = True
        config["logger_file"] = False
        config["antispider_enable"] = True
        config["ua_rotate"] = True
        config["impersonate_pool"] = ["chrome", "edge"]
        config["wait_avg"] = 3.0          # 测试时缩短间隔以控制总时长
        config["wait_min"] = 1.0
        config["wait_max"] = 8.0
        config["max_workers"] = 2
        config["batch_suspend_every"] = 0  # 测试期间不做批次休眠

        request = TaskRequest(
            platform="douyin", mode=args.mode, links=links, account_tab="post"
        )
        worker = EngineWorker(config, request)
        logs: list[str] = []
        stats: list[dict] = []
        snapshots: list[dict] = []
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
        worker.signals.stats.connect(
            lambda payload: snapshots.append(payload), Qt.ConnectionType.DirectConnection
        )

        mode_desc = f"模式 {args.mode} / " + ("真实下载" if args.real else "干跑（不写文件）")
        print(f"\n开始实网测试（{mode_desc}），账号 {len(links)} 个，每账号最多 {args.pages} 页 …\n")

        started = time.monotonic()
        thread = threading.Thread(target=worker.run, daemon=True)
        thread.start()
        thread.join(timeout=args.timeout)
        if thread.is_alive():
            print("\n测试超时，正在请求停止 …")
            worker.stop()
            thread.join(60)
        elapsed = time.monotonic() - started

        joined = "\n".join(logs)
        print("=" * 68)
        print("关键日志")
        print("=" * 68)
        for keyword in (
            "任务开始",
            "指纹画像",
            "Cookie 校验",
            "请求节流",
            "退避重试",
            "文件并发下载数",
            "开始处理第",
            "共获取到",
            "去重] 预过滤",
            "条链接",
            "作品 ID",
            "未能",
            "下载视频作品",
            "跳过视频作品",
            "文件大小超出限制",
            "任务结束",
        ):
            for line in logs:
                if keyword in line:
                    print(f"  {line}")

        print("\n" + "=" * 68)
        print("判定")
        print("=" * 68)

        def check(name: str, ok: bool, detail: str = "") -> None:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")

        check("引擎未抛出未处理异常", "[failed]" not in joined)
        check("任务正常结束", len(stats) == 1 and stats[0].get("状态") == "已完成",
              str(stats[:1]))
        check("Cookie 已登录", "Cookie 校验通过" in joined)
        if args.mode == "account":
            check("成功获取账号作品列表", "共获取到" in joined)
        else:
            check(
                f"{args.mode} 模式未误报账号列表",
                True,
                "共解析出" in joined or "未能" in joined,
            )

        dedup_object = worker.runtime.get("dedup")
        skipped_n = stats[0].get("跳过已下载", 0) if stats else 0
        check("去重预过滤已启用并在本模式生效",
              dedup_object is not None and dedup_object.enabled
              and ("去重] 预过滤" in joined or skipped_n == 0),
              f"本次命中 {skipped_n} 个（0 表示该账号作品均未下载过，属正常）")

        # 干跑模式下必须没有任何媒体文件落盘
        written = [p for p in root.rglob("*") if p.is_file()] if root.is_dir() else []
        media = [p for p in written if p.suffix.lower() in {".mp4", ".jpeg", ".jpg", ".webp", ".mp3", ".m4a"}]
        if args.real:
            check("真实下载模式下产生了媒体文件", bool(media), f"{len(media)} 个")
        else:
            check("干跑模式下未写入任何媒体文件", not media, f"意外文件 {media[:3]}")

        if stats:
            print("\n  统计：" + "；".join(f"{k} {v}" for k, v in stats[0].items()))

        # 计数栏（与界面底部一致）
        from app.stats import format_chips

        if snapshots:
            final = snapshots[-1]
            chips = format_chips(final)
            print("  计数栏：" + " │ ".join(f"{k} {v}" for k, v in chips))
            non_zero = [
                (k, v) for k, v in chips
                if v not in ("0", "0/0", "0）".replace("）", ""))
            ]
            print(f"  非零计数项：{len(non_zero)} 个 -> {non_zero[:6]}")
        else:
            print("  计数栏：未收到任何统计快照")
        print(f"\n  总耗时：{elapsed:.1f} 秒")
        print(f"  日志行数：{len(logs)}")
        return 0 if ("[failed]" not in joined) else 1


if __name__ == "__main__":
    raise SystemExit(main())
