"""DouK-Downloader GUI 应用包。

模块划分：

    paths.py          路径与环境（把内核目录加入 sys.path）
    field_spec.py     参数规格（界面项的唯一定义来源，含帮助文案）
    config_store.py   GUI 配置持久化
    theme.py          扁平化主题样式表
    widgets.py        通用控件（带 “?” 的参数编辑器、分区卡片、帮助弹窗）
    logbridge.py      日志桥接（内核 Rich 控制台 -> Qt 信号）
    antispider.py     反爬虫增强（节流 / 退避 / 指纹轮换 / 并发 / 批次休眠）
    dedup.py          去重优化（下载前预过滤 + 文件一致性校验）
    engine.py         任务引擎（后台线程驱动内核）
    settings_panel.py 左半屏设置区（抖音 / TikTok 双分页）
    log_panel.py      右半屏日志区
    main_window.py    主窗口
"""

__version__ = "1.0.0"
__all__ = ["__version__"]
