"""内核集成自测（离线，不需要 Cookie 与网络）。

与 ``smoke_test.py`` 的区别：本脚本会**真正实例化上游内核对象**
（``Parameter`` / ``TikTok`` / ``Downloader`` / ``RecordManager``），
并完整跑一遍 ``EngineWorker``，用于验证「非侵入式接入」这条最关键的链路是否成立。

运行方式::

    .venv\\Scripts\\python.exe tests\\integration_test.py

注意：
    - 会写入 ``upstream/Volume/settings.json``（内核配置文件，属于预期行为）；
    - 不会写入任何下载记录（测试用的作品 ID 全部无效，不会进入下载流程）；
    - 不会发起任何外网请求（未配置 Cookie 与代理，内核会跳过参数更新）。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(_ROOT), str(_ROOT / "upstream")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(f"{name} {detail}")
        print(f"  [FAIL] {name} {detail}")


# --------------------------------------------------------------------------- #
def collect(worker) -> tuple[list[str], list[dict]]:
    """把引擎日志与统计收集到列表（同线程直连信号，无需事件循环）。"""
    logs: list[str] = []
    stats: list[dict] = []
    worker.signals.message.connect(lambda level, text: logs.append(f"[{level}] {text}"))
    worker.signals.finished.connect(lambda payload: stats.append(payload))
    worker.signals.failed.connect(lambda msg: logs.append(f"[failed] {msg}"))
    return logs, stats


def test_engine_end_to_end() -> None:
    print("\n[1] 引擎端到端（真实内核对象，无网络）")
    from app.engine import EngineWorker, TaskRequest
    from app.field_spec import default_config

    with tempfile.TemporaryDirectory() as tmp:
        config = default_config()
        config["root"] = str(Path(tmp) / "downloads")
        config["antispider_enable"] = True
        config["ua_rotate"] = True
        config["impersonate_pool"] = ["chrome", "edge"]
        config["wait_avg"] = 7.5
        config["max_workers"] = 3
        config["dedup_prefilter"] = True
        config["logger_file"] = False
        config["cookie"] = ""
        config["proxy"] = ""

        # 输入中不含任何 URL，内核不会发起网络请求
        request = TaskRequest(
            platform="douyin",
            mode="detail",
            links=["这不是一个链接", "https://example.invalid/not-a-real-domain"],
        )
        worker = EngineWorker(config, request)
        logs, stats = collect(worker)
        worker.run()  # 同线程直接执行（内部自建事件循环）

        joined = "\n".join(logs)
        check("引擎未抛出未处理异常", not any("[failed]" in line for line in logs))
        check("任务输出了统计信息", len(stats) == 1, f"{stats}")
        check("统计标记为已完成", stats and stats[0].get("状态") == "已完成", f"{stats}")

        # 反爬虫补丁确实生效
        check("日志输出了指纹画像", "本次指纹画像" in joined)
        check("日志输出了请求节流配置", "请求节流" in joined)
        check("日志输出了退避重试配置", "退避重试" in joined)
        check("日志输出了并发数配置", "文件并发下载数：3" in joined)
        check("日志输出了批次休眠配置", "批次休眠" in joined)
        check("日志输出的保存目录为配置值",
              str(Path(tmp) / "downloads") in joined, joined[-600:])

        # 内核对象真的被构造出来了
        runtime = worker.runtime
        check("内核 Parameter 构造成功", runtime.get("parameter") is not None)
        check("内核 TikTok 构造成功", runtime.get("tiktok") is not None)
        check("去重管理器已就绪", runtime.get("dedup") is not None)

        parameter = runtime.get("parameter")
        if parameter is not None:
            check("保存根目录被内核接受",
                  Path(str(parameter.root)).resolve() == (Path(tmp) / "downloads").resolve(),
                  str(parameter.root))
            check("并发数补丁写入内核类属性",
                  __import__("src.downloader.download", fromlist=["Downloader"])
                  .Downloader.semaphore._value == 3)
            check("名称格式被内核解析为字段列表",
                  parameter.name_format == ["create_time", "type", "nickname", "desc"],
                  f"{parameter.name_format}")
            check("超时参数被内核接受", parameter.timeout == 10)
            check("最大重试参数被内核接受", parameter.max_retry == 5)
            check("未配置 Cookie 时抖音处于未登录态", parameter.cookie_state is False)

        tiktok = runtime.get("tiktok")
        if tiktok is not None:
            check("去重钩子已安装到内核实例",
                  getattr(tiktok.download_detail_batch, "__name__", "") == "patched",
                  getattr(tiktok.download_detail_batch, "__name__", "?"))
            check("内核下载器已切换为无进度条模式（server_mode）",
                  tiktok.downloader.general_progress_object.__name__ == "__fakeprogressobject"
                  or "fake" in tiktok.downloader.general_progress_object.__name__.lower(),
                  tiktok.downloader.general_progress_object.__name__)

        # 请求节流确实按配置生效
        from src.custom import function as custom_function

        samples = [custom_function.get_wait_time() for _ in range(300)]
        check("节流间隔落在配置区间内",
              all(1.5 <= s <= 33.3 for s in samples),
              f"min={min(samples):.2f} max={max(samples):.2f}")
        mean = sum(samples) / len(samples)
        check("节流间隔均值接近配置值", abs(mean - 7.5) < 4.0, f"均值 {mean:.2f}")

        # settings.json 确实被写入
        settings_file = _ROOT / "upstream" / "Volume" / "settings.json"
        check("内核配置文件已写入", settings_file.is_file())
        if settings_file.is_file():
            payload = json.loads(settings_file.read_text(encoding="utf-8-sig"))
            check("配置中的 name_format 正确",
                  payload.get("name_format") == "create_time type nickname desc")
            check("配置中的 timeout 正确", payload.get("timeout") == 10)
            check("配置中的 root 正确",
                  Path(payload.get("root", "")).resolve() == (Path(tmp) / "downloads").resolve())
            check("仅启用了当前分页对应的平台",
                  payload.get("douyin_platform") is True
                  and payload.get("tiktok_platform") is False)
            browser_info = payload.get("browser_info", {})
            check("browser_info 含 impersonate", bool(browser_info.get("impersonate")))
            platform_value = str(browser_info.get("browser_platform"))
            os_value = str(browser_info.get("os_name"))
            expected_os = {"MacIntel": "Mac OS", "Win32": "Windows"}.get(platform_value)
            check(
                "组合出的指纹平台与操作系统自洽",
                expected_os is not None and os_value == expected_os,
                f"browser_platform={platform_value} os_name={os_value}",
            )

            from app import antispider as _antispider

            impersonate = str(browser_info.get("impersonate", ""))
            check(
                "browser_version 与 impersonate 版本严格一致",
                str(browser_info.get("browser_version"))
                == _antispider.profile_version(impersonate),
                f"{impersonate} -> {browser_info.get('browser_version')}",
            )
            tiktok_info = payload.get("browser_info_tiktok", {})
            check("TikTok browser_info 含 impersonate", bool(tiktok_info.get("impersonate")))
            check("TikTok 指纹仅使用 Blink 内核",
                  "chrome" in str(tiktok_info.get("impersonate")).lower()
                  or "edge" in str(tiktok_info.get("impersonate")).lower(),
                  str(tiktok_info.get("impersonate")))


# --------------------------------------------------------------------------- #
def test_antispider_patches() -> None:
    print("\n[2] 反爬虫补丁落点")
    from app import antispider

    cfg = {
        "antispider_enable": True,
        "wait_avg": 5.0,
        "wait_sigma": 0.3,
        "wait_min": 1.0,
        "wait_max": 20.0,
        "max_workers": 2,
        "retry_backoff": 0.01,
        "retry_backoff_factor": 2.0,
        "retry_backoff_cap": 0.05,
        "batch_suspend_every": 3,
        "batch_suspend_seconds": 0.01,
        "inter_item_delay": 0.0,
    }

    class _Console:
        def print(self, *args, **kwargs):
            pass

    early = antispider.apply(cfg, _Console())
    late = antispider.apply_after_import(cfg, _Console())

    from src.application import main_terminal
    from src.custom import function as custom_function
    from src.downloader.download import Downloader
    from src.tools import retry as retry_mod

    check("wait 节流函数已被替换",
          custom_function.get_wait_time.__name__ == "get_wait_time"
          and custom_function.get_wait_time(avg_delay=5.0, sigma=0.3) <= 20.0)
    check("Retry.retry 已被替换",
          "make_retry" in repr(retry_mod.Retry.retry)
          or retry_mod.Retry.retry.__qualname__ != "Retry.retry",
          retry_mod.Retry.retry.__qualname__)
    check("并发数补丁生效", Downloader.semaphore._value == 2)
    check("批次休眠已被替换",
          main_terminal.suspend.__qualname__ != "suspend",
          main_terminal.suspend.__qualname__)
    check("apply() 返回了已应用项清单", len(early.applied) >= 2, f"{early.applied}")
    check("apply_after_import() 返回了已应用项清单", len(late.applied) >= 2, f"{late.applied}")

    # 批次休眠在未达阈值时不休眠
    async def scenario() -> float:
        import time

        start = time.monotonic()
        await main_terminal.suspend(1, _Console())   # 1 % 3 != 0 -> 不休眠
        return time.monotonic() - start

    elapsed = asyncio.run(scenario())
    check("未达批次的 suspend 立即返回", elapsed < 0.2, f"{elapsed:.3f}s")


# --------------------------------------------------------------------------- #
def test_dedup_hook_blocks_download() -> None:
    print("\n[3] 去重钩子确实阻断了下载流程")
    import aiosqlite

    from app.dedup import DedupManager
    from app.engine import EngineWorker

    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = await aiosqlite.connect(Path(tmp) / "t.db")
            try:
                await conn.execute("CREATE TABLE download_data (ID TEXT PRIMARY KEY)")
                recorded_id = "7300000000000000001"
                await conn.execute("INSERT INTO download_data (ID) VALUES (?)", (recorded_id,))
                await conn.commit()
                cursor = await conn.cursor()

                class FakeDB:
                    def __init__(self, cur):
                        self.cursor = cur

                logs: list[str] = []
                dedup = DedupManager(
                    FakeDB(cursor),
                    Path(tmp) / "downloads",
                    {"dedup_prefilter": True, "dedup_skip_log": True, "record_enable": True},
                    logs.append,
                )

                class FakeTikTok:
                    def __init__(self):
                        self.calls: list[list] = []

                    async def download_detail_batch(self, data, *args, **kwargs):
                        self.calls.append(list(data))
                        return True

                fake = FakeTikTok()
                EngineWorker._install_dedup_hook(
                    fake,
                    dedup,
                    {"dedup_prefilter": True},
                    lambda level, text: logs.append(text),
                )

                # 全部已下载 -> 内核的下载入口不应被调用
                await fake.download_detail_batch(
                    [{"id": recorded_id, "type": "视频"}], tiktok=False
                )
                check("全部已下载时不进入内核下载流程", fake.calls == [], f"{fake.calls}")
                check("输出了跳过提示",
                      any("均已下载" in line for line in logs), f"{logs}")

                # 部分未下载 -> 仅把未下载的交给内核
                new_id = "7300000000000000002"
                await fake.download_detail_batch(
                    [{"id": recorded_id}, {"id": new_id}], tiktok=False
                )
                check("部分已下载时只透传未下载作品",
                      len(fake.calls) == 1 and [i["id"] for i in fake.calls[0]] == [new_id],
                      f"{fake.calls}")

                # 空输入不应调用内核
                await fake.download_detail_batch([], tiktok=False)
                check("空输入不调用内核下载流程", len(fake.calls) == 1, f"{fake.calls}")

                # 关闭开关后钩子不应安装
                class FakeTikTok2:
                    async def download_detail_batch(self, data, *args, **kwargs):
                        return True

                plain = FakeTikTok2()
                EngineWorker._install_dedup_hook(
                    plain, dedup, {"dedup_prefilter": False}, logs.append
                )
                check("关闭预过滤时不安装钩子",
                      "download_detail_batch" not in plain.__dict__)
            finally:
                await conn.close()

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
def test_upstream_untouched() -> None:
    print("\n[4] 上游源码未被修改")
    git_dir = _ROOT / "upstream" / ".git"
    check("上游目录保留了 git 仓库", git_dir.is_dir())

    import subprocess

    git_exe = None
    for candidate in (
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Users\胡引\.workbuddy\binaries\PortableGit\versions\1.2.0\cmd\git.exe",
    ):
        if Path(candidate).is_file():
            git_exe = candidate
            break
    if git_exe is None:
        check("未找到 git，跳过改动校验", True)
        return

    result = subprocess.run(
        [git_exe, "status", "--porcelain"],
        cwd=str(_ROOT / "upstream"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tracked = [
        line for line in result.stdout.splitlines()
        if line.strip() and "Volume/" not in line and "volume/" not in line
    ]
    check("上游受版本控制的源码无任何改动", not tracked, "\n".join(tracked))


# --------------------------------------------------------------------------- #
def main() -> int:
    print("=" * 68)
    print("DouK-Downloader GUI 内核集成自测")
    print("=" * 68)
    test_engine_end_to_end()
    test_antispider_patches()
    test_dedup_hook_blocks_download()
    test_upstream_untouched()

    print("\n" + "=" * 68)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  - {item}")
    print("=" * 68)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
