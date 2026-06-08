"""
Known package → display name mapping for common Chinese apps.
Falls back to a cleaned-up version of the package name.
"""

KNOWN_APPS: dict[str, str] = {
    # 社交
    "com.tencent.mm": "微信",
    "com.tencent.mobileqq": "QQ",
    "com.sina.weibo": "微博",
    "com.zhihu.android": "知乎",
    "com.douban.frodo": "豆瓣",
    # 短视频 / 视频
    "com.ss.android.ugc.aweme": "抖音",
    "com.ss.android.ugc.livelite": "抖音极速版",
    "tv.danmaku.bili": "B站",
    "com.kuaishou.nebula": "快手",
    "com.duowan.kiwi": "虎牙直播",
    "air.tv.douyu.android": "斗鱼直播",
    # 阅读 / 内容
    "com.xingin.xhs": "小红书",
    "com.dragon.read": "番茄小说",
    "com.qidian.QDReader": "起点读书",
    "com.kmxs.reader": "七猫小说",
    "com.hupu.games": "虎扑",
    "com.max.xiaoheihe": "小黑盒",
    "com.smzdm.client.android": "什么值得买",
    # 音乐
    "com.netease.cloudmusic": "网易云音乐",
    "com.tencent.qqmusic": "QQ音乐",
    "com.kugou.android": "酷狗音乐",
    "com.heytap.music": "OPPO音乐",
    # 工具 / 效率
    "cn.ticktick.task": "滴答清单",
    "com.microsoft.office.onenote": "OneNote",
    "com.microsoft.office.outlook": "Outlook",
    "cn.wps.moffice_eng": "WPS Office",
    "com.tencent.wemeet.app": "腾讯会议",
    "com.ss.android.lark": "飞书",
    # 购物
    "com.taobao.taobao": "淘宝",
    "com.jd.jrapp": "京东金融",
    "com.jingdong.app.mall": "京东",
    "com.achievo.vipshop": "唯品会",
    "com.xunmeng.pinduoduo": "拼多多",
    "com.wuba.zhuanzhuan": "转转",
    "com.sankuai.meituan": "美团",
    "com.dianping.v1": "大众点评",
    # 支付 / 金融
    "com.eg.android.AlipayGphone": "支付宝",
    "com.tencent.mtt": "QQ浏览器",
    "com.finshell.wallet": "OPPO钱包",
    # 出行 / 地图
    "com.autonavi.minimap": "高德地图",
    "com.baidu.BaiduMap": "百度地图",
    "com.umetrip.android.msky.app": "航旅纵横",
    "com.MobileTicket": "铁路12306",
    # 相机 / 图片
    "com.arashivision.insta360akiko": "Insta360",
    # 浏览器
    "com.quark.browser": "夸克",
    "com.microsoft.bing": "Edge",
    "com.microsoft.emmx": "Edge",
    "org.mozilla.firefox": "Firefox",
    "com.UCMobile": "UC浏览器",
    "com.baidu.browser.apps": "百度浏览器",
    # 游戏中心 / 游戏
    "com.yyzy.nearme.gamecenter": "OPPO游戏中心",
    "com.oplus.games": "OPPO游戏空间",
    # AI / 大模型
    "com.deepseek.chat": "DeepSeek",
    "com.openai.chatgpt": "ChatGPT",
    "com.kimi.chat": "Kimi",
    "com.baidu.searchbox": "百度",
    "com.google.android.apps.bard": "Gemini",
    # 云 / 同步
    "com.synology.projectkailash.cn": "Synology Photos",
    "com.qq.qcloud": "腾讯云",
    "com.microsoft.skydrive": "OneDrive",
    "com.dropbox.android": "Dropbox",
    # 健康 / 运动
    "com.heytap.health": "OPPO健康",
    "com.huawei.health": "华为健康",
    "run.pace.app": "佩斯",
    "com.garmin.android.apps.connectmobile": "Garmin Connect",
    # 餐饮 / 外卖
    "com.sankuai.meituan.takeoutnew": "美团外卖",
    "com.baidu.waimai": "百度外卖",
    "com.koubei.android": "口碑",
    "com.yum.kfc": "KFC",
    "com.mcdonalds.mobileapp": "麦当劳",
    "com.heytap.foodie": "OPPO吃喝",
    # 电商 / 生活
    "com.ss.android.ugc.commerce": "抖音商城",
    "com.ss.android.ugc.ugclivelite": "抖音生活",
    "com.taobao.idlefish": "闲鱼",
    "com.kaola": "考拉海购",
    "com.netease.kaola": "考拉",
    # 办公 / 通讯
    "com.microsoft.teams": "Teams",
    "com.slack": "Slack",
    "com.dingtalk.android": "钉钉",
    "com.alibaba.android.rimet": "钉钉",
    # 新闻 / 资讯
    "com.ss.android.article.news": "今日头条",
    "com.toutiao.lite": "头条极速版",
    "com.ifeng.news2": "凤凰新闻",
    "com.tencent.news": "腾讯新闻",
    "com.netease.newsreader.activity": "网易新闻",
    # 系统（特意保留的）
    "com.android.launcher": "桌面",
    "com.oplus.launcher": "OPPO桌面",
    "com.oppo.launcher": "OPPO桌面",
    "com.android.mms": "短信",
    "com.android.dialer": "电话",
    "com.google.android.dialer": "电话",
    "com.android.camera2": "相机",
    "com.oplus.camera": "OPPO相机",
    "com.heytap.market": "应用市场",
    "com.oplus.appmarket": "应用市场",
    "com.android.settings": "设置",
    "com.oplus.settings": "OPPO设置",
    # 其他
    "com.xiaomi.smarthome": "米家",
    "com.cainiao.wireless": "菜鸟裹裹",
    "com.itlong.wanglife": "云杠铃",
    "com.larus.nova": "Nova启动器",
    "com.microsoft.appmanager": "手机连接",
    "com.lfb.android.footprint": "足迹",
    "com.tencent.hunyuan.app.chat": "腾讯元宝",
    "com.cherry_ai.cherry_studio_app": "Cherry Studio",
    "com.bytedance.trae.cn": "Trae",
    "ai.looki.lifelog": "Lifelog",
    "ai.plaud.android.plaud.zh": "PLAUD",
    "com.fqyw.screen_memo": "截图备忘",
    "com.heytap.pictureframe": "OPPO相框",
    "com.google.android.apps.photos": "Google相册",
    "com.meitu.meipai": "美拍",
    "com.meitu.meicam": "美颜相机",
    "com.zuimeia.camera360": "Camera360",
    # OPPO/ColorOS 系统服务（保留可见的）
    "com.heytap.speechassist": "小布助手",
    "com.coloros.speechassist": "小布助手",
    "com.oplus.speechassist": "小布助手",
    "com.ailingo.bluetoothaudioassistant": "蓝牙音频助手",
    "com.heytap.bluetoothaudioassistant": "蓝牙音频助手",
    "com.coloros.bluetoothaudioassistant": "蓝牙音频助手",
    "com.heytap.weather": "天气",
    "com.coloros.weather2": "天气",
    "com.coloros.weather": "天气",
    "com.oplus.weather": "天气",
    "com.heytap.htms": "热点/话题",
    "com.coloros.htms": "热点/话题",
    "com.heytap.tsmservice": "TSM服务",
    "com.ss.android.ugc.lifeservices": "抖音生活服务",
    "com.coloros.lifeservices": "生活服务",
    "com.oplus.lifeservices": "生活服务",
    "com.coloros.alarmclock": "时钟/闹钟",
    "com.oplus.alarmclock": "时钟/闹钟",
    "com.android.alarmclock": "时钟/闹钟",
    "com.google.android.googlequicksearchbox": "Google搜索",
    "com.heytap.quicksearchbox": "搜索",
    "com.coloros.quicksearchbox": "搜索",
    "com.tencent.weread": "微信读书",
    "com.heytap.community": "OPPO社区",
    "com.oplus.community": "OPPO社区",
    "com.psbc.mbank": "邮储银行",
    "com.sinovatech.unicom.ui": "中国联通",
    "com.lemon.lv": "剪映",
    "com.ss.android.ugc.cut.mini": "剪映极速版",
    "com.jike.community": "即刻",
    "com.ruguoapp.jike": "即刻",
}


_GENERIC_SUFFIXES = {"app", "android", "main", "ui", "core", "service", "client",
                     "mobile", "phone", "pad", "lite", "pro", "plus"}


def get_app_name(package: str) -> str:
    if package in KNOWN_APPS:
        return KNOWN_APPS[package]
    parts = package.split(".")
    # Try last non-generic segment first
    for part in reversed(parts):
        if len(part) > 3 and part.lower() not in _GENERIC_SUFFIXES:
            return part
    # Fall back to full package if all segments are generic/short
    return package
