"""参数规格定义（唯一事实来源）。

每条 :class:`Field` 描述一个界面设置项，包括：
    - 界面呈现形式（kind / choices / 取值范围）；
    - 持久化键（key）与上游 settings.json 的映射关系（upstream）；
    - 所属分页（platform：common / douyin / tiktok）；
    - 点击 “?” 图标后展示的描述与示例（help_desc / help_example）。

上游参数默认值严格对齐 ``upstream/src/config/settings.py`` 的 ``Settings.default``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

__all__ = [
    "Field",
    "SECTIONS",
    "FIELDS",
    "fields_for",
    "fields_of_section",
    "default_config",
    "SECTION_TITLES",
]

# --------------------------------------------------------------------------- #
# 分页与板块定义
# --------------------------------------------------------------------------- #

#: 分页标识 -> 中文名
PLATFORM_NAMES = {
    "douyin": "抖音",
    "tiktok": "TikTok",
}

#: 板块顺序（左侧设置区自上而下的排列顺序）
SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("task", "任务设置", "Cookie / 下载类型 / 链接传入方式"),
    ("download", "下载内容", "选择需要保存的作品元素"),
    ("naming", "文件命名与保存位置", "目录结构、文件名格式、数据存档"),
    ("network", "网络请求", "超时、重试、分块、代理、体积上限"),
    ("antispider", "反爬虫增强", "请求节流、指纹轮换、退避重试、批次休眠"),
    ("dedup", "去重优化", "已下载资源跳过策略"),
    ("platform", "平台开关", "启用或关闭对应平台功能"),
    ("advanced", "高级设置", "FFmpeg、浏览器指纹、自定义命令"),
)

SECTION_TITLES = {sid: title for sid, title, _ in SECTIONS}
SECTION_HINTS = {sid: hint for sid, _title, hint in SECTIONS}


# --------------------------------------------------------------------------- #
# 字段定义
# --------------------------------------------------------------------------- #


@dataclass
class Field:
    """单个设置项的描述。"""

    key: str
    label: str
    kind: str
    default: Any
    section: str
    help_desc: str
    #: 对应 upstream/settings.json 中的键；None 表示 GUI 专有参数
    upstream: str | None = None
    platform: str = "common"
    help_example: str = ""
    choices: Sequence[tuple[str, Any]] = ()
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    decimals: int = 0
    placeholder: str = ""
    rows: int = 4
    wide: bool = False
    suffix: str = ""
    depends_on: str | None = None
    #: 仅作为上游嵌套结构的分组标签使用
    group: str = ""
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 任务设置（按需求：Cookie -> 下载类型 -> 链接传入方式）
# --------------------------------------------------------------------------- #

_TASK_FIELDS: list[Field] = [
    Field(
        key="cookie",
        label="抖音 Cookie",
        kind="textblock",
        default="",
        section="task",
        platform="douyin",
        upstream="cookie",
        rows=3,
        help_desc=(
            "抖音账号的登录凭据。程序依赖 Cookie 完成 msToken / ttwid 生成、"
            "作品详情解析与鉴权；未填写时部分接口会返回风控或空数据。\n"
            "格式为浏览器请求头中 Cookie 字段的原始字符串，键值对之间用 “; ” 分隔。"
        ),
        help_example=(
            "示例：\n"
            "ttwid=1%7Cxxxx; msToken=abcdefghijklmnop; "
            "odin_tt=xxxx; passport_csrf_token=xxxx; sessionid_ss=xxxx\n\n"
            "获取方式：浏览器登录抖音网页版 → F12 开发者工具 → Network → "
            "任意 www.douyin.com 请求 → Request Headers → 复制完整 Cookie。\n"
            "关键字段是 sessionid_ss，缺少它程序会提示“Cookie 未登录”。"
        ),
    ),
    Field(
        key="cookie_tiktok",
        label="TikTok Cookie",
        kind="textblock",
        default="",
        platform="tiktok",
        section="task",
        upstream="cookie_tiktok",
        rows=3,
        help_desc=(
            "TikTok 账号的登录凭据，作用与抖音 Cookie 相同，但两个平台互不通用。\n"
            "需要科学上网环境，并确保 TikTok 站点可正常访问。"
        ),
        help_example=(
            "示例：\n"
            "tt_chain_token=xxxx; msToken=xxxx; ttwid=xxxx; "
            "sessionid=xxxx; tt_csrf_token=xxxx\n\n"
            "获取方式：浏览器登录 www.tiktok.com → F12 → Network → "
            "筛选 tiktok.com 请求 → 复制 Request Headers 中的 Cookie。\n"
            "关键字段是 sessionid，缺少它程序会提示“Cookie 未登录”。"
        ),
    ),
    Field(
        key="task_mode",
        label="下载类型",
        kind="choice",
        default="detail",
        section="task",
        platform="douyin",
        choices=(
            ("批量下载链接作品（视频 / 图集 / 实况）", "detail"),
            ("批量下载账号作品", "account"),
            ("批量下载合集作品", "mix"),
            ("获取直播拉流地址", "live"),
        ),
        help_desc=(
            "决定本次采集的业务模式，四种模式对应的上游处理流程不同。\n"
            "• 批量下载链接作品：逐条解析作品链接的 ID 并下载，最常用；\n"
            "• 批量下载账号作品：根据账号主页链接拉取该账号的发布 / 喜欢 / 收藏列表；\n"
            "• 批量下载合集作品：根据合集链接或合集内作品链接批量下载；\n"
            "• 获取直播拉流地址：解析直播间 FLV/M3U8 地址，并有条件地调用 FFmpeg 录制。"
        ),
        help_example=(
            "示例：\n"
            "只想下载几个指定视频 → 选择“批量下载链接作品”；\n"
            "想备份某个博主全部作品 → 选择“批量下载账号作品”；\n"
            "想下载一个合集 → 选择“批量下载合集作品”。"
        ),
    ),
    Field(
        key="task_mode_tiktok",
        label="下载类型",
        kind="choice",
        default="detail",
        section="task",
        platform="tiktok",
        choices=(
            ("批量下载链接作品（视频 / 图集 / 实况）", "detail"),
            ("批量下载账号作品", "account"),
            ("批量下载合集作品", "mix"),
            ("获取直播拉流地址", "live"),
        ),
        help_desc=(
            "决定本次采集的业务模式。TikTok 平台的合集解析依赖页面 HTML，"
            "需要可访问 tiktok.com 的网络环境；直播仅提供 FLV 拉流地址。"
        ),
        help_example=(
            "示例：\n"
            "https://www.tiktok.com/@user/video/7300000000000000000 "
            "→ 选择“批量下载链接作品”。"
        ),
    ),
    Field(
        key="link_source",
        label="链接传入方式",
        kind="choice",
        default="paste",
        section="task",
        platform="douyin",
        choices=(
            ("粘贴链接（在下方文本框直接粘贴）", "paste"),
            ("从本地 txt 文本读取", "file"),
        ),
        help_desc=(
            "指定待处理链接的来源。两种方式最终都会被解析为链接列表后逐个处理。\n"
            "• 粘贴链接：适合临时下载少量作品；\n"
            "• 从本地 txt 读取：适合大批量任务，每行一条链接（支持分享文案）。"
        ),
        help_example=(
            "示例：\n"
            "粘贴内容可以直接是 App 分享出来的整段文案：\n"
            "7.21 复制打开抖音，看看【某某某的作品】 https://v.douyin.com/xxxxx/ \n"
            "程序会自动从中提取链接。"
        ),
    ),
    Field(
        key="link_source_tiktok",
        label="链接传入方式",
        kind="choice",
        default="paste",
        section="task",
        platform="tiktok",
        choices=(
            ("粘贴链接（在下方文本框直接粘贴）", "paste"),
            ("从本地 txt 文本读取", "file"),
        ),
        help_desc=(
            "指定待处理链接的来源。txt 文件需为 UTF-8 编码，每行一条链接。"
        ),
        help_example=(
            "示例 txt 内容：\n"
            "https://www.tiktok.com/@user/video/7300000000000000000\n"
            "https://www.tiktok.com/@user/video/7300000000000000001"
        ),
    ),
    Field(
        key="link_text",
        label="作品链接",
        kind="textblock",
        default="",
        section="task",
        platform="douyin",
        rows=6,
        placeholder="每行一条作品链接，或直接粘贴 App 分享文案",
        help_desc="待采集的作品链接列表，支持每行一条，也支持直接粘贴包含链接的分享文案。",
        help_example=(
            "示例：\n"
            "https://v.douyin.com/iJxxxxxx/\n"
            "https://www.douyin.com/video/7300000000000000000"
        ),
    ),
    Field(
        key="link_text_tiktok",
        label="作品链接",
        kind="textblock",
        default="",
        section="task",
        platform="tiktok",
        rows=6,
        placeholder="每行一条 TikTok 作品链接",
        help_desc="待采集的 TikTok 作品 / 账号 / 合集链接，每行一条。",
        help_example=(
            "示例：\n"
            "https://www.tiktok.com/@user/video/7300000000000000000"
        ),
    ),
    Field(
        key="link_file",
        label="txt 文件路径",
        kind="openfile",
        default="",
        section="task",
        platform="douyin",
        help_desc="包含待采集链接的本地文本文件，需为 UTF-8 编码，每行一条链接。",
        help_example="示例：D:\\links\\douyin.txt",
    ),
    Field(
        key="link_file_tiktok",
        label="txt 文件路径",
        kind="openfile",
        default="",
        section="task",
        platform="tiktok",
        help_desc="包含待采集链接的本地文本文件，需为 UTF-8 编码，每行一条链接。",
        help_example="示例：D:\\links\\tiktok.txt",
    ),
    Field(
        key="account_tab",
        label="账号作品类型",
        kind="choice",
        default="post",
        section="task",
        platform="douyin",
        choices=(
            ("发布作品", "post"),
            ("喜欢作品", "favorite"),
            ("收藏作品", "collection"),
        ),
        help_desc=(
            "仅在“批量下载账号作品”模式下生效，决定采集账号主页的哪一个列表。\n"
            "采集“喜欢作品”与“收藏作品”需要登录状态且账号未设置隐私保护。"
        ),
        help_example="示例：想备份自己的点赞列表 → 选择“喜欢作品”，注意需要已登录的 Cookie。",
    ),
    Field(
        key="account_tab_tiktok",
        label="账号作品类型",
        kind="choice",
        default="post",
        section="task",
        platform="tiktok",
        choices=(
            ("发布作品", "post"),
            ("喜欢作品", "favorite"),
        ),
        help_desc="仅在“批量下载账号作品”模式下生效，决定采集账号的发布或喜欢列表。",
        help_example="示例：选择“发布作品”采集该账号公开视频。",
    ),
]


# --------------------------------------------------------------------------- #
# 下载内容
# --------------------------------------------------------------------------- #

_DOWNLOAD_FIELDS: list[Field] = [
    Field(
        key="download",
        label="启用文件下载",
        kind="bool",
        default=True,
        section="download",
        upstream="download",
        help_desc=(
            "总开关。关闭后程序只解析并记录作品信息，不下载任何媒体文件，"
            "适合只想采集元数据（配合 storage_format 存档）的场景。"
        ),
        help_example="示例：只想导出作品标题/点赞数等数据 → 关闭本项，并设置 storage_format 为 csv。",
    ),
    Field(
        key="music",
        label="下载作品音乐",
        kind="bool",
        default=False,
        section="download",
        upstream="music",
        help_desc="除视频/图集本体外，额外把作品使用的背景音乐作为独立文件保存（默认 mp3）。",
        help_example="示例：需要制作 BGM 素材库 → 勾选本项。",
    ),
    Field(
        key="static_cover",
        label="下载静态封面",
        kind="bool",
        default=False,
        section="download",
        upstream="static_cover",
        help_desc="额外保存作品的静态封面图，命名规则为“作品名.jpeg”。",
        help_example="示例：需要作品缩略图做索引 → 勾选本项。",
    ),
    Field(
        key="dynamic_cover",
        label="下载动态封面",
        kind="bool",
        default=False,
        section="download",
        upstream="dynamic_cover",
        help_desc="额外保存作品的动态封面（WebP 动图），部分作品不提供该资源。",
        help_example="示例：需要动图封面素材 → 勾选本项。",
    ),
    Field(
        key="original_quality",
        label="优先原画质量",
        kind="bool",
        default=False,
        section="download",
        upstream="original_quality",
        help_desc=(
            "在解析结果中优先使用最高码率（原画）的下载地址。\n"
            "开启后文件体积明显增大，且部分作品不提供原画地址时会自动回退。"
        ),
        help_example="示例：需要无损存档 → 勾选本项。",
    ),
    Field(
        key="folder_mode",
        label="按作品建独立文件夹",
        kind="bool",
        default=False,
        section="download",
        upstream="folder_mode",
        help_desc=(
            "开启后每个作品使用一个独立子文件夹存放其全部文件（视频、封面、音乐）；"
            "关闭时所有文件平铺在同一目录。"
        ),
        help_example="示例：图集作品图片较多，建议勾选本项以便归类。",
    ),
]


# --------------------------------------------------------------------------- #
# 文件命名与保存
# --------------------------------------------------------------------------- #

_NAMING_FIELDS: list[Field] = [
    Field(
        key="root",
        label="保存根目录",
        kind="directory",
        default="",
        section="naming",
        upstream="root",
        wide=True,
        help_desc=(
            "作品文件与数据存档的根目录。留空时使用上游内核目录下的 Volume 目录。\n"
            "建议填写一个容量充足的独立磁盘路径。"
        ),
        help_example="示例：D:\\DouK\\Download",
    ),
    Field(
        key="folder_name",
        label="默认文件夹名称",
        kind="text",
        default="Download",
        section="naming",
        upstream="folder_name",
        help_desc="“批量下载链接作品”模式下使用的文件夹名，其他模式使用 UID/MID 前缀目录。",
        help_example="示例：Download",
    ),
    Field(
        key="name_format",
        label="文件名组成",
        kind="multichoice",
        default=["create_time", "type", "nickname", "desc"],
        section="naming",
        upstream="name_format",
        wide=True,
        choices=(
            ("发布时间", "create_time"),
            ("作品类型", "type"),
            ("账号昵称", "nickname"),
            ("作品描述", "desc"),
            ("作品 ID", "id"),
            ("账号 UID", "uid"),
            ("自定义标记", "mark"),
        ),
        help_desc=(
            "决定生成的文件名由哪些字段拼接而成。\n"
            "**勾选的先后顺序就是拼接顺序**；取消后重新勾选即可调整位置。\n"
            "勾选顺序与当前效果会在下方“参考文件名”里实时显示。\n\n"
            "注意：\n"
            "• 包含“账号昵称”时，内核才会启用「昵称变更后自动重命名历史文件」；\n"
            "• 包含“自定义标记”时才会启用按标记重命名；\n"
            "• 建议至少保留“作品 ID”或“作品描述”之一，避免不同作品重名互相覆盖；\n"
            "• 勾选“作品 ID”虽然可保证唯一，但文件名会变得较长。"
        ),
        help_example=(
            "示例：依次勾选 发布时间 → 作品类型 → 账号昵称 → 作品描述，"
            "分隔符为 “-”，得到：\n"
            "2026-09-17 10.22.46-视频-某某某-今天天气不错.mp4"
        ),
    ),
    Field(
        key="split",
        label="文件名分隔符",
        kind="text",
        default="-",
        section="naming",
        upstream="split",
        help_desc="拼接文件名各字段时使用的分隔符，不能包含 Windows 非法字符。",
        help_example="示例：- 或 _ 或 “ ”（空格）",
    ),
    Field(
        key="name_length",
        label="文件名最大长度",
        kind="int",
        default=128,
        section="naming",
        upstream="name_length",
        minimum=32,
        maximum=255,
        help_desc="文件名（不含扩展名）的截断长度上限，超出部分会被裁掉。",
        help_example="示例：128",
    ),
    Field(
        key="desc_length",
        label="描述最大长度",
        kind="int",
        default=64,
        section="naming",
        upstream="desc_length",
        minimum=16,
        maximum=255,
        help_desc="作品描述参与命名时的截断长度，避免文件名过长。",
        help_example="示例：64",
    ),
    Field(
        key="truncate",
        label="日志显示截断长度",
        kind="int",
        default=50,
        section="naming",
        upstream="truncate",
        minimum=25,
        maximum=255,
        help_desc="日志中作品名称的显示长度上限，仅影响日志观感，不影响实际文件名。",
        help_example="示例：50",
    ),
    Field(
        key="date_format",
        label="时间格式",
        kind="text",
        default="%Y-%m-%d %H:%M:%S",
        section="naming",
        upstream="date_format",
        wide=True,
        help_desc="文件名中发布时间字段的格式化模板，遵循 Python strftime 规则。",
        help_example="示例：%Y-%m-%d %H:%M:%S → 2026-09-17 10:22:46；%Y%m%d → 20260917",
    ),
    Field(
        key="storage_format",
        label="数据存档格式",
        kind="choice",
        default="",
        section="naming",
        upstream="storage_format",
        choices=(
            ("不存档（仅下载媒体文件）", ""),
            ("CSV 文件", "csv"),
            ("Excel 文件（xlsx）", "xlsx"),
            ("SQLite 数据库", "sql"),
        ),
        help_desc=(
            "把采集到的作品元数据（标题、点赞数、下载地址等）额外写入结构化文件。\n"
            "留空则不产生任何数据文件。注意：部分采集类功能强制要求设置本项。"
        ),
        help_example="示例：选择“Excel 文件（xlsx）”后，作品数据会写入保存目录下的 Data 文件夹。",
    ),
    Field(
        key="fix_cache_rename",
        label="修复昵称变更改名缺陷",
        kind="bool",
        default=True,
        section="naming",
        help_desc=(
            "上游内核在“博主改昵称”后会尝试重命名历史文件，但在默认配置下会因\n"
            "目录定位错误抛出 FileNotFoundError 并中断该账号的处理。\n"
            "开启本项后由图形界面在运行时接管这段逻辑：\n"
            "• 修正目录定位，不再抛异常；\n"
            "• 文件改名遍历全部匹配项，不再因目录枚举顺序而只改一部分；\n"
            "• 避免旧值为空时把新值错误地插到文件名最前面。\n\n"
            "该机制只在 name_format 勾选了“账号昵称”或“自定义标记”时才有意义。"
        ),
        help_example=(
            "示例：博主“小明”改名为“大明”，历史文件名里的“小明”会被替换为“大明”。\n"
            "关闭本项则完全沿用内核原始行为（默认配置下该功能不可用）。"
        ),
    ),
    Field(
        key="rename_account_folder",
        label="昵称变更时同步重命名账号文件夹",
        kind="bool",
        default=True,
        section="naming",
        help_desc=(
            "上游在昵称变化时只改文件名、不改文件夹名，而下载阶段会按新昵称新建目录，\n"
            "导致同一个账号分裂出“旧昵称文件夹 + 新昵称空文件夹”两份目录。\n"
            "开启本项后，昵称变化时会把账号文件夹一并改名到新昵称，避免目录重复。\n\n"
            "仅在未设置“自定义标记”时生效（设置了标记时目录名以标记为准）。"
        ),
        help_example=(
            "示例：UID123_小明_发布作品 → UID123_大明_发布作品，\n"
            "同时把文件夹内文件名中的“小明”替换为“大明”。"
        ),
    ),
]


# --------------------------------------------------------------------------- #
# 网络请求
# --------------------------------------------------------------------------- #

_NETWORK_FIELDS: list[Field] = [
    Field(
        key="proxy",
        label="抖音代理",
        kind="text",
        default="",
        section="network",
        platform="douyin",
        upstream="proxy",
        wide=True,
        placeholder="http://127.0.0.1:7890 或 socks5://127.0.0.1:1080",
        help_desc=(
            "抖音请求使用的代理地址。程序在启动时会先做一次可用性探测，"
            "探测失败会提示“代理测试失败”并回退为直连。\n"
            "抖音通常无需代理，国内直连即可。"
        ),
        help_example="示例：http://127.0.0.1:7890",
    ),
    Field(
        key="proxy_tiktok",
        label="TikTok 代理",
        kind="text",
        default="",
        section="network",
        platform="tiktok",
        upstream="proxy_tiktok",
        wide=True,
        placeholder="http://127.0.0.1:7890",
        help_desc=(
            "TikTok 请求使用的代理地址。访问 TikTok 通常必须配置代理，否则会连接超时。"
        ),
        help_example="示例：http://127.0.0.1:7890",
    ),
    Field(
        key="timeout",
        label="请求超时（秒）",
        kind="int",
        default=10,
        section="network",
        upstream="timeout",
        minimum=2,
        maximum=300,
        help_desc="单个网络请求的最大等待时间，超过则判为超时并进入重试流程。",
        help_example="示例：10",
    ),
    Field(
        key="max_retry",
        label="最大重试次数",
        kind="int",
        default=5,
        section="network",
        upstream="max_retry",
        minimum=0,
        maximum=20,
        help_desc="单次请求失败后的重试上限，0 表示不重试。与反爬虫增强中的退避策略配合生效。",
        help_example="示例：5",
    ),
    Field(
        key="chunk",
        label="分块大小（字节）",
        kind="int",
        default=2097152,
        section="network",
        upstream="chunk",
        minimum=131072,
        maximum=104857600,
        step=131072,
        help_desc=(
            "从服务器接收数据时每次读取的分块大小，影响断点续传的粒度。\n"
            "网络不稳定时可调小以减少单次失败的重传量。"
        ),
        help_example="示例：2097152（即 2 MiB）",
    ),
    Field(
        key="max_size",
        label="单文件体积上限（字节）",
        kind="int",
        default=0,
        section="network",
        upstream="max_size",
        minimum=0,
        maximum=2147483647,
        step=1048576,
        help_desc=(
            "超过该体积的文件直接跳过下载，0 表示不限制。用于避免超长视频占用带宽。\n"
            "注意：受界面控件限制，上限为 2147483647 字节（约 2 GiB）。"
        ),
        help_example="示例：104857600（约 100 MiB）",
    ),
    Field(
        key="max_pages",
        label="最大翻页数",
        kind="int",
        default=0,
        section="network",
        upstream="max_pages",
        minimum=0,
        maximum=100000,
        help_desc="账号 / 合集等列表接口的最大翻页次数，0 表示由程序自动决定（内部按 99999 处理）。",
        help_example="示例：只想先试跑 2 页 → 填 2",
    ),
]


# --------------------------------------------------------------------------- #
# 反爬虫增强（GUI 专有参数）
# --------------------------------------------------------------------------- #

_ANTISPIDER_FIELDS: list[Field] = [
    Field(
        key="antispider_enable",
        label="启用反爬虫增强",
        kind="bool",
        default=True,
        section="antispider",
        help_desc=(
            "总开关。开启后会接管上游内核的请求节流、指纹轮换与重试退避逻辑；"
            "关闭则完全使用上游默认行为（固定约 6 秒随机间隔、固定指纹）。"
        ),
        help_example="示例：出现 403 / 空数据 / 需要频繁验证时 → 保持开启并适当加大请求间隔。",
    ),
    Field(
        key="wait_avg",
        label="请求平均间隔（秒）",
        kind="float",
        default=6.0,
        section="antispider",
        upstream="__wait_avg",
        minimum=0.5,
        maximum=120.0,
        step=0.5,
        decimals=1,
        help_desc=(
            "相邻两次“数据获取”请求之间的平均等待时间，实际值按对数正态分布抖动。\n"
            "该间隔仅作用于接口请求，不作用于文件下载。"
        ),
        help_example="示例：6.0 表示平均 6 秒一次；风控严重时可调到 15~30。",
    ),
    Field(
        key="wait_sigma",
        label="间隔抖动系数 σ",
        kind="float",
        default=0.5,
        section="antispider",
        upstream="__wait_sigma",
        minimum=0.0,
        maximum=1.5,
        step=0.05,
        decimals=2,
        help_desc=(
            "对数正态分布的形状参数。值越大，请求间隔的随机性越强，"
            "越不容易被识别为固定频率的脚本流量；0 表示固定间隔。"
        ),
        help_example="示例：0.5（上游默认）；需要更强随机性可设 0.8。",
    ),
    Field(
        key="wait_min",
        label="间隔下限（秒）",
        kind="float",
        default=1.5,
        section="antispider",
        upstream="__wait_min",
        minimum=0.1,
        maximum=60.0,
        step=0.1,
        decimals=1,
        help_desc="抖动结果的硬性下限，防止随机值过小导致瞬时请求过密。",
        help_example="示例：1.5",
    ),
    Field(
        key="wait_max",
        label="间隔上限（秒）",
        kind="float",
        default=33.3,
        section="antispider",
        upstream="__wait_max",
        minimum=1.0,
        maximum=600.0,
        step=0.5,
        decimals=1,
        help_desc="抖动结果的硬性上限，防止随机值过大导致任务长时间停滞。",
        help_example="示例：33.3（上游默认）",
    ),
    Field(
        key="max_workers",
        label="文件并发下载数",
        kind="int",
        default=4,
        section="antispider",
        upstream="__max_workers",
        minimum=1,
        maximum=16,
        help_desc=(
            "同时下载文件的最大任务数（对直播录制无效）。\n"
            "数值越高越快，但并发过高更容易触发风控与带宽拥塞，建议 2~4。"
        ),
        help_example="示例：4（上游默认）",
    ),
    Field(
        key="ua_rotate",
        label="启用指纹轮换",
        kind="bool",
        default=True,
        section="antispider",
        help_desc=(
            "每次任务启动时，从指纹池中随机挑选一个浏览器 TLS 指纹（impersonate），"
            "并随机化浏览器版本号等字段，避免长期使用同一指纹被聚类识别。"
        ),
        help_example="示例：连续几天批量采集同一平台时开启，可显著降低被限流的概率。",
    ),
    Field(
        key="impersonate_pool",
        label="指纹池",
        kind="multichoice",
        default=["chrome", "edge", "safari"],
        section="antispider",
        upstream="__impersonate_pool",
        wide=True,
        choices=(
            ("Chrome 系列", "chrome"),
            ("Edge 系列", "edge"),
            ("Safari 系列", "safari"),
            ("Firefox 系列", "firefox"),
        ),
        help_desc=(
            "参与轮换的浏览器指纹族。程序会在启动时枚举本机 curl_cffi 实际支持的版本，"
            "取每个族的最新若干版本组成候选集。"
        ),
        help_example="示例：同时勾选 Chrome 与 Edge，任务运行时随机使用其中之一。",
    ),
    Field(
        key="random_fingerprint",
        label="随机化浏览器指纹字段",
        kind="bool",
        default=True,
        section="antispider",
        help_desc=(
            "随机化 browser_info 中的语言、平台、系统版本、CPU 核心数等参与签名的字段，"
            "使每次运行的请求指纹更接近真实设备分布。"
        ),
        help_example="示例：开启后 browser_version 会在最新几个大版本之间随机取值。",
    ),
    Field(
        key="retry_backoff",
        label="退避重试基数（秒）",
        kind="float",
        default=2.0,
        section="antispider",
        upstream="__retry_backoff",
        minimum=0.0,
        maximum=120.0,
        step=0.5,
        decimals=1,
        help_desc=(
            "请求失败进入重试前的额外等待基数。等待时间 = 基数 × 倍数^(重试序号-1)，"
            "并受上限约束。相比固定间隔，指数退避更容易在服务端限流后恢复。"
        ),
        help_example="示例：基数 2、倍数 2、上限 60，则等待依次为 2、4、8、16、32 秒。",
    ),
    Field(
        key="retry_backoff_factor",
        label="退避倍数",
        kind="float",
        default=2.0,
        section="antispider",
        upstream="__retry_backoff_factor",
        minimum=1.0,
        maximum=5.0,
        step=0.5,
        decimals=1,
        help_desc="指数退避的增长倍数，1.0 表示线性固定间隔。",
        help_example="示例：2.0",
    ),
    Field(
        key="retry_backoff_cap",
        label="退避上限（秒）",
        kind="float",
        default=60.0,
        section="antispider",
        upstream="__retry_backoff_cap",
        minimum=1.0,
        maximum=900.0,
        step=1.0,
        decimals=1,
        help_desc="单次退避等待的时间上限，避免重试等待过久。",
        help_example="示例：60.0",
    ),
    Field(
        key="batch_suspend_every",
        label="每处理 N 个任务休眠",
        kind="int",
        default=10,
        section="antispider",
        upstream="__batch_suspend_every",
        minimum=0,
        maximum=10000,
        help_desc=(
            "在账号 / 合集等批量模式下，每处理 N 个对象主动休眠一段时间，"
            "模拟人工节奏以规避频率风控；0 表示禁用该策略。"
        ),
        help_example="示例：10 表示每处理 10 个账号休眠一次。",
    ),
    Field(
        key="batch_suspend_seconds",
        label="休眠时长（秒）",
        kind="float",
        default=60.0,
        section="antispider",
        upstream="__batch_suspend_seconds",
        minimum=1.0,
        maximum=3600.0,
        step=1.0,
        decimals=1,
        help_desc="单次批次休眠的持续时间。",
        help_example="示例：60.0",
    ),
    Field(
        key="inter_item_delay",
        label="作品间额外间隔（秒）",
        kind="float",
        default=0.0,
        section="antispider",
        upstream="__inter_item_delay",
        minimum=0.0,
        maximum=60.0,
        step=0.5,
        decimals=1,
        help_desc=(
            "在链接批量下载模式下，每处理完一个作品后额外等待的时间，"
            "用于进一步拉长请求节奏。0 表示不额外等待。"
        ),
        help_example="示例：1.5",
    ),
]


# --------------------------------------------------------------------------- #
# 去重优化
# --------------------------------------------------------------------------- #

_DEDUP_FIELDS: list[Field] = [
    Field(
        key="dedup_prefilter",
        label="下载前预过滤已下载作品",
        kind="bool",
        default=True,
        section="dedup",
        help_desc=(
            "【核心优化】在向接口请求作品详情之前，先比对本地下载记录，"
            "把已下载的作品 ID 从任务列表中剔除。\n"
            "上游内核是在拿到详情之后才做去重判断，因此重复任务仍会消耗一次接口请求；"
            "开启本项可让重复任务完全不产生网络流量。"
        ),
        help_example=(
            "示例：一个含 200 条链接的任务，其中 180 条此前已下载。\n"
            "关闭：仍然发起 200 次详情请求，仅跳过 180 次文件下载；\n"
            "开启：只发起 20 次详情请求，直接省去 90% 的接口流量。"
        ),
    ),
    Field(
        key="dedup_skip_log",
        label="输出跳过明细日志",
        kind="bool",
        default=True,
        section="dedup",
        help_desc="是否在日志中逐条打印被跳过的作品 ID，便于核对跳过是否符合预期。",
        help_example="示例：任务量大时可关闭以减少日志噪音。",
    ),
    Field(
        key="dedup_verify_file",
        label="严格校验本地文件",
        kind="bool",
        default=False,
        section="dedup",
        help_desc=(
            "下载记录与磁盘文件不一致时的兜底策略。\n"
            "开启后，若某作品 ID 存在于下载记录中，但保存目录下找不到任何包含该 ID 的文件，"
            "则视为记录失效，重新下载该作品。\n"
            "该功能需要扫描一次保存目录，目录内文件极多时会明显增加启动耗时。"
        ),
        help_example=(
            "示例：手工删除了部分下载文件，但 IDRecorder/数据库记录仍在 → 开启本项可自动补下。"
        ),
    ),
    Field(
        key="record_enable",
        label="启用下载记录（去重基础）",
        kind="bool",
        default=True,
        section="dedup",
        upstream="__record",
        help_desc=(
            "对应上游的 Record 开关。关闭后程序不再读写作品下载记录表，"
            "所有去重逻辑（包括预过滤）将失效。"
        ),
        help_example="示例：需要完整重新下载全部作品时，可临时关闭。",
    ),
    Field(
        key="logger_file",
        label="记录运行日志到文件",
        kind="bool",
        default=False,
        section="dedup",
        upstream="__logger",
        help_desc=(
            "对应上游的 Logger 开关。开启后除界面日志外，还会把完整日志写入"
            "保存目录下的 Logs 文件夹，便于事后排查。"
        ),
        help_example="示例：长时间批量采集建议开启。",
    ),
]


# --------------------------------------------------------------------------- #
# 平台开关
# --------------------------------------------------------------------------- #

_PLATFORM_FIELDS: list[Field] = [
    Field(
        key="douyin_platform",
        label="启用抖音平台",
        kind="bool",
        default=True,
        section="platform",
        upstream="douyin_platform",
        help_desc=(
            "关闭后程序不再初始化抖音相关请求参数（包括代理探测与 msToken 更新），"
            "只处理 TikTok 任务。"
        ),
        help_example="示例：只做 TikTok 采集 → 关闭本项可减少启动耗时。",
    ),
    Field(
        key="tiktok_platform",
        label="启用 TikTok 平台",
        kind="bool",
        default=True,
        section="platform",
        upstream="tiktok_platform",
        help_desc="关闭后程序不再初始化 TikTok 相关请求参数与代理探测。",
        help_example="示例：只做抖音采集 → 关闭本项。",
    ),
]


# --------------------------------------------------------------------------- #
# 高级设置
# --------------------------------------------------------------------------- #

_ADVANCED_FIELDS: list[Field] = [
    Field(
        key="ffmpeg",
        label="FFmpeg 可执行文件",
        kind="openfile",
        default="",
        section="advanced",
        upstream="ffmpeg",
        wide=True,
        help_desc=(
            "直播录制与音视频合并所依赖的 FFmpeg 可执行文件路径。\n"
            "留空时程序会尝试从系统 PATH 中查找；未检测到时直播下载功能不可用。"
        ),
        help_example="示例：C:\\ffmpeg\\bin\\ffmpeg.exe",
    ),
    Field(
        key="live_qualities",
        label="直播清晰度",
        kind="text",
        default="",
        section="advanced",
        upstream="live_qualities",
        help_desc=(
            "直播拉流时自动选择的清晰度。填写清晰度名称或序号；留空时程序会尝试交互式询问，"
            "在图形界面环境下将跳过直播下载（仅解析地址）。"
        ),
        help_example="示例：origin（原画）或 FULL_HD1 或序号 1",
    ),
    Field(
        key="run_command",
        label="自定义启动命令",
        kind="text",
        default="",
        section="advanced",
        upstream="run_command",
        wide=True,
        help_desc=(
            "预置的命令行参数，用于在上游内核中自动选择功能菜单项，内容为主菜单序号，"
            "多个序号以空格分隔。图形界面驱动内核时通常无需设置。"
        ),
        help_example="示例：1 1 表示依次选择第 1 个菜单的第 1 项（历史遗留参数）。",
    ),
    Field(
        key="browser_info_impersonate",
        label="抖音 TLS 指纹",
        kind="text",
        default="chrome146",
        section="advanced",
        platform="douyin",
        upstream="browser_info.impersonate",
        help_desc=(
            "curl_cffi 使用的浏览器 TLS 指纹标识。必须为 curl_cffi 支持的取值。\n"
            "开启“指纹轮换”后本项仅作为兜底值。"
        ),
        help_example="示例：chrome146、edge101、safari184",
    ),
    Field(
        key="browser_info_tiktok_impersonate",
        label="TikTok TLS 指纹",
        kind="text",
        default="chrome146",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.impersonate",
        help_desc="TikTok 平台使用的浏览器 TLS 指纹标识。",
        help_example="示例：chrome146",
    ),
    Field(
        key="browser_info_browser_language",
        label="浏览器语言",
        kind="text",
        default="zh-CN",
        section="advanced",
        platform="douyin",
        upstream="browser_info.browser_language",
        help_desc="参与签名与请求头的浏览器语言字段。",
        help_example="示例：zh-CN",
    ),
    Field(
        key="browser_info_browser_platform",
        label="浏览器平台",
        kind="text",
        default="MacIntel",
        section="advanced",
        platform="douyin",
        upstream="browser_info.browser_platform",
        help_desc="参与签名的浏览器平台标识，需与声明的操作系统保持一致。",
        help_example="示例：MacIntel 或 Win32",
    ),
    Field(
        key="browser_info_browser_name",
        label="浏览器名称",
        kind="text",
        default="Chrome",
        section="advanced",
        platform="douyin",
        upstream="browser_info.browser_name",
        help_desc="参与签名的浏览器名称。",
        help_example="示例：Chrome",
    ),
    Field(
        key="browser_info_browser_version",
        label="浏览器版本",
        kind="text",
        default="146.0.0.0",
        section="advanced",
        platform="douyin",
        upstream="browser_info.browser_version",
        help_desc="参与签名的浏览器版本号，需与 TLS 指纹的版本大致对应。",
        help_example="示例：146.0.0.0",
    ),
    Field(
        key="browser_info_pc_libra_divert",
        label="客户端分流标识",
        kind="text",
        default="Mac",
        section="advanced",
        platform="douyin",
        upstream="browser_info.pc_libra_divert",
        help_desc="抖音 Web 端参数 pc_libra_divert 的取值，与浏览器平台对应。",
        help_example="示例：Mac 或 Windows",
    ),
    Field(
        key="browser_info_engine_name",
        label="浏览器内核名称",
        kind="text",
        default="Blink",
        section="advanced",
        platform="douyin",
        upstream="browser_info.engine_name",
        help_desc="参与签名的渲染内核名称。",
        help_example="示例：Blink（Chrome/Edge）或 WebKit（Safari）",
    ),
    Field(
        key="browser_info_engine_version",
        label="浏览器内核版本",
        kind="text",
        default="146.0.0.0",
        section="advanced",
        platform="douyin",
        upstream="browser_info.engine_version",
        help_desc="参与签名的渲染内核版本号。",
        help_example="示例：146.0.0.0",
    ),
    Field(
        key="browser_info_os_name",
        label="操作系统名称",
        kind="text",
        default="Mac OS",
        section="advanced",
        platform="douyin",
        upstream="browser_info.os_name",
        help_desc="参与签名的操作系统名称。",
        help_example="示例：Mac OS 或 Windows",
    ),
    Field(
        key="browser_info_os_version",
        label="操作系统版本",
        kind="text",
        default="10.15.7",
        section="advanced",
        platform="douyin",
        upstream="browser_info.os_version",
        help_desc="参与签名的操作系统版本号。",
        help_example="示例：10.15.7 或 10",
    ),
    Field(
        key="browser_info_webid",
        label="WebID",
        kind="text",
        default="",
        section="advanced",
        platform="douyin",
        upstream="browser_info.webid",
        help_desc="抖音 WebID，留空时由程序根据 Cookie 自动推导，通常无需填写。",
        help_example="示例：留空即可",
    ),
    Field(
        key="browser_info_tiktok_device_id",
        label="TikTok 设备 ID",
        kind="text",
        default="",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.device_id",
        help_desc=(
            "TikTok 请求必填参数 device_id。留空时由程序自动生成随机值。\n"
            "若 TikTok 下载持续报错，可参照上游文档填入真实 device_id。"
        ),
        help_example="示例：7xxxxxxxxxxxxxxxxxx（19 位数字）",
    ),
    Field(
        key="browser_info_tiktok_priority_region",
        label="TikTok 优先地区",
        kind="text",
        default="US",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.priority_region",
        help_desc="参与 TikTok 请求签名的优先地区代码。",
        help_example="示例：US、JP、SG",
    ),
    Field(
        key="browser_info_tiktok_region",
        label="TikTok 地区",
        kind="text",
        default="US",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.region",
        help_desc="参与 TikTok 请求签名的地区代码，通常与优先地区一致。",
        help_example="示例：US",
    ),
    Field(
        key="browser_info_tiktok_tz_name",
        label="TikTok 时区",
        kind="text",
        default="Asia/Shanghai",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.tz_name",
        help_desc="参与 TikTok 请求签名的时区名称。",
        help_example="示例：Asia/Shanghai、America/New_York",
    ),
    Field(
        key="browser_info_tiktok_language",
        label="TikTok 语言",
        kind="text",
        default="zh-Hans",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.language",
        help_desc="参与 TikTok 请求接口的语言参数。",
        help_example="示例：zh-Hans 或 en",
    ),
    Field(
        key="browser_info_tiktok_app_language",
        label="TikTok 应用语言",
        kind="text",
        default="zh-Hans",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.app_language",
        help_desc="参与 TikTok 请求签名的应用语言参数。",
        help_example="示例：zh-Hans",
    ),
    Field(
        key="browser_info_tiktok_webcast_language",
        label="TikTok 直播语言",
        kind="text",
        default="zh-Hans",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.webcast_language",
        help_desc="TikTok 直播相关接口使用的语言参数。",
        help_example="示例：zh-Hans",
    ),
    Field(
        key="browser_info_tiktok_browser_language",
        label="TikTok 浏览器语言",
        kind="text",
        default="zh-CN",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.browser_language",
        help_desc="TikTok 请求头中的浏览器语言字段。",
        help_example="示例：zh-CN",
    ),
    Field(
        key="browser_info_tiktok_browser_name",
        label="TikTok 浏览器名称",
        kind="text",
        default="Mozilla",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.browser_name",
        help_desc="参与 TikTok 请求签名的浏览器名称。",
        help_example="示例：Mozilla",
    ),
    Field(
        key="browser_info_tiktok_browser_platform",
        label="TikTok 浏览器平台",
        kind="text",
        default="MacIntel",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.browser_platform",
        help_desc="参与 TikTok 请求签名的浏览器平台标识。",
        help_example="示例：MacIntel",
    ),
    Field(
        key="browser_info_tiktok_browser_version",
        label="TikTok 浏览器版本",
        kind="text",
        default=(
            "5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
        ),
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.browser_version",
        wide=True,
        help_desc="参与 TikTok 请求签名的完整浏览器 UA 版本串。",
        help_example="示例：5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/146.0.0.0",
    ),
    Field(
        key="browser_info_tiktok_os",
        label="TikTok 操作系统",
        kind="text",
        default="mac",
        section="advanced",
        platform="tiktok",
        upstream="browser_info_tiktok.os",
        help_desc="参与 TikTok 请求签名的操作系统标识。",
        help_example="示例：mac 或 windows",
    ),
]


# --------------------------------------------------------------------------- #
# 汇总
# --------------------------------------------------------------------------- #

FIELDS: list[Field] = (
    _TASK_FIELDS
    + _DOWNLOAD_FIELDS
    + _NAMING_FIELDS
    + _NETWORK_FIELDS
    + _ANTISPIDER_FIELDS
    + _DEDUP_FIELDS
    + _PLATFORM_FIELDS
    + _ADVANCED_FIELDS
)

# 以 "__" 开头的 upstream 值仅是「该参数由 GUI 侧接管、不写入 settings.json」的
# 内部标记，这里统一清空，避免在帮助弹窗中显示成内核配置键。
for _field in FIELDS:
    if _field.upstream and _field.upstream.startswith("__"):
        _field.upstream = None

_BY_KEY: dict[str, Field] = {f.key: f for f in FIELDS}


def fields_for(platform: str, section: str | None = None) -> list[Field]:
    """返回指定分页（及可选板块）下的字段列表，保持定义顺序。"""
    result = [
        f for f in FIELDS if f.platform in ("common", platform) and not f.extra.get("hidden")
    ]
    if section is not None:
        result = [f for f in result if f.section == section]
    return result


def fields_of_section(section: str, platform: str) -> list[Field]:
    """返回某个板块在指定分页下的字段。"""
    return fields_for(platform, section)


def default_config() -> dict[str, Any]:
    """构造 GUI 默认配置字典。"""
    return {f.key: _copy_default(f.default) for f in FIELDS}


def _copy_default(value: Any) -> Any:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        return dict(value)
    return value
