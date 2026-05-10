"""
Telegram 群管理机器人 - 广告过滤模块
检测广告、垃圾信息、链接等
"""

import re
from datetime import datetime, timedelta
import database as db
import config


# 广告特征模式
AD_PATTERNS = [
    # 链接过多
    r'https?://\S+',
    r't\.me/\S+',
    r'bit\.ly/\S+',
    # 电报群/频道邀请
    r'加入.{0,10}(群|频道|组)',
    r'点击.{0,10}(加入|进群)',
    # 联系方式
    r'微信[：:]\s*\S+',
    r'QQ[：:]\s*\d+',
    r'电报[：:]\s*\S+',
    r'联系[：:]\s*\S+',
    # 金钱相关
    r'日赚\d+',
    r'月入\d+',
    r'赚\d+',
    r'返[还现]\d+',
    # 赌博/色情
    r'博彩|彩票|棋牌|约炮|约P',
]

# 编译正则
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in AD_PATTERNS]


async def check_message(message, user_id, chat_id):
    """
    检查消息是否为广告
    返回: {"is_spam": bool, "reason": str, "score": int}
    """
    text = message.text or message.caption or ""
    if not text:
        return {"is_spam": False, "reason": "", "score": 0}

    # 检查用户是否有广告防护盾
    user = await db.get_user_info(chat_id, user_id)
    if user and user.get("has_anti_spam_shield"):
        return {"is_spam": False, "reason": "", "score": 0}

    score = 0
    reasons = []

    # 1. 检查违禁词
    banned_words = await db.get_banned_words(chat_id)
    for word in banned_words:
        if word.lower() in text.lower():
            score += 3
            reasons.append(f"违禁词: {word}")

    # 2. 检查链接数量
    links = re.findall(r'https?://\S+|t\.me/\S+', text)
    if len(links) > config.MAX_LINKS_COUNT:
        score += 2
        reasons.append(f"链接过多({len(links)}个)")

    # 3. 检查广告模式
    for pattern in COMPILED_PATTERNS:
        if pattern.search(text):
            score += 1
            reasons.append(f"广告特征")

    # 4. 检查消息长度（超长消息可能是广告）
    if len(text) > config.MAX_MESSAGE_LENGTH:
        score += 1
        reasons.append("消息过长")

    # 5. 检查是否为新用户
    if await db.get_user_info(chat_id, user_id):
        joined_at = (await db.get_user_info(chat_id, user_id)).get("joined_at")
        if joined_at:
            try:
                join_time = datetime.fromisoformat(joined_at)
                settings = await db.get_group_settings(chat_id)
                restrict_seconds = settings.get("new_user_restrict_seconds", config.NEW_USER_RESTRICT_SECONDS)
                if (datetime.now() - join_time).total_seconds() < restrict_seconds:
                    # 新用户，链接直接判为广告
                    if links:
                        score += 5
                        reasons.append("新用户发链接")
            except Exception:
                pass

    is_spam = score >= 3
    reason = "; ".join(reasons) if reasons else ""

    return {"is_spam": is_spam, "reason": reason, "score": score}


async def handle_spam_message(message, user_id, chat_id, result):
    """
    处理广告消息
    根据违规次数决定处罚
    """
    # 记录违规
    await db.add_violation(chat_id, user_id, "spam", result["reason"])

    # 获取违规次数
    violation_count = await db.get_violation_count(chat_id, user_id)

    # 获取群设置
    settings = await db.get_group_settings(chat_id)
    warn_threshold = settings.get("warn_threshold", config.WARN_THRESHOLD)
    mute_threshold = settings.get("mute_threshold", config.MUTE_THRESHOLD)
    ban_threshold = settings.get("ban_threshold", config.BAN_THRESHOLD)

    # 决定处罚
    if violation_count >= ban_threshold:
        action = "ban"
    elif violation_count >= mute_threshold:
        action = "mute"
    elif violation_count >= warn_threshold:
        action = "kick"
    else:
        action = "warn"

    msg = f"(第{violation_count}次违规)"

    # 执行处罚
    try:
        if action == "ban":
            await message.chat.ban_member(user_id)
            await message.reply(f"🚫 已封禁用户\n原因: {result['reason']}\n{msg}")
        elif action == "kick":
            await message.chat.ban_member(user_id)
            await message.chat.unban_member(user_id)
            await message.reply(f"👢 已踢出用户\n原因: {result['reason']}\n{msg}")
        elif action == "mute":
            until = datetime.now() + timedelta(hours=1)
            # 使用空权限实现禁言
            await message.chat.restrict_member(
                user_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
            await message.reply(f"🔇 已禁言1小时\n原因: {result['reason']}\n{msg}")
        elif action == "warn":
            await message.reply(f"⚠️ 警告\n原因: {result['reason']}\n{msg}")
    except Exception as e:
        print(f"[AntiSpam] Failed to execute action: {e}")


async def is_user_new(user_id: int, chat_id: int) -> bool:
    """判断用户是否为新用户（入群时间在限制时间内）"""
    user_info = await db.get_user_info(chat_id, user_id)
    if not user_info:
        return True

    joined_at = user_info.get("joined_at")
    if not joined_at:
        return True

    try:
        join_time = datetime.fromisoformat(joined_at)
        settings = await db.get_group_settings(chat_id)
        restrict_seconds = settings.get("new_user_restrict_seconds", config.NEW_USER_RESTRICT_SECONDS)
        return (datetime.now() - join_time).total_seconds() < restrict_seconds
    except Exception:
        return True
