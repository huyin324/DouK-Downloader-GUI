"""把界面渲染成 PNG 预览图（离屏渲染，无需真实显示器）。

用法::

    .venv\\Scripts\\python.exe tests\\render_preview.py [输出目录]

生成：
    preview_main.png    主窗口整体（抖音分页）
    preview_tiktok.png  主窗口整体（TikTok 分页）
    preview_help.png    参数帮助弹窗
    preview_task.png    任务设置板块（放大细节）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(_ROOT), str(_ROOT / "upstream")):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

SAMPLE_LOGS = [
    ("system", "=" * 60),
    ("system", "任务开始：抖音 · 批量下载账号作品"),
    ("system", "待处理链接 1 条"),
    ("system", "已启用反爬虫增强："),
    ("system", "  · 请求节流：平均 6.0s / σ=0.50 / 区间 1.5~33.3s"),
    ("system", "  · 退避重试：基数 2.0s / 倍数 2.0 / 上限 60s"),
    ("system", "  · 文件并发下载数：4"),
    ("system", "  · 批次休眠：每 10 个对象休眠 60s"),
    ("system", "本次指纹画像：Chrome 142.0.0.0 · Mac OS · TLS=chrome142"),
    ("info", "文件保存根目录：D:\\DouK\\Download"),
    ("success", "抖音 Cookie 校验通过：已处于登录状态。"),
    ("info", "正在更新平台请求参数（msToken / ttwid）…"),
    ("info", "开始处理第 1 个账号"),
    ("info", "昵称/标题：某博主；标识：某博主；ID：MS4wLjABAAAA…"),
    ("info", "共获取到 9 个账号发布作品"),
    ("system", "[去重] 预过滤：账号/合集列表共 9 个作品，跳过 7 个已下载作品，实际需要下载 2 个。"),
    ("system", "[去重] 跳过清单：7300000000000000001、7300000000000000002 …（共 7 个）"),
    ("info", "[去重] 本次列表中的作品均已下载，跳过下载阶段。"),
    ("info", "【视频】2026-05-12 14.02.13-视频-某博主-今天天气不错 文件下载成功"),
    ("info", "【图集】2026-06-08 15.56.45-图集-某博主-黑色系穿搭_1 文件下载成功"),
    ("warning", "作品 7300000000000000004 处理失败：响应码异常 HTTPError('500')"),
    ("warning", "正在进行第 1 次重试"),
    ("info", "下载视频作品 2 个"),
    ("info", "跳过视频作品 7 个"),
    ("system", "任务结束：平台 抖音；模式 批量下载账号作品；提交链接 1；跳过已下载 7；处理作品 1；状态 已完成"),
]


def main() -> int:
    from PyQt6.QtWidgets import QApplication

    from app.fonts import ensure_cjk_font
    from app.main_window import MainWindow
    from app.theme import build_qss

    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else (_ROOT / "docs" / "screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    family = ensure_cjk_font(app)
    print(f"使用字体族：{family}")
    app.setStyleSheet(build_qss(False))

    window = MainWindow()
    window.resize(1560, 950)

    # 填入一份贴近真实使用的参数与日志，便于观察效果
    window.config["cookie"] = (
        "ttwid=1%7Cxxxx; msToken=AbCdEfGhIjKlMnOp; odin_tt=xxxx; "
        "passport_csrf_token=xxxx; sessionid_ss=xxxx"
    )
    window.config["root"] = r"D:\DouK\Download"
    window.config["task_mode"] = "account"
    window.config["link_source"] = "file"
    window.config["link_file"] = r"D:\DouK\关注用户列表.txt"
    window.config["dedup_prefilter"] = True
    window.config["ua_rotate"] = True
    window._load_into_ui()

    for level, text in SAMPLE_LOGS:
        window.log_panel.append(level, text)
    window.phase_label.setText("已完成")
    window._on_stats(
        {
            "accounts_done": 3,
            "accounts_total": 110,
            "work_ids": 209,
            "dedup_skipped": 25,
            "types": {
                "视频": {"download": 12, "skip": 8},
                "图集": {"download": 5, "skip": 3},
                "实况": {"download": 1, "skip": 0},
                "音乐": {"download": 2, "skip": 0},
                "封面": {"download": 4, "skip": 1},
            },
            "size_skipped": 1,
        }
    )
    window.stats_label.setText("")

    window.show()
    app.processEvents()
    window._apply_splitter_ratio()
    app.processEvents()

    shots: list[tuple[str, str]] = []

    # 抖音分页
    window.tabs.setCurrentIndex(0)
    app.processEvents()
    path = out_dir / "preview_main.png"
    window.grab().save(str(path))
    shots.append(("主窗口 · 抖音分页", str(path)))

    # 任务设置板块放大
    douyin = window.panels["douyin"]
    card = douyin.cards["task"]
    card_path = out_dir / "preview_task.png"
    card.grab().save(str(card_path))
    shots.append(("任务设置板块（Cookie / 下载类型 / 链接传入方式）", str(card_path)))

    # 反爬虫板块放大
    antispider_path = out_dir / "preview_antispider.png"
    douyin.cards["antispider"].grab().save(str(antispider_path))
    shots.append(("反爬虫增强板块", str(antispider_path)))

    # 文件命名与保存位置板块放大（含昵称变更改名修复开关）
    naming_path = out_dir / "preview_naming.png"
    douyin.cards["naming"].grab().save(str(naming_path))
    shots.append(("文件命名与保存位置板块", str(naming_path)))

    # TikTok 分页
    window.tabs.setCurrentIndex(1)
    app.processEvents()
    tiktok_path = out_dir / "preview_tiktok.png"
    window.grab().save(str(tiktok_path))
    shots.append(("主窗口 · TikTok 分页", str(tiktok_path)))

    # 参数帮助弹窗
    from app.field_spec import fields_of_section
    from app.widgets import HelpDialog

    field = next(f for f in fields_of_section("dedup", "douyin") if f.key == "dedup_prefilter")
    dialog = HelpDialog(field)
    dialog.resize(600, 640)
    dialog.show()
    app.processEvents()
    help_path = out_dir / "preview_help.png"
    dialog.grab().save(str(help_path))
    shots.append(("参数帮助弹窗（点击 “?” 后）", str(help_path)))
    dialog.close()

    # 底部计数栏
    footer_path = out_dir / "preview_counter.png"
    window.grab().copy(0, window.height() - 112, window.width(), 112).save(str(footer_path))
    shots.append(("底部计数栏（账号在进度条左侧 + 分类统计）", str(footer_path)))

    # 关于对话框
    from app.about_dialog import AboutDialog

    about = AboutDialog(window)
    about.resize(700, 820)
    about.show()
    for _ in range(3):
        app.processEvents()
    about_path = out_dir / "preview_about.png"
    about.grab().save(str(about_path))
    shots.append(("关于对话框（含免责声明与捐赠收款码）", str(about_path)))
    about.close()

    window.autosave.setChecked(False)
    window.close()

    print("已生成预览图：")
    for title, path in shots:
        print(f"  {title}\n    -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
