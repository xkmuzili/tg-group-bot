"""
Telegram Group Management Bot - Configuration File
Telegram 群管理机器人 - 配置文件

Copy this file to config.py and fill in your settings.
复制此文件为 config.py 并填入你的设置。
"""

# ==================== Basic Configuration / 基础配置 ====================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Super Admin Telegram User ID(s) / 超级管理员 Telegram User ID
SUPER_ADMIN_IDS = [123456789]

# ==================== Points Configuration / 积分配置 ====================
DAILY_CHECKIN_POINTS = 10      # Daily checkin reward / 每日签到奖励
CHECKIN_STREAK_BONUS = 5       # Streak bonus per day / 连续签到每日加成
MAX_STREAK_BONUS = 50          # Max streak bonus / 最大连续签到加成
MESSAGE_POINTS = 1             # Points per message / 每条消息积分
MESSAGE_POINTS_INTERVAL = 60   # Seconds between message points / 消息积分间隔(秒)
MAX_MESSAGE_POINTS_PER_DAY = 20 # Max daily message points / 每日消息积分上限
INVITE_POINTS = 50             # Points per invite / 每次邀请积分

# ==================== Anti-Spam Configuration / 广告过滤配置 ====================
NEW_USER_RESTRICT_SECONDS = 300  # New user restriction time (0=verification only) / 新用户限制时间(0=仅验证)
WARN_THRESHOLD = 3               # Warnings before mute / 警告次数阈值
MUTE_THRESHOLD = 5               # Mutes before ban / 禁言次数阈值
BAN_THRESHOLD = 10               # Bans before permanent ban / 封禁次数阈值
MAX_MESSAGE_LENGTH = 2000        # Max message length / 最大消息长度
MAX_LINKS_COUNT = 3              # Max links per message / 单条消息最大链接数

# ==================== Banned Words / 违禁词配置 ====================
DEFAULT_BANNED_WORDS = [
    "加我", "私聊我", "加群", "免费领", "日赚", "月入",
    "兼职", "赚钱", "刷单", "代理", "招商", "加盟",
    "优惠券", "折扣", "促销", "清仓", "秒杀",
    "约炮", "约P", "一夜情",
    "博彩", "彩票", "棋牌",
    "投资理财", "稳赚不赔", "高回报", "低风险高收益",
    "VPN", "翻墙", "科学上网",
]

# ==================== Welcome Message / 欢迎消息配置 ====================
DEFAULT_WELCOME_MESSAGE = (
    "👋 欢迎 {name} 加入本群！\n\n"
    "📋 请遵守群规：\n"
    "1. 禁止发布广告和垃圾信息\n"
    "2. 禁止人身攻击和骚扰\n"
    "3. 禁止发布色情、赌博等违法内容\n"
    "4. 保持友善交流\n\n"
    "💡 使用 /checkin 签到获取积分\n"
    "💡 使用 /help 查看所有命令"
)

# ==================== Shop Items / 商城配置 ====================
DEFAULT_SHOP_ITEMS = {
    "mute_card": {"name": "🔇 禁言卡", "description": "可解除一次禁言", "price": 100, "stock": 999},
    "double_card": {"name": "📈 双倍积分卡", "description": "24小时内签到双倍积分", "price": 200, "stock": 999},
    "vip_card": {"name": "👑 VIP会员卡", "description": "7天VIP会员", "price": 500, "stock": 999},
    "shield_card": {"name": "🛡️ 广告防护盾", "description": "24小时内免受广告检测处罚", "price": 300, "stock": 999},
}

# ==================== Database / 数据库配置 ====================
DATABASE_PATH = "group_bot.db"
