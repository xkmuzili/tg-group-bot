"""
Telegram 群管理机器人 - Web 管理面板 v4.0
功能：创建者角色体系 + 权限隔离 + 商品分群 + 管理员独立URL + 管理员角色显示名自定义
角色权限：创建者 > 超级管理员 > 管理员
显示名映射：creator→创建者, super_admin→超级管理员(高级), admin→超级管理员, editor→管理员
"""

import os
import sys
import logging
import hashlib
import secrets
import sqlite3
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, g
)

# ==================== 配置 ====================
app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_PANEL_SECRET_KEY", "stellar-warden-admin-2026")
app.config["SESSION_COOKIE_NAME"] = "stellar_admin"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8633849209:AAF7NnqWlMX6PQXBqj8TUgd_oPIj78KJJ_c")
DB_PATH = os.environ.get("DATABASE_PATH", "group_bot.db")

ADMIN_USERNAME = os.environ.get("ADMIN_PANEL_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PANEL_PASSWORD", "woaini1012")

SUPER_ADMIN_IDS = [6299747858]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 角色常量 ====================
ROLE_CREATOR = "creator"          # 创建者 - 最高权限
ROLE_SUPER_ADMIN = "super_admin"  # 超级管理员
ROLE_ADMIN = "admin"              # 管理员
ROLE_EDITOR = "editor"            # 编辑者

# 角色层级（数字越大权限越高）
ROLE_LEVELS = {
    ROLE_EDITOR: 0,
    ROLE_ADMIN: 1,
    ROLE_SUPER_ADMIN: 2,
    ROLE_CREATOR: 3,
}

def role_level(role):
    """获取角色权限层级"""
    return ROLE_LEVELS.get(role, -1)

def is_at_least_role(current_role, required_role):
    """判断当前角色是否 >= 要求的角色"""
    return role_level(current_role) >= role_level(required_role)

# ==================== 数据库工具 ====================

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def send_telegram_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                logger.info(f"Telegram sent: chat_id={chat_id}")
            else:
                logger.warning(f"Telegram failed: {result}")
    except Exception as e:
        logger.error(f"Telegram error: {e}")


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def get_group_title(db, chat_id):
    """获取群组标题"""
    row = db.execute("SELECT title FROM group_settings WHERE chat_id=?", (chat_id,)).fetchone()
    if row and row["title"]:
        return row["title"]
    # 正数chat_id是用户ID，不是群组
    if chat_id > 0:
        return f"私聊({chat_id})"
    return str(chat_id)


def telegram_api_get(method, params=None):
    """调用Telegram Bot API"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
        if params:
            data = urllib.parse.urlencode(params).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            if result.get("ok"):
                return result.get("result")
    except Exception as e:
        logger.error(f"Telegram API error ({method}): {e}")
    return None


def get_live_group_title(chat_id):
    """通过Telegram API获取群组名称，fallback到数据库"""
    if chat_id > 0:
        return f"私聊({chat_id})"
    result = telegram_api_get("getChat", {"chat_id": chat_id})
    if result:
        title = result.get("title", str(chat_id))
        try:
            db = get_db()
            db.execute(
                """INSERT INTO group_settings (chat_id, title) VALUES (?, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title""",
                (chat_id, title)
            )
            db.commit()
        except Exception:
            pass
        return title
    try:
        db = get_db()
        row = db.execute("SELECT title FROM group_settings WHERE chat_id=?", (chat_id,)).fetchone()
        if row and row["title"]:
            return row["title"]
    except Exception:
        pass
    return str(chat_id)


def get_live_member_count(chat_id):
    """通过Telegram API获取群组实时成员数"""
    if chat_id > 0:
        return 0
    result = telegram_api_get("getChatMemberCount", {"chat_id": chat_id})
    if result:
        return result
    try:
        db = get_db()
        row = db.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM group_users WHERE chat_id=?", (chat_id,)).fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0


def get_managed_groups(db, session):
    """获取当前管理员可管理的群组列表"""
    admin = db.execute(
        "SELECT * FROM admin_users WHERE username=?",
        (session.get("admin_user"),)
    ).fetchone()
    if not admin:
        return None  # 无权限
    if admin["role"] in (ROLE_CREATOR, ROLE_SUPER_ADMIN):  # 管理员不能看全部群组
        return None  # 全部群组
    try:
        perms = json.loads(admin["permissions"]) if admin["permissions"] else {}
        return perms.get("managed_groups", [])
    except:
        return []


def filter_managed_query(db, base_query, params, session):
    """根据管理员权限过滤查询"""
    managed = get_managed_groups(db, session)
    if managed is None:
        return base_query, params
    if not managed:
        return base_query + " AND 1=0", params
    placeholders = ",".join(["?" for _ in managed])
    return base_query + f" AND chat_id IN ({placeholders})", params + managed


# ==================== 认证装饰器 ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f):
    """需要管理员或更高权限"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def super_admin_required(f):
    """需要超级管理员或更高权限"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        role = session.get("role", "")
        if not is_at_least_role(role, ROLE_SUPER_ADMIN):
            flash("需要超级管理员权限", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function


def creator_required(f):
    """需要创建者权限"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "admin_id" not in session:
            return redirect(url_for("login"))
        if session.get("role") != ROLE_CREATOR:
            flash("需要创建者权限", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated_function


# ==================== 主题系统 ====================

@app.context_processor
def inject_theme():
    theme = session.get("theme", "dark")
    current_role = session.get("role", "")
    return {
        "current_theme": theme,
        "current_role": current_role,
        "ROLE_CREATOR": ROLE_CREATOR,
        "ROLE_SUPER_ADMIN": ROLE_SUPER_ADMIN,
        "ROLE_ADMIN": ROLE_ADMIN,
        "ROLE_EDITOR": ROLE_EDITOR,
    }


@app.route("/theme/<theme_name>", methods=["POST"])
@login_required
def set_theme(theme_name):
    if theme_name in ("dark", "light"):
        session["theme"] = theme_name
    return jsonify({"status": "ok", "theme": theme_name})


# ==================== 路由：登录 ====================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_id"] = 1
            session["admin_user"] = username
            session["theme"] = session.get("theme", "dark")
            session.permanent = True
            
            try:
                db = get_db()
                admin = db.execute(
                    "SELECT role FROM admin_users WHERE username=?",
                    (username,)
                ).fetchone()
                session["role"] = admin["role"] if admin else ROLE_SUPER_ADMIN
                db.execute(
                    "UPDATE admin_users SET last_login=CURRENT_TIMESTAMP WHERE username=?",
                    (username,)
                )
                db.commit()
            except Exception:
                session["role"] = ROLE_SUPER_ADMIN
            
            flash("登录成功", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("用户名或密码错误", "error")
    
    return render_template("login.html")


@app.route("/t/<token>")
def login_by_token(token):
    """通过独立URL登录管理员"""
    db = get_db()
    admin = db.execute(
        "SELECT * FROM admin_users WHERE login_token=? AND is_active=1",
        (token,)
    ).fetchone()
    
    if not admin:
        flash("无效的登录链接", "error")
        return redirect(url_for("login"))
    
    # 设置session
    session["admin_id"] = admin["id"]
    session["admin_user"] = admin["username"]
    session["role"] = admin["role"]
    session["theme"] = session.get("theme", "dark")
    session.permanent = True
    
    db.execute(
        "UPDATE admin_users SET last_login=CURRENT_TIMESTAMP WHERE id=?",
        (admin["id"],)
    )
    db.commit()
    
    flash(f"欢迎回来，{admin['username']}", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==================== 路由：仪表盘 ====================

@app.route("/")
@login_required
def dashboard():
    db = get_db()
    
    stats = {}
    
    # 根据权限过滤
    managed = get_managed_groups(db, session)
    
    if managed is None:
        # 超级管理员/创建者 - 全部
        row = db.execute("SELECT COUNT(DISTINCT chat_id) as cnt FROM group_users").fetchone()
        stats["total_groups"] = row["cnt"] if row else 0
        
        row = db.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM group_users").fetchone()
        stats["total_users"] = row["cnt"] if row else 0
        
        today = datetime.now().strftime("%Y-%m-%d")
        row = db.execute("SELECT COUNT(*) as cnt FROM checkin_records WHERE checkin_date=?", (today,)).fetchone()
        stats["today_checkins"] = row["cnt"] if row else 0
        
        row = db.execute("SELECT SUM(points) as total FROM group_users").fetchone()
        stats["total_points"] = row["total"] if row else 0
        
        row = db.execute("SELECT COUNT(*) as cnt FROM shop_items").fetchone()
        stats["total_items"] = row["cnt"] if row else 0
        
        # 群组列表 - 使用Telegram API获取实时成员数
        group_rows = db.execute(
            """SELECT DISTINCT chat_id FROM group_users
               UNION SELECT DISTINCT chat_id FROM group_settings"""
        ).fetchall()
        groups = []
        for row in group_rows:
            chat_id = row["chat_id"]
            title = get_live_group_title(chat_id)
            user_count = get_live_member_count(chat_id)
            groups.append({"chat_id": chat_id, "user_count": user_count, "title": title})
    else:
        if not managed:
            stats = {"total_groups": 0, "total_users": 0, "today_checkins": 0, "total_points": 0, "total_items": 0}
            groups = []
        else:
            placeholders = ",".join(["?" for _ in managed])
            
            row = db.execute(f"SELECT COUNT(DISTINCT chat_id) as cnt FROM group_users WHERE chat_id IN ({placeholders})", managed).fetchone()
            stats["total_groups"] = row["cnt"] if row else 0
            
            row = db.execute(f"SELECT COUNT(DISTINCT user_id) as cnt FROM group_users WHERE chat_id IN ({placeholders})", managed).fetchone()
            stats["total_users"] = row["cnt"] if row else 0
            
            today = datetime.now().strftime("%Y-%m-%d")
            row = db.execute(f"SELECT COUNT(*) as cnt FROM checkin_records WHERE checkin_date=? AND chat_id IN ({placeholders})", [today] + managed).fetchone()
            stats["today_checkins"] = row["cnt"] if row else 0
            
            row = db.execute(f"SELECT SUM(points) as total FROM group_users WHERE chat_id IN ({placeholders})", managed).fetchone()
            stats["total_points"] = row["total"] if row else 0
            
            row = db.execute(f"SELECT COUNT(*) as cnt FROM shop_items WHERE chat_id IN ({placeholders})", managed).fetchone()
            stats["total_items"] = row["cnt"] if row else 0
            
            group_rows = db.execute(
                f"""SELECT DISTINCT chat_id FROM group_users WHERE chat_id IN ({placeholders})
                   UNION SELECT DISTINCT chat_id FROM group_settings WHERE chat_id IN ({placeholders})""",
                managed + managed
            ).fetchall()
            groups = []
            for row in group_rows:
                chat_id = row["chat_id"]
                title = get_live_group_title(chat_id)
                user_count = get_live_member_count(chat_id)
                groups.append({"chat_id": chat_id, "user_count": user_count, "title": title})
    
    # 最近7天签到趋势
    checkin_trend = []
    for i in range(6, -1, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        if managed is None:
            row = db.execute("SELECT COUNT(*) as cnt FROM checkin_records WHERE checkin_date=?", (date,)).fetchone()
        elif managed:
            placeholders = ",".join(["?" for _ in managed])
            row = db.execute(f"SELECT COUNT(*) as cnt FROM checkin_records WHERE checkin_date=? AND chat_id IN ({placeholders})", [date] + managed).fetchone()
        else:
            row = {"cnt": 0}
        checkin_trend.append({"date": date, "count": row["cnt"] if row else 0})
    
    # 最近签到用户（去重，取最新5条）
    if managed is None:
        recent_checkins = db.execute(
            """SELECT gu.user_id, gu.first_name, gu.username, cr.checkin_date, cr.chat_id
               FROM checkin_records cr
               LEFT JOIN group_users gu ON cr.user_id=gu.user_id AND cr.chat_id=gu.chat_id
               ORDER BY cr.id DESC LIMIT 5"""
        ).fetchall()
    elif managed:
        placeholders = ",".join(["?" for _ in managed])
        recent_checkins = db.execute(
            f"""SELECT gu.user_id, gu.first_name, gu.username, cr.checkin_date, cr.chat_id
               FROM checkin_records cr
               LEFT JOIN group_users gu ON cr.user_id=gu.user_id AND cr.chat_id=gu.chat_id
               WHERE cr.chat_id IN ({placeholders})
               ORDER BY cr.id DESC LIMIT 5""",
            managed
        ).fetchall()
    else:
        recent_checkins = []
    
    # 最近注册用户（取最新5条）
    if managed is None:
        recent_users = db.execute(
            """SELECT user_id, first_name, username, chat_id, joined_at
               FROM group_users ORDER BY id DESC LIMIT 5"""
        ).fetchall()
    elif managed:
        placeholders = ",".join(["?" for _ in managed])
        recent_users = db.execute(
            f"""SELECT user_id, first_name, username, chat_id, joined_at
               FROM group_users WHERE chat_id IN ({placeholders})
               ORDER BY id DESC LIMIT 5""",
            managed
        ).fetchall()
    else:
        recent_users = []
    
    # 群组简要信息（不调用Telegram API，从数据库取）
    if managed is None:
        group_info = db.execute(
            """SELECT chat_id, COUNT(DISTINCT user_id) as user_count,
               MAX(first_name) as sample_name
               FROM group_users GROUP BY chat_id"""
        ).fetchall()
    elif managed:
        placeholders = ",".join(["?" for _ in managed])
        group_info = db.execute(
            f"""SELECT chat_id, COUNT(DISTINCT user_id) as user_count,
               MAX(first_name) as sample_name
               FROM group_users WHERE chat_id IN ({placeholders})
               GROUP BY chat_id""",
            managed
        ).fetchall()
    else:
        group_info = []
    
    return render_template(
        "dashboard.html",
        stats=stats,
        checkin_trend=checkin_trend,
        groups=groups,
        recent_checkins=recent_checkins,
        recent_users=recent_users,
        group_info=group_info
    )


# ==================== 路由：用户管理 ====================

@app.route("/users")
@login_required
def users_list():
    """群组列表页 - 显示所有可管理的群组卡片"""
    db = get_db()
    managed = get_managed_groups(db, session)

    if managed is None:
        # 超级管理员：看所有有用户的群
        group_rows = db.execute(
            """SELECT gu.chat_id, gs.title,
                      COUNT(*) as db_user_count,
                      SUM(gu.points) as total_points,
                      SUM(CASE WHEN gu.checkin_streak > 0 THEN 1 ELSE 0 END) as active_users,
                      SUM(CASE WHEN gu.is_banned THEN 1 ELSE 0 END) as banned_count
               FROM group_users gu
               LEFT JOIN group_settings gs ON gu.chat_id = gs.chat_id
               GROUP BY gu.chat_id ORDER BY gs.title"""
        ).fetchall()
    elif managed:
        placeholders = ",".join(["?" for _ in managed])
        group_rows = db.execute(
            f"""SELECT gu.chat_id, gs.title,
                        COUNT(*) as db_user_count,
                        SUM(gu.points) as total_points,
                        SUM(CASE WHEN gu.checkin_streak > 0 THEN 1 ELSE 0 END) as active_users,
                        SUM(CASE WHEN gu.is_banned THEN 1 ELSE 0 END) as banned_count
                 FROM group_users gu
                 LEFT JOIN group_settings gs ON gu.chat_id = gs.chat_id
                 WHERE gu.chat_id IN ({placeholders})
                 GROUP BY gu.chat_id ORDER BY gs.title""",
            managed
        ).fetchall()
    else:
        group_rows = []

    # 用数据库实际用户数（与点进去的列表一致）
    groups = []
    for row in group_rows:
        groups.append({
            "chat_id": row["chat_id"],
            "title": row["title"],
            "user_count": row["db_user_count"],
            "total_points": row["total_points"] or 0,
            "active_users": row["active_users"] or 0,
            "banned_count": row["banned_count"] or 0,
        })

    return render_template("users.html", groups=groups)


@app.route("/users/<chat_id>")
@login_required
def users_group(chat_id):
    """某群组的用户列表"""
    db = get_db()

    # 权限检查
    managed = get_managed_groups(db, session)
    if managed is not None:
        if managed and int(chat_id) not in [int(x) for x in managed]:
            flash("无权查看该群组", "error")
            return redirect(url_for("users_list"))

    page = request.args.get("page", 1, type=int)
    per_page = 20
    search = request.args.get("search", "").strip()

    query = "SELECT * FROM group_users WHERE chat_id=?"
    params = [int(chat_id)]

    if search:
        query += " AND (username LIKE ? OR first_name LIKE ? OR user_id=?)"
        params.extend([f"%{search}%", f"%{search}%", search])

    count_query = query.replace("SELECT *", "SELECT COUNT(*) as cnt")
    total = db.execute(count_query, params).fetchone()["cnt"]

    query += " ORDER BY points DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    users = db.execute(query, params).fetchall()
    total_pages = (total + per_page - 1) // per_page

    # 群组名称
    gs = db.execute("SELECT title FROM group_settings WHERE chat_id=?", (int(chat_id),)).fetchone()
    group_title = gs["title"] if gs else None

    return render_template(
        "users_group.html",
        users=users,
        chat_id=chat_id,
        group_title=group_title,
        page=page,
        total_pages=total_pages,
        total=total,
        search=search
    )



@app.route("/users/<chat_id>/<user_id>/reward", methods=["POST"])
@login_required
def reward_user(chat_id, user_id):
    db = get_db()
    chat_id = int(chat_id)
    user_id = int(user_id)
    points = request.form.get("points", 0, type=int)
    reason = request.form.get("reason", "").strip()
    
    if points <= 0:
        flash("积分必须大于0", "error")
        return redirect(url_for("users_list"))
    
    db.execute(
        "UPDATE group_users SET points=points+?, total_points=total_points+? WHERE chat_id=? AND user_id=?",
        (points, points, chat_id, user_id)
    )
    db.commit()
    
    db.execute(
        "INSERT INTO admin_logs (admin_user, action, target, detail) VALUES (?, ?, ?, ?)",
        (session.get("admin_user", "admin"), "reward", f"{user_id}", f"+{points}积分: {reason}")
    )
    db.commit()
    
    user_info = db.execute("SELECT username, first_name, points FROM group_users WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    if user_info:
        display_name = user_info["first_name"] or user_info["username"] or str(user_id)
        new_points = user_info["points"]
        admin_name = session.get("admin_user", "admin")
        notify_lines = [
            "🎁 <b>积分奖励通知</b>", "",
            f"👤 用户: {display_name}",
            f"💰 奖励: +{points} 积分",
        ]
        if reason:
            notify_lines.append(f"📝 原因: {reason}")
        notify_lines.extend([
            f"💎 当前积分: {new_points}",
            f"👨‍💼 管理员: {admin_name}",
            f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ])
        send_telegram_message(chat_id, "\n".join(notify_lines))

    flash(f"已奖励 {points} 积分", "success")
    return redirect(url_for("users_group", chat_id=chat_id))


@app.route("/users/<chat_id>/<user_id>/ban", methods=["POST"])
@login_required
def ban_user(chat_id, user_id):
    db = get_db()
    chat_id = int(chat_id)
    user_id = int(user_id)
    
    db.execute("UPDATE group_users SET is_banned=1 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    db.commit()
    
    db.execute(
        "INSERT INTO admin_logs (admin_user, action, target, detail) VALUES (?, ?, ?, ?)",
        (session.get("admin_user", "admin"), "ban", f"{user_id}", f"封禁用户")
    )
    db.commit()
    
    flash("用户已封禁", "success")
    return redirect(url_for("users_group", chat_id=chat_id))


@app.route("/users/<chat_id>/<user_id>/unban", methods=["POST"])
@login_required
def unban_user(chat_id, user_id):
    db = get_db()
    chat_id = int(chat_id)
    user_id = int(user_id)
    
    db.execute("UPDATE group_users SET is_banned=0 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    db.commit()
    
    db.execute(
        "INSERT INTO admin_logs (admin_user, action, target, detail) VALUES (?, ?, ?, ?)",
        (session.get("admin_user", "admin"), "unban", f"{user_id}", f"解封用户")
    )
    db.commit()
    
    flash("用户已解封", "success")
    return redirect(url_for("users_group", chat_id=chat_id))


# ==================== 路由：商品管理（分群） ====================

def check_group_permission(db, session, chat_id):
    """检查当前用户是否有权操作指定群组"""
    managed = get_managed_groups(db, session)
    if managed is None:
        return True
    return chat_id in managed


def get_managed_groups_list(db, session):
    """获取当前用户可管理的群组列表（带实时信息）"""
    managed = get_managed_groups(db, session)
    if managed is None:
        groups = db.execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall()
    elif managed:
        if not managed:
            return []
        placeholders = ",".join(["?" for _ in managed])
        groups = db.execute(
            f"SELECT chat_id, title FROM group_settings WHERE chat_id IN ({placeholders}) ORDER BY chat_id",
            managed
        ).fetchall()
    else:
        return []
    
    result = []
    for g in groups:
        chat_id = g["chat_id"]
        title = g["title"] or get_live_group_title(chat_id)
        member_count = get_live_member_count(chat_id)
        item_count = db.execute(
            "SELECT COUNT(*) as cnt FROM shop_items WHERE chat_id=?", (chat_id,)
        ).fetchone()["cnt"]
        result.append({
            "chat_id": chat_id,
            "title": title,
            "member_count": member_count,
            "item_count": item_count
        })
    return result


@app.route("/shop")
@login_required
def shop_list():
    """商品管理首页 - 显示群组列表"""
    db = get_db()
    groups = get_managed_groups_list(db, session)
    return render_template("shop.html", groups=groups)


@app.route("/shop/<chat_id>")
@login_required
def shop_group_items(chat_id):
    """指定群组的商品列表"""
    chat_id = int(chat_id)
    db = get_db()
    
    if not check_group_permission(db, session, chat_id):
        flash("无权操作该群组", "error")
        return redirect(url_for("shop_list"))
    
    items = db.execute(
        "SELECT * FROM shop_items WHERE chat_id=? ORDER BY item_id", (chat_id,)
    ).fetchall()
    group_title = get_live_group_title(chat_id)
    
    return render_template("shop_items.html", items=items, chat_id=chat_id, group_title=group_title)


@app.route("/shop/<chat_id>/add", methods=["GET", "POST"])
@login_required
def shop_add(chat_id):
    """添加商品到指定群组"""
    chat_id = int(chat_id)
    db = get_db()
    
    if not check_group_permission(db, session, chat_id):
        flash("无权操作该群组", "error")
        return redirect(url_for("shop_list"))
    
    group_title = get_live_group_title(chat_id)
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", 0, type=int)
        stock = request.form.get("stock", -1, type=int)
        item_type = request.form.get("type", "general").strip()
        
        if not name or price <= 0:
            flash("商品名和价格必须有效", "error")
            return render_template("shop_form.html", item=None, action="add", chat_id=chat_id, group_title=group_title)
        
        db.execute(
            "INSERT INTO shop_items (name, description, price, stock, type, chat_id) VALUES (?, ?, ?, ?, ?, ?)",
            (name, description, price, stock, item_type, chat_id)
        )
        db.commit()
        flash("商品添加成功", "success")
        return redirect(url_for("shop_group_items", chat_id=chat_id))
    
    return render_template("shop_form.html", item=None, action="add", chat_id=chat_id, group_title=group_title)


@app.route("/shop/<chat_id>/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def shop_edit(chat_id, item_id):
    """编辑指定群组的商品"""
    chat_id = int(chat_id)
    db = get_db()
    
    if not check_group_permission(db, session, chat_id):
        flash("无权操作该群组", "error")
        return redirect(url_for("shop_list"))
    
    group_title = get_live_group_title(chat_id)
    
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", 0, type=int)
        stock = request.form.get("stock", -1, type=int)
        item_type = request.form.get("type", "general").strip()
        
        if not name or price <= 0:
            flash("商品名和价格必须有效", "error")
            item = db.execute("SELECT * FROM shop_items WHERE item_id=? AND chat_id=?", (item_id, chat_id)).fetchone()
            return render_template("shop_form.html", item=item, action="edit", chat_id=chat_id, group_title=group_title)
        
        db.execute(
            "UPDATE shop_items SET name=?, description=?, price=?, stock=?, type=? WHERE item_id=? AND chat_id=?",
            (name, description, price, stock, item_type, item_id, chat_id)
        )
        db.commit()
        flash("商品更新成功", "success")
        return redirect(url_for("shop_group_items", chat_id=chat_id))
    
    item = db.execute("SELECT * FROM shop_items WHERE item_id=? AND chat_id=?", (item_id, chat_id)).fetchone()
    if not item:
        flash("商品不存在", "error")
        return redirect(url_for("shop_group_items", chat_id=chat_id))
    
    return render_template("shop_form.html", item=item, action="edit", chat_id=chat_id, group_title=group_title)


@app.route("/shop/<chat_id>/delete/<int:item_id>", methods=["POST"])
@login_required
def shop_delete(chat_id, item_id):
    """删除指定群组的商品"""
    chat_id = int(chat_id)
    db = get_db()
    
    if not check_group_permission(db, session, chat_id):
        flash("无权操作该群组", "error")
        return redirect(url_for("shop_list"))
    
    db.execute("DELETE FROM shop_items WHERE item_id=? AND chat_id=?", (item_id, chat_id))
    db.commit()
    flash("商品已删除", "success")
    return redirect(url_for("shop_group_items", chat_id=chat_id))


@app.route("/shop/<chat_id>/toggle/<int:item_id>", methods=["POST"])
@login_required
def shop_toggle(chat_id, item_id):
    """切换商品启用/关闭状态"""
    chat_id = int(chat_id)
    db = get_db()
    
    if not check_group_permission(db, session, chat_id):
        flash("无权操作该群组", "error")
        return redirect(url_for("shop_list"))
    
    item = db.execute("SELECT enabled FROM shop_items WHERE item_id=? AND chat_id=?", (item_id, chat_id)).fetchone()
    if not item:
        flash("商品不存在", "error")
        return redirect(url_for("shop_group_items", chat_id=chat_id))
    
    new_status = 0 if item["enabled"] else 1
    db.execute("UPDATE shop_items SET enabled=? WHERE item_id=? AND chat_id=?", (new_status, item_id, chat_id))
    db.commit()
    status_text = "已开启" if new_status else "已关闭"
    flash(f"商品{status_text}", "success")
    return redirect(url_for("shop_group_items", chat_id=chat_id))


# ==================== 路由：群组管理 ====================
# ==================== 路由：群组管理 ====================

@app.route("/groups")
@login_required
def groups_list():
    db = get_db()
    
    managed = get_managed_groups(db, session)
    
    if managed is None:
        group_rows = db.execute(
            """SELECT DISTINCT chat_id FROM group_users
               UNION SELECT DISTINCT chat_id FROM group_settings"""
        ).fetchall()
    elif managed:
        if not managed:
            group_rows = []
        else:
            placeholders = ",".join(["?" for _ in managed])
            group_rows = db.execute(
                f"""SELECT DISTINCT chat_id FROM group_users WHERE chat_id IN ({placeholders})
                    UNION SELECT DISTINCT chat_id FROM group_settings WHERE chat_id IN ({placeholders})""",
                managed + managed
            ).fetchall()
    else:
        group_rows = []
    
    groups = []
    group_settings = {}
    for row in group_rows:
        chat_id = row["chat_id"]
        title = get_live_group_title(chat_id)
        member_count = get_live_member_count(chat_id)
        stats = db.execute(
            "SELECT COALESCE(SUM(points), 0) as total_points FROM group_users WHERE chat_id=?",
            (chat_id,)
        ).fetchone()
        total_points = stats["total_points"] if stats else 0
        
        settings = db.execute("SELECT * FROM group_settings WHERE chat_id=?", (chat_id,)).fetchone()
        group_settings[chat_id] = settings
        
        groups.append({
            "chat_id": chat_id,
            "user_count": member_count,
            "total_points": total_points,
            "title": title
        })
    
    return render_template("groups.html", groups=groups, group_settings=group_settings)


@app.route("/groups/<chat_id>/settings", methods=["GET", "POST"])
@login_required
def group_settings_edit(chat_id):
    db = get_db()
    chat_id = int(chat_id)
    
    # 权限检查
    if not check_group_permission(db, session, chat_id):
        flash("无权修改该群组设置", "error")
        return redirect(url_for("groups_list"))
    
    if request.method == "POST":
        welcome_message = request.form.get("welcome_message", "").strip()
        welcome_enabled = 1 if request.form.get("welcome_enabled") else 0
        anti_spam_enabled = 1 if request.form.get("anti_spam_enabled") else 0
        checkin_enabled = 1 if request.form.get("checkin_enabled") else 0
        shop_enabled = 1 if request.form.get("shop_enabled") else 0
        verify_enabled = 1 if request.form.get("verify_enabled") else 0
        warn_threshold = request.form.get("warn_threshold", 3, type=int)
        mute_threshold = request.form.get("mute_threshold", 5, type=int)
        ban_threshold = request.form.get("ban_threshold", 10, type=int)
        
        db.execute(
            """INSERT INTO group_settings (chat_id, welcome_message, welcome_enabled, 
               anti_spam_enabled, checkin_enabled, shop_enabled, verify_enabled,
               warn_threshold, mute_threshold, ban_threshold)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET
               welcome_message=excluded.welcome_message,
               welcome_enabled=excluded.welcome_enabled,
               anti_spam_enabled=excluded.anti_spam_enabled,
               checkin_enabled=excluded.checkin_enabled,
               shop_enabled=excluded.shop_enabled,
               verify_enabled=excluded.verify_enabled,
               warn_threshold=excluded.warn_threshold,
               mute_threshold=excluded.mute_threshold,
               ban_threshold=excluded.ban_threshold""",
            (chat_id, welcome_message, welcome_enabled, anti_spam_enabled,
             checkin_enabled, shop_enabled, verify_enabled,
             warn_threshold, mute_threshold, ban_threshold)
        )
        db.commit()
        
        flash("群组设置已更新", "success")
        return redirect(url_for("groups_list"))
    
    settings = db.execute("SELECT * FROM group_settings WHERE chat_id=?", (chat_id,)).fetchone()
    group_title = get_group_title(db, chat_id)
    
    return render_template("group_settings.html", chat_id=chat_id, settings=settings, group_title=group_title)


# ==================== 路由：管理员管理（含创建者权限控制） ====================

@app.route("/admins")
@login_required
def admins_list():
    db = get_db()
    
    # 获取所有管理员
    admins = db.execute("SELECT * FROM admin_users ORDER BY id").fetchall()
    
    # 为每个管理员生成群组名称
    admin_groups = {}
    for admin in admins:
        try:
            perms = json.loads(admin["permissions"]) if admin["permissions"] else {}
            managed = perms.get("managed_groups", [])
        except:
            managed = []
        
        if admin["role"] in (ROLE_CREATOR, ROLE_SUPER_ADMIN):  # 管理员不能看全部群组
            admin_groups[admin["id"]] = "全部群组"
        elif managed:
            titles = []
            for cid in managed:
                t = db.execute("SELECT title FROM group_settings WHERE chat_id=?", (cid,)).fetchone()
                titles.append(t["title"] if t and t["title"] else str(cid))
            admin_groups[admin["id"]] = ", ".join(titles)
        else:
            admin_groups[admin["id"]] = "无"
    
    return render_template("admins.html", admins=admins, admin_groups=admin_groups)


@app.route("/admins/add", methods=["GET", "POST"])
@login_required
def admin_add():
    current_admin = db_session()
    admin_role = session.get("role") or (current_admin["role"] if current_admin else None)
    
    # 需要超级管理员或更高权限
    if not is_at_least_role(admin_role, ROLE_SUPER_ADMIN):
        flash("需要超级管理员权限", "error")
        return redirect(url_for("dashboard"))
    
    # 超级管理员创建其他超管需要创建者授权
    can_create_super_admin = False
    if admin_role == ROLE_SUPER_ADMIN:
        # 检查创建者是否允许超管创建其他超管
        if current_admin:
            try:
                perms = json.loads(current_admin["permissions"]) if current_admin["permissions"] else {}
                can_create_super_admin = perms.get("can_create_super_admin", False)
            except:
                can_create_super_admin = False
    
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "admin").strip()
        telegram_id = request.form.get("telegram_id", "").strip()
        
        if not username or not password:
            flash("用户名和密码不能为空", "error")
            return render_template("admin_form.html", admin=None, action="add",
                                   groups=get_db().execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall(),
                                   managed_groups=[],
                                   can_create_super_admin=can_create_super_admin)
        
        # 权限检查：超级管理员不能创建超管（除非被授权）
        if role == ROLE_SUPER_ADMIN and admin_role == ROLE_SUPER_ADMIN and not can_create_super_admin:
            flash("超级管理员无权创建其他超级管理员，需要创建者授权", "error")
            return redirect(url_for("admin_add"))
        
        # 只有创建者能创建其他创建者
        if role == ROLE_CREATOR and admin_role != ROLE_CREATOR:
            flash("只有创建者才能创建其他创建者", "error")
            return redirect(url_for("admin_add"))
        
        # 超级管理员不能创建比自己角色高的
        if role_level(role) >= role_level(admin_role) and admin_role != ROLE_CREATOR:
            flash("不能创建与自己同级或更高级别的管理员", "error")
            return redirect(url_for("admin_add"))
        
        db = get_db()
        
        existing = db.execute("SELECT id FROM admin_users WHERE username=?", (username,)).fetchone()
        if existing:
            flash("用户名已存在", "error")
            return render_template("admin_form.html", admin=None, action="add",
                                   groups=db.execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall(),
                                   managed_groups=[],
                                   can_create_super_admin=can_create_super_admin)
        
        managed_groups = request.form.getlist("managed_groups")
        permissions = json.dumps({"managed_groups": [int(g) for g in managed_groups]})
        
        # 生成独立登录token
        login_token = secrets.token_urlsafe(32)
        
        db.execute(
            "INSERT INTO admin_users (username, password_hash, role, telegram_id, permissions, login_token, created_at) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (username, hash_password(password), role, telegram_id, permissions, login_token)
        )
        db.commit()
        
        db.execute(
            "INSERT INTO admin_logs (admin_user, action, target, detail) VALUES (?, ?, ?, ?)",
            (session.get("admin_user", "admin"), "add_admin", username, f"角色: {role}, 管理群: {len(managed_groups)}个")
        )
        db.commit()
        
        flash(f"管理员 {username} 添加成功", "success")
        return redirect(url_for("admins_list"))
    
    db = get_db()
    groups = db.execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall()
    return render_template("admin_form.html", admin=None, action="add", groups=groups, managed_groups=[],
                           can_create_super_admin=can_create_super_admin)


@app.route("/admins/<int:admin_id>/edit", methods=["GET", "POST"])
@login_required
def admin_edit(admin_id):
    current_admin = db_session()
    admin_role = session.get("role") or (current_admin["role"] if current_admin else None)
    
    if not is_at_least_role(admin_role, ROLE_SUPER_ADMIN):
        flash("需要超级管理员权限", "error")
        return redirect(url_for("dashboard"))
    
    db = get_db()
    admin = db.execute("SELECT * FROM admin_users WHERE id=?", (admin_id,)).fetchone()
    if not admin:
        flash("管理员不存在", "error")
        return redirect(url_for("admins_list"))
    
    # === 创建者保护：只有创建者自己能编辑创建者 ===
    if admin["role"] == ROLE_CREATOR and admin_role != ROLE_CREATOR:
        flash("无法编辑创建者的信息", "error")
        return redirect(url_for("admins_list"))
    
    # === 超级管理员不能编辑同级或更高级 ===
    if admin_role == ROLE_SUPER_ADMIN and role_level(admin["role"]) >= role_level(ROLE_SUPER_ADMIN):
        flash("超级管理员无法编辑其他超级管理员", "error")
        return redirect(url_for("admins_list"))
    
    # 超级管理员不能将普通管理员提升为超管（除非被授权）
    can_create_super_admin = False
    if admin_role == ROLE_SUPER_ADMIN and current_admin:
        try:
            perms = json.loads(current_admin["permissions"]) if current_admin["permissions"] else {}
            can_create_super_admin = perms.get("can_create_super_admin", False)
        except:
            can_create_super_admin = False
    
    if request.method == "POST":
        role = request.form.get("role", "admin").strip()
        telegram_id = request.form.get("telegram_id", "").strip()
        new_password = request.form.get("password", "").strip()
        
        # 权限检查：超级管理员不能提升为超管（除非被授权）
        if role in (ROLE_SUPER_ADMIN, ROLE_CREATOR) and admin_role == ROLE_SUPER_ADMIN and not can_create_super_admin:
            flash("超级管理员无权设置超管/创建者角色", "error")
            return redirect(url_for("admin_edit", admin_id=admin_id))
        
        # 只有创建者能设置创建者角色
        if role == ROLE_CREATOR and admin_role != ROLE_CREATOR:
            flash("只有创建者才能设置创建者角色", "error")
            return redirect(url_for("admin_edit", admin_id=admin_id))
        
        # 超级管理员不能提升到比自己高
        if role_level(role) >= role_level(admin_role) and admin_role != ROLE_CREATOR:
            flash("不能设置与自己同级或更高级别的角色", "error")
            return redirect(url_for("admin_edit", admin_id=admin_id))
        
        managed_groups = request.form.getlist("managed_groups")
        permissions = json.dumps({"managed_groups": [int(g) for g in managed_groups]})
        
        if new_password:
            db.execute(
                "UPDATE admin_users SET role=?, telegram_id=?, password_hash=?, permissions=? WHERE id=?",
                (role, telegram_id, hash_password(new_password), permissions, admin_id)
            )
        else:
            db.execute(
                "UPDATE admin_users SET role=?, telegram_id=?, permissions=? WHERE id=?",
                (role, telegram_id, permissions, admin_id)
            )
        db.commit()
        
        db.execute(
            "INSERT INTO admin_logs (admin_user, action, target, detail) VALUES (?, ?, ?, ?)",
            (session.get("admin_user", "admin"), "edit_admin", admin["username"], f"角色: {role}, 管理群: {len(managed_groups)}个")
        )
        db.commit()
        
        flash("管理员信息已更新", "success")
        return redirect(url_for("admins_list"))
    
    groups = db.execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall()
    
    try:
        perms = json.loads(admin["permissions"]) if admin["permissions"] else {}
        managed_groups = perms.get("managed_groups", [])
    except:
        managed_groups = []
    
    # 生成独立登录URL
    base_url = "https://qg.xkwangluo.cn"
    login_url = f"{base_url}/t/{admin['login_token']}" if admin["login_token"] else ""
    
    return render_template("admin_form.html", admin=admin, action="edit", groups=groups,
                           managed_groups=managed_groups, login_url=login_url,
                           can_create_super_admin=can_create_super_admin)


@app.route("/admins/<int:admin_id>/regen_token", methods=["POST"])
@login_required
def admin_regen_token(admin_id):
    """重新生成管理员独立登录URL"""
    current_admin = db_session()
    admin_role = session.get("role") or (current_admin["role"] if current_admin else None)
    if not is_at_least_role(admin_role, ROLE_SUPER_ADMIN):
        flash("需要超级管理员权限", "error")
        return redirect(url_for("dashboard"))
    
    db = get_db()
    admin = db.execute("SELECT * FROM admin_users WHERE id=?", (admin_id,)).fetchone()
    if not admin:
        flash("管理员不存在", "error")
        return redirect(url_for("admins_list"))
    
    # 创建者保护
    if admin["role"] == ROLE_CREATOR and admin_role != ROLE_CREATOR:
        flash("无法操作创建者", "error")
        return redirect(url_for("admins_list"))
    
    new_token = secrets.token_urlsafe(32)
    db.execute("UPDATE admin_users SET login_token=? WHERE id=?", (new_token, admin_id))
    db.commit()
    
    flash("登录链接已重新生成", "success")
    return redirect(url_for("admin_edit", admin_id=admin_id))


@app.route("/admins/<int:admin_id>/delete", methods=["POST"])
@login_required
def admin_delete(admin_id):
    current_admin = db_session()
    admin_role = session.get("role") or (current_admin["role"] if current_admin else None)
    if not is_at_least_role(admin_role, ROLE_SUPER_ADMIN):
        flash("需要超级管理员权限", "error")
        return redirect(url_for("dashboard"))
    
    db = get_db()
    admin = db.execute("SELECT * FROM admin_users WHERE id=?", (admin_id,)).fetchone()
    if not admin:
        flash("管理员不存在", "error")
        return redirect(url_for("admins_list"))
    
    # === 创建者不可删除 ===
    if admin["role"] == ROLE_CREATOR:
        flash("创建者不可删除", "error")
        return redirect(url_for("admins_list"))
    
    # 超级管理员不能删除同级或更高级
    if admin_role == ROLE_SUPER_ADMIN and role_level(admin["role"]) >= role_level(ROLE_SUPER_ADMIN):
        flash("超级管理员无法删除其他超级管理员", "error")
        return redirect(url_for("admins_list"))
    
    if admin["username"] == session.get("admin_user"):
        flash("不能删除自己的账号", "error")
        return redirect(url_for("admins_list"))
    
    db.execute("DELETE FROM admin_users WHERE id=?", (admin_id,))
    db.commit()
    
    db.execute(
        "INSERT INTO admin_logs (admin_user, action, target, detail) VALUES (?, ?, ?, ?)",
        (session.get("admin_user", "admin"), "delete_admin", admin["username"], "删除管理员")
    )
    db.commit()
    
    flash(f"管理员 {admin['username']} 已删除", "success")
    return redirect(url_for("admins_list"))


@app.route("/admins/<int:admin_id>/toggle_create_super_admin", methods=["POST"])
@login_required
def toggle_create_super_admin(admin_id):
    """创建者：允许/禁止超管创建其他超管"""
    current_admin = db_session()
    if not current_admin or current_admin["role"] != ROLE_CREATOR:
        flash("需要创建者权限", "error")
        return redirect(url_for("dashboard"))
    
    db = get_db()
    admin = db.execute("SELECT * FROM admin_users WHERE id=?", (admin_id,)).fetchone()
    if not admin:
        flash("管理员不存在", "error")
        return redirect(url_for("admins_list"))
    
    if admin["role"] != ROLE_SUPER_ADMIN:
        flash("此功能仅针对超级管理员", "error")
        return redirect(url_for("admins_list"))
    
    # 切换权限
    try:
        perms = json.loads(admin["permissions"]) if admin["permissions"] else {}
    except:
        perms = {}
    
    current_val = perms.get("can_create_super_admin", False)
    perms["can_create_super_admin"] = not current_val
    
    db.execute("UPDATE admin_users SET permissions=? WHERE id=?", (json.dumps(perms), admin_id))
    db.commit()
    
    status = "允许" if not current_val else "禁止"
    flash(f"已{status} {admin['username']} 创建其他超级管理员", "success")
    return redirect(url_for("admins_list"))


def db_session():
    db = get_db()
    return db.execute("SELECT * FROM admin_users WHERE username=?", (session.get("admin_user"),)).fetchone()


# ==================== 路由：日志 ====================

@app.route("/logs")
@login_required
def logs_list():
    db = get_db()
    page = request.args.get("page", 1, type=int)
    per_page = 30
    
    total = db.execute("SELECT COUNT(*) as cnt FROM admin_logs").fetchone()["cnt"]
    logs = db.execute(
        "SELECT * FROM admin_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page)
    ).fetchall()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template("logs.html", logs=logs, page=page, total_pages=total_pages)


# ==================== 路由：排行榜 ====================

@app.route("/leaderboard")
@login_required
def leaderboard():
    db = get_db()
    chat_id = request.args.get("chat_id", "")
    
    chat_id_int = None
    if chat_id:
        try:
            chat_id_int = int(chat_id)
        except ValueError:
            pass
    
    # 获取可管理的群组
    managed = get_managed_groups(db, session)
    
    if managed is None:
        groups = db.execute(
            """SELECT DISTINCT gu.chat_id, gs.title FROM group_users gu
               LEFT JOIN group_settings gs ON gu.chat_id = gs.chat_id ORDER BY gu.chat_id"""
        ).fetchall()
    elif managed:
        placeholders = ",".join(["?" for _ in managed])
        groups = db.execute(
            f"""SELECT DISTINCT gu.chat_id, gs.title FROM group_users gu
               LEFT JOIN group_settings gs ON gu.chat_id = gs.chat_id
               WHERE gu.chat_id IN ({placeholders}) ORDER BY gu.chat_id""",
            managed
        ).fetchall()
    else:
        groups = []
    
    if not chat_id_int and groups:
        chat_id_int = groups[0]["chat_id"]
    
    users = []
    if chat_id_int:
        users = db.execute(
            """SELECT user_id, username, first_name, points, total_points, 
               checkin_streak, is_vip, level
               FROM group_users WHERE chat_id=? ORDER BY points DESC LIMIT 50""",
            (chat_id_int,)
        ).fetchall()
    
    return render_template("leaderboard.html", users=users, groups=groups, chat_id=chat_id_int)


# ==================== 路由：API ====================

@app.route("/api/stats")
@login_required
def api_stats():
    db = get_db()
    stats = {}
    
    row = db.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM group_users").fetchone()
    stats["total_users"] = row["cnt"] if row else 0
    
    row = db.execute("SELECT COUNT(DISTINCT chat_id) as cnt FROM group_users").fetchone()
    stats["total_groups"] = row["cnt"] if row else 0
    
    today = datetime.now().strftime("%Y-%m-%d")
    row = db.execute("SELECT COUNT(*) as cnt FROM checkin_records WHERE checkin_date=?", (today,)).fetchone()
    stats["today_checkins"] = row["cnt"] if row else 0
    
    return jsonify(stats)


@app.route("/api/user/<chat_id>/<user_id>")
@login_required
def api_user_info(chat_id, user_id):
    db = get_db()
    user = db.execute(
        "SELECT * FROM group_users WHERE chat_id=? AND user_id=?",
        (int(chat_id), int(user_id))
    ).fetchone()
    
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    return jsonify(dict(user))



# ==================== IPTV兑换码管理 ====================

@app.route("/cards")
@login_required
def cards_list():
    db = get_db()
    filter_chat_id = request.args.get("chat_id", "", type=str)
    filter_item_id = request.args.get("item_id", "", type=str)
    filter_status = request.args.get("status", "all", type=str)
    
    query = "SELECT * FROM iptv_cards WHERE 1=1"
    params = []
    
    if filter_chat_id:
        try:
            query += " AND chat_id=?"
            params.append(int(filter_chat_id))
        except ValueError:
            pass
    if filter_item_id:
        try:
            query += " AND shop_item_id=?"
            params.append(int(filter_item_id))
        except ValueError:
            pass
    if filter_status and filter_status != "all":
        query += " AND status=?"
        params.append(filter_status)
    
    query += " ORDER BY created_at DESC"
    cards = db.execute(query, params).fetchall()
    
    total = len(cards)
    unused = sum(1 for c in cards if c["status"] == "unused")
    used = sum(1 for c in cards if c["status"] == "used")
    
    managed = get_managed_groups(db, session)
    if managed is None:
        groups_raw = db.execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall()
    elif managed:
        if managed:
            placeholders = ",".join(["?" for _ in managed])
            groups_raw = db.execute(f"SELECT chat_id, title FROM group_settings WHERE chat_id IN ({placeholders}) ORDER BY chat_id", managed).fetchall()
        else:
            groups_raw = []
    else:
        groups_raw = []
    
    # 为每个群组计算卡片统计
    groups = []
    for g in groups_raw:
        g_chat_id = g["chat_id"]
        card_count = db.execute("SELECT COUNT(*) as cnt FROM iptv_cards WHERE chat_id=?", (g_chat_id,)).fetchone()["cnt"]
        unused_count = db.execute("SELECT COUNT(*) as cnt FROM iptv_cards WHERE chat_id=? AND status='unused'", (g_chat_id,)).fetchone()["cnt"]
        groups.append({"chat_id": g_chat_id, "title": g["title"], "card_count": card_count, "unused_count": unused_count})
    
    shop_items = db.execute("SELECT item_id, name, chat_id FROM shop_items ORDER BY chat_id").fetchall()
    
    return render_template("cards.html", cards=cards, total=total, unused=unused, used=used,
                           groups=groups, shop_items=shop_items,
                           filter_chat_id=filter_chat_id, filter_item_id=filter_item_id, filter_status=filter_status)


@app.route("/cards/add", methods=["GET", "POST"])
@login_required
def card_add():
    db = get_db()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        days = int(request.form.get("days", 7))
        card_type = request.form.get("card_type", "normal")
        batch_name = request.form.get("batch_name", "").strip()
        bind_chat_id = request.form.get("bind_chat_id", "").strip()
        bind_item_id = request.form.get("bind_item_id", "").strip()
        if not code:
            return render_template("card_form.html", error="兑换码不能为空")
        chat_id_val = int(bind_chat_id) if bind_chat_id else None
        item_id_val = int(bind_item_id) if bind_item_id else None
        try:
            db.execute(
                "INSERT INTO iptv_cards (code, days, card_type, batch_name, chat_id, shop_item_id) VALUES (?, ?, ?, ?, ?, ?)",
                (code, days, card_type, batch_name, chat_id_val, item_id_val)
            )
            db.commit()
            return redirect(url_for("cards_list"))
        except Exception:
            return render_template("card_form.html", error="兑换码已存在")
    
    managed = get_managed_groups(db, session)
    if managed is None:
        groups = db.execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall()
    elif managed:
        if managed:
            placeholders = ",".join(["?" for _ in managed])
            groups = db.execute(f"SELECT chat_id, title FROM group_settings WHERE chat_id IN ({placeholders}) ORDER BY chat_id", managed).fetchall()
        else:
            groups = []
    else:
        groups = []
    shop_items = db.execute("SELECT item_id, name, chat_id FROM shop_items ORDER BY chat_id").fetchall()
    return render_template("card_form.html", groups=groups, shop_items=shop_items)


@app.route("/cards/batch", methods=["GET", "POST"])
@login_required
def card_batch_add():
    db = get_db()
    if request.method == "POST":
        codes_text = request.form.get("codes", "").strip()
        days = int(request.form.get("days", 7))
        card_type = request.form.get("card_type", "normal")
        batch_name = request.form.get("batch_name", "").strip()
        bind_chat_id = request.form.get("bind_chat_id", "").strip()
        bind_item_id = request.form.get("bind_item_id", "").strip()
        if not codes_text:
            return render_template("card_batch.html", error="请输入兑换码")
        chat_id_val = int(bind_chat_id) if bind_chat_id else None
        item_id_val = int(bind_item_id) if bind_item_id else None
        codes = [c.strip() for c in codes_text.split(chr(10)) if c.strip()]
        added = 0
        skipped = 0
        for code in codes:
            try:
                db.execute(
                    "INSERT INTO iptv_cards (code, days, card_type, batch_name, chat_id, shop_item_id) VALUES (?, ?, ?, ?, ?, ?)",
                    (code, days, card_type, batch_name, chat_id_val, item_id_val)
                )
                added += 1
            except Exception:
                skipped += 1
        db.commit()
        return render_template("card_batch.html", success=f"成功添加 {added} 张，跳过 {skipped} 张重复")
    
    managed = get_managed_groups(db, session)
    if managed is None:
        groups = db.execute("SELECT chat_id, title FROM group_settings ORDER BY chat_id").fetchall()
    elif managed:
        if managed:
            placeholders = ",".join(["?" for _ in managed])
            groups = db.execute(f"SELECT chat_id, title FROM group_settings WHERE chat_id IN ({placeholders}) ORDER BY chat_id", managed).fetchall()
        else:
            groups = []
    else:
        groups = []
    shop_items = db.execute("SELECT item_id, name, chat_id FROM shop_items ORDER BY chat_id").fetchall()
    return render_template("card_batch.html", groups=groups, shop_items=shop_items)


@app.route("/cards/delete/<int:card_id>", methods=["POST"])
@login_required
def card_delete(card_id):
    db = get_db()
    db.execute("DELETE FROM iptv_cards WHERE id=?", (card_id,))
    db.commit()
    return redirect(url_for("cards_list"))


@app.route("/cards/toggle/<int:card_id>", methods=["POST"])
@login_required
def card_toggle(card_id):
    db = get_db()
    card = db.execute("SELECT * FROM iptv_cards WHERE id=?", (card_id,)).fetchone()
    if card:
        new_status = "unused" if card["status"] == "used" else "used"
        db.execute("UPDATE iptv_cards SET status=? WHERE id=?", (new_status, card_id))
        db.commit()
    return redirect(url_for("cards_list"))


def page_not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template("500.html"), 500


# ==================== 启动 ====================

if __name__ == "__main__":
    host = os.environ.get("ADMIN_PANEL_HOST", "0.0.0.0")
    port = int(os.environ.get("ADMIN_PANEL_PORT", 5000))
    
    logger.info(f"Starting Admin Panel on {host}:{port}")
    app.run(host=host, port=port, debug=False)
