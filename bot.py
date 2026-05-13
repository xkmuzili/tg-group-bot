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
from database import now_cn
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
        if not item.get("enabled", 1):
            continue
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
    success, message, extra = await db.buy_item(user_id, chat_id, item_id)

    if success:
        await update.message.reply_text(f"✅ {message}")
        # 如果有兑换码，私信发给用户
        if extra and extra.get("card_code"):
            card_code = extra["card_code"]
            card_days = extra["card_days"]
            private_msg = ("🎫 你的IPTV兑换码：" + chr(10) + chr(10) + f"`{card_code}`" + chr(10) + chr(10) + f"天数：{card_days}天" + chr(10) + chr(10) + "请复制兑换码到IPTV管理面板使用")
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=private_msg,
                    parse_mode="Markdown"
                )
            except Exception:
                # 如果私信发送失败（用户未开启私信），在群里补充提示
                await update.message.reply_text(
                    "⚠️ 兑换码已发放，但无法私信发送。请先给机器人发送一条消息开启私信，然后重新使用 /myitems 查看。"
                )
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
        until = now_cn() + timedelta(hours=1)
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

    # 只处理群组消息，忽略私聊
    if message.chat.type not in ["group", "supergroup"]:
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # 确保用户在数据库中
    await db.ensure_user(chat_id, user_id, username, first_name)

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
        today = now_cn().strftime("%Y-%m-%d")

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
        # 私聊中确认验证
        chat_id = int(data.split("_")[2])
        user_id = query.from_user.id
        # 标记已验证
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

    # 将所有已有用户标记为已验证
    # Bot后于群成员加入时，无法对已有成员进行验证，默认它们已通过验证
    # 只有Bot启动后新加入的成员才会触发入群验证流程
    asyncio.get_event_loop().run_until_complete(db.mark_all_existing_verified())

    print("✅ Bot 已启动，开始监听消息...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
