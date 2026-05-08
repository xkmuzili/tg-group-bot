"""
Telegram 群管理机器人 - 配置文件模板
复制此文件为 config.py 并填入你的设置
"""

# ==================== 基础配置 ====================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
SUPER_ADMIN_IDS = [123456789]

# ==================== 积分配置 ====================
DAILY_CHECKIN_POINTS = 10
CHECKIN_STREAK_BONUS = 5
MAX_STREAK_BONUS = 50
MESSAGE_POINTS = 1
MESSAGE_POINTS_INTERVAL = 60
MAX_MESSAGE_POINTS_PER_DAY = 20
INVITE_POINTS = 50

# ==================== 广告过滤配置 ====================
NEW_USER_RESTRICT_SECONDS = 300
WARN_THRESHOLD = 3
MUTE_THRESHOLD = 5
BAN_THRESHOLD = 10
MAX_MESSAGE_LENGTH = 2000
MAX_LINKS_COUNT = 3

# ==================== 违禁词配置 ====================
DEFAULT_BANNED_WORDS = [
    "加我", "私聊我", "加群", "免费领", "日赚", "月入",
    "兼职", "赚钱", "刷单", "代理", "招商", "加盟",
    "优惠券", "折扣", "促销", "清仓", "秒杀",
    "约炮", "约P", "一夜情",
    "博彩", "彩票", "棋牌",
    "投资理财", "稳赚不赔", "高回报", "低风险高收益",
    "VPN", "翻墙", "科学上网",
]

# ==================== 欢迎消息配置 ====================
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

# ==================== 商城配置 ====================
DEFAULT_SHOP_ITEMS = {
    "mute_card": {"name": "🔇 禁言卡", "description": "可解除一次禁言", "price": 100, "stock": 999},
    "double_card": {"name": "📈 双倍积分卡", "description": "24小时内签到双倍积分", "price": 200, "stock": 999},
    "vip_card": {"name": "👑 VIP会员卡", "description": "7天VIP会员", "price": 500, "stock": 999},
    "shield_card": {"name": "🛡️ 广告防护盾", "description": "24小时内免受广告检测处罚", "price": 300, "stock": 999},
}

# ==================== 机器人信息 ====================
BOT_NAME_CN = "星辰守望者"
BOT_NAME_EN = "Stellar Warden"
BOT_DESCRIPTION = (
    "🛡️ 智能群管理 | 🎯 广告查杀 | 🏆 积分系统\n"
    "✅ 入群验证 | 🛒 积分商城 | 👥 群组统计"
)
AVATAR_PATH = "avatar.png"

# ==================== 授权系统配置 ====================
LICENSE_ENFORCE = False  # True=强制执行授权, False=测试阶段免费
TRIAL_DAYS = 30

# USDT 支付
USDT_WALLET = "YOUR_USDT_WALLET_ADDRESS"
USDT_NETWORK = "TRC20"
ADMIN_CONTACT = "@your_username"

# 授权套餐
LICENSE_PLANS = {
    "1m": {"name": "月度授权", "days": 30, "price_usdt": 5, "emoji": "🌙"},
    "3m": {"name": "季度授权", "days": 90, "price_usdt": 12, "emoji": "🌟"},
    "6m": {"name": "半年授权", "days": 180, "price_usdt": 20, "emoji": "💫"},
    "1y": {"name": "年度授权", "days": 365, "price_usdt": 35, "emoji": "👑"},
}

# ==================== 后台管理面板 ====================
ADMIN_PANEL_HOST = "0.0.0.0"
ADMIN_PANEL_PORT = 5000
ADMIN_PANEL_SECRET_KEY = "change-this-to-random-string"
ADMIN_PANEL_USERNAME = "admin"
ADMIN_PANEL_PASSWORD = "change-this-password"

# ==================== 数据库配置 ====================
DATABASE_PATH = "group_bot.db"
