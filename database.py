"""
Telegram 群管理机器人 - 数据库模块
使用 aiosqlite 实现异步数据库操作
"""

import aiosqlite
import time
from datetime import datetime, timedelta, timezone
import config

# 统一使用 UTC+8 时区
TZ_CN = timezone(timedelta(hours=8))


def now_cn():
    """获取当前 UTC+8 时间"""
    return datetime.now(TZ_CN)

DB_PATH = config.DATABASE_PATH


async def init_db():
    """初始化数据库，创建所有表"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS group_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                points INTEGER DEFAULT 0,
                total_points INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                checkin_streak INTEGER DEFAULT 0,
                last_checkin TEXT,
                last_message_time REAL DEFAULT 0,
                message_points_today INTEGER DEFAULT 0,
                message_points_date TEXT,
                invite_count INTEGER DEFAULT 0,
                is_vip INTEGER DEFAULT 0,
                vip_expire TEXT,
                has_double_checkin INTEGER DEFAULT 0,
                has_anti_spam_shield INTEGER DEFAULT 0,
                mute_card INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                is_muted INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                joined_at TEXT,
                UNIQUE(chat_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS group_settings (
                chat_id INTEGER PRIMARY KEY,
                welcome_message TEXT,
                welcome_enabled INTEGER DEFAULT 1,
                anti_spam_enabled INTEGER DEFAULT 1,
                custom_banned_words TEXT,
                auto_delete_links INTEGER DEFAULT 0,
                max_links_count INTEGER DEFAULT 3,
                new_user_restrict_seconds INTEGER DEFAULT 300,
                warn_threshold INTEGER DEFAULT 3,
                mute_threshold INTEGER DEFAULT 5,
                ban_threshold INTEGER DEFAULT 10,
                log_channel_id INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                type TEXT,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                processed INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS shop_items (
                item_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                price INTEGER NOT NULL,
                stock INTEGER DEFAULT 999,
                type TEXT DEFAULT 'general',
                chat_id INTEGER,
                enabled INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS iptv_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                days INTEGER NOT NULL,
                card_type TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'unused',
                used_by INTEGER,
                used_at TEXT,
                batch_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                chat_id INTEGER,
                shop_item_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS exchange_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                points_spent INTEGER NOT NULL,
                exchanged_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS checkin_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                checkin_date TEXT NOT NULL,
                points_earned INTEGER DEFAULT 0,
                UNIQUE(user_id, chat_id, checkin_date)
            );
        """)
        await db.commit()
        
        # 清理错误数据：正数chat_id是私聊ID，不是群组
        await db.execute("DELETE FROM group_users WHERE chat_id > 0")
        await db.commit()


# ==================== 用户操作 ====================

async def ensure_user(chat_id, user_id, username=None, first_name=None):
    """确保用户存在，不存在则创建。返回用户信息字典"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM group_users WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        row = await cursor.fetchone()
        if row:
            # 更新用户名和昵称
            if username or first_name:
                await db.execute(
                    "UPDATE group_users SET username=COALESCE(?,username), first_name=COALESCE(?,first_name) WHERE chat_id=? AND user_id=?",
                    (username, first_name, chat_id, user_id)
                )
                await db.commit()
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        else:
            now = now_cn().isoformat()
            await db.execute(
                """INSERT INTO group_users
                   (chat_id, user_id, username, first_name, joined_at, message_points_date)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chat_id, user_id, username or "", first_name or "", now, now_cn().strftime("%Y-%m-%d"))
            )
            await db.commit()
            return await get_user_info(chat_id, user_id)


async def get_user_info(chat_id, user_id):
    """获取用户信息"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM group_users WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))


async def add_points(chat_id, user_id, points, reason=""):
    """添加积分"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET points=points+?, total_points=total_points+? WHERE chat_id=? AND user_id=?",
            (points, points, chat_id, user_id)
        )
        await db.commit()


async def deduct_points(chat_id, user_id, points):
    """扣除积分"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET points=MAX(0,points-?) WHERE chat_id=? AND user_id=?",
            (points, chat_id, user_id)
        )
        await db.commit()


async def get_leaderboard(chat_id, limit=10):
    """获取积分排行榜"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name, points, level FROM group_users WHERE chat_id=? ORDER BY points DESC LIMIT ?",
            (chat_id, limit)
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                "user_id": row[0], "username": row[1], "first_name": row[2],
                "points": row[3], "level": row[4],
            })
        return result


async def checkin(chat_id, user_id):
    """签到"""
    today = now_cn().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        # 检查今天是否已签到
        cursor = await db.execute(
            "SELECT id FROM checkin_records WHERE user_id=? AND chat_id=? AND checkin_date=?",
            (user_id, chat_id, today)
        )
        if await cursor.fetchone():
            return None  # 已签到

        # 获取用户信息
        user = await get_user_info(chat_id, user_id)
        if not user:
            user = await ensure_user(chat_id, user_id)

        # 计算积分
        streak = user.get("checkin_streak", 0)
        yesterday = (now_cn() - timedelta(days=1)).strftime("%Y-%m-%d")
        cursor = await db.execute(
            "SELECT id FROM checkin_records WHERE user_id=? AND chat_id=? AND checkin_date=?",
            (user_id, chat_id, yesterday)
        )
        if await cursor.fetchone():
            streak += 1
        else:
            streak = 1

        bonus = min(streak * config.CHECKIN_STREAK_BONUS, config.MAX_STREAK_BONUS)
        base = config.DAILY_CHECKIN_POINTS
        # 双倍积分卡
        if user.get("has_double_checkin"):
            base *= 2
        total = base + bonus

        # 记录签到
        await db.execute(
            "INSERT INTO checkin_records (user_id, chat_id, checkin_date, points_earned) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, today, total)
        )
        # 更新用户
        await db.execute(
            "UPDATE group_users SET points=points+?, total_points=total_points+?, checkin_streak=?, last_checkin=? WHERE chat_id=? AND user_id=?",
                        (total, total, streak, now_cn().isoformat(), chat_id, user_id)
        )
        await db.commit()
        return {"points": total, "streak": streak, "base": base, "bonus": bonus}


# ==================== 群设置 ====================

async def get_group_settings(chat_id):
    """获取群设置"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM group_settings WHERE chat_id=?", (chat_id,)
        )
        row = await cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return {}


async def update_group_settings(chat_id, **kwargs):
    """更新群设置"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 先确保记录存在
        cursor = await db.execute(
            "SELECT chat_id FROM group_settings WHERE chat_id=?", (chat_id,)
        )
        if not await cursor.fetchone():
            await db.execute(
                "INSERT INTO group_settings (chat_id) VALUES (?)", (chat_id,)
            )
        # 更新
        for key, value in kwargs.items():
            await db.execute(
                f"UPDATE group_settings SET {key}=? WHERE chat_id=?",
                (value, chat_id)
            )
        await db.commit()


# ==================== 违禁词 ====================

async def get_banned_words(chat_id):
    """获取违禁词列表（默认 + 自定义）"""
    settings = await get_group_settings(chat_id)
    custom = settings.get("custom_banned_words", "") or ""
    custom_words = [w.strip() for w in custom.split(",") if w.strip()]
    return list(set(config.DEFAULT_BANNED_WORDS + custom_words))


async def add_banned_word(chat_id, word):
    """添加自定义违禁词"""
    settings = await get_group_settings(chat_id)
    custom = settings.get("custom_banned_words", "") or ""
    words = [w.strip() for w in custom.split(",") if w.strip()]
    if word not in words:
        words.append(word)
    await update_group_settings(chat_id, custom_banned_words=",".join(words))


async def remove_banned_word(chat_id, word):
    """删除自定义违禁词"""
    settings = await get_group_settings(chat_id)
    custom = settings.get("custom_banned_words", "") or ""
    words = [w.strip() for w in custom.split(",") if w.strip() and w.strip() != word]
    await update_group_settings(chat_id, custom_banned_words=",".join(words))


async def get_custom_banned_words(chat_id):
    """获取自定义违禁词"""
    settings = await get_group_settings(chat_id)
    custom = settings.get("custom_banned_words", "") or ""
    return [w.strip() for w in custom.split(",") if w.strip()]


# ==================== 违规记录 ====================

async def add_violation(chat_id, user_id, vtype, reason=""):
    """记录违规"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO violations (user_id, chat_id, type, reason) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, vtype, reason)
        )
        await db.commit()


async def get_violation_count(chat_id, user_id):
    """获取违规次数"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM violations WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        return (await cursor.fetchone())[0]


# ==================== 群统计 ====================

async def get_group_stats(chat_id):
    """获取群组统计"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM group_users WHERE chat_id=?", (chat_id,)
        )
        total_users = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COUNT(*) FROM group_users WHERE chat_id=? AND is_muted=1", (chat_id,)
        )
        muted_users = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COUNT(*) FROM group_users WHERE chat_id=? AND is_banned=1", (chat_id,)
        )
        banned_users = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT COUNT(*) FROM violations WHERE chat_id=?", (chat_id,)
        )
        total_violations = (await cursor.fetchone())[0]
        cursor = await db.execute(
            "SELECT SUM(points) FROM group_users WHERE chat_id=?", (chat_id,)
        )
        total_points = (await cursor.fetchone())[0] or 0
        return {
            "total_users": total_users,
            "muted_users": muted_users,
            "banned_users": banned_users,
            "total_violations": total_violations,
            "total_points": total_points,
        }


# ==================== 商城 ====================

async def get_shop_items():
    """获取商城物品"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT * FROM shop_items")
        rows = await cursor.fetchall()
        if not rows:
            # 初始化默认物品
            for item_id, item in config.DEFAULT_SHOP_ITEMS.items():
                await db.execute(
                    "INSERT OR IGNORE INTO shop_items (item_id, name, description, price, stock) VALUES (?, ?, ?, ?, ?)",
                    (item_id, item["name"], item["description"], item["price"], item["stock"])
                )
            await db.commit()
            cursor = await db.execute("SELECT * FROM shop_items")
            rows = await cursor.fetchall()
        result = {}
        for row in rows:
            result[row[0]] = {"name": row[1], "price": int(row[2]) if row[2] else 0, "stock": int(row[3]) if row[3] else 0, "description": row[4] if len(row) > 4 else "", "type": row[5] if len(row) > 5 else "general", "chat_id": row[6] if len(row) > 6 else None, "enabled": int(row[7]) if len(row) > 7 and row[7] is not None else 1}
        return result


async def buy_item(user_id, chat_id, item_id):
    """购买物品"""
    # 确保item_id是整数（数据库中item_id是INTEGER类型）
    try:
        item_id = int(item_id)
    except (ValueError, TypeError):
        return False, "物品ID无效", None
    items = await get_shop_items()
    if item_id not in items:
        return False, "物品不存在", None
    item = items[item_id]
    if not item.get("enabled", 1):
        return False, "该商品已关闭", None
    # stock=-1 表示无限库存，stock=0 表示售罄
    if item["stock"] == 0:
        return False, "库存不足", None
    user = await get_user_info(chat_id, user_id)
    if not user:
        return False, "用户不存在", None
    if user["points"] < item["price"]:
        return False, f'积分不足（需要{item["price"]}，当前{user["points"]}）', None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET points=points-? WHERE chat_id=? AND user_id=?",
            (item["price"], chat_id, user_id)
        )
        # stock=-1 表示无限库存，不扣减；其他情况扣减库存
        if item["stock"] > 0:
            await db.execute(
                "UPDATE shop_items SET stock=stock-1 WHERE item_id=?", (item_id,)
            )
        await db.execute(
            "INSERT INTO exchange_records (user_id, chat_id, item_id, item_name, points_cost) VALUES (?, ?, ?, ?, ?)",
            (user_id, chat_id, item_id, item["name"], item["price"])
        )
        # 如果是禁言卡，给用户添加
        if item_id == "mute_card":
            await db.execute(
                "UPDATE group_users SET mute_card=mute_card+1 WHERE chat_id=? AND user_id=?",
                (chat_id, user_id)
            )
        elif item_id == "double_card":
            await db.execute(
                "UPDATE group_users SET has_double_checkin=1 WHERE chat_id=? AND user_id=?",
                (chat_id, user_id)
            )
        elif item_id == "shield_card":
            await db.execute(
                "UPDATE group_users SET has_anti_spam_shield=1 WHERE chat_id=? AND user_id=?",
                (chat_id, user_id)
            )
        elif item_id == "vip_card":
            vip_expire = (now_cn() + timedelta(days=7)).isoformat()
            await db.execute(
                "UPDATE group_users SET is_vip=1, vip_expire=? WHERE chat_id=? AND user_id=?",
                (vip_expire, chat_id, user_id)
            )

        # 如果是兑换卡类型，从 iptv_cards 库存中取一个未使用的码
        card_code = None
        item_type = item.get("type", "general")
        if item_type == "iptv_card":
            cursor2 = await db.execute(
                "SELECT id, code, days FROM iptv_cards WHERE status='unused' AND (chat_id IS NULL OR chat_id=?) AND (shop_item_id IS NULL OR shop_item_id=?) ORDER BY id LIMIT 1",
                (chat_id, item_id)
            )
            card_row = await cursor2.fetchone()
            if not card_row:
                # 库存不足，回滚积分
                await db.execute(
                    "UPDATE group_users SET points=points+? WHERE chat_id=? AND user_id=?",
                    (item["price"], chat_id, user_id)
                )
                await db.commit()
                return False, "兑换码库存不足，请联系管理员补充", None
            card_id_db, card_code, card_days = card_row
            await db.execute(
                "UPDATE iptv_cards SET status='used', used_by=?, used_at=? WHERE id=?",
                (user_id, now_cn().isoformat(), card_id_db)
            )

        await db.commit()

    if card_code:
        return True, f"购买成功！消耗{item['price']}积分", {"card_code": card_code, "card_days": card_days}
    return True, f"购买成功！消耗{item['price']}积分", None


async def get_user_items(chat_id, user_id):
    """获取用户拥有的物品"""
    user = await get_user_info(chat_id, user_id)
    if not user:
        return {}
    items = {}
    if user.get("mute_card", 0) > 0:
        items["mute_card"] = {"name": "🔇 禁言卡", "count": user["mute_card"]}
    if user.get("has_double_checkin"):
        items["double_card"] = {"name": "📈 双倍积分卡", "count": 1}
    if user.get("has_anti_spam_shield"):
        items["shield_card"] = {"name": "🛡️ 广告防护盾", "count": 1}
    if user.get("is_vip"):
        items["vip_card"] = {"name": "👑 VIP会员卡", "count": 1}
    return items


# ==================== 禁言/封禁状态 ====================

async def set_muted(chat_id, user_id, muted=True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET is_muted=? WHERE chat_id=? AND user_id=?",
            (1 if muted else 0, chat_id, user_id)
        )
        await db.commit()


async def set_banned(chat_id, user_id, banned=True):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET is_banned=? WHERE chat_id=? AND user_id=?",
            (1 if banned else 0, chat_id, user_id)
        )
        await db.commit()


async def add_warning(chat_id, user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET warnings=warnings+1 WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        await db.commit()
        cursor = await db.execute(
            "SELECT warnings FROM group_users WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def use_mute_card(chat_id, user_id):
    """使用禁言卡解除禁言"""
    user = await get_user_info(chat_id, user_id)
    if not user or user.get("mute_card", 0) <= 0:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET mute_card=mute_card-1, is_muted=0 WHERE chat_id=? AND user_id=?",
            (chat_id, user_id)
        )
        await db.commit()
    return True


# ==================== 入群验证 ====================

async def set_verified(chat_id, user_id, verified=True):
    """设置用户验证状态"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE group_users SET is_verified=? WHERE chat_id=? AND user_id=?",
            (1 if verified else 0, chat_id, user_id)
        )
        await db.commit()


async def is_verified(chat_id, user_id):
    """检查用户是否已验证"""
    user = await get_user_info(chat_id, user_id)
    if not user:
        return False
    return bool(user.get("is_verified", 0))


async def mark_all_existing_verified():
    """Bot启动时将数据库中所有已有用户标记为已验证。
    原因：Bot后于群成员加入时，无法对已有成员进行验证，默认它们已通过验证。
    只有Bot启动后新加入的成员才会触发入群验证流程。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE group_users SET is_verified=1 WHERE is_verified=0"
        )
        count = cursor.rowcount
        await db.commit()
        if count > 0:
            print(f"[INFO] 已将 {count} 个已有用户标记为已验证（Bot启动初始化）")
        return count


async def get_pending_verifications(chat_id):
    """获取待验证用户"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id, username, first_name, joined_at FROM group_users WHERE chat_id=? AND is_verified=0",
            (chat_id,)
        )
        return await cursor.fetchall()



# ==================== IPTV 兑换码管理 ====================

async def add_iptv_cards(codes_text, days, card_type="normal", batch_name=None, chat_id=None, shop_item_id=None):
    """批量导入兑换码，codes_text 为换行分隔的兑换码"""
    codes = [c.strip() for c in codes_text.strip().split(chr(10)) if c.strip()]
    added = 0
    skipped = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for code in codes:
            try:
                await db.execute(
                    "INSERT INTO iptv_cards (code, days, card_type, batch_name, chat_id, shop_item_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (code, days, card_type, batch_name, chat_id, shop_item_id)
                )
                added += 1
            except Exception:
                skipped += 1
        await db.commit()
    return added, skipped


async def get_iptv_cards(status=None, chat_id=None, shop_item_id=None):
    """获取兑换码列表，status 可选 unused/used/all，可按chat_id和shop_item_id过滤"""
    async with aiosqlite.connect(DB_PATH) as db:
        conditions = []
        params = []
        if status and status != "all":
            conditions.append("status=?")
            params.append(status)
        if chat_id is not None:
            conditions.append("chat_id=?")
            params.append(chat_id)
        if shop_item_id is not None:
            conditions.append("shop_item_id=?")
            params.append(shop_item_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        cursor = await db.execute(
            f"SELECT id, code, days, status, used_by, used_at, created_at, chat_id, shop_item_id FROM iptv_cards{where} ORDER BY id DESC",
            params
        )
        return await cursor.fetchall()


async def get_iptv_card_stats(chat_id=None, shop_item_id=None):
    """获取兑换码统计，可按chat_id和shop_item_id过滤"""
    async with aiosqlite.connect(DB_PATH) as db:
        conditions = []
        params = []
        if chat_id is not None:
            conditions.append("chat_id=?")
            params.append(chat_id)
        if shop_item_id is not None:
            conditions.append("shop_item_id=?")
            params.append(shop_item_id)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        cursor = await db.execute(f"SELECT COUNT(*) FROM iptv_cards{where} AND status='unused'" if where else "SELECT COUNT(*) FROM iptv_cards WHERE status='unused'")
        unused = (await cursor.fetchone())[0]
        cursor = await db.execute(f"SELECT COUNT(*) FROM iptv_cards{where} AND status='used'" if where else "SELECT COUNT(*) FROM iptv_cards WHERE status='used'")
        used = (await cursor.fetchone())[0]
        return {"unused": unused, "used": used, "total": unused + used}


async def delete_iptv_card(card_id):
    """删除兑换码"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM iptv_cards WHERE id=? AND status='unused'", (card_id,))
        await db.commit()


async def delete_used_cards():
    """清理已使用的兑换码"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM iptv_cards WHERE status='used'")
        deleted = cursor.rowcount
        await db.commit()
    return deleted


async def add_shop_item_db(item_id, name, description, price, item_type="general", chat_id=None):
    """添加商品到数据库"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO shop_items (item_id, name, description, price, stock, type, chat_id) VALUES (?, ?, ?, ?, 999, ?, ?)",
            (item_id, name, description, price, item_type, chat_id)
        )
        await db.commit()


async def delete_shop_item_db(item_id):
    """从数据库删除商品"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM shop_items WHERE item_id=?", (item_id,))
        await db.commit()
