# DouK-Downloader GUI

基于 **Python + PyQt6** 的图形界面外壳，内核为
[DouK-Downloader V5.8](https://github.com/JoeanAmier/TikTokDownloader)（抖音 / TikTok 作品下载与数据采集工具）。

> **设计原则：内核源码零改动。**
> 上游 `upstream/` 目录以 git submodule 引入、与原仓库完全一致；
> 所有界面化改造、去重优化与反爬虫增强均通过**运行时包装**实现，
> 可随时关闭并完全回退到内核的原始行为。

**最新发布**：[Releases · V1.0](https://github.com/huyin324/DouK-Downloader-GUI/releases/tag/v1.0)
（含单文件 exe，无需安装 Python）

---

## 一、本 GUI 详细介绍

### 1.1 它是什么

一个把命令行工具「变成窗口」的**外壳**：内核的下载与解析逻辑一个字节未改，
GUI 只负责把内核 `settings.json` 里的全部参数变成表单、把输出变成日志、
并把若干明显可优化的行为做成**可关闭的运行时增强**。

- **不替代内核**：直接运行 `upstream/main.py` 就是原命令行版本；
- **不绑架配置**：GUI 的参数最终展开成内核自己的 `settings.json` 结构写入；
- **可完全回退**：每项增强都有开关，全部关闭后网络行为与命令行版一致。

### 1.2 界面布局

| 区域 | 内容 | 占比 |
| --- | --- | --- |
| 左侧 | 设置区，含 **抖音** / **TikTok** 两个分页 | **40%** |
| 右侧 | 运行日志区（按级别着色、可过滤、可导出） | **60%** |
| 底部第一行 | 「账号数量」进度 + 进度条 + 当前阶段 + 自动保存开关 | — |
| 底部第二行 | **实时计数栏**（分类文件的已下载 / 跳过数量） | — |

分隔条可自由拖动；首次打开按 40% : 60% 分配。

<p>
  <img src="https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_main.png" width="880" alt="主窗口（抖音分页）">
</p>

<details>
<summary>更多界面截图（点击展开）</summary>

| 主窗口（TikTok 分页） | 任务设置板块 |
| --- | --- |
| ![TikTok 分页](https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_tiktok.png) | ![任务设置](https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_task.png) |

| 文件命名与保存位置（含实时文件名预览） | 反爬虫增强板块 |
| --- | --- |
| ![文件命名](https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_naming.png) | ![反爬虫](https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_antispider.png) |

| 底部计数栏 | 参数帮助弹窗（点击 `?`） | 关于对话框 |
| --- | --- | --- |
| ![计数栏](https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_counter.png) | ![帮助](https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_help.png) | ![关于](https://raw.githubusercontent.com/huyin324/DouK-Downloader-GUI/main/docs/screenshots/preview_about.png) |

</details>

### 1.3 参数帮助与实时预览

**每个参数右侧都有 `?` 图标**，点击后弹出说明窗口，包含功能说明、示例、
可选值列表（下拉 / 多选型）、取值范围（数值型）。

「文件命名与保存位置」板块还有一行**实时生成的参考文件名**：勾选元素、
切换分隔符、修改长度或时间格式时立即刷新。

```
2026-09-17 10.22.46-视频-某某某-今天天气不错.mp4
```

算法与内核完全一致，并已用上游真实的 `Cleaner` / `beautify_string` 逐例对照验证：
先截断描述 → 按勾选顺序用分隔符拼接 → `filter_name` 清洗
（**`:` 会替换成 `.`**，移除非法字符 / 控制字符 / emoji）→ 按最大长度截断 →
清洗后为空则回退作品 ID。

### 1.4 实时计数栏

```
账号数量 3/110   [━━━━━━ 进度条 ━━━━━━]

视频：12 | 8 │ 图集：5 | 3 │ 实况：1 | 0 │ 音乐：2 | 0 │ 封面：4 | 1 │ 动图：0 | 0
```

- 每项形如 `类型：已下载数 | 跳过数`，**绿色为已下载、红色为跳过**，全为 0 时置灰；
- 数据来自两条互补路径：**内核日志**（可覆盖内核自身统计不到的音乐 / 封面 / 动图）
  与**引擎自身计数**（账号进度、作品 ID、预过滤跳过）；
- 任务结束时日志留一行汇总，便于事后核对。

### 1.5 持久化

- 参数保存在 `config/gui_settings.json`，点击「保存配置」或开始前自动写盘；
- 勾选「退出时自动保存配置」后关闭窗口即保存；
- 配置文件损坏时自动备份为 `gui_settings.broken-<时间>.json` 并回退默认值；
- 手工编辑造成的类型错误会在读取时自动纠正。

> ⚠️ 该文件含**明文 Cookie**，已在 `.gitignore` 中，请勿外发。

---

## 二、相比原版新特性

| # | 新特性 | 原版（命令行）行为 | 本 GUI | 实测效果 |
| --- | --- | --- | --- | --- |
| 1 | **图形界面** | 终端交互、手工编辑 `settings.json` | 双分页表单，85 个参数全覆盖，每项带帮助 | — |
| 2 | **下载前预过滤** | 拿到详情**之后**才判断去重 | 发起请求**之前**用批量 SQL 比对下载记录 | 30,172 条记录过滤 **113 ms**；重复任务媒体请求 **12 → 0** |
| 3 | **反爬虫增强** | 固定间隔、固定指纹、硬编码批次休眠 | 请求节流 / TLS 指纹自洽轮换 / 指数退避 / 并发与批次可配置 | 全部可关闭，关闭后等同原版 |
| 4 | **链接类型识别** | 选错下载类型会白跑一轮 | 启动前自动识别，不匹配时弹窗并**一键切换** | 避免 12 分钟空跑 |
| 5 | **仅短链联网解析** | 每条链接都发一次请求解析 | 完整链接直接正则提取作品 ID，零请求 | 110 条链接：**12 分 14 秒 → 1.6 秒**，省下 110 次请求 |
| 6 | **上游改名缺陷修复** | 昵称变更时抛 `FileNotFoundError` 并中断账号 | 运行时补丁（不改源码）+ 可选同步重命名文件夹 | 3/3 文件正确改名，无重复目录 |
| 7 | **实时计数栏** | 无 | 分类统计已下载 / 跳过 | — |
| 8 | **文件名实时预览** | 无 | 与内核算法逐例对照 | — |
| 9 | **旧版记录迁移** | 需手工合并 SQLite | 一键导入 V5.7 的下载记录与昵称缓存 | 导入 30,172 条 + 657 条昵称缓存，幂等 |
| 10 | **单文件 exe** | 需 Python 环境 | 内置运行环境 + `--selftest` 自检（19 项） | 53 MB，双击即用 |

### 2.1 增强的可关闭性

| 需求 | 实现位置 | 关闭方式 |
| --- | --- | --- |
| 图形界面化 | `app/` | 直接运行 `upstream/main.py` 即原命令行版本 |
| 去重优化 | `app/dedup.py` | 取消勾选「下载前预过滤已下载作品」 |
| 反爬虫增强 | `app/antispider.py` | 取消勾选「启用反爬虫增强」 |
| 上游改名缺陷修复 | `app/upstream_fixes.py` | 取消勾选「修复昵称变更改名缺陷」 |

关闭全部增强后，程序的网络行为与内核命令行版本完全一致。

---

## 三、快速开始

### 3.1 方式 A：下载 exe（推荐，无需安装 Python）

到 [Releases](https://github.com/huyin324/DouK-Downloader-GUI/releases) 下载
`DouK-Downloader-GUI.exe`，双击运行。

exe 所在目录会生成：

```
├── DouK-Downloader-GUI.exe     单文件程序（内核与依赖都在里面）
├── Volume\    下载记录数据库 DouK-Downloader.db、settings.json、Cache
├── config\    gui_settings.json（含 Cookie，请勿外发）
├── Downloads\ 未指定保存位置时的默认下载目录
└── backup\    改动数据库前的自动备份
```

> **数据写在 exe 所在目录、不在临时目录**：PyInstaller 单文件模式会把资源解压到
> 临时目录（`_MEIxxxxxx`）并在退出后删除。本项目在打包运行时把数据根目录切到
> exe 所在目录（与内核 `Path(sys.executable).parent` 一致），因此记录与配置可持久保存。
> 也可用环境变量 `DOUK_DATA_DIR` 指定其它位置。

**自检**（验证内核、依赖、数据库、界面是否完整，报告写入 exe 同目录
`selftest_report.txt`）：

```bat
DouK-Downloader-GUI.exe --selftest
DouK-Downloader-GUI.exe --selftest --network   :: 额外做一次真实 HTTPS 请求
```

共 19 项，含「内核主程序入口」「按引擎方式真实初始化内核（Settings → Database →
Parameter → TikTok）」等打包最容易出问题的环节。

### 3.2 方式 B：从源码运行

```bash
# 0. 克隆（upstream/ 是上游内核的 git submodule，务必带 --recursive）
git clone --recursive https://github.com/huyin324/DouK-Downloader-GUI.git
cd DouK-Downloader-GUI

# 1. 创建虚拟环境（需 Python 3.12 及以上）
python -m venv .venv

# 2. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. 启动
.venv\Scripts\python.exe run.py
```

也可以直接双击 `启动.bat`（自动优先使用 `.venv`）。

**首次使用请先填写 Cookie**：在对应分页首行填入 Cookie，点「校验登录状态」确认。
获取方法见内核文档的
[Cookie 获取教程](https://github.com/JoeanAmier/TikTokDownloader/blob/master/docs/Cookie%E8%8E%B7%E5%8F%96%E6%95%99%E7%A8%8B.md)。

### 3.3 从命令行版本迁移

1. **复用下载记录（推荐）** —— 工具栏「导入下载记录」，选择旧安装目录下的
   `Volume\DouK-Downloader.db`。采用 `INSERT OR IGNORE` 只增不覆盖、可反复执行，
   写入前自动备份、完成后做 `integrity_check`。也可用命令行：

   ```bash
   .venv\Scripts\python.exe import_legacy_records.py --inspect    # 只看不写
   .venv\Scripts\python.exe import_legacy_records.py --source "D:\old\Volume\DouK-Downloader.db"
   ```

2. **复用参数与 Cookie** —— 工具栏「导入内核配置」选择旧 `settings.json`。
   Cookie 支持浏览器复制的 `k=v; k=v` 与内核旧配置的 JSON 对象两种格式。
   > 注意：旧配置里的「保存根目录」可能来自其它电脑（如 `/Volumes/Data/...`），
   > 导入后请改成当前系统的有效路径。

### 3.4 自行打包

```bat
打包.bat                      :: 一键脚本（双击即可）
```
```bash
.venv\Scripts\python.exe -m pip install pyinstaller   # 首次
.venv\Scripts\python.exe build_exe.py
```

产出 `dist\DouK-Downloader-GUI.exe`（约 53 MB，`--onefile`、无控制台窗口）。

---

## 四、目录结构

```
DouK-Downloader-GUI/
├── run.py                    启动入口（支持 --selftest）
├── 启动.bat                  Windows 一键启动（GBK + CRLF）
├── 打包.bat                  一键打包（GBK + CRLF）
├── build.spec                PyInstaller 打包配置
├── build_exe.py              打包脚本：清理缓存 → 打包 → 复制数据目录
├── import_legacy_records.py  旧版下载记录导入（命令行版）
├── requirements.txt          依赖清单（含内核依赖）
├── LICENSE                   GPL-3.0
├── config/
│   └── gui_settings.json     参数持久化（自动生成，含 Cookie）
├── app/                      图形界面外壳
│   ├── field_spec.py         参数规格：界面项 / 默认值 / 帮助文案的唯一来源
│   ├── config_store.py       配置读写与容错
│   ├── settings_panel.py     左侧设置区（双分页）
│   ├── log_panel.py          右侧日志区
│   ├── main_window.py        主窗口（工具栏、计数栏、任务调度）
│   ├── engine.py             任务引擎（后台线程 + asyncio 驱动内核）
│   ├── logbridge.py          日志桥接：内核 Rich 控制台 → Qt 信号
│   ├── widgets.py            通用控件（带 “?” 的参数编辑器、帮助弹窗）
│   ├── naming_preview.py     文件名参考预览（复刻上游命名算法）
│   ├── stats.py              实时统计收集器（解析内核日志 + 引擎计数）
│   ├── selftest.py           打包后的自检（--selftest）
│   ├── dedup.py              去重优化
│   ├── antispider.py         反爬虫增强
│   ├── link_analysis.py      链接类型识别与下载类型匹配检查
│   ├── upstream_fixes.py     上游改名缺陷的运行时修复
│   ├── legacy_import.py      旧版下载记录导入
│   ├── about_dialog.py       关于对话框（项目信息 / 免责声明 / 捐赠）
│   ├── theme.py              扁平化主题样式（含勾选对勾图标）
│   ├── fonts.py              中文字体兜底
│   ├── paths.py              路径与环境（打包运行时切换数据目录）
│   └── assets/check.svg      勾选态对勾图标
├── docs/screenshots/         界面预览图（离屏渲染生成）
├── tests/                    自测脚本（见下）
└── upstream/                 上游内核（git submodule，未做任何修改）
```

内核运行数据（下载记录数据库、日志、缓存）在源码模式下落在 `upstream/Volume/`，
与内核原本行为一致；打包模式下落在 exe 所在目录的 `Volume/`。

### 自测脚本

| 脚本 | 覆盖内容 | 结果 |
| --- | --- | --- |
| `smoke_test.py` | 参数规格完整性、配置持久化与容错、反爬解析、去重 SQL、界面联动 | 86 项通过 |
| `integration_test.py` | 真实构造内核对象、补丁落点、去重钩子、上游未被修改 | 46 项通过 |
| `cache_rename_test.py` | 复现上游改名缺陷并验证修复与可回退 | 19 项通过 |
| `feature_test.py` | 文件名预览、记录导入、启动/打包脚本约束、图标资源、界面布局 | 164 项通过 |
| `benchmark_dedup.py` | 去重性能基准（传入真实数据库） | — |
| `live_test.py` | 实网干跑联调（`max_size=1`，不写媒体文件） | 6 项通过 |
| `live_dedup_test.py` | 去重预过滤实网对照实验 | 12 项通过 |
| `render_preview.py` | 生成 `docs/screenshots/` 预览图 | — |

上游 `git -C upstream status --porcelain` 输出为空，即内核源码确实零改动。

---

## 五、参数说明

### 5.1 每个分页的排列顺序

1. **Cookie**（首行）—— 附「从剪贴板粘贴」「校验登录状态」「清空」
2. **下载类型** —— 批量下载链接作品 / 账号作品 / 合集作品 / 获取直播拉流地址
3. **链接传入方式** —— 粘贴链接 或 从本地 txt 读取（附「解析文件内容」）
4. **下载内容** —— 音乐、静态封面、动态封面、原画质量、独立文件夹
5. **文件命名与保存位置**
6. **网络请求** —— 超时、重试、分块、体积上限、代理、翻页上限
7. **反爬虫增强**
8. **去重优化**
9. **平台开关**
10. **高级设置** —— FFmpeg、直播清晰度、浏览器指纹

两个分页共享「通用」参数，切换时自动同步。任务模式与链接来源联动：
选「账号作品」才显示账号作品类型；选「txt 文件」时粘贴框自动隐藏。

### 5.2 下载类型必须与链接类型匹配

| 下载类型 | 能识别的链接 | 例子 |
| --- | --- | --- |
| 批量下载链接作品 | **作品链接**（含 19 位作品 ID） | `douyin.com/video/7300000000000000000` |
| 批量下载账号作品 | **账号主页链接** | `douyin.com/user/MS4wLjABAAAA…` |
| 批量下载合集作品 | **合集链接**（或合集内任意作品链接） | `douyin.com/collection/7300000000000000000` |
| 获取直播拉流地址 | **直播链接** | `live.douyin.com/123456` |

程序在启动前自动识别，若某类占比 ≥60% 且与所选模式不匹配，会弹窗并给出**一键切换**建议。

### 5.3 参数清单

共 **85** 项（下表为界面可见的主参数；抖音 / TikTok 同构参数合并列出）。

#### 任务设置

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| 抖音 / TikTok Cookie | 登录凭据，支持 `k=v; k=v` 与 JSON 对象 | 空 |
| 下载类型 | 链接作品 / 账号作品 / 合集作品 / 直播拉流 | 批量下载链接作品 |
| 链接传入方式 | 粘贴链接 / 本地 txt 文件 | 粘贴链接 |
| 作品链接 / txt 文件路径 | 待处理输入 | 空 |
| 账号作品类型 | post（发布）/ favorite（喜欢）/ collection 等 | post |

#### 下载内容

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| 启用文件下载 | 关闭则只采集数据不落盘 | 开 |
| 下载作品音乐 | 保存作品原声 | 关 |
| 下载静态封面 / 动态封面 | 保存封面图 / 动图 | 关 |
| 优先原画质量 | 优先取最高画质 | 关 |
| 按作品建独立文件夹 | 每个作品单独建目录 | 关 |

#### 文件命名与保存位置

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| 保存根目录 | 下载文件存放位置 | 空（回退默认） |
| 默认文件夹名称 | 未指定子目录时的目录名 | Download |
| 文件名组成 | 作品 ID / 描述 / 发布时间 / 昵称 / UID / 标记 / 类型，**按勾选顺序拼接** | 发布时间 + 类型 + 昵称 + 描述 |
| 文件名分隔符 | 各段之间的连接符 | `-` |
| 文件名最大长度 | 超长时保留首尾并加 `...` | 128 |
| 描述最大长度 | 作品描述截断长度 | 64 |
| 日志显示截断长度 | 日志中文件名的显示长度 | 50 |
| 时间格式 | `strftime` 格式串 | `%Y-%m-%d %H:%M:%S` |
| 数据存档格式 | 不存档 / CSV / SQLite / MySQL | 不存档 |
| 修复昵称变更改名缺陷 | 上游缺陷的运行时补丁 | 开 |
| 昵称变更时同步重命名账号文件夹 | 避免新旧昵称双份目录 | 开 |

#### 网络请求

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| 抖音 / TikTok 代理 | 形如 `http://127.0.0.1:7890` | 空 |
| 请求超时（秒） | 单次请求超时 | 10 |
| 最大重试次数 | 失败重试次数 | 5 |
| 分块大小（字节） | 下载分块 | 2,097,152 |
| 单文件体积上限（字节） | 0 表示不限；设为 1 可做**干跑联调** | 0 |
| 最大翻页数 | 0 表示不限 | 0 |

#### 反爬虫增强（总开关：启用反爬虫增强）

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| 请求平均间隔（秒） | 按对数正态分布抖动 | 6.0 |
| 间隔抖动系数 σ | σ=0 即固定间隔 | 0.5 |
| 间隔下限 / 上限（秒） | 抖动结果的硬性边界 | 1.5 / 33.3 |
| 文件并发下载数 | 同时下载的文件数（1–16） | 4 |
| 启用指纹轮换 | 每次任务随机挑选自洽的 TLS 指纹与指纹字段 | 开 |
| 指纹池 | Chrome / Edge / Safari / Firefox | chrome + edge + safari |
| 随机化浏览器指纹字段 | 同步随机化 UA、平台、系统版本等 | 开 |
| 退避重试基数 / 倍数 / 上限 | `基数 × 倍数^(n-1)`，受上限约束 | 2.0 / 2.0 / 60 |
| 每处理 N 个任务休眠 / 休眠时长 | 批次休眠，N=0 表示禁用 | 10 / 60 秒 |
| 作品间额外间隔（秒） | 每个作品处理完后的额外等待 | 0 |

> **指纹自洽性**：`curl_cffi` 的枚举里混有移动端与命名不规范的取值
> （`chrome99_android`、`safari17_0`、`chrome133a` 等），直接使用会产生
> 「声称 macOS 却用 Android 指纹」的矛盾画像。本项目按浏览器族正则筛选并显式推导版本号，
> 保证 TLS 指纹 / UA / 浏览器版本 / 平台 / 系统版本互相一致
> ——抖音的 `a_bogus` 签名会使用这些字段。
> TikTok 平台只轮换 Blink 内核族（Chrome / Edge），避免 UA 结构偏离内核预期。

#### 去重优化

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| 下载前预过滤已下载作品 | 请求前用批量 SQL 比对下载记录，命中即剔除（零流量） | 开 |
| 输出跳过明细日志 | 逐条打印被跳过的作品 ID | 开 |
| 严格校验本地文件 | 记录存在但文件缺失时判为失效并重新下载（需扫描目录） | 关 |
| 启用下载记录（去重基础） | 对应内核 `Record`；关闭后全部去重失效 | 开 |
| 记录运行日志到文件 | 保存日志到 Volume 目录 | 关 |

#### 平台开关 / 高级设置

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| 启用抖音平台 / 启用 TikTok 平台 | 平台开关 | 开 |
| FFmpeg 可执行文件 | 用于转码 / 合成 | 空 |
| 直播清晰度 | 多档用 `,` 分隔；留空则由内核决定 | 空 |
| 自定义启动命令 | 下载完成后执行 | 空 |
| 浏览器指纹字段组 | TLS 指纹、UA、平台、语言、内核版本、地区等 20+ 项 | 见界面默认值 |

> 指纹字段在开启「启用指纹轮换」时由程序自动生成一套自洽取值；
> 需要固定画像时，可关闭轮换后手工填写。

---

## 六、原项目介绍

本项目**不是**独立的下载器，而是下面这个开源项目的图形界面：

| 项 | 内容 |
| --- | --- |
| 项目名称 | **DouK-Downloader V5.8**（原 TikTokDownloader） |
| 作者 | JoeanAmier |
| 项目地址 | https://github.com/JoeanAmier/TikTokDownloader |
| 项目文档 | https://github.com/JoeanAmier/TikTokDownloader/wiki/Documentation |
| 开源许可 | GNU General Public License v3.0 |
| 功能 | 抖音 / TikTok 作品、账号主页、合集、直播的批量下载与数据采集 |

内核在本仓库中以 **git submodule** 形式引入（`upstream/`，@473c90f），
**未做任何修改**——所有下载、解析、签名、落盘逻辑均来自原项目。

本外壳仅新增：参数表单、日志面板、计数栏、文件名预览、
以及若干**可关闭**的运行时增强（见第二节）。

> 若只需命令行版本，请直接运行 `upstream/main.py` 或访问原项目主页。

---

## 七、常见问题（FAQ）

**Q：提示「Cookie 未登录」？**
A：Cookie 缺少 `sessionid_ss`（抖音）或 `sessionid`（TikTok）。重新从浏览器复制完整
Cookie，点「校验登录状态」确认；也可点「导入内核配置」从旧配置导入。

**Q：TikTok 一直超时？**
A：TikTok 通常需要代理。在 TikTok 分页的「网络请求」中填写代理地址。

**Q：日志里出现「[交互请求已自动跳过]」？**
A：内核某些分支需要终端交互（如直播清晰度选择）。GUI 无法交互，程序会安全跳过
（不会卡住）。直播录制请预先填写「直播清晰度」。

**Q：界面卡住不动？**
A：采集全部在后台线程执行。长时间无输出多为网络超时或正在退避重试，
可在日志区确认；也可先「停止」再调整「请求平均间隔」。

**Q：txt 里的 `#博主昵称` 行为什么没被处理？**
A：有意设计。程序只处理能解析出链接的行；注释行与说明文字会被忽略，
避免产生大量无效请求。直接填写裸 sec_user_id 仍会被保留。

**Q：博主改了昵称，历史文件夹和文件名会自动更新吗？**
A：会，前提是 `name_format` 勾选了「账号昵称」（默认已勾选）。
改名由内核 `mapping_data` 缓存驱动；勾选「昵称变更时同步重命名账号文件夹」后
文件夹名也会一起更新。
需注意：内核原始实现在默认配置下这段逻辑会抛 `FileNotFoundError`，
请保持「修复昵称变更改名缺陷」开启。已存在的同 UID 多昵称文件夹是上游
「只改文件名、不改文件夹名 + 按新昵称新建目录」造成的，新设置可避免继续产生。

**Q：日志出现「未能解析出任何作品 ID」，怎么排查？**
A：九成是**下载类型选错**。用 txt 读账号列表时，文件里是 `douyin.com/user/...`
账号主页链接，必须选**批量下载账号作品**；「批量下载链接作品」只认含 19 位
作品 ID 的作品链接。程序会在启动前自动识别并提示。

**Q：为什么之前跑一次要十几分钟？**
A：内核逐条解析链接的耗时（每条一次请求 + 反爬间隔）。现已优化为
**只对短链发请求**，完整链接直接提取作品 ID；短链解析另有进度与预估耗时提示。

**Q：双击「启动.bat」一闪而过（闪退）怎么办？**
A：脚本已按 cmd 解析要求重写（GBK + CRLF、不用 `goto`、块内不用 `&` 转义、
不调 `chcp`、末尾 `pause`）。若仍闪退，确认 `.venv\Scripts\python.exe`
是否存在，或直接运行 `.venv\Scripts\python.exe run.py` 看报错。

**Q：怎么彻底停用某项优化？**
A：「反爬虫增强」里关总开关、「去重优化」里关「下载前预过滤已下载作品」、
「文件命名与保存位置」里关「修复昵称变更改名缺陷」，即完全回到内核原始行为。

**Q：打包版把配置和数据存在哪？**
A：exe 所在目录（`config\`、`Volume\`、`Downloads\`、`backup\`），
不在临时目录。可用环境变量 `DOUK_DATA_DIR` 指定其它位置。
运行 `DouK-Downloader-GUI.exe --selftest` 可验证完整性。

**Q：收款码图片为什么没显示？**
A：收款码属个人信息，**不随 Release 的 exe 分发**。把 `微信收款码.JPG`、
`支付宝收款码.JPG` 放到程序所在目录即可显示；文件缺失时显示占位提示。
仓库根目录若包含这两张图片，属作者个人收款信息，二次分发时请自行移除。

---

## 八、免责声明

本图形界面仅是对开源项目 DouK-Downloader 的界面封装，未改变其功能与用途。

使用者在使用本项目时必须严格遵守 GNU General Public License v3.0，
并自行研究相关法律法规，确保使用行为合法合规。
本项目不参与、不支持、不认可任何非法内容的获取或分发，
不对使用者涉及的数据收集、存储、传输等处理活动的合规性承担责任。

**本外壳补充说明：**

1. 本外壳不改变内核的功能与用途，仅提供参数配置、日志展示与运行时增强；
2. 使用者应自行确保使用行为符合当地法律法规及平台服务条款；
3. 因使用本工具产生的任何风险与后果，均由使用者自行承担；
4. 本工具仅供学习研究与技术交流，请勿用于任何侵犯他人合法权益的用途。

完整的免责声明请阅读内核项目文档。

---

## 九、许可证

本项目与上游内核 [DouK-Downloader](https://github.com/JoeanAmier/TikTokDownloader)
均以 **GNU General Public License v3.0** 发布（见根目录 [`LICENSE`](LICENSE)）。

`upstream/` 目录以上游仓库的 git submodule 形式引入，未做任何修改。

---

**作者**：HuYin · aihuyin@qq.com
