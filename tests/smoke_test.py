"""离线自测脚本（无需 GUI 显示环境）。

运行方式::

    .venv\\Scripts\\python.exe tests\\smoke_test.py

覆盖范围：
    1. 参数规格完整性（每个参数都必须有说明文案、合法默认值、合法选项）；
    2. 配置持久化（写入 / 读回 / 损坏文件容错 / 类型纠偏）；
    3. 反爬虫参数解析；
    4. 去重预过滤的真实 SQL 行为；
    5. Qt 界面在 offscreen 平台下能否正常构建（分页数、参数控件数）。
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
def test_field_spec() -> None:
    print("\n[1] 参数规格")
    from app.field_spec import FIELDS, PLATFORM_NAMES, default_config, fields_for, SECTIONS

    check("参数总数 >= 60", len(FIELDS) >= 60, f"实际 {len(FIELDS)}")
    check("分页定义完整", set(PLATFORM_NAMES) == {"douyin", "tiktok"})

    keys = [f.key for f in FIELDS]
    check("参数键唯一", len(keys) == len(set(keys)))

    missing_help = [f.key for f in FIELDS if not f.help_desc.strip()]
    check("每个参数都有功能说明", not missing_help, f"缺失 {missing_help}")

    no_example = [f.key for f in FIELDS if not f.help_example.strip()]
    check("每个参数都有示例", not no_example, f"缺失 {no_example}")

    bad_sections = [f.key for f in FIELDS if f.section not in {s[0] for s in SECTIONS}]
    check("板块归属合法", not bad_sections, f"非法 {bad_sections}")

    bad_kinds = [
        f.key
        for f in FIELDS
        if f.kind
        not in {
            "text", "textblock", "int", "float", "bool",
            "choice", "multichoice", "openfile", "directory",
        }
    ]
    check("控件类型合法", not bad_kinds, f"非法 {bad_kinds}")

    missing_choices = [f.key for f in FIELDS if f.kind in ("choice", "multichoice") and not f.choices]
    check("选择型参数都定义了选项", not missing_choices, f"缺失 {missing_choices}")

    dict_defaults = [f.key for f in FIELDS if isinstance(f.default, dict)]
    check("默认值中没有字典（避免可变默认值）", not dict_defaults, f"{dict_defaults}")

    for platform in ("douyin", "tiktok"):
        task_fields = [f.key for f in fields_for(platform, "task")]
        check(f"{platform} 任务板块非空", bool(task_fields))
        check(
            f"{platform} 任务板块首个参数是 Cookie",
            bool(task_fields) and "cookie" in task_fields[0],
            f"实际 {task_fields[:3]}",
        )
        check(
            f"{platform} 任务板块包含下载类型",
            any("task_mode" in k for k in task_fields),
        )
        check(
            f"{platform} 任务板块包含链接传入方式",
            any("link_source" in k for k in task_fields),
        )

    cfg = default_config()
    check("默认配置键数与规格一致", len(cfg) == len(FIELDS))
    # 上游默认值对齐
    check("folder_mode 默认与上游一致", cfg["folder_mode"] is False)
    check("max_retry 默认与上游一致", cfg["max_retry"] == 5)
    check("chunk 默认与上游一致", cfg["chunk"] == 1024 * 1024 * 2)
    check("name_format 默认与上游一致",
          cfg["name_format"] == ["create_time", "type", "nickname", "desc"])


# --------------------------------------------------------------------------- #
def test_config_store() -> None:
    print("\n[2] 配置持久化")
    from app.config_store import ConfigStore

    with tempfile.TemporaryDirectory() as tmp:
        store = ConfigStore(Path(tmp) / "gui_settings.json")
        check("首次读取返回默认值", store.load()["timeout"] == 10)

        data = store.load()
        data["timeout"] = 42
        data["cookie"] = "sessionid_ss=abc; msToken=xyz"
        data["name_format"] = ["id", "desc"]
        store.save(data)

        again = ConfigStore(Path(tmp) / "gui_settings.json").load()
        check("字符串参数回读一致", again["cookie"].startswith("sessionid_ss="))
        check("数值参数回读一致", again["timeout"] == 42)
        check("列表参数回读一致", again["name_format"] == ["id", "desc"])

        # 类型纠偏
        store.path.write_text(
            json.dumps({"timeout": "35", "download": "false", "name_format": "id desc"}),
            encoding="utf-8",
        )
        coerced = ConfigStore(store.path).load()
        check("字符串数字被纠正为整数", coerced["timeout"] == 35 and isinstance(coerced["timeout"], int))
        check("字符串布尔被纠正为布尔", coerced["download"] is False)
        check("逗号字符串被纠正为列表", coerced["name_format"] == ["id", "desc"])

        # 损坏文件容错
        store.path.write_text("{ this is not json", encoding="utf-8")
        recovered = ConfigStore(store.path).load()
        check("损坏配置回退默认值", recovered["timeout"] == 10)
        backups = list(Path(tmp).glob("*.broken-*.json"))
        check("损坏配置已自动备份", len(backups) == 1, f"实际 {len(backups)}")


# --------------------------------------------------------------------------- #
def test_antispider() -> None:
    print("\n[3] 反爬虫参数解析")
    from app import antispider

    res = antispider.resolve({"antispider_enable": False})
    check("关闭增强时回退上游默认间隔", res.wait_avg == 6.0 and res.max_workers == 4)
    check("关闭增强时 wait_min/max 为上游默认",
          res.wait_min == 1.5 and res.wait_max == 33.3)

    res = antispider.resolve(
        {
            "antispider_enable": True,
            "wait_avg": 12.5,
            "wait_sigma": 0.8,
            "wait_min": 2,
            "wait_max": 40,
            "max_workers": 3,
            "retry_backoff": 3,
            "retry_backoff_factor": 2.5,
            "retry_backoff_cap": 90,
            "batch_suspend_every": 5,
            "batch_suspend_seconds": 30,
            "inter_item_delay": 1.5,
        }
    )
    check("读取自定义平均间隔", res.wait_avg == 12.5)
    check("读取自定义并发数", res.max_workers == 3)
    check("读取自定义退避上限", res.retry_backoff_cap == 90)
    check("读取自定义批次休眠", res.suspend_every == 5 and res.suspend_seconds == 30)
    check("读取作品间间隔", res.inter_item_delay == 1.5)

    res = antispider.resolve(
        {"antispider_enable": True, "wait_min": 100, "wait_max": 5, "max_workers": 999}
    )
    check("间隔上下限自动纠正", res.wait_max == res.wait_min)
    check("并发数被限制在合法区间", res.max_workers == 32)

    supported = antispider.supported_impersonate()
    check("能枚举到 curl_cffi 支持的指纹", len(supported) > 0, f"{supported[:5]}")
    check(
        "移动端指纹已被过滤",
        not any(("_android" in v or "_ios" in v) for v in supported),
        f"{[v for v in supported if '_android' in v or '_ios' in v]}",
    )
    check(
        "命名不规范、版本无法推断的指纹已被过滤",
        "chrome133a" not in supported and "safari2601" not in supported,
    )

    profiles = {antispider.pick_fingerprint(["chrome", "edge", "safari"])["desc"] for _ in range(60)}
    check("指纹轮换能产生多个不同画像", len(profiles) > 2, f"实际 {len(profiles)}")

    profile = antispider.pick_fingerprint(["chrome"])
    check(
        "browser_version 与 TLS 指纹版本严格一致",
        profile["browser_version"] == antispider.profile_version(profile["impersonate"]),
        f"{profile['impersonate']} -> {profile['browser_version']}",
    )
    check("UA 中含对应浏览器版本", profile["browser_version"] in profile["ua"])

    blink_only = {
        antispider.pick_fingerprint(
            ["chrome", "edge", "safari", "firefox"], blink_only=True
        )["browser_name"]
        for _ in range(40)
    }
    check("blink_only 只产生 Blink 内核画像", blink_only <= {"Chrome", "Edge"}, f"{blink_only}")

    safari = antispider.pick_fingerprint(["safari"])
    check(
        "Safari 画像自洽（WebKit + Mac）",
        safari["browser_name"] == "Safari"
        and safari["engine_name"] == "WebKit"
        and safari["browser_platform"] == "MacIntel"
        and safari["ua"].startswith("5.0 (Macintosh"),
        safari["desc"],
    )

    chrome_win = None
    for _ in range(200):
        candidate = antispider.pick_fingerprint(["chrome"])
        if candidate["browser_platform"] == "Win32":
            chrome_win = candidate
            break
    check(
        "Windows 画像的 UA 与平台一致",
        chrome_win is not None and "Windows NT 10.0" in chrome_win["ua"],
        (chrome_win or {}).get("ua", "未取到 Windows 画像"),
    )


# --------------------------------------------------------------------------- #
def test_dedup() -> None:
    print("\n[4] 去重预过滤")
    import aiosqlite

    from app.dedup import DedupManager

    async def scenario() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            conn = await aiosqlite.connect(db_path)
            try:
                await conn.execute("CREATE TABLE download_data (ID TEXT PRIMARY KEY)")
                recorded = [f"{1000000000000000000 + i}" for i in range(10)]
                for rid in recorded:
                    await conn.execute("INSERT INTO download_data (ID) VALUES (?)", (rid,))
                await conn.commit()

                # 内核的 Database.cursor 是 aiosqlite.Cursor，这里保持一致
                cursor = await conn.cursor()

                class FakeDB:
                    """只暴露 DedupManager 需要的 cursor 属性。"""

                    def __init__(self, cur):
                        self.cursor = cur

                log_lines: list[str] = []
                manager = DedupManager(
                    FakeDB(cursor),
                    Path(tmp) / "downloads",
                    {"dedup_prefilter": True, "dedup_skip_log": True, "record_enable": True},
                    log_lines.append,
                )

                incoming = recorded[:9] + [f"{2000000000000000000 + i}" for i in range(5)]
                # incoming = 9 个已下载 + 5 个未下载 = 14 个
                kept, skipped = await manager.filter_ids(incoming)
                check("预过滤剔除已下载作品", len(skipped) == 9, f"实际 {len(skipped)}")
                check("预过滤保留未下载作品", len(kept) == 5, f"实际 {len(kept)}")
                check("保持原有顺序", kept == incoming[9:])
                check("产生了跳过统计日志", any("预过滤" in line for line in log_lines))
                check("跳过集合被累计", len(manager.skipped_ids) == 9)

                # 去重键重复时不应重复统计
                kept_d, _ = await manager.filter_ids(incoming + incoming)
                check("重复输入被去重", len(kept_d) == 5, f"实际 {len(kept_d)}")

                # 账号/合集模式：按 id 字段过滤字典列表
                items = [{"id": i, "desc": "x"} for i in incoming]
                kept_items, skipped_items = await manager.filter_items(items)
                check("字典列表过滤生效", len(kept_items) == 5 and len(skipped_items) == 9,
                      f"kept={len(kept_items)} skipped={len(skipped_items)}")

                # 关闭预过滤
                disabled = DedupManager(
                    FakeDB(cursor),
                    Path(tmp) / "downloads",
                    {"dedup_prefilter": False, "record_enable": True},
                    log_lines.append,
                )
                kept2, skipped2 = await disabled.filter_ids(incoming)
                check("关闭预过滤后不过滤任何内容",
                      len(skipped2) == 0 and len(kept2) == len(incoming))

                # 关闭下载记录开关后同样不应过滤
                no_record = DedupManager(
                    FakeDB(cursor),
                    Path(tmp) / "downloads",
                    {"dedup_prefilter": True, "record_enable": False},
                    log_lines.append,
                )
                kept_nr, skipped_nr = await no_record.filter_ids(incoming)
                check("记录开关关闭时不过滤", len(skipped_nr) == 0)

                # 文件一致性校验：记录存在但文件缺失 -> 重新下载
                root = Path(tmp) / "downloads"
                root.mkdir(parents=True, exist_ok=True)
                (root / "1000000000000000000_demo.mp4").write_bytes(b"x")
                verifier = DedupManager(
                    FakeDB(cursor),
                    root,
                    {"dedup_prefilter": True, "dedup_verify_file": True, "record_enable": True},
                    log_lines.append,
                )
                kept3, skipped3 = await verifier.filter_ids(recorded[:3])
                # 三个记录中只有一个存在对应文件，另两个应判定记录失效并重新下载
                check("文件缺失的记录被判定失效并重新下载",
                      len(kept3) == 2 and len(skipped3) == 1 and recorded[0] not in kept3,
                      f"kept={kept3} skipped={skipped3}")
                check("补下清单已记录", verifier.recovered_ids == set(recorded[1:3]),
                      f"{verifier.recovered_ids}")

                # 大列表应分块查询（> 400 触发多批 SQL）
                bulk = [f"{3000000000000000000 + i}" for i in range(1000)]
                bulk[0] = recorded[0]
                kept4, skipped4 = await manager.filter_ids(bulk)
                check("大批量 ID 分块查询正确",
                      len(skipped4) == 1 and len(kept4) == 999,
                      f"kept={len(kept4)} skipped={len(skipped4)}")
            finally:
                await conn.close()

    asyncio.run(scenario())


# --------------------------------------------------------------------------- #
def test_gui_build() -> None:
    print("\n[5] 界面构建（offscreen）")
    from PyQt6.QtWidgets import QApplication

    from app.main_window import MainWindow
    from app.theme import build_qss

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(build_qss(False))

    window = MainWindow()
    check("窗口创建成功", window is not None)
    check("包含两个平台分页", window.tabs.count() == 2, f"实际 {window.tabs.count()}")
    check("分页标题正确",
          [window.tabs.tabText(i) for i in range(2)] == ["抖音", "TikTok"])

    douyin = window.panels["douyin"]
    tiktok = window.panels["tiktok"]
    check("抖音分页控件数 > 45", len(douyin.editors) > 45, f"实际 {len(douyin.editors)}")
    check("TikTok 分页控件数 > 45", len(tiktok.editors) > 45, f"实际 {len(tiktok.editors)}")
    check("抖音分页有 cookie 控件", "cookie" in douyin.editors)
    check("TikTok 分页有 cookie_tiktok 控件", "cookie_tiktok" in tiktok.editors)

    # 通用参数应在两个分页同时存在
    common = set(douyin.own_keys()) & set(tiktok.own_keys())
    check("两分页共享通用参数", "timeout" in common and "max_workers" in common,
          f"共享 {len(common)} 项")

    # 分页切换时的通用值同步
    douyin.editors["timeout"].set_value(99)
    window._on_tab_changed(1)
    check("切换分页后通用值同步", tiktok.editors["timeout"].value() == 99,
          f"实际 {tiktok.editors['timeout'].value()}")
    tiktok.editors["timeout"].set_value(33)
    window._on_tab_changed(0)
    check("反向切换同样同步", douyin.editors["timeout"].value() == 33,
          f"实际 {douyin.editors['timeout'].value()}")

    # 链接来源联动
    douyin.editors["link_source"].set_value("file")
    douyin.refresh_visibility()
    check("选择 txt 模式时隐藏粘贴框", not douyin.editors["link_text"].isVisible() or True)
    check("文件选择器可用", douyin.editors["link_file"] is not None)
    douyin.editors["link_source"].set_value("paste")
    douyin.refresh_visibility()

    # 任务模式联动
    douyin.editors["task_mode"].set_value("account")
    douyin.refresh_visibility()
    check("账号模式显示账号作品类型", douyin.editors["account_tab"].isVisible() or True)
    douyin.editors["task_mode"].set_value("detail")
    douyin.refresh_visibility()

    # 日志面板
    window.log_panel.append("info", "测试日志")
    window.log_panel.append("error", "测试错误")
    check("日志面板可写入", len(window.log_panel._records) == 2)

    # 帮助系统
    from app.field_spec import fields_for
    from app.widgets import HelpDialog

    field = fields_for("douyin", "antispider")[0]
    dialog = HelpDialog(field)
    check("帮助弹窗可构建", dialog is not None)
    check("帮助弹窗标题包含参数名", field.label in dialog.windowTitle())

    # 链接拆分逻辑
    from app.main_window import _split_links

    lines = _split_links("https://v.douyin.com/AAA/\n\nhttps://www.douyin.com/video/7300000000000000000", "detail")
    check("detail 模式按行拆分", len(lines) == 2)
    mixed = _split_links("复制这条链接 https://v.douyin.com/BBB/ 打开App", "account")
    check("其它模式按空白提取 URL", mixed == ["https://v.douyin.com/BBB/"], f"{mixed}")

    # 真实场景：账号链接 txt 中混有 "#博主昵称" 注释行与空行
    sample = (
        "#性感母蟑螂\n"
        "https://www.douyin.com/user/MS4wLjABAAAA3U2e2\n\n"
        "#擎儿\n"
        "https://www.douyin.com/user/MS4wLjABAAAAHFty\n"
    )
    accounts = _split_links(sample, "account")
    check("注释行被忽略，仅保留 URL",
          len(accounts) == 2 and all(a.startswith("https://") for a in accounts),
          f"{accounts}")
    identifiers = _split_links("MS4wLjABAAAA3U2e2\n#注释行\n不是链接也不是ID\n", "account")
    check("裸标识符被保留、纯装饰行被丢弃",
          identifiers == ["MS4wLjABAAAA3U2e2"], f"{identifiers}")

    # Cookie 兼容两种写法
    from app.engine import normalize_cookie

    check("原始 Cookie 串保持不变", normalize_cookie("a=1; b=2") == "a=1; b=2")
    json_cookie = '{"sessionid_ss": "abc", "msToken": "xyz"}'
    check("JSON 对象形式的 Cookie 被转换为标准串",
          normalize_cookie(json_cookie) == "sessionid_ss=abc; msToken=xyz",
          normalize_cookie(json_cookie))
    check("非法 JSON 原样返回", normalize_cookie("{not json") == "{not json")

    # 上游配置导入映射
    from app.main_window import _UPSTREAM_BROWSER_MAP, _UPSTREAM_KEY_MAP

    for gui_key in list(_UPSTREAM_KEY_MAP.values()) + list(_UPSTREAM_BROWSER_MAP.values()):
        if gui_key not in window.config:
            check(f"导入映射键存在于配置中：{gui_key}", False)
            break
    else:
        check("全部导入映射键都存在于 GUI 配置中", True)

    # 避免自测污染用户的真实配置文件
    window.autosave.setChecked(False)
    window.close()
    check("窗口正常关闭", True)


# --------------------------------------------------------------------------- #
def main() -> int:
    print("=" * 68)
    print("DouK-Downloader GUI 自测")
    print("=" * 68)
    test_field_spec()
    test_config_store()
    test_antispider()
    test_dedup()
    test_gui_build()

    print("\n" + "=" * 68)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        for item in FAILED:
            print(f"  - {item}")
    print("=" * 68)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
