"""
Telegram 群管理机器人 - 主程序
功能：广告查杀、签到积分、积分兑换、群管理
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from html import escape

import aiosqlite

from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ChatMemberHandler, ContextTypes, filters,
)

import config
import database as db
import anti_spam

# ==================== 日志配置 ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ==================== 工具函数 ====================

def is_admin(user_id: int, chat_id: int = None) -> bool:
    """检查是否为超级管理员"""
    return user_id in config.SUPER_ADMIN_IDS


async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """从回复或参数中获取目标用户 ID"""
    msg = update.effective_message
    # 优先从回复消息获取
    if msg.reply_to_message:
        return msg.reply_to_message.from_user.id
    if context.args:
        arg = context.args[0]
        if arg.startswith("@"):
            # 通过 Telegram API 查找群成员
            try:
                username = arg[1:]  # 去掉 @
                chat = update.effective_chat
                member = await chat.get_member(username)
                return member.user.id
            except Exception:
                return None
        try:
            return int(arg)
        except ValueError:
            return None
    return None


async def get_target_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取目标用户信息，返回 (user_id, member_info) 或 (None, None)"""
    msg = update.effective_message
    if msg.reply_to_message:
        user = msg.reply_to_message.from_user
        try:
            member = await update.effective_chat.get_member(user.id)
            return user.id, member
        except Exception:
            return user.id, None
    if context.args:
        arg = context.args[0]
        if arg.startswith("@"):
            try:
                username = arg[1:]
                member = await update.effective_chat.get_member(username)
                return member.user.id, member
            except Exception:
                return None, None
        try:
            uid = int(arg)
            member = await update.effective_chat.get_member(uid)
            return uid, member
        except Exception:
            return None, None
    return None, None


# ==================== /start 命令 ====================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """主菜单 / 深度链接入口"""
    # 检查深度链接参数（如 verify_{chat_id}）
    args = context.args if context.args else []
    if args and args[0].startswith("verify_"):
        # 用户从群内验证按钮跳转过来
        try:
            target_chat_id = int(args[0].split("_", 1)[1])
        except (ValueError, IndexError):
            target_chat_id = None

        if target_chat_id:
            user_id = update.effective_user.id
            # 检查是否已验证
            if await db.is_verified(target_chat_id, user_id):
                text = "✅ 你已经验证过了，可以直接在群里发言！"
                await update.message.reply_text(text)
                return

            # 显示验证确认按钮
            keyboard = [
                [InlineKeyboardButton("✅ 确认验证", callback_data=f"confirm_verify_{target_chat_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            text = (
                f"🔐 **入群验证**\n\n"
                f"你好 {escape(update.effective_user.first_name)}！\n"
                f"请点击下方按钮完成验证\n\n"
                f"⚠️ 验证后即可在群里正常发言"
            )
            await update.message.reply_text(text, reply_markup=reply_markup)
            return

    # 正常主菜单
    keyboard = [
        [InlineKeyboardButton("📋 帮助", callback_data="help"),
         InlineKeyboardButton("📊 我的信息", callback_data="mymenu")],
        [InlineKeyboardButton("✅ 签到", callback_data="checkin"),
         InlineKeyboardButton("🏆 排行榜", callback_data="rank")],
        [InlineKeyboardButton("🛒 商城", callback_data="shop")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        f"🤖 星辰守望者 - 群管理机器人\n\n"
        f"👋 你好 {escape(update.effective_user.first_name)}！\n\n"
        f"💡 使用 /help 查看所有命令\n"
        f"💡 点击下方按钮快速操作"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)


# ==================== /help 命令 ====================

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """帮助信息"""
    text = (
        "📖 **使用帮助**\n\n"
        "**积分系统：**\n"
        "/checkin - 每日签到\n"
        "/points - 查看积分\n"
        "/rank - 积分排行\n"
        "/shop - 积分商城\n"
        "/exchange <物品ID> - 兑换商品\n"
        "/myitems - 我的物品\n\n"
        "**群管理（管理员）：**\n"
        "/mute <用户> - 禁言\n"
        "/unmute <用户> - 解除禁言\n"
        "/ban <用户> - 封禁\n"
        "/unban <用户> - 解封\n"
        "/kick <用户> - 踢出\n"
        "/userinfo <用户> - 查看用户信息\n"
        "/stats - 群组统计\n\n"
        "**群组设置（管理员）：**\n"
        "/setwelcome <消息> - 设置欢迎语\n"
        "/welcome - 查看欢迎语\n"
        "/antispam on/off - 广告防护开关\n"
        "/addword <词> - 添加违禁词\n"
        "/delword <词> - 删除违禁词\n"
        "/wordlist - 查看违禁词列表\n\n"
        "💡 回复某条消息使用命令可直接对该用户操作"
    )
    await update.message.reply_text(text)


# ==================== 积分系统命令 ====================

async def cmd_checkin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """每日签到"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    await db.ensure_user(chat_id, user_id, username, first_name)
    result = await db.checkin(chat_id, user_id)

    if result is None:
        await update.message.reply_text("❌ 你今天已经签到过了！")
        return

    text = (
        f"✅ 签到成功！\n\n"
        f"💰 获得积分: +{result['points']}\n"
        f"📅 连续签到: {result['streak']}天\n"
        f"📊 基础: {result['base']} + 连续奖励: {result['bonus']}"
    )
    await update.message.reply_text(text)


async def cmd_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看积分"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    user = await db.ensure_user(chat_id, user_id, username, first_name)
    text = (
        f"💰 **积分信息**\n\n"
        f"👤 用户: {escape(first_name)}\n"
        f"💎 当前积分: {user['points']}\n"
        f"📊 累计积分: {user['total_points']}\n"
        f"📅 连续签到: {user['checkin_streak']}天\n"
        f"⭐ 等级: {user['level']}"
    )
    await update.message.reply_text(text)


async def cmd_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """积分排行"""
    chat_id = update.effective_chat.id
    leaderboard = await db.get_leaderboard(chat_id, 10)

    if not leaderboard:
        await update.message.reply_text("📊 暂无排行数据")
        return

    text = "🏆 **积分排行榜**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, user in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f" {i+1}."
        name = user["first_name"] or user["username"] or str(user["user_id"])
        text += f"{medal} {escape(name)} - {user['points']}分\n"

    await update.message.reply_text(text)


async def cmd_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """积分商城"""
    items = await db.get_shop_items()
    text = "🛒 **积分商城**\n\n"
    for item_id, item in items.items():
        text += f"**{item['name']}**\n"
        text += f"  📝 {item['description']}\n"
        text += f"  💰 {item['price']}积分 | 库存: {item['stock']}\n"
        text += f"  🆔 `{item_id}`\n\n"
    text += "💡 使用 /exchange <物品ID> 兑换"
    await update.message.reply_text(text)


async def cmd_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """兑换商品"""
    if not context.args:
        await update.message.reply_text("❌ 用法: /exchange <物品ID>\n💡 使用 /shop 查看物品列表")
        return

    item_id = context.args[0]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    await db.ensure_user(chat_id, user_id, username, first_name)
    success, message = await db.buy_item(user_id, chat_id, item_id)

    if success:
        await update.message.reply_text(f"✅ {message}")
    else:
        await update.message.reply_text(f"❌ {message}")


async def cmd_myitems(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """我的物品"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    await db.ensure_user(chat_id, user_id, username, first_name)
    items = await db.get_user_items(chat_id, user_id)

    if not items:
        await update.message.reply_text("📦 你还没有任何物品\n💡 使用 /shop 查看商城")
        return

    text = "📦 **我的物品**\n\n"
    for item_id, item in items.items():
        text += f"**{item['name']}** x{item['count']}\n"
    await update.message.reply_text(text)


# ==================== 群管理命令 ====================

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """禁言用户"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    target_id, member = await get_target_user_info(update, context)
    if not target_id:
        await update.message.reply_text("❌ 请回复要禁言的用户，或 /mute @用户名")
        return

    if is_admin(target_id, chat_id):
        await update.message.reply_text("❌ 不能禁言管理员")
        return

    try:
        until = datetime.now() + timedelta(hours=1)
        await update.effective_chat.restrict_member(
            target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await db.set_muted(chat_id, target_id, True)
        await update.message.reply_text(f"🔇 已禁言用户 {target_id}（1小时）")
    except Exception as e:
        await update.message.reply_text(f"❌ 禁言失败: {e}")


async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解除禁言"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    target_id, member = await get_target_user_info(update, context)
    if not target_id:
        await update.message.reply_text("❌ 请回复要解除禁言的用户，或 /unmute @用户名")
        return

    try:
        await update.effective_chat.restrict_member(
            target_id,
            permissions=ChatPermissions(
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
                can_change_info=True,
                can_pin_messages=True,
                can_manage_topics=True,
            ),
        )
        await db.set_muted(chat_id, target_id, False)
        await update.message.reply_text(f"✅ 已解除禁言 {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ 解除禁言失败: {e}")


async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """封禁用户"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    target_id, member = await get_target_user_info(update, context)
    if not target_id:
        await update.message.reply_text("❌ 请回复要封禁的用户，或 /ban @用户名")
        return

    if is_admin(target_id, chat_id):
        await update.message.reply_text("❌ 不能封禁管理员")
        return

    try:
        await update.effective_chat.ban_member(target_id)
        await db.set_banned(chat_id, target_id, True)
        await update.message.reply_text(f"🚫 已封禁用户 {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ 封禁失败: {e}")


async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解封用户"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    target_id, member = await get_target_user_info(update, context)
    if not target_id:
        await update.message.reply_text("❌ 请回复要解封的用户，或 /unban @用户名")
        return

    try:
        await update.effective_chat.unban_member(target_id)
        await db.set_banned(chat_id, target_id, False)
        await update.message.reply_text(f"✅ 已解封用户 {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ 解封失败: {e}")


async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """踢出用户"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    target_id, member = await get_target_user_info(update, context)
    if not target_id:
        await update.message.reply_text("❌ 请回复要踢出的用户，或 /kick @用户名")
        return

    if is_admin(target_id, chat_id):
        await update.message.reply_text("❌ 不能踢出管理员")
        return

    try:
        await update.effective_chat.ban_member(target_id)
        await update.effective_chat.unban_member(target_id)
        await update.message.reply_text(f"👢 已踢出用户 {target_id}")
    except Exception as e:
        await update.message.reply_text(f"❌ 踢出失败: {e}")


async def cmd_userinfo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看用户信息"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username
    first_name = update.effective_user.first_name

    # 先确保自己在数据库中
    await db.ensure_user(chat_id, user_id, username, first_name)

    target_id, member = await get_target_user_info(update, context)
    if not target_id:
        await update.message.reply_text("❌ 请回复要查看的用户，或 /userinfo @用户名")
        return

    # 尝试从数据库获取
    user = await db.get_user_info(chat_id, target_id)

    # 从 Telegram API 获取基础信息
    try:
        member_info = await update.effective_chat.get_member(target_id)
        tg_user = member_info.user
        status = member_info.status
    except Exception:
        tg_user = None
        status = "unknown"

    name = ""
    uname = ""
    if tg_user:
        name = tg_user.first_name or ""
        uname = tg_user.username or ""
    elif user:
        name = user.get("first_name", "")
        uname = user.get("username", "")

    status_map = {
        "creator": "👑 群主",
        "administrator": "⭐ 管理员",
        "member": "👤 普通成员",
        "restricted": "🔇 受限",
        "kicked": "👢 已踢出",
        "banned": "🚫 已封禁",
        "left": "👋 已离开",
        "unknown": "❓ 未知",
    }
    status_text = status_map.get(status, status)

    text = f"👤 **用户信息**\n\n"
    text += f"🆔 ID: `{target_id}`\n"
    if name:
        text += f"📝 昵称: {escape(name)}\n"
    if uname:
        text += f"🔗 用户名: @{escape(uname)}\n"
    text += f"📊 状态: {status_text}\n"

    if user:
        text += f"\n💰 积分: {user.get('points', 0)}\n"
        text += f"📊 累计: {user.get('total_points', 0)}\n"
        text += f"📅 连续签到: {user.get('checkin_streak', 0)}天\n"
        text += f"⭐ 等级: {user.get('level', 1)}\n"
        text += f"⚠️ 警告: {user.get('warnings', 0)}次\n"
        if user.get("is_muted"):
            text += f"🔇 已禁言\n"
        if user.get("is_banned"):
            text += f"🚫 已封禁\n"
        if user.get("mute_card", 0) > 0:
            text += f"🎫 禁言卡: {user['mute_card']}张\n"
        if user.get("is_vip"):
            text += f"👑 VIP会员\n"
    else:
        text += f"\n📝 数据库中暂无记录（用户可能未发过消息）\n"

    await update.message.reply_text(text)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """群组统计"""
    chat_id = update.effective_chat.id
    stats = await db.get_group_stats(chat_id)

    text = (
        f"📊 **群组统计**\n\n"
        f"👥 总用户: {stats['total_users']}\n"
        f"🔇 已禁言: {stats['muted_users']}\n"
        f"🚫 已封禁: {stats['banned_users']}\n"
        f"⚠️ 总违规: {stats['total_violations']}\n"
        f"💰 总积分: {stats['total_points']}"
    )
    await update.message.reply_text(text)


# ==================== 群组设置命令 ====================

async def cmd_setwelcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """设置欢迎语"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    if not context.args:
        await update.message.reply_text("❌ 用法: /setwelcome <欢迎消息>\n💡 可用变量: {name} {chat_name}")
        return

    welcome_msg = " ".join(context.args)
    await db.update_group_settings(chat_id, welcome_message=welcome_msg)
    await update.message.reply_text(f"✅ 欢迎语已更新！\n\n预览:\n{welcome_msg}")


async def cmd_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看欢迎语"""
    chat_id = update.effective_chat.id
    settings = await db.get_group_settings(chat_id)
    welcome = settings.get("welcome_message") or config.DEFAULT_WELCOME_MESSAGE
    enabled = settings.get("welcome_enabled", 1)
    status = "✅ 开启" if enabled else "❌ 关闭"
    await update.message.reply_text(f"👋 **当前欢迎语** ({status})\n\n{welcome}")


async def cmd_antispam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """广告防护设置"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    if not context.args:
        settings = await db.get_group_settings(chat_id)
        enabled = settings.get("anti_spam_enabled", 1)
        status = "✅ 开启" if enabled else "❌ 关闭"
        await update.message.reply_text(
            f"🛡️ **广告防护** 当前状态: {status}\n\n"
            f"用法:\n"
            f"/antispam on - 开启防护\n"
            f"/antispam off - 关闭防护"
        )
        return

    arg = context.args[0].lower()
    if arg in ("on", "开启", "1", "true"):
        await db.update_group_settings(chat_id, anti_spam_enabled=1)
        await update.message.reply_text("✅ 广告防护已开启！")
    elif arg in ("off", "关闭", "0", "false"):
        await db.update_group_settings(chat_id, anti_spam_enabled=0)
        await update.message.reply_text("❌ 广告防护已关闭！")
    else:
        await update.message.reply_text("❌ 用法: /antispam on/off")


async def cmd_addword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加违禁词"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    if not context.args:
        await update.message.reply_text("❌ 用法: /addword <违禁词>")
        return

    word = " ".join(context.args)
    await db.add_banned_word(chat_id, word)
    await update.message.reply_text(f"✅ 已添加违禁词: {word}")


async def cmd_delword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """删除违禁词"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    if not context.args:
        await update.message.reply_text("❌ 用法: /delword <违禁词>")
        return

    word = " ".join(context.args)
    await db.remove_banned_word(chat_id, word)
    await update.message.reply_text(f"✅ 已删除违禁词: {word}")


async def cmd_wordlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看违禁词列表"""
    chat_id = update.effective_chat.id
    custom_words = await db.get_custom_banned_words(chat_id)

    text = "🚫 **违禁词列表**\n\n"
    text += f"📋 默认违禁词: {len(config.DEFAULT_BANNED_WORDS)}个\n"
    if custom_words:
        text += f"📝 自定义违禁词: {', '.join(custom_words)}\n"
    else:
        text += f"📝 自定义违禁词: 无\n"
    text += f"\n💡 使用 /addword 添加，/delword 删除"
    await update.message.reply_text(text)




async def cmd_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """管理员发验证链接到群里，用户点击跳转Bot验证"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    # 获取 bot username
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username

    # 统计未验证用户
    all_users = await db.get_all_group_users(chat_id)
    unverified = [u for u in all_users if not u.get("is_verified")]
    unverified_count = len(unverified)

    # 群里弹出验证按钮，用户点击跳转 Bot 私聊
    verify_url = f"https://t.me/{bot_username}?start=verify_{chat_id}"
    keyboard = [
        [InlineKeyboardButton("🔐 点击验证", url=verify_url)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🔐 **入群验证**\n\n"
        f"未验证用户: {unverified_count} 人\n"
        f"请点击下方按钮，跳转到 Bot 完成验证\n\n"
        f"⚠️ 验证后即可在群里正常发言",
        reply_markup=reply_markup
    )




# ==================== /keyword command ====================

async def cmd_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage keyword auto-reply rules"""
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("需要管理员权限")
        return
    chat_id = update.effective_chat.id
    args = context.args
    if not args:
        await update.message.reply_text(
            "关键词自动回复\n\n"
            "/keyword add 关键词 回复内容\n"
            "/keyword add:exact 精确关键词 回复\n"
            "/keyword add:startswith 前缀 回复\n"
            "/keyword del 关键词\n"
            "/keyword list"
        )
        return
    import sqlite3
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS keyword_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL, keyword TEXT NOT NULL,
        reply_text TEXT NOT NULL, match_type TEXT DEFAULT 'contains',
        enabled INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chat_id, keyword))""")
    conn.commit()
    action = args[0].lower()
    if action.startswith("add"):
        match_type = "contains"
        if ":" in action:
            mt = action.split(":")[1]
            if mt in ("exact", "startswith"):
                match_type = mt
        if len(args) < 3:
            await update.message.reply_text("用法: /keyword add 关键词 回复内容")
            conn.close()
            return
        keyword = args[1]
        reply_text = " ".join(args[2:])
        try:
            conn.execute(
                "INSERT OR REPLACE INTO keyword_replies (chat_id, keyword, reply_text, match_type) VALUES (?,?,?,?)",
                (chat_id, keyword, reply_text, match_type))
            conn.commit()
            await update.message.reply_text(f"已添加: {keyword} [{match_type}]")
        except Exception as e:
            await update.message.reply_text(f"失败: {e}")
    elif action == "del":
        if len(args) < 2:
            await update.message.reply_text("用法: /keyword del 关键词")
            conn.close()
            return
        cur = conn.execute("DELETE FROM keyword_replies WHERE chat_id=? AND keyword=?", (chat_id, args[1]))
        conn.commit()
        await update.message.reply_text("已删除" if cur.rowcount > 0 else "未找到")
    elif action == "list":
        rules = conn.execute("SELECT keyword, reply_text, match_type FROM keyword_replies WHERE chat_id=? AND enabled=1", (chat_id,)).fetchall()
        if not rules:
            await update.message.reply_text("暂无关键词规则")
        else:
            lines = []
            for i, r in enumerate(rules, 1):
                lines.append(f"{i}. [{r[2]}] {r[0]} -> {r[1][:50]}")
            await update.message.reply_text("关键词规则:\n" + "\n".join(lines))
    conn.close()




# ==================== /tempmute command ====================

async def cmd_tempmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Temporary mute: /tempmute @user minutes [reason]"""
    if not is_admin(update.effective_user.id, update.effective_chat.id):
        await update.message.reply_text("需要管理员权限")
        return
    chat_id = update.effective_chat.id
    args = context.args
    target_id = None
    target_name = ""
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_name = update.message.reply_to_message.from_user.first_name or ""
        minutes_str = args[0] if args else ""
        reason = " ".join(args[1:]) if len(args) > 1 else ""
    else:
        if len(args) < 2:
            await update.message.reply_text("用法: /tempmute @user 分钟数 [原因]\n或回复消息: /tempmute 分钟数")
            return
        user_arg = args[0]
        minutes_str = args[1]
        reason = " ".join(args[2:]) if len(args) > 2 else ""
        if user_arg.startswith("@"):
            try:
                member = await update.effective_chat.get_member(user_arg[1:])
                target_id = member.user.id
                target_name = member.user.first_name or ""
            except Exception:
                await update.message.reply_text("找不到该用户")
                return
        else:
            try:
                target_id = int(user_arg)
            except ValueError:
                await update.message.reply_text("无效用户ID")
                return
    try:
        minutes = int(minutes_str)
    except (ValueError, TypeError):
        await update.message.reply_text("无效的分钟数")
        return
    if minutes < 1 or minutes > 10080:
        await update.message.reply_text("范围: 1-10080 分钟")
        return
    if target_id == update.effective_user.id:
        await update.message.reply_text("不能禁言自己")
        return
    if is_admin(target_id, chat_id):
        await update.message.reply_text("不能禁言管理员")
        return
    from datetime import datetime, timedelta
    until_date = datetime.now() + timedelta(minutes=minutes)
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date)
        import sqlite3
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.execute("INSERT INTO violations (chat_id,user_id,reason,action,admin_id,created_at) VALUES (?,?,?,?,?,?)",
            (chat_id, target_id, reason or "临时禁言", f"tempmute_{minutes}min", update.effective_user.id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        rtext = f"\n原因: {reason}" if reason else ""
        await update.message.reply_text(f"已禁言 {escape(target_name)} {minutes} 分钟{rtext}")
    except Exception as e:
        await update.message.reply_text(f"禁言失败: {e}")


async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """新成员加入 - 入群验证（限制发言+弹窗提示）"""
    chat_id = update.effective_chat.id
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        # 确保用户在数据库中
        await db.ensure_user(chat_id, member.id, member.username, member.first_name)
        # 先限制发言：禁止发送文字、图片、贴纸等
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=member.id,
                permissions=ChatPermissions(
                    can_send_messages=False,
                    can_send_audios=False,
                    can_send_documents=False,
                    can_send_photos=False,
                    can_send_videos=False,
                    can_send_video_notes=False,
                    can_send_voice_notes=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False,
                    can_invite_users=False,
                    can_change_info=False,
                    can_pin_messages=False,
                    can_manage_topics=False,
                )
            )
        except Exception as e:
            print(f"[WARN] restrict_chat_member failed for {member.id}: {e}")
        # 发送验证提示消息
        name = member.first_name or member.username or "新成员"
        keyboard = [
            [InlineKeyboardButton("✅ 点击验证", callback_data=f"verify_{member.id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = (
            f"👋 欢迎 {escape(name)} 加入本群！\n\n"
            f"🔐 请先完成验证才能发言\n"
            f"点击下方按钮，我会私聊你完成验证\n\n"
            f"⚠️ 未验证用户将被限制发言"
        )
        await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """成员离开"""
    pass  # 可以添加告别消息


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理普通消息"""
    message = update.message
    if not message or not message.from_user:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # 确保用户在数据库中
    await db.ensure_user(chat_id, user_id, username, first_name)

    # 记录消息统计
    await db.record_message_stat(chat_id, user_id)

    # 白名单用户跳过所有检查
    if await db.is_whitelisted(chat_id, user_id):
        pass  # 白名单用户不受限制
    # 检查是否已验证（未验证用户拦截消息）
    if not is_admin(user_id, chat_id) and not await db.is_verified(chat_id, user_id):
        # 删除未验证用户的消息
        try:
            await message.delete()
        except Exception:
            pass
        # 每5条提醒一次（避免刷屏）
        import random
        if random.randint(1, 5) == 1:
            keyboard = [
                [InlineKeyboardButton("🔐 点击验证", callback_data=f"verify_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                f"⚠️ {escape(first_name)}，请先完成验证才能发言",
                reply_markup=reply_markup
            )
        return  # 不处理未验证用户的消息

    # CAPTCHA验证回复检查
    if message.text and message.text.strip().isdigit():
        captcha_ok = await db.verify_captcha(chat_id, user_id, message.text.strip())
        if captcha_ok:
            await db.set_verified(chat_id, user_id, True)
            # 解除群内发言限制
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=ChatPermissions(
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
                        can_change_info=True,
                        can_pin_messages=True,
                        can_manage_topics=True,
                    )
                )
            except Exception:
                pass
            await message.reply_text("✅ 验证成功！你现在可以在群里正常发言了")
            # 通知群聊
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ {escape(first_name)} 已完成验证，欢迎加入！"
                )
            except Exception:
                pass
            return

    # Check keyword auto-reply
    if message.text:
        keyword_reply = await check_keyword_reply(message, chat_id, message.text)
        if keyword_reply:
            await message.reply_text(keyword_reply)
            return

    settings = await db.get_group_settings(chat_id)
    if settings.get("anti_spam_enabled", 1):
        result = await anti_spam.check_message(message, user_id, chat_id)
        if result["is_spam"]:
            await message.delete()
            await anti_spam.handle_spam_message(message, user_id, chat_id, result)
            return

    # 积分：发消息获得积分
    user = await db.get_user_info(chat_id, user_id)
    if user:
        now = time.time()
        last_msg_time = user.get("last_message_time", 0)
        msg_points_date = user.get("message_points_date", "")
        today = datetime.now().strftime("%Y-%m-%d")

        if now - last_msg_time >= config.MESSAGE_POINTS_INTERVAL:
            if msg_points_date == today:
                if user.get("message_points_today", 0) < config.MAX_MESSAGE_POINTS_PER_DAY:
                    await db.add_points(chat_id, user_id, config.MESSAGE_POINTS)
                    await db.ensure_user(chat_id, user_id, username, first_name)
                    async with aiosqlite.connect(config.DATABASE_PATH) as db_conn:
                        await db_conn.execute(
                            "UPDATE group_users SET last_message_time=?, message_points_today=message_points_today+1 WHERE chat_id=? AND user_id=?",
                            (now, chat_id, user_id)
                        )
                        await db_conn.commit()
            else:
                await db.add_points(chat_id, user_id, config.MESSAGE_POINTS)
                async with aiosqlite.connect(config.DATABASE_PATH) as db_conn:
                    await db_conn.execute(
                        "UPDATE group_users SET last_message_time=?, message_points_today=1, message_points_date=? WHERE chat_id=? AND user_id=?",
                        (now, today, chat_id, user_id)
                    )
                    await db_conn.commit()


# ==================== 回调查询处理 ====================



# ==================== Keyword Auto-Reply ====================

async def check_keyword_reply(message, chat_id, text):
    """Check if message matches any keyword auto-reply rule"""
    import sqlite3
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        table_check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_replies'"
        ).fetchone()
        if not table_check:
            conn.close()
            return None
        rules = conn.execute(
            "SELECT keyword, reply_text, match_type FROM keyword_replies WHERE chat_id=? AND enabled=1",
            (chat_id,)
        ).fetchall()
        conn.close()
        text_lower = text.lower()
        for rule in rules:
            keyword = rule["keyword"].lower()
            match_type = rule["match_type"]
            matched = False
            if match_type == "exact" and text_lower == keyword:
                matched = True
            elif match_type == "contains" and keyword in text_lower:
                matched = True
            elif match_type == "startswith" and text_lower.startswith(keyword):
                matched = True
            if matched:
                return rule["reply_text"]
    except Exception:
        pass
    return None


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    data = query.data

    if data == "help":
        await cmd_help(update, context)
    elif data == "checkin":
        # 模拟 message
        update.message = query.message
        await cmd_checkin(update, context)
    elif data == "rank":
        update.message = query.message
        await cmd_rank(update, context)
    elif data == "shop":
        update.message = query.message
        await cmd_shop(update, context)
    elif data == "mymenu":
        user_id = query.from_user.id
        chat_id = query.message.chat.id
        user = await db.get_user_info(chat_id, user_id)
        if not user:
            user = await db.ensure_user(chat_id, user_id, query.from_user.username, query.from_user.first_name)
        text = (
            f"📊 **我的信息**\n\n"
            f"👤 {escape(query.from_user.first_name)}\n"
            f"💎 积分: {user.get('points', 0)}\n"
            f"📊 累计: {user.get('total_points', 0)}\n"
            f"📅 连续签到: {user.get('checkin_streak', 0)}天\n"
            f"⭐ 等级: {user.get('level', 1)}\n"
            f"🎫 禁言卡: {user.get('mute_card', 0)}张"
        )
        await query.edit_message_text(text)
    elif data.startswith("verify_"):
        # 群内点击验证按钮 → 私聊用户
        target_user_id = int(data.split("_")[1])
        chat_id = query.message.chat.id
        # 检查点击者是否是目标用户
        if query.from_user.id != target_user_id:
            await query.answer("❌ 这不是你的验证按钮", show_alert=True)
            return
        # 私聊用户
        keyboard = [
            [InlineKeyboardButton("✅ 确认验证", callback_data=f"confirm_verify_{chat_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🔐 **入群验证**\n\n"
                    f"你好！请确认你是本人操作\n"
                    f"点击下方按钮完成验证\n\n"
                    f"⚠️ 验证后即可在群里正常发言"
                ),
                reply_markup=reply_markup
            )
            await query.answer("✅ 已私聊你，请查看", show_alert=True)
        except Exception as e:
            await query.answer("❌ 无法私聊你，请先私聊机器人 /start", show_alert=True)
    elif data.startswith("confirm_verify_"):
        # 私聊中确认验证（兼容旧流程）
        chat_id = int(data.split("_")[2])
        user_id = query.from_user.id
        await db.set_verified(chat_id, user_id, True)
        # 解除群内发言限制
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=ChatPermissions(
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
                    can_change_info=True,
                    can_pin_messages=True,
                    can_manage_topics=True,
                )
            )
        except Exception as e:
            print(f"[WARN] unrestrict_chat_member failed for {user_id}: {e}")
        text = (
            f"✅ **验证成功！**\n\n"
            f"你现在可以在群里正常发言了\n"
            f"返回群聊试试吧！"
        )
        await query.edit_message_text(text)
        # 通知群聊
        try:
            user = await db.get_user_info(chat_id, user_id)
            name = user.get("first_name", "") if user else query.from_user.first_name
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ {escape(name)} 已完成验证，欢迎加入！"
            )
        except Exception:
            pass

    await query.answer()


# ==================== 错误处理 ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理错误"""
    logger.error(f"Exception while handling an update: {context.error}")


# ==================== 主函数 ====================



# ==================== P0: CAPTCHA 验证系统 ====================

import random
import string
import csv
import io
from collections import defaultdict

def generate_captcha():
    """生成数学验证码"""
    ops = ['+', '-', '*']
    op = random.choice(ops)
    if op == '+':
        a = random.randint(1, 50)
        b = random.randint(1, 50)
        answer = str(a + b)
    elif op == '-':
        a = random.randint(10, 50)
        b = random.randint(1, 10)
        answer = str(a - b)
    else:
        a = random.randint(2, 12)
        b = random.randint(2, 12)
        answer = str(a * b)
    question = f"请计算: {a} {op} {b} = ?"
    return question, answer


# ==================== P1: 定时消息/公告 ====================

async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """定时消息管理: /schedule add <时间> <消息> | /schedule list | /schedule del <ID>"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "⏰ **定时消息**\n\n"
            "/schedule add <时间> <消息> - 添加定时消息\n"
            "/schedule list - 查看待发送消息\n"
            "/schedule del <ID> - 删除定时消息\n\n"
            "时间格式:\n"
            "• `2026-05-17 09:00` - 指定时间\n"
            "• `+30m` - 30分钟后\n"
            "• `+2h` - 2小时后\n"
            "• `+1d` - 1天后"
        )
        return

    action = args[0].lower()

    if action == "add":
        if len(args) < 3:
            await update.message.reply_text("❌ 用法: /schedule add <时间> <消息>")
            return

        time_str = args[1]
        msg_text = " ".join(args[2:])

        # 解析时间
        now = datetime.now()
        if time_str.startswith("+"):
            unit = time_str[-1]
            try:
                val = int(time_str[1:-1])
            except ValueError:
                await update.message.reply_text("❌ 无效时间格式")
                return
            if unit == "m":
                schedule_time = (now + timedelta(minutes=val)).strftime("%Y-%m-%d %H:%M:%S")
            elif unit == "h":
                schedule_time = (now + timedelta(hours=val)).strftime("%Y-%m-%d %H:%M:%S")
            elif unit == "d":
                schedule_time = (now + timedelta(days=val)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                await update.message.reply_text("❌ 时间单位: m(分) h(时) d(天)")
                return
        else:
            try:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
                schedule_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                await update.message.reply_text("❌ 时间格式: YYYY-MM-DD HH:MM")
                return

        msg_id = await db.add_scheduled_message(chat_id, msg_text, schedule_time, "once", user_id)
        await update.message.reply_text(f"✅ 定时消息已添加 (ID: {msg_id})\n⏰ 发送时间: {schedule_time}")

    elif action == "list":
        messages = await db.get_scheduled_messages(chat_id)
        if not messages:
            await update.message.reply_text("📋 暂无定时消息")
            return
        text = "⏰ **定时消息列表**\n\n"
        for msg in messages:
            status = "✅ 已发送" if msg[4] else "⏳ 待发送"
            text += f"🆔 {msg[0]} | {status}\n"
            text += f"⏰ {msg[2]}\n"
            text += f"📝 {msg[1][:50]}...\n\n"
        await update.message.reply_text(text)

    elif action == "del":
        if len(args) < 2:
            await update.message.reply_text("❌ 用法: /schedule del <ID>")
            return
        try:
            msg_id = int(args[1])
            await db.delete_scheduled_message(msg_id, chat_id)
            await update.message.reply_text(f"✅ 已删除定时消息 (ID: {msg_id})")
        except ValueError:
            await update.message.reply_text("❌ 无效的ID")


async def scheduled_checker(context: ContextTypes.DEFAULT_TYPE):
    """定时检查待发送的消息"""
    pending = await db.get_pending_scheduled_messages()
    for msg in pending:
        msg_id, chat_id, text, schedule_time, repeat_type = msg
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            await db.mark_scheduled_sent(msg_id)
            logger.info(f"Sent scheduled message {msg_id} to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send scheduled message {msg_id}: {e}")


# ==================== P1: 用户举报 ====================

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """举报消息: 回复一条消息 /report <原因>"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ 请回复要举报的消息\n用法: 回复消息后 /report <原因>")
        return

    reported_msg = update.message.reply_to_message
    reported_user = reported_msg.from_user

    if reported_user.id == user_id:
        await update.message.reply_text("❌ 不能举报自己")
        return

    if is_admin(reported_user.id, chat_id):
        await update.message.reply_text("❌ 不能举报管理员")
        return

    reason = " ".join(context.args) if context.args else "未说明原因"

    await db.add_report(
        chat_id, user_id, reported_user.id,
        reported_msg.text or "[非文本消息]",
        reported_msg.message_id, reason
    )

    # 通知管理员
    admin_text = (
        f"⚠️ **新举报**\n\n"
        f"👤 举报者: {escape(update.effective_user.first_name)} (ID: {user_id})\n"
        f"🎯 被举报: {escape(reported_user.first_name)} (ID: {reported_user.id})\n"
        f"📝 原因: {reason}\n"
        f"💬 消息: {(reported_msg.text or '[非文本]')[:100]}"
    )
    await update.message.reply_text("✅ 举报已提交，管理员会尽快处理")

    # 通知所有管理员
    for admin_id in config.SUPER_ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception:
            pass


async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看待处理举报"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    reports = await db.get_pending_reports(chat_id)
    if not reports:
        await update.message.reply_text("✅ 暂无待处理举报")
        return

    text = f"⚠️ **待处理举报** ({len(reports)}条)\n\n"
    for r in reports[:10]:
        text += f"🆔 举报#{r[0]}\n"
        text += f"👤 举报者: {r[1]} → 🎯 被举报: {r[2]}\n"
        text += f"📝 原因: {r[4]}\n"
        text += f"⏰ 时间: {r[5]}\n\n"

    text += "💡 使用 /dismiss <ID> 驳回，/punish <ID> 处罚被举报者"
    await update.message.reply_text(text)


async def cmd_dismiss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """驳回举报"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    if not context.args:
        await update.message.reply_text("❌ 用法: /dismiss <举报ID>")
        return

    try:
        report_id = int(context.args[0])
        await db.update_report_status(report_id, "dismissed", user_id)
        await update.message.reply_text(f"✅ 举报#{report_id} 已驳回")
    except ValueError:
        await update.message.reply_text("❌ 无效的ID")


async def cmd_punish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处罚被举报用户（禁言1小时）"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    if not context.args:
        await update.message.reply_text("❌ 用法: /punish <举报ID>")
        return

    try:
        report_id = int(context.args[0])
        # 获取举报信息
        reports = await db.get_pending_reports(chat_id)
        target_report = None
        for r in reports:
            if r[0] == report_id:
                target_report = r
                break

        if not target_report:
            await update.message.reply_text("❌ 未找到该举报或已处理")
            return

        reported_user_id = target_report[2]
        until = datetime.now() + timedelta(hours=1)
        await update.effective_chat.restrict_member(
            reported_user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await db.update_report_status(report_id, "punished", user_id)
        await db.add_violation(chat_id, reported_user_id, "report_punish", f"举报#{report_id}")
        await update.message.reply_text(f"✅ 已处罚用户 {reported_user_id}（禁言1小时）")
    except Exception as e:
        await update.message.reply_text(f"❌ 处罚失败: {e}")


# ==================== P2: 投票/问卷 ====================

async def cmd_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """创建投票: /poll <问题> | <选项1> | <选项2> | ..."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "📊 **创建投票**\n\n"
            "用法: /poll <问题> | <选项1> | <选项2> | ...\n\n"
            "示例:\n"
            "/poll 今天吃什么？ | 火锅 | 烧烤 | 日料 | 西餐"
        )
        return

    full_text = " ".join(context.args)
    parts = [p.strip() for p in full_text.split("|")]

    if len(parts) < 3:
        await update.message.reply_text("❌ 至少需要1个问题和2个选项（用 | 分隔）")
        return

    question = parts[0]
    options = parts[1:]

    if len(options) > 10:
        await update.message.reply_text("❌ 最多10个选项")
        return

    try:
        poll_message = await context.bot.send_poll(
            chat_id=chat_id,
            question=question,
            options=options,
            is_anonymous=False,
        )
    except Exception as e:
        await update.message.reply_text(f"❌ 创建投票失败: {e}")


# ==================== P2: 入群欢迎卡片（同意规则才解除限制） ====================

async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看/设置群规"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if context.args and is_admin(user_id, chat_id):
        # 设置群规
        rules_text = " ".join(context.args)
        await db.set_group_rules(chat_id, rules_text, 1)
        await update.message.reply_text(f"✅ 群规已设置！\n\n{rules_text}")
    else:
        # 查看群规
        rules = await db.get_group_rules(chat_id)
        if rules and rules["rules_text"]:
            text = f"📋 **群规**\n\n{rules['rules_text']}"
        else:
            text = "📋 暂未设置群规\n\n💡 管理员可使用 /rules <内容> 设置群规"
        await update.message.reply_text(text)


# ==================== P2: 群数据导出 ====================

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """导出群数据: /export users|points|violations"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📥 **数据导出**\n\n"
            "/export users - 导出用户列表\n"
            "/export points - 导出积分排行\n"
            "/export violations - 导出违规记录"
        )
        return

    export_type = args[0].lower()
    output = io.StringIO()

    if export_type == "users":
        users = await db.get_all_group_users(chat_id)
        writer = csv.writer(output)
        writer.writerow(["用户ID", "用户名", "昵称", "积分", "等级", "签到连续", "状态", "加入时间"])
        for u in users:
            status = "正常"
            if u.get("is_muted"):
                status = "禁言"
            elif u.get("is_banned"):
                status = "封禁"
            writer.writerow([
                u["user_id"], u.get("username", ""), u.get("first_name", ""),
                u.get("points", 0), u.get("level", 1), u.get("checkin_streak", 0),
                status, u.get("joined_at", "")
            ])
        filename = f"users_{chat_id}.csv"

    elif export_type == "points":
        leaderboard = await db.get_leaderboard(chat_id, 9999)
        writer = csv.writer(output)
        writer.writerow(["排名", "用户ID", "用户名", "昵称", "积分", "等级"])
        for i, u in enumerate(leaderboard, 1):
            writer.writerow([i, u["user_id"], u.get("username", ""), u.get("first_name", ""), u["points"], u["level"]])
        filename = f"points_{chat_id}.csv"

    elif export_type == "violations":
        async with aiosqlite.connect(config.DATABASE_PATH) as db_conn:
            cursor = await db_conn.execute(
                "SELECT user_id, type, reason, timestamp FROM violations WHERE chat_id=? ORDER BY timestamp DESC",
                (chat_id,)
            )
            rows = await cursor.fetchall()
        writer = csv.writer(output)
        writer.writerow(["用户ID", "类型", "原因", "时间"])
        for r in rows:
            writer.writerow(r)
        filename = f"violations_{chat_id}.csv"
    else:
        await update.message.reply_text("❌ 未知导出类型: users/points/violations")
        return

    # 保存文件并发送
    csv_content = output.getvalue()
    file_path = f"/tmp/{filename}"
    with open(file_path, "w", encoding="utf-8-sig") as f:
        f.write(csv_content)

    with open(file_path, "rb") as f:
        await context.bot.send_document(
            chat_id=chat_id,
            document=f,
            filename=filename,
            caption=f"📥 {export_type.upper()} 数据导出完成"
        )

    import os
    os.remove(file_path)


# ==================== P3: 自定义命令 ====================

async def cmd_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """自定义命令管理: /cmd add <命令> <回复> | /cmd del <命令> | /cmd list"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "🔧 **自定义命令**\n\n"
            "/cmd add <命令名> <回复内容> - 添加\n"
            "/cmd del <命令名> - 删除\n"
            "/cmd list - 查看所有\n\n"
            "添加后用户输入 /<命令名> 即可触发"
        )
        return

    action = args[0].lower()

    if action == "add":
        if len(args) < 3:
            await update.message.reply_text("❌ 用法: /cmd add <命令名> <回复内容>")
            return
        cmd_name = args[1].lstrip("/")
        response = " ".join(args[2:])
        await db.add_custom_command(chat_id, cmd_name, response, user_id)
        await update.message.reply_text(f"✅ 自定义命令 /{cmd_name} 已添加")

    elif action == "del":
        if len(args) < 2:
            await update.message.reply_text("❌ 用法: /cmd del <命令名>")
            return
        cmd_name = args[1].lstrip("/")
        await db.delete_custom_command(chat_id, cmd_name)
        await update.message.reply_text(f"✅ 自定义命令 /{cmd_name} 已删除")

    elif action == "list":
        commands = await db.get_all_custom_commands(chat_id)
        if not commands:
            await update.message.reply_text("📋 暂无自定义命令")
            return
        text = "🔧 **自定义命令列表**\n\n"
        for cmd in commands:
            status = "✅" if cmd[2] else "❌"
            text += f"{status} /{cmd[0]} → {cmd[1][:40]}\n"
        await update.message.reply_text(text)


# ==================== P3: 消息统计图表 ====================

async def cmd_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """消息统计: /activity [天数]"""
    chat_id = update.effective_chat.id
    days = 7

    if context.args:
        try:
            days = int(context.args[0])
            days = min(max(days, 1), 30)
        except ValueError:
            pass

    stats = await db.get_message_stats(chat_id, days)
    top_chatters = await db.get_top_chatters(chat_id, 10, days)

    if not stats:
        await update.message.reply_text("📊 暂无统计数据")
        return

    # 文字柱状图
    text = f"📊 **近{days}天消息统计**\n\n"
    max_count = max(s[1] for s in stats) if stats else 1

    for date, count in stats:
        bar_len = int((count / max_count) * 15) if max_count > 0 else 0
        bar = "█" * bar_len
        text += f"`{date}` {bar} {count}\n"

    total = sum(s[1] for s in stats)
    text += f"\n📈 总消息数: {total}\n"
    text += f"📅 日均: {total // len(stats) if stats else 0}\n"

    if top_chatters:
        text += f"\n🏆 **活跃用户 TOP {min(10, len(top_chatters))}**\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (uid, count) in enumerate(top_chatters):
            medal = medals[i] if i < 3 else f" {i+1}."
            try:
                user_info = await db.get_user_info(chat_id, uid)
                name = user_info.get("first_name", str(uid)) if user_info else str(uid)
            except Exception:
                name = str(uid)
            text += f"{medal} {escape(name)} - {count}条\n"

    await update.message.reply_text(text)


# ==================== P3: 黑白名单 ====================

async def cmd_blacklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """黑名单管理: /blacklist add <用户ID> [原因] | /blacklist del <用户ID> | /blacklist list"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "🚫 **黑名单**\n\n"
            "/blacklist add <用户ID> [原因] - 添加\n"
            "/blacklist del <用户ID> - 移除\n"
            "/blacklist list - 查看列表\n\n"
            "黑名单用户入群后会被自动踢出"
        )
        return

    action = args[0].lower()

    if action == "add":
        if len(args) < 2:
            await update.message.reply_text("❌ 用法: /blacklist add <用户ID> [原因]")
            return
        try:
            target_id = int(args[1])
            reason = " ".join(args[2:]) if len(args) > 2 else "管理员添加"
            await db.add_to_blacklist(chat_id, target_id, reason, user_id)
            await update.message.reply_text(f"✅ 已将 {target_id} 加入黑名单")
        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID")

    elif action == "del":
        if len(args) < 2:
            await update.message.reply_text("❌ 用法: /blacklist del <用户ID>")
            return
        try:
            target_id = int(args[1])
            await db.remove_from_blacklist(chat_id, target_id)
            await update.message.reply_text(f"✅ 已将 {target_id} 从黑名单移除")
        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID")

    elif action == "list":
        bl = await db.get_blacklist(chat_id)
        if not bl:
            await update.message.reply_text("📋 黑名单为空")
            return
        text = f"🚫 **黑名单** ({len(bl)}人)\n\n"
        for entry in bl:
            text += f"🆔 {entry[0]} | 📝 {entry[1]} | ⏰ {entry[2]}\n"
        await update.message.reply_text(text)


async def cmd_whitelist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """白名单管理: /whitelist add <用户ID> [原因] | /whitelist del <用户ID> | /whitelist list"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id, chat_id):
        await update.message.reply_text("❌ 仅管理员可使用此命令")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "✅ **白名单**\n\n"
            "/whitelist add <用户ID> [原因] - 添加\n"
            "/whitelist del <用户ID> - 移除\n"
            "/whitelist list - 查看列表\n\n"
            "白名单用户不受广告检测和验证限制"
        )
        return

    action = args[0].lower()

    if action == "add":
        if len(args) < 2:
            await update.message.reply_text("❌ 用法: /whitelist add <用户ID> [原因]")
            return
        try:
            target_id = int(args[1])
            reason = " ".join(args[2:]) if len(args) > 2 else "管理员添加"
            await db.add_to_whitelist(chat_id, target_id, reason, user_id)
            await update.message.reply_text(f"✅ 已将 {target_id} 加入白名单")
        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID")

    elif action == "del":
        if len(args) < 2:
            await update.message.reply_text("❌ 用法: /whitelist del <用户ID>")
            return
        try:
            target_id = int(args[1])
            await db.remove_from_whitelist(chat_id, target_id)
            await update.message.reply_text(f"✅ 已将 {target_id} 从白名单移除")
        except ValueError:
            await update.message.reply_text("❌ 无效的用户ID")

    elif action == "list":
        wl = await db.get_whitelist(chat_id)
        if not wl:
            await update.message.reply_text("📋 白名单为空")
            return
        text = f"✅ **白名单** ({len(wl)}人)\n\n"
        for entry in wl:
            text += f"🆔 {entry[0]} | 📝 {entry[1]} | ⏰ {entry[2]}\n"
        await update.message.reply_text(text)


# ==================== P1: 消息自动回复/关键词触发 ====================
# 已有 cmd_keyword，无需新增

# ==================== P2: 临时禁言 ====================
# 已有 cmd_tempmute，无需新增



def main():
    """启动 Bot"""
    print("🤖 Telegram 群管理机器人启动中...")

    # 向 Telegram 注册命令菜单（输入 / 时弹出）
    commands = [
        BotCommand("start", "打开主菜单"),
        BotCommand("help", "使用帮助"),
        BotCommand("checkin", "每日签到"),
        BotCommand("points", "查看积分"),
        BotCommand("rank", "积分排行"),
        BotCommand("shop", "积分商城"),
        BotCommand("exchange", "兑换商品"),
        BotCommand("myitems", "我的物品"),
        BotCommand("mute", "禁言用户"),
        BotCommand("unmute", "解除禁言"),
        BotCommand("ban", "封禁用户"),
        BotCommand("unban", "解封用户"),
        BotCommand("kick", "踢出用户"),
        BotCommand("userinfo", "查看用户信息"),
        BotCommand("stats", "群组统计"),
        BotCommand("setwelcome", "设置欢迎语"),
        BotCommand("welcome", "查看欢迎语"),
        BotCommand("antispam", "广告防护设置"),
        BotCommand("addword", "添加违禁词"),
        BotCommand("delword", "删除违禁词"),
        BotCommand("wordlist", "查看违禁词列表"),
        BotCommand("verify", "重发验证(管理员)"),
        BotCommand("schedule", "定时消息(管理员)"),
        BotCommand("report", "举报消息"),
        BotCommand("reports", "查看举报(管理员)"),
        BotCommand("dismiss", "驳回举报(管理员)"),
        BotCommand("punish", "处罚被举报者(管理员)"),
        BotCommand("poll", "创建投票"),
        BotCommand("rules", "查看/设置群规"),
        BotCommand("export", "导出数据(管理员)"),
        BotCommand("cmd", "自定义命令(管理员)"),
        BotCommand("activity", "消息统计"),
        BotCommand("blacklist", "黑名单(管理员)"),
        BotCommand("whitelist", "白名单(管理员)"),
    ]

    async def post_init(application):
        await application.bot.set_my_commands(commands)
        print("✅ 命令菜单已注册到 Telegram")

    # 创建 Application
    app = Application.builder().token(config.BOT_TOKEN).post_init(post_init).build()

    # 注册命令处理器
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))

    # 积分系统
    app.add_handler(CommandHandler("checkin", cmd_checkin))
    app.add_handler(CommandHandler("points", cmd_points))
    app.add_handler(CommandHandler("rank", cmd_rank))
    app.add_handler(CommandHandler("shop", cmd_shop))
    app.add_handler(CommandHandler("exchange", cmd_exchange))
    app.add_handler(CommandHandler("myitems", cmd_myitems))

    # 群管理
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("userinfo", cmd_userinfo))
    app.add_handler(CommandHandler("stats", cmd_stats))

    # 群组设置
    app.add_handler(CommandHandler("setwelcome", cmd_setwelcome))
    app.add_handler(CommandHandler("welcome", cmd_welcome))
    app.add_handler(CommandHandler("antispam", cmd_antispam))
    app.add_handler(CommandHandler("addword", cmd_addword))
    app.add_handler(CommandHandler("delword", cmd_delword))
    app.add_handler(CommandHandler("wordlist", cmd_wordlist))
    app.add_handler(CommandHandler("verify", cmd_verify))
    app.add_handler(CommandHandler("keyword", cmd_keyword))
    app.add_handler(CommandHandler("tempmute", cmd_tempmute))

    # 新功能命令
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("reports", cmd_reports))
    app.add_handler(CommandHandler("dismiss", cmd_dismiss))
    app.add_handler(CommandHandler("punish", cmd_punish))
    app.add_handler(CommandHandler("poll", cmd_poll))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(CommandHandler("cmd", cmd_cmd))
    app.add_handler(CommandHandler("activity", cmd_activity))
    app.add_handler(CommandHandler("blacklist", cmd_blacklist))
    app.add_handler(CommandHandler("whitelist", cmd_whitelist))

    # 回调查询
    app.add_handler(CallbackQueryHandler(callback_handler))

    # 消息处理器
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_member))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    # 错误处理
    app.add_error_handler(error_handler)

    # 初始化数据库
    asyncio.get_event_loop().run_until_complete(db.init_db())
    asyncio.get_event_loop().run_until_complete(db.init_new_tables())

    # 定时消息检查器
    job_queue = app.job_queue
    job_queue.run_repeating(scheduled_checker, interval=60, first=10)

    print("✅ Bot 已启动，开始监听消息...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
