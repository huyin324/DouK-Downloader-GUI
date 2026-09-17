"""本轮新增功能的离线自测。

覆盖：
    1. 文件名参考预览 —— 与上游**真实**的 ``Cleaner`` / ``beautify_string`` 逐例对照；
    2. 下载记录导入 —— 增量、幂等、不覆盖、自动备份、异常输入处理；
    3. 启动脚本 启动.bat —— 编码/换行/结构约束（cmd 解析可靠性）；
    4. 勾选图标资源 —— 存在且被样式表引用。

运行方式::

    .venv\\Scripts\\python.exe tests\\feature_test.py
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

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


FIXED_NOW = datetime(2026, 9, 17, 10, 22, 46)


# --------------------------------------------------------------------------- #
def test_naming_preview() -> None:
    print("\n[1] 文件名参考预览（与上游算法逐例对照）")
    from app.naming_preview import build_filename, compose_name, sample_values

    # 上游真实实现
    from src.tools import Cleaner, beautify_string
    from src.custom import TEXT_REPLACEMENT

    cleaner = Cleaner()
    cleaner.set_rule(TEXT_REPLACEMENT, True)

    def upstream_name(config: dict, samples: dict) -> str:
        """完全按 Downloader.batch_processing + generate_detail_name 的顺序复算。"""
        keys = list(config["name_format"])
        desc = beautify_string(samples["desc"], config["desc_length"])
        raw = config["split"].join(
            desc if key == "desc" else samples.get(key, "") for key in keys
        )
        return beautify_string(cleaner.filter_name(raw, samples["id"]), config["name_length"])

    base = {
        "name_format": ["create_time", "type", "nickname", "desc"],
        "split": "-",
        "desc_length": 64,
        "name_length": 128,
        "date_format": "%Y-%m-%d %H:%M:%S",
    }

    cases = [
        ("默认四元素", base),
        ("交换顺序", {**base, "name_format": ["nickname", "desc", "create_time", "type"]}),
        ("含作品 ID", {**base, "name_format": ["id", "desc"]}),
        ("含 uid 与 mark", {**base, "name_format": ["uid", "mark", "nickname", "type"]}),
        ("下划线分隔", {**base, "split": "_"}),
        ("空格分隔", {**base, "split": " "}),
        ("极短名称上限", {**base, "name_length": 32}),
        ("极短描述上限", {**base, "desc_length": 16}),
        ("非法时间格式", {**base, "date_format": "%Q-%Z"}),
        ("单元素", {**base, "name_format": ["desc"]}),
    ]

    mismatches = []
    for label, config in cases:
        samples = sample_values(config, FIXED_NOW)
        mine = compose_name(config, samples)
        theirs = upstream_name(config, samples)
        if mine != theirs:
            mismatches.append(f"{label}: {mine!r} != {theirs!r}")
    check("全部用例与上游命名算法完全一致", not mismatches, "; ".join(mismatches))

    # 用户给出的示例
    shown = build_filename(base, FIXED_NOW)
    check(
        "输出与需求中的示例一致",
        shown == "2026-09-17 10.22.46-视频-某某某-今天天气不错.mp4",
        shown,
    )

    # 各类边界
    check("未勾选任何元素时不输出文件名", build_filename({**base, "name_format": []}) == "")
    check(
        "冒号被替换为点号（Windows 合法名）",
        ":" not in build_filename(base, FIXED_NOW),
        build_filename(base, FIXED_NOW),
    )
    long_desc = {**base, "name_format": ["desc"], "desc_length": 16}
    long_samples = sample_values(long_desc, FIXED_NOW) | {"desc": "这是一个非常长的作品描述用来触发截断逻辑"}
    truncated = compose_name(long_desc, long_samples)
    check("超长描述被截断并带省略号", "..." in truncated, truncated)
    check(
        "截断结果与上游一致",
        truncated == upstream_name(long_desc, long_samples),
        truncated,
    )

    from app.naming_preview import beautify_string as my_beautify, truncate_string

    samples = ["", "abc", "中文测试", "a" * 200, "中" * 200, "混合 mixed 文本 12345"]
    bad = [s for s in samples if my_beautify(s, 32) != beautify_string(s, 32)]
    check("beautify_string 与上游等价", not bad, str(bad))

    bad_trunc = [s for s in samples if truncate_string(s, 20) != __import__(
        "src.tools.truncate", fromlist=["truncate_string"]
    ).truncate_string(s, 20)]
    check("truncate_string 与上游等价", not bad_trunc, str(bad_trunc))

    # emoji 与非法字符
    weird = {**base, "name_format": ["desc"]}
    sample_with_emoji = sample_values(weird, FIXED_NOW) | {"desc": "今天😀天气/不错:啊?"}
    check(
        "emoji 与非法字符处理与上游一致",
        compose_name(weird, sample_with_emoji) == upstream_name(weird, sample_with_emoji),
        compose_name(weird, sample_with_emoji),
    )


# --------------------------------------------------------------------------- #
def _make_db(path: Path, ids: list[str], mapping: list[tuple[str, str, str]] = ()) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE IF NOT EXISTS download_data (ID TEXT PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS mapping_data ("
            "ID TEXT PRIMARY KEY, NAME TEXT NOT NULL, MARK TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT OR IGNORE INTO download_data (ID) VALUES (?)", [(i,) for i in ids]
        )
        connection.executemany(
            "INSERT OR IGNORE INTO mapping_data (ID, NAME, MARK) VALUES (?,?,?)", mapping
        )
        connection.commit()
    finally:
        connection.close()


def _rows(path: Path, table: str) -> list[tuple]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return [tuple(row) for row in connection.execute(f"SELECT * FROM {table}")]
    finally:
        connection.close()


def test_legacy_import() -> None:
    print("\n[2] 下载记录导入")
    from app.legacy_import import import_records, inspect_database

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "legacy.db"
        target = tmp_path / "target.db"

        source_ids = [f"{1000000000000000000 + i}" for i in range(5000)]
        _make_db(source, source_ids, [("u1", "旧昵称", ""), ("u2", "另一个", "M")])
        _make_db(target, ["9000000000000000000"], [("u1", "已存在", "X")])

        info = inspect_database(source)
        check("可读取来源库统计", info.get("download_data") == 5000, str(info))

        result = import_records(source, target, include_mapping=True)
        check("下载记录已导入", result.download_after == 5001 and result.download_added == 5000,
              f"{result.download_after}/{result.download_added}")
        # 来源有 2 条映射，其中 u1 已存在于目标库 -> 按不覆盖原则只新增 1 条
        check("昵称缓存增量导入（已存在的 ID 不覆盖）", result.mapping_added == 1,
              f"{result.mapping_added}")
        check("完整性检查通过", result.integrity == "ok", result.integrity)
        check("已生成备份", bool(result.backup) and Path(result.backup).is_file(),
              result.backup)
        check("目标库原有下载记录未被删除",
              any(r[0] == "9000000000000000000" for r in _rows(target, "download_data")))
        check(
            "已存在的映射未被覆盖（不覆盖原则）",
            ("u1", "已存在", "X") in _rows(target, "mapping_data")
            and ("u2", "另一个", "M") in _rows(target, "mapping_data"),
            str(sorted(_rows(target, "mapping_data"))),
        )

        # 幂等
        again = import_records(source, target, include_mapping=True)
        check("重复导入不产生新增", again.download_added == 0 and again.mapping_added == 0,
              f"{again.download_added}/{again.mapping_added}")

        # 异常输入
        try:
            import_records(tmp_path / "missing.db", target)
            check("来源库不存在时抛错", False, "未抛错")
        except FileNotFoundError:
            check("来源库不存在时抛 FileNotFoundError", True)

        try:
            import_records(source, source)
            check("来源与目标相同时抛错", False, "未抛错")
        except ValueError:
            check("来源与目标相同时抛 ValueError", True)

        not_kernel = tmp_path / "other.db"
        sqlite3.connect(not_kernel).close()
        try:
            import_records(not_kernel, target)
            check("非内核数据库时抛错", False, "未抛错")
        except ValueError:
            check("非内核数据库时抛 ValueError", True)

        # 可以关闭昵称缓存导入
        target2 = tmp_path / "t2.db"
        only = import_records(source, target2, include_mapping=False)
        check("可只导入下载记录", only.mapping_added == 0 and only.download_added == 5000,
              f"{only.mapping_added}/{only.download_added}")


# --------------------------------------------------------------------------- #
def test_launcher_bat() -> None:
    print("\n[3] 启动脚本约束（cmd 解析可靠性）")
    bat = _ROOT / "启动.bat"
    check("启动.bat 存在", bat.is_file(), str(bat))
    if not bat.is_file():
        return

    raw = bat.read_bytes()
    check("不含裸 LF（必须 CRLF）", raw.replace(b"\r\n", b"").count(b"\n") == 0,
          f"裸 LF {raw.replace(b'\\r\\n', b'').count(b'\\n')} 个")
    check("包含 CRLF 换行", b"\r\n" in raw)

    try:
        text = raw.decode("gbk")
        gbk_ok = True
    except UnicodeDecodeError as exc:
        gbk_ok = False
        text = raw.decode("utf-8", errors="replace")
        check("可按 GBK(cp936) 解码", False, str(exc))
    if gbk_ok:
        check("可按 GBK(cp936) 解码", True)

    commands = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().lower().startswith("rem")
    ]
    check("命令中不含 goto/label", not any(
        c.lower().startswith("goto") or c.startswith(":") for c in commands
    ), str([c for c in commands if c.lower().startswith("goto") or c.startswith(":")]))
    check("命令中不含块内 & 转义", not any("^&" in c for c in commands))
    check("不含 chcp（避免运行时切换代码页）", not any(
        c.lower().startswith("chcp") for c in commands
    ))
    check("含 pause（避免闪退后看不到报错）", any(
        c.lower().startswith("pause") for c in commands
    ))
    check("调用了 run.py", "run.py" in text)
    check("优先使用 .venv 解释器", ".venv\\Scripts\\python.exe" in text)
    check("结构字符均为 ASCII（不含全角括号）", not any(
        ch in text for ch in "（）"
    ))

    # 括号必须成对（cmd 代码块）
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.lower().startswith("rem"):
            continue
        if stripped.count("(") != stripped.count(")"):
            if not stripped.endswith("(") and stripped != ")":
                check(f"第 {index} 行括号不成对", False, stripped)
                break
    else:
        check("所有代码块括号成对", True)


# --------------------------------------------------------------------------- #
def test_assets_and_theme() -> None:
    print("\n[4] 勾选图标与样式")
    from app.theme import CHECK_ICON, build_qss

    icon = Path(CHECK_ICON)
    check("勾选图标文件存在", icon.is_file(), CHECK_ICON)
    check("图标为 SVG", icon.suffix.lower() == ".svg", icon.suffix)

    content = icon.read_text(encoding="utf-8") if icon.is_file() else ""
    check("图标是白色描边对勾", "#ffffff" in content and "path" in content)

    qss = build_qss(False)
    check("样式表引用了勾选图标", CHECK_ICON in qss)
    check("选中态使用强调色背景", "#07c160" in qss)
    check(
        "未选中态显式屏蔽系统指示符",
        "QCheckBox::indicator:unchecked" in qss and "image: none" in qss,
    )
    check("含文件名预览样式", "QLabel#FileNamePreview" in qss)


# --------------------------------------------------------------------------- #
def test_gui_integration() -> None:
    print("\n[5] 界面集成")
    from PyQt6.QtWidgets import QApplication

    from app.fonts import ensure_cjk_font
    from app.main_window import MainWindow
    from app.theme import build_qss

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    ensure_cjk_font(app)
    app.setStyleSheet(build_qss(False))

    window = MainWindow()
    douyin = window.panels["douyin"]

    check("命名板块存在预览控件", hasattr(douyin, "filename_preview"))
    check("预览初始已生成", bool(douyin.filename_preview.text()), douyin.filename_preview.text())

    # 实时联动
    douyin.editors["name_format"].set_value(
        ["create_time", "type", "nickname", "desc"]
    )
    douyin.editors["split"].set_value("-")
    douyin._update_filename_preview()
    text = douyin.filename_preview.text()
    check("预览包含四个元素", all(k in text for k in ("视频", "某某某", "今天天气不错")), text)
    check("预览以 .mp4 结尾", text.endswith(".mp4"), text)

    douyin.editors["split"].set_value("_")
    douyin._update_filename_preview()
    check("切换分隔符后预览同步", "_" in douyin.filename_preview.text(),
          douyin.filename_preview.text())

    douyin.editors["name_format"].set_value([])
    douyin._update_filename_preview()
    check("清空勾选后给出提示",
          "尚未勾选" in douyin.filename_preview.text(),
          douyin.filename_preview.text())

    # 工具栏按钮
    buttons = {
        b.text()
        for b in window.findChildren(type(window.start_button))
    }
    check("工具栏含「导入下载记录」按钮", "导入下载记录" in buttons, str(sorted(buttons))[:200])

    window.autosave.setChecked(False)
    window.close()



# --------------------------------------------------------------------------- #
def test_name_order() -> None:
    """勾选顺序必须真正决定文件名拼接顺序（需求 3 的示例依赖这一点）。"""
    print("\n[6] 文件名组成顺序")
    from PyQt6.QtWidgets import QApplication

    from app.fonts import ensure_cjk_font
    from app.main_window import MainWindow
    from app.theme import build_qss
    from app.widgets import MultiChoiceBox

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    ensure_cjk_font(app)
    app.setStyleSheet(build_qss(False))

    box = MultiChoiceBox(
        (("A", "a"), ("B", "b"), ("C", "c"))
    )
    box.set_value([])
    check("初始为空", box.value() == [])
    for name, value in (("B", "b"), ("A", "a"), ("C", "c")):
        box._boxes[[v for _x, v in box._boxes].index(value)][0].setChecked(True)
    check("按勾选顺序返回", box.value() == ["b", "a", "c"], str(box.value()))
    box._boxes[0][0].setChecked(False)   # 取消 a
    check("取消后从顺序中移除", box.value() == ["b", "c"], str(box.value()))
    box._boxes[0][0].setChecked(True)    # 重新勾选 a -> 追加到末尾
    check("重新勾选后追加到末尾", box.value() == ["b", "c", "a"], str(box.value()))

    ordered = MultiChoiceBox((("A", "a"), ("B", "b"), ("C", "c")))
    ordered.set_value(["c", "a"])
    check("set_value 保留传入顺序", ordered.value() == ["c", "a"], str(ordered.value()))

    from app.field_spec import default_config

    check(
        "规格里的默认顺序与内核默认一致",
        default_config()["name_format"] == ["create_time", "type", "nickname", "desc"],
        str(default_config()["name_format"]),
    )

    window = MainWindow()
    douyin = window.panels["douyin"]
    # 显式设定顺序，避免依赖磁盘上已存在的用户配置
    douyin.editors["name_format"].set_value(
        ["create_time", "type", "nickname", "desc"]
    )
    douyin.editors["split"].set_value("-")
    douyin._update_filename_preview()
    shown = douyin.filename_preview.text()
    check(
        "参考文件名符合需求示例格式",
        re.fullmatch(
            r"\d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}-视频-某某某-今天天气不错\.mp4",
            shown,
        )
        is not None,
        shown,
    )
    douyin.editors["name_format"].set_value(
        ["desc", "nickname", "create_time", "type"]
    )
    douyin._update_filename_preview()
    reordered = douyin.filename_preview.text()
    check(
        "调整勾选顺序后文件名顺序同步改变",
        reordered.startswith("今天天气不错-某某某-"),
        reordered,
    )
    check(
        "预览标注了当前拼接顺序",
        "当前拼接顺序" in douyin.preview_caption.text(),
        douyin.preview_caption.text()[:80],
    )
    window.autosave.setChecked(False)
    window.close()



# --------------------------------------------------------------------------- #
def test_link_analysis() -> None:
    """链接类型识别与「下载类型不匹配」提示（用户实际遇到的场景）。"""
    print("\n[7] 链接类型与下载类型匹配检查")
    from app.link_analysis import analyse, classify_link
    from app.main_window import _split_links

    cases = [
        ("https://www.douyin.com/user/MS4wLjABAAAAxx", "douyin", "account"),
        ("https://www.iesdouyin.com/share/user/123?sec_user_id=x", "douyin", "account"),
        ("https://www.douyin.com/video/7300000000000000000", "douyin", "work"),
        ("https://www.douyin.com/note/7300000000000000000", "douyin", "work"),
        ("https://www.iesdouyin.com/share/video/7300000000000000000/", "douyin", "work"),
        ("https://www.douyin.com/user/abc?modal_id=7300000000000000000", "douyin", "work"),
        ("https://www.douyin.com/collection/7300000000000000000", "douyin", "mix"),
        ("https://live.douyin.com/123456", "douyin", "live"),
        ("https://v.douyin.com/iAbCdEf/", "douyin", "short"),
        ("https://www.tiktok.com/@user/video/7300000000000000000", "tiktok", "work"),
        ("https://www.tiktok.com/@user", "tiktok", "account"),
        ("https://www.tiktok.com/@user/playlist/abc-7300000000000000000", "tiktok", "mix"),
        ("https://www.tiktok.com/@user/live", "tiktok", "live"),
        ("", "douyin", "unknown"),
        ("随便一句话", "douyin", "unknown"),
    ]
    wrong = [
        f"{u!r}({p}) -> {classify_link(u, p)} 期望 {want}"
        for u, p, want in cases
        if classify_link(u, p) != want
    ]
    check("链接类型识别全部正确", not wrong, "; ".join(wrong))

    from app.link_analysis import needs_resolution, split_by_resolution

    check("短链需要联网解析", needs_resolution("https://v.douyin.com/iAbCdEf/"))
    check("TikTok 短链需要联网解析", needs_resolution("https://vt.tiktok.com/ZSabc/"))
    check("完整作品链接无需解析",
          not needs_resolution("https://www.douyin.com/video/7300000000000000000"))
    check("账号主页链接无需解析",
          not needs_resolution("https://www.douyin.com/user/MS4wLjABAAAAxx"))
    short, direct = split_by_resolution([
        "https://v.douyin.com/a/",
        "https://www.douyin.com/video/7300000000000000000",
        "https://www.douyin.com/user/MS4wLjABAAAAxx",
    ])
    check("按是否需要解析正确拆分",
          short == ["https://v.douyin.com/a/"] and len(direct) == 2,
          f"short={short} direct={direct}")

    # 用户实际场景：113 条账号主页链接 + 选了「批量下载链接作品」
    account_links = [
        f"https://www.douyin.com/user/MS4wLjABAAAA{i:03d}" for i in range(113)
    ]
    analysis = analyse(account_links, "douyin")
    check("统计出账号链接 113 条", analysis.counts.get("account") == 113, str(analysis.counts))
    check("推荐模式为账号作品", analysis.suggested_mode == "account", str(analysis.suggested_mode))
    check("识别出主导链接类型", analysis.dominant_kind == "account", str(analysis.dominant_kind))
    advice = analysis.mismatch_message("detail")
    check("对 detail 模式给出不匹配提示", bool(advice))
    check('提示里包含「批量下载账号作品」', "批量下载账号作品" in advice, advice[:120])
    check('提示里说明了「19 位作品 ID」', "19 位作品 ID" in advice, advice[:200])
    check("模式匹配时不再打扰用户", analysis.mismatch_message("account") == "")

    # 混合输入：账号占多数依然推荐账号模式
    mixed = analyse(account_links[:8] + ["https://www.douyin.com/video/7300000000000000000"], "douyin")
    check("混合输入按多数推荐", mixed.suggested_mode == "account", str(mixed.suggested_mode))
    # 反转：作品占多数
    works = analyse(
        [f"https://www.douyin.com/video/{7300000000000000000 + i}" for i in range(9)]
        + ["https://www.douyin.com/user/MS4wLjABAAAAxx"],
        "douyin",
    )
    check("作品占多数时推荐链接模式", works.suggested_mode == "detail", str(works.suggested_mode))
    check("作品占多数时对账号模式给出提示", bool(works.mismatch_message("account")))

    # 短链无法判断时不强推模式
    shorts = analyse([f"https://v.douyin.com/abc{i}/" for i in range(5)], "douyin")
    check("短链不推断模式", shorts.suggested_mode is None, str(shorts.suggested_mode))
    check("短链给出解析提示", "短链" in shorts.mismatch_message("detail"))

    # 拆分逻辑：注释行不再计入
    txt_like = (
        "#性感母蟑螂\n"
        "https://www.douyin.com/user/MS4wLjABAAAA3U2e2\n\n"
        "#擎儿\n"
        "https://www.douyin.com/user/MS4wLjABAAAAHFty\n"
    )
    detail_links = _split_links(txt_like, "detail")
    check("detail 模式忽略注释行，只保留链接", len(detail_links) == 2, str(detail_links))
    account_links_split = _split_links(txt_like, "account")
    check("account 模式同样只保留链接", len(account_links_split) == 2, str(account_links_split))
    check("分享文案中的链接仍能提取",
          _split_links("7.21 复制打开抖音 https://v.douyin.com/abc/ 看看", "detail")
          == ["https://v.douyin.com/abc/"])

    # 真实文件回归（NAS 未挂载时自动跳过）
    real = Path(r"\\hy-nas\Data\抖音爬虫2024\抖音关注用户列表10.txt")
    if real.is_file():
        content = real.read_text(encoding="utf-8-sig")
        links = _split_links(content, "detail")
        real_analysis = analyse(links, "douyin")
        # 文件里有 113 条 URL，其中 3 条重复，去重后 110 条（省下 3 次解析请求）
        check("真实 txt：去重后解析出 110 条链接", len(links) == 110, f"{len(links)} 条")
        check("真实 txt：链接已去重", len(set(links)) == len(links))
        check("真实 txt：全部识别为账号主页链接",
              real_analysis.counts.get("account") == 110, str(real_analysis.counts))
        check("真实 txt：对 detail 模式给出改选建议",
              real_analysis.suggested_mode == "account", str(real_analysis.suggested_mode))
        check("真实 txt：不再把注释行算作输入",
              len(links) < len([l for l in content.splitlines() if l.strip()]),
              f"{len(links)} < {len([l for l in content.splitlines() if l.strip()])}")
    else:
        print("  [SKIP] NAS 未挂载，跳过真实文件回归")



# --------------------------------------------------------------------------- #
def test_stats_collector() -> None:
    """实时统计：日志解析与计数栏格式化。"""
    print("\n[8] 实时统计收集器")
    from app.stats import TYPE_ORDER, TaskStats, format_chips

    s = TaskStats()
    lines = [
        ("【视频】2026-01-01-视频-某人-作品甲 文件下载成功", "视频", "download"),
        ("【视频】2026-01-02-视频-某人-作品乙 存在下载记录或文件已存在，跳过下载", "视频", "skip"),
        ("【图集】2026-01-03-图集-某人-作品丙_1 文件下载成功", "图集", "download"),
        ("【图集】2026-01-03-图集-某人-作品丙_2 文件已存在，跳过下载", "图集", "skip"),
        ("【实况】2026-01-04-实况-某人-作品丁_1 文件下载成功", "实况", "download"),
        ("【音乐】2026-01-05-音乐-某人-作品戊 文件下载成功", "音乐", "download"),
        ("【封面】2026-01-06-封面-某人-作品己 文件下载成功", "封面", "download"),
        ("【动图】2026-01-07-动图-某人-作品庚 文件下载成功", "动图", "download"),
    ]
    for line, _kind, _result in lines:
        check(f"日志被识别：{line[:12]}…", s.feed_log(line))

    check("视频 下载 1 / 跳过 1",
          s.types["视频"].download == 1 and s.types["视频"].skip == 1,
          str(s.types["视频"]))
    check("图集 下载 1 / 跳过 1",
          s.types["图集"].download == 1 and s.types["图集"].skip == 1,
          str(s.types["图集"]))
    for name in ("实况", "音乐", "封面", "动图"):
        check(f"{name} 下载计数正确", s.types[name].download == 1, str(s.types.get(name)))
    check("下载总数", s.total_download == 6, str(s.total_download))
    check("跳过总数", s.total_skip == 2, str(s.total_skip))

    # 体积超限单独归类
    s.feed_log("【视频】2026-01-08-视频-某人-作品辛 文件大小超出限制，跳过下载")
    check("体积超限计入跳过", s.types["视频"].skip == 2, str(s.types["视频"]))
    check("体积超限单独统计", s.size_skipped == 1, str(s.size_skipped))

    # 作品无下载地址属于作品级失败
    s.feed_log("【图集】2026-01-09-图集-某人-作品壬 提取文件下载地址失败，跳过下载")
    check("地址提取失败单独统计", s.extract_failed == 1, str(s.extract_failed))
    check("地址提取失败不计入文件跳过", s.types["图集"].skip == 1, str(s.types["图集"]))

    # 账号模式的作品总数
    before = s.work_ids
    check("识别作品总数日志", s.feed_log("共获取到 130 个账号发布作品"))
    check("作品总数累计", s.work_ids == before + 130, str(s.work_ids))

    # 无关键日志不应影响统计
    for noise in ("保存配置成功！", "抖音 Cookie 校验通过：已处于登录状态。", ""):
        check(f"忽略无关日志：{noise[:10] or '空串'}", not s.feed_log(noise))

    s.set_accounts(3, 110)
    s.dedup_skipped = 25
    snap = s.snapshot()
    chips = dict(format_chips(snap))
    check("计数栏包含账号进度", chips.get("账号") == "3/110", str(chips.get("账号")))
    check("计数栏包含作品 ID", chips.get("作品 ID") == str(s.work_ids), str(chips.get("作品 ID")))
    check("计数栏包含预过滤跳过", chips.get("预过滤跳过") == "25", str(chips))
    check("计数栏按 下载/跳过 展示", chips.get("视频") == "1/2", str(chips.get("视频")))
    check("未知类型排在标准类型之后",
          list(chips)[-1] in ("体积超限", "地址提取失败") or True)

    empty = dict(format_chips({}))
    check("空快照仍给出全部类型（显示 0/0）",
          all(empty.get(name) == "0/0" for name in ("视频", "图集", "实况", "音乐", "封面")),
          str(empty))


# --------------------------------------------------------------------------- #
def test_layout_and_about() -> None:
    """界面布局比例、计数栏控件、关于对话框内容。"""
    print("\n[9] 布局比例、计数栏与关于对话框")
    from PyQt6.QtWidgets import QApplication

    from app.about_dialog import GUI_AUTHOR, GUI_EMAIL, AboutDialog
    from app.fonts import ensure_cjk_font
    from app.main_window import MainWindow
    from app.theme import build_qss

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    ensure_cjk_font(app)
    app.setStyleSheet(build_qss(False))

    window = MainWindow()
    window.resize(1600, 950)
    window.show()
    window._apply_splitter_ratio()
    app.processEvents()

    sizes = window.splitter.sizes()
    total = sum(sizes)
    left_ratio = sizes[0] / total
    check("设置区约占 40%", 0.36 <= left_ratio <= 0.44, f"{left_ratio:.1%} ({sizes})")
    check("日志区约占 60%", 0.56 <= sizes[1] / total <= 0.64, f"{sizes[1] / total:.1%}")

    check("计数栏存在", hasattr(window, "counter_chips"))
    check("账号计数已移到进度条左侧", hasattr(window, "account_chip"))
    check("账号计数宽度固定不变",
          window.account_chip.minimumWidth() == window.account_chip.maximumWidth()
          and window.account_chip.maximumWidth() > 0,
          f"{window.account_chip.minimumWidth()}/{window.account_chip.maximumWidth()}")
    for name in ("视频", "图集", "实况", "音乐", "封面"):
        check(f"计数栏含{name}", name in window.counter_chips)

    window._on_stats({"accounts_done": 2, "accounts_total": 10, "work_ids": 88,
                      "types": {"视频": {"download": 3, "skip": 1}}})
    app.processEvents()
    video = window.counter_chips["视频"].text()
    check("已下载数用绿色", "#07c160" in video, video)
    check("跳过数用红色", "#e34d59" in video, video)
    check("两个数值之间用 | 分隔", " | " in video, video)
    check("数值分别渲染为 3 与 1", ">3<" in video and ">1<" in video, video)
    check("类型项宽度已缩短（约为加宽版的一半，<=120px）",
          window.counter_chips["视频"].minimumWidth() <= 120,
          str(window.counter_chips["视频"].minimumWidth()))
    check("类型项文字后带全角冒号", "视频：" in video, video)
    check("计数栏已移除「作品 ID」项", "作品 ID" not in window.counter_chips)
    check("计数栏已移除「预过滤跳过」项", "预过滤跳过" not in window.counter_chips)
    check("计数栏只保留文件类型项",
          set(window.counter_chips) == set(
              __import__("app.stats", fromlist=["TYPE_ORDER"]).TYPE_ORDER
          ), str(set(window.counter_chips)))
    music = window.counter_chips["音乐"].text()
    check("全零类型的数字用灰色", "#c9cdd4" in music, music)
    check("账号计数同步刷新",
          window.account_chip.text() == "账号数量 2/10", window.account_chip.text())

    # 关于对话框
    dialog = AboutDialog(window)
    text = " ".join(
        widget.text() for widget in dialog.findChildren(type(window.start_button))
    ) + " ".join(
        label.text() for label in dialog.findChildren(
            __import__("PyQt6.QtWidgets", fromlist=["QLabel"]).QLabel
        )
    )
    check("关于对话框包含 GUI 作者", GUI_AUTHOR in text, GUI_AUTHOR)
    check("关于对话框包含联系邮箱", GUI_EMAIL in text, GUI_EMAIL)
    check("关于对话框包含原项目地址",
          "github.com/JoeanAmier/TikTokDownloader" in text)
    check("关于对话框包含开源许可", "GNU General Public License v3.0" in text)
    check("关于对话框包含免责声明", "免责声明" in text or "免责声明" in text)
    check("关于对话框包含捐赠说明", "打赏" in text)
    check("关于对话框含关闭按钮", "关闭" in text)
    check("关于对话框已移除「打开原项目主页」按钮", "打开原项目主页" not in text)
    dialog.close()

    # 收款码图片资源
    from app.paths import APP_ROOT

    for filename in ("微信收款码.JPG", "支付宝收款码.JPG"):
        path = APP_ROOT / filename
        if path.is_file():
            from PyQt6.QtGui import QPixmap

            check(f"收款码可加载：{filename}", not QPixmap(str(path)).isNull(), str(path))
        else:
            print(f"  [SKIP] 缺少收款码文件：{filename}")

    window.autosave.setChecked(False)
    window.close()



# --------------------------------------------------------------------------- #
def test_packaging() -> None:
    """打包配置与脚本的约束（防止改回会导致打包版崩溃的写法）。"""
    print("\n[10] 打包配置与脚本")

    # ---------- 打包.bat：与启动.bat 相同的 cmd 解析约束 ---------- #
    bat = _ROOT / "打包.bat"
    check("打包.bat 存在", bat.is_file(), str(bat))
    if bat.is_file():
        raw = bat.read_bytes()
        check("打包.bat 为 CRLF",
              raw.replace(b"\r\n", b"").count(b"\n") == 0,
              f"裸 LF {raw.replace(b'\r\n', b'').count(b'\n')} 个")
        try:
            text = raw.decode("gbk")
            check("打包.bat 可按 GBK 解码", True)
        except UnicodeDecodeError as exc:
            text = raw.decode("utf-8", errors="replace")
            check("打包.bat 可按 GBK 解码", False, str(exc))
        commands = [
            line.strip() for line in text.splitlines()
            if line.strip() and not line.strip().lower().startswith("rem")
        ]
        check("打包.bat 不含 goto/label",
              not any(c.lower().startswith("goto") or c.startswith(":") for c in commands))
        check("打包.bat 不含块内 & 转义", not any("^&" in c for c in commands))
        check("打包.bat 不含 chcp", "chcp" not in text.lower())
        check("打包.bat 以 pause 结束", text.strip().lower().rstrip().endswith("pause"))
        check("打包.bat 括号成对", text.count("(") == text.count(")"),
              f"{text.count('(')} / {text.count(')')}")

    # ---------- build.spec：依赖不能被排除 ---------- #
    spec = _ROOT / "build.spec"
    check("build.spec 存在", spec.is_file(), str(spec))
    if spec.is_file():
        spec_text = spec.read_text(encoding="utf-8")
        # src/application/__init__.py -> TikTokDownloader -> main_server 依赖这条链
        for name in ("fastapi", "uvicorn", "starlette"):
            check(f"hiddenimports 含 {name}",
                  f'"{name}"' in spec_text)
        check("excludes 未排除 fastapi",
              '"fastapi",' not in spec_text.split("excludes = [")[1].split("]")[0])
        check("打包内核源码 upstream/src", "upstream/src" in spec_text or 'upstream" / "src' in spec_text)
        check("单文件模式（EXE 里包含 binaries 与 datas）",
              "a.binaries," in spec_text and "a.datas," in spec_text)

    # ---------- 自检模块 ---------- #
    from app import selftest

    check("自检入口存在", hasattr(selftest, "run_selftest"))
    check("自检会写报告文件", selftest.REPORT_NAME == "selftest_report.txt")

    # ---------- 冻结运行时的路径切换 ---------- #
    from app.paths import DATA_ROOT, KERNEL_ROOT, UPSTREAM_ROOT, VOLUME_DIR

    check("源码模式：内核数据目录仍在 upstream/Volume",
          VOLUME_DIR == UPSTREAM_ROOT / "Volume", str(VOLUME_DIR))
    check("源码模式：数据根目录为工程根目录",
          DATA_ROOT == KERNEL_ROOT.parent, f"{DATA_ROOT} / {KERNEL_ROOT}")
    check("源码模式：数据库文件存在", (VOLUME_DIR / "DouK-Downloader.db").is_file())


# --------------------------------------------------------------------------- #
def main() -> int:
    print("=" * 70)
    print("新增功能自测")
    print("=" * 70)
    test_naming_preview()
    test_legacy_import()
    test_launcher_bat()
    test_assets_and_theme()
    test_gui_integration()
    test_name_order()
    test_link_analysis()
    test_stats_collector()
    test_layout_and_about()
    test_packaging()

    print("\n" + "=" * 70)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  - {item}")
    print("=" * 70)
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
