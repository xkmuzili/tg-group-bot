"""
Telegram 群管理机器人 - 完整版
功能：广告过滤、违禁词检测、签到积分、积分商城、群管理
"""
import asyncio
import logging
import sqlite3
import time
import re
from datetime import datetime, timedelta
from collections import defaultdict

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatPermissions, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatType

# ==================== 配置 ====================
BOT_TOKEN = "8633849209:AAF7NnqWlMX6PQXBqj8TUgd_oPIj78KJJ_c"
SUPER_ADMIN_IDS = [6299747858]

# 积分配置
DAILY_CHECKIN_POINTS = 10
CHECKIN_STREAK_BONUS = 5
MAX_STREAK_BONUS = 50
MESSAGE_POINTS = 1
MESSAGE_POINTS_INTERVAL = 60
MAX_MESSAGE_POINTS_PER_DAY = 20
INVITE_POINTS = 50

# 广告过滤配置
NEW_USER_RESTRICT_SECONDS = 300
WARN_THRESHOLD = 3
MUTE_THRESHOLD = 5
BAN_THRESHOLD = 10
MAX_MESSAGE_LENGTH = 2000
MAX_LINKS_COUNT = 3

# 违禁词
DEFAULT_BANNED_WORDS = [
    "加我", "私聊我", "加群", "免费领", "日赚", "月入",
    "兼职", "赚钱", "刷单", "代理", "招商", "加盟",
    "优惠券", "折扣", "促销", "清仓", "秒杀",
    "约炮", "约P", "一夜情",
    "博彩", "彩票", "棋牌",
    "投资理财", "稳赚不赔", "高回报", "低风险高收益",
    "VPN", "翻墙", "科学上网",
]

# 欢迎消息
DEFAULT_WELCOME = (
    "\U0001f44b 欢迎 {name} 加入本群！\n\n"
    "\U0001f4cb 请遵守群规：\n"
    "1. 禁止发布广告和垃圾信息\n"
    "2. 禁止人身攻击和骚扰\n"
    "3. 禁止发布色情、赌博等违法内容\n"
    "4. 保持友善交流\n\n"
    "\U0001f4a1 使用 /checkin 签到获取积分\n"
    "\U0001f4a1 使用 /help 查看所有命令"
)

# 积分商城
DEFAULT_SHOP_ITEMS = {
    1: {"name": "自定义头衔", "price": 500, "stock": -1, "desc": "获得一个自定义群内头衔", "type": "title"},
    2: {"name": "禁言卡 (1小时)", "price": 200, "stock": 50, "desc": "可以对任意群成员禁言1小时", "type": "mute_card"},
    3: {"name": "免广告卡", "price": 300, "stock": 30, "desc": "24小时内不会被广告检测误判", "type": "anti_spam"},
    4: {"name": "签到双倍卡", "price": 400, "stock": 20, "desc": "下次签到获得双倍积分", "type": "double_checkin"},
    5: {"name": "VIP会员 (7天)", "price": 1000, "stock": 10, "desc": "7天VIP会员，签到积分x2", "type": "vip_7d"},
}

DATABASE_PATH = "/opt/tg-group-bot/group_bot.db"

# ==================== 日志 ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ==================== 数据库 ====================
class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            points INTEGER DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            checkin_streak INTEGER DEFAULT 0,
            last_checkin TEXT,
            last_message_time REAL DEFAULT 0,
            message_points_today INTEGER DEFAULT 0,
            message_points_date TEXT,
            warn_count INTEGER DEFAULT 0,
            mute_count INTEGER DEFAULT 0,
            ban_count INTEGER DEFAULT 0,
            is_vip INTEGER DEFAULT 0,
            vip_expire TEXT,
            title TEXT,
            inventory TEXT DEFAULT '{}'
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS shop_items (
            item_id INTEGER PRIMARY KEY,
            name TEXT,
            price INTEGER,
            stock INTEGER DEFAULT -1,
            description TEXT,
            type TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS group_config (
            chat_id INTEGER PRIMARY KEY,
            welcome_message TEXT,
            banned_words TEXT,
            anti_spam_enabled INTEGER DEFAULT 1,
            welcome_enabled INTEGER DEFAULT 1,
            points_enabled INTEGER DEFAULT 1
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            type TEXT,
            reason TEXT,
            timestamp TEXT,
            processed INTEGER DEFAULT 0
        )""")
        conn.commit()
        # 初始化商城
        for item_id, item in DEFAULT_SHOP_ITEMS.items():
            c.execute("SELECT COUNT(*) FROM shop_items WHERE item_id=?", (item_id,))
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO shop_items (item_id, name, price, stock, description, type) VALUES (?,?,?,?,?,?)",
                    (item_id, item["name"], item["price"], item["stock"], item["desc"], item["type"]))
        conn.commit()
        conn.close()

    def get_user(self, user_id):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
            row = c.fetchone()
        conn.close()
        return dict(row)

    def update_user(self, user_id, **kwargs):
        conn = self._get_conn()
        c = conn.cursor()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [user_id]
        c.execute(f"UPDATE users SET {sets} WHERE user_id=?", vals)
        conn.commit()
        conn.close()

    def add_points(self, user_id, amount):
        user = self.get_user(user_id)
        self.update_user(user_id,
            points=user["points"] + amount,
            total_points=user["total_points"] + amount)

    def get_group_config(self, chat_id):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM group_config WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO group_config (chat_id) VALUES (?)", (chat_id,))
            conn.commit()
            c.execute("SELECT * FROM group_config WHERE chat_id=?", (chat_id,))
            row = c.fetchone()
        conn.close()
        return dict(row)

    def update_group_config(self, chat_id, **kwargs):
        conn = self._get_conn()
        c = conn.cursor()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [chat_id]
        c.execute(f"UPDATE group_config SET {sets} WHERE chat_id=?", vals)
        conn.commit()
        conn.close()

    def get_banned_words(self, chat_id):
        config = self.get_group_config(chat_id)
        custom = config.get("banned_words", "")
        words = list(DEFAULT_BANNED_WORDS)
        if custom:
            words.extend([w.strip() for w in custom.split(",") if w.strip()])
        return words

    def add_violation(self, user_id, chat_id, vtype, reason=""):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO violations (user_id, chat_id, type, reason, timestamp) VALUES (?,?,?,?,?)",
            (user_id, chat_id, vtype, reason, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def get_violation_count(self, user_id, chat_id, vtype=None):
        conn = self._get_conn()
        c = conn.cursor()
        if vtype:
            c.execute("SELECT COUNT(*) FROM violations WHERE user_id=? AND chat_id=? AND type=?", (user_id, chat_id, vtype))
        else:
            c.execute("SELECT COUNT(*) FROM violations WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        count = c.fetchone()[0]
        conn.close()
        return count

    def get_shop_items(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM shop_items ORDER BY item_id")
        items = [dict(row) for row in c.fetchall()]
        conn.close()
        return items

    def get_leaderboard(self, limit=10):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT user_id, username, first_name, points, total_points FROM users ORDER BY total_points DESC LIMIT ?", (limit,))
        rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return rows


db = Database()

# ==================== 工具函数 ====================
def is_super_admin(user_id):
    return user_id in SUPER_ADMIN_IDS

def get_display_name(user):
    if user.first_name:
        name = user.first_name
        if user.last_name:
            name += " " + user.last_name
        return name
    return user.username or str(user.id)

def restrict_chat(chat_id, user_id, until_date=None):
    """禁言用户"""
    permissions = ChatPermissions(can_send_messages=False)
    return ChatMember.restrict(chat_id, user_id, permissions, until_date=until_date)

def unrestrict_chat(chat_id, user_id):
    """解除禁言"""
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_invite_users=True,
        can_change_info=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )
    return ChatMember.restrict(chat_id, user_id, permissions)

# ==================== 命令处理 ====================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始命令"""
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "\U0001f916 你好！我是群管理机器人\n\n"
            "把我添加到 Telegram 群组中，我就能帮你管理群组。\n\n"
            "\U0001f4a1 功能列表：\n"
            "- 广告/垃圾信息自动过滤\n"
            "- 违禁词检测与处理\n"
            "- 签到积分系统\n"
            "- 积分商城\n"
            "- 群组数据统计\n\n"
            "使用 /help 查看所有命令"
        )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """帮助命令"""
    help_text = (
        "\U0001f4a1 **命令列表**\n\n"
        "**用户命令：**\n"
        "/checkin - 签到获取积分\n"
        "/points - 查看我的积分\n"
        "/rank - 查看积分排行榜\n"
        "/shop - 积分商城\n"
        "/inventory - 我的背包\n"
        "/help - 显示帮助\n\n"
        "**管理员命令：**\n"
        "/ban @user - 封禁用户\n"
        "/unban @user - 解封用户\n"
        "/mute @user - 禁言用户\n"
        "/unmute @user - 解除禁言\n"
        "/warn @user - 警告用户\n"
        "/stats - 群组统计\n"
        "/setwelcome <消息> - 设置欢迎语\n"
        "/togglewelcome - 开关欢迎语\n"
        "/togglepoints - 开关积分系统\n"
        "/addword <词> - 添加违禁词\n"
        "/delword <词> - 删除违禁词\n"
        "/wordlist - 查看违禁词列表\n"
        "/addpoints @user <数量> - 给用户加分\n"
        "/delpoints @user <数量> - 扣除用户积分\n"
        "/additem - 添加商城商品\n"
        "/reload - 重新加载配置"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

# ==================== 签到系统 ====================
async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """签到"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if user["last_checkin"] == today:
        await update.message.reply_text("\u274c 你今天已经签到过了，明天再来吧！")
        return

    # 检查连续签到
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    streak = user["checkin_streak"] + 1 if user["last_checkin"] == yesterday else 1
    streak = min(streak, 365)

    # 计算积分
    points = DAILY_CHECKIN_POINTS
    streak_bonus = min(streak * CHECKIN_STREAK_BONUS, MAX_STREAK_BONUS)
    if streak > 1:
        points += streak_bonus

    # VIP 双倍
    if user["is_vip"] and user["vip_expire"]:
        try:
            vip_expire = datetime.fromisoformat(user["vip_expire"])
            if now < vip_expire:
                points *= 2
        except:
            pass

    # 双倍卡
    inventory = eval(user.get("inventory", "{}")) if user.get("inventory") else {}
    if "double_checkin" in inventory and inventory["double_checkin"] > 0:
        points *= 2
        inventory["double_checkin"] -= 1
        if inventory["double_checkin"] <= 0:
            del inventory["double_checkin"]
        db.update_user(user_id, inventory=str(inventory))

    db.update_user(user_id,
        last_checkin=today,
        checkin_streak=streak)
    db.add_points(user_id, points)

    msg = (
        f"\u2705 签到成功！\n\n"
        f"\U0001f4b0 获得积分：**{points}**\n"
        f"\U0001f525 连续签到：**{streak}** 天\n"
    )
    if streak > 1:
        msg += f"\U0001f3c6 连签奖励：**+{streak_bonus}**\n"
    msg += f"\U0001f4b3 当前积分：**{user['points'] + points}**"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看积分"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    await update.message.reply_text(
        f"\U0001f4b3 **我的积分**\n\n"
        f"当前积分：**{user['points']}**\n"
        f"累计获得：**{user['total_points']}**\n"
        f"连续签到：**{user['checkin_streak']}** 天",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """积分排行榜"""
    rows = db.get_leaderboard(10)
    if not rows:
        await update.message.reply_text("暂无数据")
        return
    medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
    msg = "\U0001f3c6 **积分排行榜**\n\n"
    for i, row in enumerate(rows):
        name = row["first_name"] or row["username"] or str(row["user_id"])
        medal = medals[i] if i < 3 else f"{i+1}."
        msg += f"{medal} **{name}** - {row['total_points']} 分\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ==================== 积分商城 ====================
async def cmd_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """积分商城"""
    items = db.get_shop_items()
    if not items:
        await update.message.reply_text("商城暂无商品")
        return
    msg = "\U0001f6d2 **积分商城**\n\n"
    keyboard = []
    for item in items:
        stock_text = f"库存:{item['stock']}" if item['stock'] >= 0 else "库存:无限"
        msg += f"**{item['name']}** - {item['price']} 积分 ({stock_text})\n{item['description']}\n\n"
        keyboard.append([InlineKeyboardButton(
            f"{item['name']} - {item['price']}积分",
            callback_data=f"buy_{item['item_id']}"
        )])
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """购买商品"""
    query = update.callback_query
    await query.answer()
    item_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    user = db.get_user(user_id)
    items = db.get_shop_items()
    item = next((i for i in items if i["item_id"] == item_id), None)
    if not item:
        await query.edit_message_text("商品不存在")
        return
    if user["points"] < item["price"]:
        await query.edit_message_text(f"\u274c 积分不足！需要 {item['price']}，当前 {user['points']}")
        return
    if item["stock"] == 0:
        await query.edit_message_text("\u274c 该商品已售罄")
        return

    # 扣积分
    db.add_points(user_id, -item["price"])

    # 更新库存
    if item["stock"] > 0:
        conn = db._get_conn()
        c = conn.cursor()
        c.execute("UPDATE shop_items SET stock=stock-1 WHERE item_id=?", (item_id,))
        conn.commit()
        conn.close()

    # 添加到背包
    inventory = eval(user.get("inventory", "{}")) if user.get("inventory") else {}
    item_type = item["type"]
    inventory[item_type] = inventory.get(item_type, 0) + 1
    db.update_user(user_id, inventory=str(inventory))

    await query.edit_message_text(
        f"\u2705 购买成功！\n\n"
        f"商品：{item['name']}\n"
        f"花费：{item['price']} 积分\n"
        f"剩余积分：{user['points'] - item['price']}"
    )

async def cmd_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """我的背包"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    inventory = eval(user.get("inventory", "{}")) if user.get("inventory") else {}
    if not inventory:
        await update.message.reply_text("\U0001f392 背包是空的，去商城逛逛吧！")
        return
    item_names = {
        "title": "自定义头衔",
        "mute_card": "禁言卡",
        "anti_spam": "免广告卡",
        "double_checkin": "签到双倍卡",
        "vip_7d": "VIP会员 (7天)",
    }
    msg = "\U0001f392 **我的背包**\n\n"
    for item_type, count in inventory.items():
        if count > 0:
            name = item_names.get(item_type, item_type)
            msg += f"- {name} x{count}\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# ==================== 管理员命令 ====================
async def _get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取目标用户"""
    if context.args:
        arg = context.args[0]
        if arg.startswith("@"):
            return arg[1:]  # 返回 username
        try:
            return int(arg)  # 返回 user_id
        except:
            pass
    # 回复消息中的用户
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    return None

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """封禁用户"""
    if not await _check_admin(update):
        return
    target = await _get_target_user(update, context)
    if not target:
        await update.message.reply_text("用法：/ban @user 或回复用户消息")
        return
    try:
        await update.effective_chat.ban_member(target)
        db.update_user(target if isinstance(target, int) else 0, ban_count=db.get_user(target if isinstance(target, int) else 0).get("ban_count", 0) + 1)
        await update.message.reply_text(f"\u2705 已封禁用户 {target}")
    except Exception as e:
        await update.message.reply_text(f"\u274c 封禁失败：{e}")

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解封用户"""
    if not await _check_admin(update):
        return
    target = await _get_target_user(update, context)
    if not target:
        await update.message.reply_text("用法：/unban @user")
        return
    try:
        await update.effective_chat.unban_member(target)
        await update.message.reply_text(f"\u2705 已解封用户 {target}")
    except Exception as e:
        await update.message.reply_text(f"\u274c 解封失败：{e}")

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """禁言用户"""
    if not await _check_admin(update):
        return
    target = await _get_target_user(update, context)
    if not target:
        await update.message.reply_text("用法：/mute @user 或回复用户消息")
        return
    try:
        permissions = ChatPermissions(can_send_messages=False)
        until = None
        if context.args and len(context.args) > 1:
            try:
                minutes = int(context.args[-1])
                until = datetime.now() + timedelta(minutes=minutes)
            except:
                pass
        await update.effective_chat.restrict_member(target, permissions, until_date=until)
        await update.message.reply_text(f"\u2705 已禁言用户 {target}")
    except Exception as e:
        await update.message.reply_text(f"\u274c 禁言失败：{e}")

async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解除禁言"""
    if not await _check_admin(update):
        return
    target = await _get_target_user(update, context)
    if not target:
        await update.message.reply_text("用法：/unmute @user")
        return
    try:
        permissions = ChatPermissions(can_send_messages=True)
        await update.effective_chat.restrict_member(target, permissions)
        await update.message.reply_text(f"\u2705 已解除禁言 {target}")
    except Exception as e:
        await update.message.reply_text(f"\u274c 解除禁言失败：{e}")

async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """警告用户"""
    if not await _check_admin(update):
        return
    target = await _get_target_user(update, context)
    if not target:
        await update.message.reply_text("用法：/warn @user 或回复用户消息")
        return
    user_id = target if isinstance(target, int) else 0
    user = db.get_user(user_id)
    new_warns = user["warn_count"] + 1
    db.update_user(user_id, warn_count=new_warns)
    db.add_violation(user_id, update.effective_chat.id, "warn", "管理员警告")

    msg = f"\u26a0\ufe0f 警告用户 {target}\n当前警告次数：{new_warns}/{WARN_THRESHOLD}"
    if new_warns >= WARN_THRESHOLD:
        try:
            permissions = ChatPermissions(can_send_messages=False)
            await update.effective_chat.restrict_member(target, permissions)
            db.update_user(user_id, mute_count=user["mute_count"] + 1)
            msg += "\n\u274c 已达到警告上限，自动禁言"
        except:
            msg += "\n\u274c 自动禁言失败"
    await update.message.reply_text(msg)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """群组统计"""
    if not await _check_admin(update):
        return
    conn = db._get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM violations")
    total_violations = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM violations WHERE type='warn'")
    total_warns = c.fetchone()[0]
    c.execute("SELECT SUM(points) FROM users")
    total_points = c.fetchone()[0] or 0
    conn.close()
    await update.message.reply_text(
        f"\U0001f4ca **群组统计**\n\n"
        f"注册用户：{total_users}\n"
        f"总违规次数：{total_violations}\n"
        f"总警告次数：{total_warns}\n"
        f"总积分流通：{total_points}",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置欢迎语"""
    if not await _check_admin(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/setwelcome 欢迎消息（支持 {name} 变量）")
        return
    welcome = " ".join(context.args)
    db.update_group_config(update.effective_chat.id, welcome_message=welcome)
    await update.message.reply_text(f"\u2705 欢迎语已更新")

async def cmd_togglewelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开关欢迎语"""
    if not await _check_admin(update):
        return
    config = db.get_group_config(update.effective_chat.id)
    new_val = 0 if config["welcome_enabled"] else 1
    db.update_group_config(update.effective_chat.id, welcome_enabled=new_val)
    status = "开启" if new_val else "关闭"
    await update.message.reply_text(f"\u2705 欢迎语已{status}")

async def cmd_togglepoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开关积分系统"""
    if not await _check_admin(update):
        return
    config = db.get_group_config(update.effective_chat.id)
    new_val = 0 if config["points_enabled"] else 1
    db.update_group_config(update.effective_chat.id, points_enabled=new_val)
    status = "开启" if new_val else "关闭"
    await update.message.reply_text(f"\u2705 积分系统已{status}")

async def cmd_addword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加违禁词"""
    if not await _check_admin(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/addword 违禁词")
        return
    word = " ".join(context.args)
    config = db.get_group_config(update.effective_chat.id)
    existing = config.get("banned_words", "")
    if word in (existing.split(",") if existing else []):
        await update.message.reply_text("该词已在违禁列表中")
        return
    new_words = f"{existing},{word}" if existing else word
    db.update_group_config(update.effective_chat.id, banned_words=new_words)
    await update.message.reply_text(f"\u2705 已添加违禁词：{word}")

async def cmd_delword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """删除违禁词"""
    if not await _check_admin(update):
        return
    if not context.args:
        await update.message.reply_text("用法：/delword 违禁词")
        return
    word = " ".join(context.args)
    config = db.get_group_config(update.effective_chat.id)
    existing = config.get("banned_words", "")
    if not existing:
        await update.message.reply_text("自定义违禁词列表为空")
        return
    words = [w.strip() for w in existing.split(",") if w.strip() and w.strip() != word]
    db.update_group_config(update.effective_chat.id, banned_words=",".join(words))
    await update.message.reply_text(f"\u2705 已删除违禁词：{word}")

async def cmd_wordlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看违禁词列表"""
    if not await _check_admin(update):
        return
    config = db.get_group_config(update.effective_chat.id)
    custom = config.get("banned_words", "")
    msg = f"\U0001f6ab **违禁词列表**\n\n"
    msg += f"**内置违禁词** ({len(DEFAULT_BANNED_WORDS)} 个)：\n"
    msg += ", ".join(DEFAULT_BANNED_WORDS[:20]) + "...\n\n"
    if custom:
        msg += f"**自定义违禁词**：\n{custom}"
    else:
        msg += "暂无自定义违禁词"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_addpoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """给用户加分"""
    if not await _check_admin(update):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("用法：/addpoints @user <数量>")
        return
    target = await _get_target_user(update, context)
    if not target:
        await update.message.reply_text("请指定用户")
        return
    try:
        amount = int(context.args[-1])
    except:
        await update.message.reply_text("请输入有效的积分数量")
        return
    user_id = target if isinstance(target, int) else 0
    db.add_points(user_id, amount)
    await update.message.reply_text(f"\u2705 已给 {target} 增加 {amount} 积分")

async def cmd_delpoints(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """扣除用户积分"""
    if not await _check_admin(update):
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("用法：/delpoints @user <数量>")
        return
    target = await _get_target_user(update, context)
    if not target:
        await update.message.reply_text("请指定用户")
        return
    try:
        amount = int(context.args[-1])
    except:
        await update.message.reply_text("请输入有效的积分数量")
        return
    user_id = target if isinstance(target, int) else 0
    db.add_points(user_id, -amount)
    await update.message.reply_text(f"\u2705 已扣除 {target} {amount} 积分")

async def cmd_additem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加商城商品"""
    if not await _check_admin(update):
        return
    await update.message.reply_text(
        "添加商品功能请使用数据库直接操作\n"
        "格式：/additem 名称 价格 库存(-1无限) 描述 类型"
    )

async def cmd_reload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """重新加载配置"""
    if not await _check_admin(update):
        return
    await update.message.reply_text("\u2705 配置已重新加载")

async def _check_admin(update: Update):
    """检查是否为管理员"""
    user_id = update.effective_user.id
    if is_super_admin(user_id):
        return True
    try:
        member = await update.effective_chat.get_member(user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

# ==================== 消息处理 ====================
async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """新成员加入"""
    if not update.message or not update.message.new_chat_members:
        return
    chat_id = update.effective_chat.id
    config = db.get_group_config(chat_id)
    if not config["welcome_enabled"]:
        return

    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        name = get_display_name(member)
        welcome = config.get("welcome_message", DEFAULT_WELCOME).replace("{name}", name)
        await update.message.reply_text(welcome)

        # 限制新用户发消息
        try:
            until = datetime.now() + timedelta(seconds=NEW_USER_RESTRICT_SECONDS)
            permissions = ChatPermissions(can_send_messages=False)
            await update.effective_chat.restrict_member(member.id, permissions, until_date=until)
        except:
            pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理所有消息"""
    if not update.message or update.effective_chat.type == "private":
        return

    user = update.effective_user
    if user.is_bot:
        return

    chat_id = update.effective_chat.id
    user_id = user.id
    text = update.message.text or ""

    # 注册用户
    db.get_user(user_id)
    db.update_user(user_id, username=user.username, first_name=get_display_name(user))

    config = db.get_group_config(chat_id)

    # 1. 广告过滤
    if config["anti_spam_enabled"]:
        if await _check_spam(update, context, config):
            return

    # 2. 违禁词检测
    if await _check_banned_words(update, context, config):
        return

    # 3. 积分系统
    if config["points_enabled"]:
        await _handle_points(update, context, config)

async def _check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """检查广告/垃圾信息"""
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    # 检查 VIP 免广告
    user_data = db.get_user(user_id)
    if user_data.get("is_vip"):
        try:
            vip_expire = datetime.fromisoformat(user_data.get("vip_expire", ""))
            if datetime.now() < vip_expire:
                return False
        except:
            pass

    # 检查免广告卡
    inventory = eval(user_data.get("inventory", "{}")) if user_data.get("inventory") else {}
    if "anti_spam" in inventory and inventory["anti_spam"] > 0:
        return False

    reasons = []

    # 消息过长
    if len(text) > MAX_MESSAGE_LENGTH:
        reasons.append("消息过长")

    # 链接过多
    links = re.findall(r'https?://\S+|t\.me/\S+|@\w+', text)
    if len(links) > MAX_LINKS_COUNT:
        reasons.append("链接过多")

    # 特征广告词
    spam_patterns = [
        r'加我', r'私聊我', r'免费领', r'日赚\d+', r'月入\d+',
        r'兼职', r'刷单', r'代理', r'招商', r'加盟',
        r'优惠券', r'折扣', r'促销', r'清仓', r'秒杀',
        r'博彩', r'彩票', r'棋牌', r'约炮',
    ]
    for pattern in spam_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            reasons.append(f"疑似广告 ({pattern})")
            break

    # 大量 emoji / 特殊字符
    emoji_count = len(re.findall(r'[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f900-\U0001f9ff]', text))
    if emoji_count > 10:
        reasons.append("过多emoji")

    if not reasons:
        return False

    # 记录违规
    reason_str = "; ".join(reasons)
    db.add_violation(user_id, chat_id, "spam", reason_str)
    violation_count = db.get_violation_count(user_id, chat_id, "spam")

    # 删除消息
    try:
        await update.message.delete()
    except:
        pass

    # 处理
    if violation_count >= BAN_THRESHOLD:
        try:
            await update.effective_chat.ban_member(user_id)
            await update.message.reply_text(
                f"\U0001f6ab 用户 {get_display_name(user)} 因多次发布垃圾信息已被封禁"
            )
        except:
            pass
    elif violation_count >= MUTE_THRESHOLD:
        try:
            permissions = ChatPermissions(can_send_messages=False)
            until = datetime.now() + timedelta(hours=1)
            await update.effective_chat.restrict_member(user_id, permissions, until_date=until)
            await update.message.reply_text(
                f"\u26a0\ufe0f 用户 {get_display_name(user)} 因发布垃圾信息已被禁言1小时"
            )
        except:
            pass
    else:
        db.update_user(user_id, warn_count=user_data.get("warn_count", 0) + 1)
        await update.message.reply_text(
            f"\u26a0\ufe0f {get_display_name(user)}，你的消息疑似垃圾信息，已被删除。"
            f"\n警告 {violation_count}/{WARN_THRESHOLD}",
            reply_to_message_id=update.message.message_id
        )
    return True

async def _check_banned_words(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """检查违禁词"""
    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    banned_words = db.get_banned_words(chat_id)
    found = [w for w in banned_words if w.lower() in text.lower()]

    if not found:
        return False

    # 删除消息
    try:
        await update.message.delete()
    except:
        pass

    db.add_violation(user_id, chat_id, "banned_word", ",".join(found))
    violation_count = db.get_violation_count(user_id, chat_id, "banned_word")
    user_data = db.get_user(user_id)

    if violation_count >= BAN_THRESHOLD:
        try:
            await update.effective_chat.ban_member(user_id)
            await update.message.reply_text(
                f"\U0001f6ab 用户 {get_display_name(user)} 因多次使用违禁词已被封禁"
            )
        except:
            pass
    elif violation_count >= MUTE_THRESHOLD:
        try:
            permissions = ChatPermissions(can_send_messages=False)
            until = datetime.now() + timedelta(hours=1)
            await update.effective_chat.restrict_member(user_id, permissions, until_date=until)
            await update.message.reply_text(
                f"\u26a0\ufe0f 用户 {get_display_name(user)} 因使用违禁词已被禁言1小时"
            )
        except:
            pass
    else:
        db.update_user(user_id, warn_count=user_data.get("warn_count", 0) + 1)
        await update.message.reply_text(
            f"\u26a0\ufe0f {get_display_name(user)}，你的消息包含违禁词，已被删除。\n"
            f"违禁词：{', '.join(found)}\n"
            f"警告 {violation_count}/{WARN_THRESHOLD}",
            reply_to_message_id=update.message.message_id
        )
    return True

async def _handle_points(update: Update, context: ContextTypes.DEFAULT_TYPE, config):
    """处理积分"""
    user_id = update.effective_user.id
    user = db.get_user(user_id)
    now = time.time()
    today = datetime.now().strftime("%Y-%m-%d")

    # 消息积分
    if now - user.get("last_message_time", 0) >= MESSAGE_POINTS_INTERVAL:
        if user.get("message_points_date") != today:
            db.update_user(user_id, message_points_today=0, message_points_date=today)

        if user.get("message_points_today", 0) < MAX_MESSAGE_POINTS_PER_DAY:
            db.add_points(user_id, MESSAGE_POINTS)
            db.update_user(user_id,
                last_message_time=now,
                message_points_today=user.get("message_points_today", 0) + 1)

# ==================== 错误处理 ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """错误处理"""
    logger.error(f"Exception while handling an update: {context.error}")

# ==================== 主函数 ====================
def main():
    """启动机器人"""
    print("\U0001f916 正在启动 Telegram 群管理机器人...")

    app = Application.builder().token(BOT_TOKEN).build()

    # 命令处理
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("points", cmd_points))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("shop", cmd_shop))
    app.add_handler(CommandHandler("inventory", cmd_inventory))

    # 管理员命令
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("setwelcome", cmd_setwelcome))
    app.add_handler(CommandHandler("togglewelcome", cmd_togglewelcome))
    app.add_handler(CommandHandler("togglepoints", cmd_togglepoints))
    app.add_handler(CommandHandler("addword", cmd_addword))
    app.add_handler(CommandHandler("delword", cmd_delword))
    app.add_handler(CommandHandler("wordlist", cmd_wordlist))
    app.add_handler(CommandHandler("addpoints", cmd_addpoints))
    app.add_handler(CommandHandler("delpoints", cmd_delpoints))
    app.add_handler(CommandHandler("additem", cmd_additem))
    app.add_handler(CommandHandler("reload", cmd_reload))

    # 回调处理
    app.add_handler(CallbackQueryHandler(callback_buy, pattern=r"^buy_"))

    # 消息处理
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 错误处理
    app.add_error_handler(error_handler)

    print("\u2705 机器人已启动！")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
