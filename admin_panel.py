"""
星辰守望者 - 后台管理面板
域名: jq.xkwangluo.cn
"""

import os
import json
import sqlite3
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, flash, jsonify, g
)

import config

app = Flask(__name__)
app.secret_key = config.ADMIN_PANEL_SECRET_KEY

# ==================== 数据库连接 ====================

def get_db():
    """获取数据库连接"""
    if 'db' not in g:
        g.db = sqlite3.connect(config.DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# ==================== 登录验证 ====================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== HTML模板 ====================

BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - 星辰守望者管理面板</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            min-height: 100vh;
        }
        .sidebar {
            position: fixed;
            left: 0;
            top: 0;
            bottom: 0;
            width: 240px;
            background: #1a1a2e;
            border-right: 1px solid #2a2a4a;
            padding: 20px 0;
            z-index: 100;
        }
        .sidebar .logo {
            text-align: center;
            padding: 20px;
            border-bottom: 1px solid #2a2a4a;
            margin-bottom: 20px;
        }
        .sidebar .logo h2 {
            color: #ffd700;
            font-size: 18px;
        }
        .sidebar .logo p {
            color: #888;
            font-size: 12px;
            margin-top: 5px;
        }
        .sidebar a {
            display: block;
            padding: 12px 24px;
            color: #aaa;
            text-decoration: none;
            transition: all 0.3s;
        }
        .sidebar a:hover, .sidebar a.active {
            background: #2a2a4a;
            color: #ffd700;
            border-left: 3px solid #ffd700;
        }
        .main-content {
            margin-left: 240px;
            padding: 30px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 24px;
            color: #ffd700;
        }
        .card {
            background: #1a1a2e;
            border: 1px solid #2a2a4a;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }
        .card h3 {
            color: #ffd700;
            margin-bottom: 16px;
            font-size: 16px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: #1a1a2e;
            border: 1px solid #2a2a4a;
            border-radius: 12px;
            padding: 24px;
            text-align: center;
        }
        .stat-card .number {
            font-size: 32px;
            color: #ffd700;
            font-weight: bold;
        }
        .stat-card .label {
            color: #888;
            margin-top: 8px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid #2a2a4a;
        }
        th {
            color: #ffd700;
            font-weight: 600;
        }
        tr:hover {
            background: #2a2a4a;
        }
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .btn-primary {
            background: #ffd700;
            color: #000;
        }
        .btn-primary:hover {
            background: #ffed4a;
        }
        .btn-danger {
            background: #ff4444;
            color: #fff;
        }
        .btn-danger:hover {
            background: #ff6666;
        }
        .btn-success {
            background: #44ff44;
            color: #000;
        }
        .form-group {
            margin-bottom: 16px;
        }
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #aaa;
        }
        .form-group input, .form-group textarea, .form-group select {
            width: 100%;
            padding: 10px 14px;
            background: #0f0f23;
            border: 1px solid #2a2a4a;
            border-radius: 6px;
            color: #e0e0e0;
            font-size: 14px;
        }
        .form-group input:focus, .form-group textarea:focus {
            border-color: #ffd700;
            outline: none;
        }
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        .badge-success { background: #44ff4422; color: #44ff44; }
        .badge-warning { background: #ffd70022; color: #ffd700; }
        .badge-danger { background: #ff444422; color: #ff4444; }
        .flash-message {
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        .flash-success { background: #44ff4422; color: #44ff44; border: 1px solid #44ff44; }
        .flash-error { background: #ff444422; color: #ff4444; border: 1px solid #ff4444; }
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        .empty-state h3 { color: #888; margin-bottom: 10px; }
        .logout-btn {
            position: absolute;
            bottom: 20px;
            left: 20px;
            right: 20px;
            padding: 10px;
            background: #2a2a4a;
            border: 1px solid #444;
            border-radius: 6px;
            color: #aaa;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
        }
        .logout-btn:hover { background: #3a3a5a; color: #fff; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="logo">
            <h2>🌟 星辰守望者</h2>
            <p>Stellar Warden</p>
        </div>
        <a href="{{ url_for('dashboard') }}" class="{{ 'active' if active_page == 'dashboard' }}">📊 仪表盘</a>
        <a href="{{ url_for('licenses') }}" class="{{ 'active' if active_page == 'licenses' }}">🔐 授权管理</a>
        <a href="{{ url_for('groups') }}" class="{{ 'active' if active_page == 'groups' }}">👥 群组管理</a>
        <a href="{{ url_for('payments') }}" class="{{ 'active' if active_page == 'payments' }}">💰 支付记录</a>
        <a href="{{ url_for('settings') }}" class="{{ 'active' if active_page == 'settings' }}">⚙️ 系统设置</a>
        <a href="{{ url_for('logout') }}" class="logout-btn">🚪 退出登录</a>
    </div>
    <div class="main-content">
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        {% for category, message in messages %}
        <div class="flash-message flash-{{ category }}">{{ message }}</div>
        {% endfor %}
        {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

# ==================== 路由 ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == config.ADMIN_PANEL_USERNAME and password == config.ADMIN_PANEL_PASSWORD:
            session['logged_in'] = True
            flash('登录成功', 'success')
            return redirect(url_for('dashboard'))
        flash('用户名或密码错误', 'error')
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>登录 - 星辰守望者管理面板</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #0f0f23;
                color: #e0e0e0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .login-box {
                background: #1a1a2e;
                border: 1px solid #2a2a4a;
                border-radius: 16px;
                padding: 40px;
                width: 400px;
                text-align: center;
            }
            .login-box h1 { color: #ffd700; margin-bottom: 8px; }
            .login-box p { color: #888; margin-bottom: 30px; }
            .form-group { margin-bottom: 20px; text-align: left; }
            .form-group label { display: block; margin-bottom: 8px; color: #aaa; }
            .form-group input {
                width: 100%;
                padding: 12px 16px;
                background: #0f0f23;
                border: 1px solid #2a2a4a;
                border-radius: 8px;
                color: #e0e0e0;
                font-size: 14px;
            }
            .form-group input:focus { border-color: #ffd700; outline: none; }
            .btn {
                width: 100%;
                padding: 12px;
                background: #ffd700;
                color: #000;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
            }
            .btn:hover { background: #ffed4a; }
            .flash-error {
                background: #ff444422;
                color: #ff4444;
                border: 1px solid #ff4444;
                padding: 10px;
                border-radius: 6px;
                margin-bottom: 20px;
            }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>🌟 星辰守望者</h1>
            <p>Stellar Warden 管理面板</p>
            {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            {% for category, message in messages %}
            <div class="flash-{{ category }}">{{ message }}</div>
            {% endfor %}
            {% endif %}
            {% endwith %}
            <form method="POST">
                <div class="form-group">
                    <label>用户名</label>
                    <input type="text" name="username" placeholder="请输入用户名" required>
                </div>
                <div class="form-group">
                    <label>密码</label>
                    <input type="password" name="password" placeholder="请输入密码" required>
                </div>
                <button type="submit" class="btn">登录</button>
            </form>
        </div>
    </body>
    </html>
    """)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    db = get_db()

    # 统计数据
    total_groups = db.execute("SELECT COUNT(DISTINCT chat_id) FROM bot_licenses").fetchone()[0]
    total_users = db.execute("SELECT COUNT(*) FROM group_users").fetchone()[0]
    total_payments = db.execute("SELECT COUNT(*) FROM license_payments").fetchone()[0]
    total_revenue = db.execute("SELECT COALESCE(SUM(stars_paid), 0) FROM license_payments").fetchone()[0]

    # 最近授权
    recent_licenses = db.execute("""
        SELECT l.*, 
            (SELECT COUNT(*) FROM group_users WHERE chat_id = l.chat_id) as user_count
        FROM bot_licenses l 
        ORDER BY l.created_at DESC LIMIT 10
    """).fetchall()

    # 授权状态统计
    now = datetime.now().isoformat()
    active_licenses = db.execute(
        "SELECT COUNT(*) FROM bot_licenses WHERE is_licensed=1 AND license_end > ?", (now,)
    ).fetchone()[0]
    trial_only = db.execute(
        "SELECT COUNT(*) FROM bot_licenses WHERE is_licensed=0 AND trial_end > ?", (now,)
    ).fetchone()[0]
    expired = db.execute(
        "SELECT COUNT(*) FROM bot_licenses WHERE is_licensed=0 AND trial_end <= ? AND license_end IS NULL", (now,)
    ).fetchone()[0]

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="header">
        <h1>📊 仪表盘</h1>
        <span style="color: #888;">{{ now }}</span>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="number">{{ total_groups }}</div>
            <div class="label">接入群组</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ total_users }}</div>
            <div class="label">总用户数</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ active_licenses }}</div>
            <div class="label">已授权群组</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ total_revenue }}</div>
            <div class="label">总收入 (USDT)</div>
        </div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="number" style="color: #44ff44;">{{ active_licenses }}</div>
            <div class="label">活跃授权</div>
        </div>
        <div class="stat-card">
            <div class="number" style="color: #ffd700;">{{ trial_only }}</div>
            <div class="label">试用中</div>
        </div>
        <div class="stat-card">
            <div class="number" style="color: #ff4444;">{{ expired }}</div>
            <div class="label">已过期</div>
        </div>
        <div class="stat-card">
            <div class="number">{{ total_payments }}</div>
            <div class="label">支付订单</div>
        </div>
    </div>

    <div class="card">
        <h3>📋 最近接入的群组</h3>
        {% if recent_licenses %}
        <table>
            <thead>
                <tr>
                    <th>群组ID</th>
                    <th>用户数</th>
                    <th>安装时间</th>
                    <th>试用到期</th>
                    <th>授权状态</th>
                </tr>
            </thead>
            <tbody>
                {% for lic in recent_licenses %}
                <tr>
                    <td><code>{{ lic.chat_id }}</code></td>
                    <td>{{ lic.user_count }}</td>
                    <td>{{ lic.installed_at[:10] if lic.installed_at else '-' }}</td>
                    <td>{{ lic.trial_end[:10] if lic.trial_end else '-' }}</td>
                    <td>
                        {% if lic.is_licensed %}
                            <span class="badge badge-success">已授权</span>
                        {% elif lic.trial_end and lic.trial_end > now %}
                            <span class="badge badge-warning">试用中</span>
                        {% else %}
                            <span class="badge badge-danger">已过期</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty-state">
            <h3>暂无数据</h3>
            <p>还没有群组接入</p>
        </div>
        {% endif %}
    </div>
    {% endblock %}
    """, title="仪表盘", active_page="dashboard",
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_groups=total_groups, total_users=total_users,
        total_payments=total_payments, total_revenue=total_revenue,
        recent_licenses=recent_licenses,
        active_licenses=active_licenses, trial_only=trial_only, expired=expired)


@app.route('/licenses')
@login_required
def licenses():
    db = get_db()
    now = datetime.now().isoformat()

    licenses_list = db.execute("""
        SELECT l.*, 
            (SELECT COUNT(*) FROM group_users WHERE chat_id = l.chat_id) as user_count
        FROM bot_licenses l 
        ORDER BY l.created_at DESC
    """).fetchall()

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="header">
        <h1>🔐 授权管理</h1>
    </div>

    <div class="card">
        <h3>授权列表</h3>
        {% if licenses_list %}
        <table>
            <thead>
                <tr>
                    <th>群组ID</th>
                    <th>用户数</th>
                    <th>安装时间</th>
                    <th>试用到期</th>
                    <th>授权到期</th>
                    <th>状态</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {% for lic in licenses_list %}
                <tr>
                    <td><code>{{ lic.chat_id }}</code></td>
                    <td>{{ lic.user_count }}</td>
                    <td>{{ lic.installed_at[:10] if lic.installed_at else '-' }}</td>
                    <td>{{ lic.trial_end[:10] if lic.trial_end else '-' }}</td>
                    <td>{{ lic.license_end[:10] if lic.license_end else '-' }}</td>
                    <td>
                        {% if lic.is_licensed %}
                            <span class="badge badge-success">已授权</span>
                        {% elif lic.trial_end and lic.trial_end > now %}
                            <span class="badge badge-warning">试用中</span>
                        {% else %}
                            <span class="badge badge-danger">已过期</span>
                        {% endif %}
                    </td>
                    <td>
                        <a href="{{ url_for('extend_license', chat_id=lic.chat_id) }}" class="btn btn-primary" style="font-size:12px;">续期</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty-state">
            <h3>暂无授权数据</h3>
        </div>
        {% endif %}
    </div>
    {% endblock %}
    """, title="授权管理", active_page="licenses",
        licenses_list=licenses_list, now=now)


@app.route('/licenses/extend/<int:chat_id>', methods=['GET', 'POST'])
@login_required
def extend_license(chat_id):
    db = get_db()

    if request.method == 'POST':
        days = int(request.form.get('days', 30))
        now = datetime.now()

        info = db.execute("SELECT * FROM bot_licenses WHERE chat_id=?", (chat_id,)).fetchone()
        if info and info['license_end']:
            current_end = datetime.fromisoformat(info['license_end'])
            if current_end > now:
                new_end = current_end + timedelta(days=days)
            else:
                new_end = now + timedelta(days=days)
        else:
            new_end = now + timedelta(days=days)

        db.execute(
            "UPDATE bot_licenses SET is_licensed=1, license_end=?, updated_at=? WHERE chat_id=?",
            (new_end.isoformat(), now.isoformat(), chat_id)
        )
        db.commit()
        flash(f'已为群组 {chat_id} 续期 {days} 天', 'success')
        return redirect(url_for('licenses'))

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="header">
        <h1>🔐 续期授权 - {{ chat_id }}</h1>
    </div>
    <div class="card">
        <form method="POST">
            <div class="form-group">
                <label>续期天数</label>
                <select name="days">
                    <option value="30">30天</option>
                    <option value="90">90天</option>
                    <option value="180">180天</option>
                    <option value="365">365天</option>
                </select>
            </div>
            <button type="submit" class="btn btn-primary">确认续期</button>
            <a href="{{ url_for('licenses') }}" class="btn" style="background:#2a2a4a;color:#aaa;">取消</a>
        </form>
    </div>
    {% endblock %}
    """, title="续期授权", active_page="licenses", chat_id=chat_id)


@app.route('/groups')
@login_required
def groups():
    db = get_db()

    groups_list = db.execute("""
        SELECT chat_id, COUNT(*) as user_count, 
            SUM(CASE WHEN is_verified=1 THEN 1 ELSE 0 END) as verified_count
        FROM group_users 
        GROUP BY chat_id
        ORDER BY user_count DESC
    """).fetchall()

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="header">
        <h1>👥 群组管理</h1>
    </div>
    <div class="card">
        {% if groups_list %}
        <table>
            <thead>
                <tr>
                    <th>群组ID</th>
                    <th>总用户</th>
                    <th>已验证</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                {% for g in groups_list %}
                <tr>
                    <td><code>{{ g.chat_id }}</code></td>
                    <td>{{ g.user_count }}</td>
                    <td>{{ g.verified_count }}</td>
                    <td>
                        <a href="{{ url_for('group_detail', chat_id=g.chat_id) }}" class="btn btn-primary" style="font-size:12px;">详情</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty-state">
            <h3>暂无群组数据</h3>
        </div>
        {% endif %}
    </div>
    {% endblock %}
    """, title="群组管理", active_page="groups", groups_list=groups_list)


@app.route('/groups/<int:chat_id>')
@login_required
def group_detail(chat_id):
    db = get_db()

    users = db.execute(
        "SELECT * FROM group_users WHERE chat_id=? ORDER BY points DESC LIMIT 50",
        (chat_id,)
    ).fetchall()

    settings = db.execute(
        "SELECT * FROM group_settings WHERE chat_id=?", (chat_id,)
    ).fetchone()

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="header">
        <h1>👥 群组详情 - {{ chat_id }}</h1>
    </div>

    <div class="card">
        <h3>群组设置</h3>
        {% if settings %}
        <p>广告防护: {{ '✅ 开启' if settings.anti_spam_enabled else '❌ 关闭' }}</p>
        <p>欢迎消息: {{ '✅ 开启' if settings.welcome_enabled else '❌ 关闭' }}</p>
        {% else %}
        <p>使用默认设置</p>
        {% endif %}
    </div>

    <div class="card">
        <h3>用户列表 (前50名)</h3>
        {% if users %}
        <table>
            <thead>
                <tr>
                    <th>用户ID</th>
                    <th>昵称</th>
                    <th>积分</th>
                    <th>等级</th>
                    <th>状态</th>
                </tr>
            </thead>
            <tbody>
                {% for u in users %}
                <tr>
                    <td><code>{{ u.user_id }}</code></td>
                    <td>{{ u.first_name or u.username or '-' }}</td>
                    <td>{{ u.points }}</td>
                    <td>{{ u.level }}</td>
                    <td>
                        {% if u.is_banned %}<span class="badge badge-danger">封禁</span>
                        {% elif u.is_muted %}<span class="badge badge-warning">禁言</span>
                        {% else %}<span class="badge badge-success">正常</span>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty-state">
            <h3>暂无用户数据</h3>
        </div>
        {% endif %}
    </div>
    {% endblock %}
    """, title="群组详情", active_page="groups", chat_id=chat_id, users=users, settings=settings)


@app.route('/payments')
@login_required
def payments():
    db = get_db()

    payments_list = db.execute("""
        SELECT * FROM license_payments ORDER BY paid_at DESC LIMIT 50
    """).fetchall()

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="header">
        <h1>💰 支付记录</h1>
    </div>
    <div class="card">
        {% if payments_list %}
        <table>
            <thead>
                <tr>
                    <th>群组ID</th>
                    <th>套餐</th>
                    <th>金额</th>
                    <th>天数</th>
                    <th>支付时间</th>
                    <th>交易ID</th>
                </tr>
            </thead>
            <tbody>
                {% for p in payments_list %}
                <tr>
                    <td><code>{{ p.chat_id }}</code></td>
                    <td>{{ p.plan_id }}</td>
                    <td>{{ p.stars_paid }} USDT</td>
                    <td>+{{ p.days_added }}天</td>
                    <td>{{ p.paid_at[:16] if p.paid_at else '-' }}</td>
                    <td><code>{{ p.payment_id[:16] if p.payment_id else '-' }}...</code></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty-state">
            <h3>暂无支付记录</h3>
        </div>
        {% endif %}
    </div>
    {% endblock %}
    """, title="支付记录", active_page="payments", payments_list=payments_list)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        # 更新配置（运行时修改，重启后恢复 config.py 默认值）
        config.LICENSE_ENFORCE = request.form.get('license_enforce') == 'on'
        config.USDT_WALLET = request.form.get('usdt_wallet', config.USDT_WALLET)
        config.USDT_NETWORK = request.form.get('usdt_network', config.USDT_NETWORK)
        config.ADMIN_CONTACT = request.form.get('admin_contact', config.ADMIN_CONTACT)
        flash('设置已保存（重启后恢复默认）', 'success')
        return redirect(url_for('settings'))

    return render_template_string(BASE_TEMPLATE + """
    {% block content %}
    <div class="header">
        <h1>⚙️ 系统设置</h1>
    </div>
    <div class="card">
        <form method="POST">
            <h3>授权系统</h3>
            <div class="form-group">
                <label>
                    <input type="checkbox" name="license_enforce" {{ 'checked' if config.LICENSE_ENFORCE else '' }}>
                    启用授权强制执行（关闭时所有群组免费使用）
                </label>
            </div>

            <h3>USDT 支付配置</h3>
            <div class="form-group">
                <label>钱包地址 ({{ config.USDT_NETWORK }})</label>
                <input type="text" name="usdt_wallet" value="{{ config.USDT_WALLET }}">
            </div>
            <div class="form-group">
                <label>网络类型</label>
                <select name="usdt_network">
                    <option value="TRC20" {{ 'selected' if config.USDT_NETWORK == 'TRC20' }}>TRC20</option>
                    <option value="ERC20" {{ 'selected' if config.USDT_NETWORK == 'ERC20' }}>ERC20</option>
                </select>
            </div>
            <div class="form-group">
                <label>管理员联系方式</label>
                <input type="text" name="admin_contact" value="{{ config.ADMIN_CONTACT }}">
            </div>

            <h3>授权套餐</h3>
            <table>
                <thead>
                    <tr><th>套餐</th><th>天数</th><th>价格 (USDT)</th></tr>
                </thead>
                <tbody>
                    {% for pid, plan in config.LICENSE_PLANS.items() %}
                    <tr>
                        <td>{{ plan.emoji }} {{ plan.name }}</td>
                        <td>{{ plan.days }}天</td>
                        <td>{{ plan.price_usdt }} USDT</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>

            <br>
            <button type="submit" class="btn btn-primary">保存设置</button>
        </form>
    </div>
    {% endblock %}
    """, title="系统设置", active_page="settings", config=config)


# ==================== API 接口 ====================

@app.route('/api/license/<int:chat_id>', methods=['POST'])
def api_activate_license():
    """API: 激活授权（管理员手动确认支付后调用）"""
    data = request.get_json()
    chat_id = data.get('chat_id')
    days = data.get('days', 30)
    plan_id = data.get('plan_id', 'manual')

    db = get_db()
    now = datetime.now()

    info = db.execute("SELECT * FROM bot_licenses WHERE chat_id=?", (chat_id,)).fetchone()
    if info and info['license_end']:
        current_end = datetime.fromisoformat(info['license_end'])
        if current_end > now:
            new_end = current_end + timedelta(days=days)
        else:
            new_end = now + timedelta(days=days)
    else:
        new_end = now + timedelta(days=days)

    db.execute(
        "UPDATE bot_licenses SET is_licensed=1, license_end=?, updated_at=? WHERE chat_id=?",
        (new_end.isoformat(), now.isoformat(), chat_id)
    )
    db.execute(
        "INSERT INTO license_payments (chat_id, plan_id, stars_paid, days_added) VALUES (?, ?, ?, ?)",
        (chat_id, plan_id, days, days)
    )
    db.commit()

    return jsonify({"success": True, "new_end": new_end.isoformat()})


# ==================== 启动 ====================

if __name__ == '__main__':
    print(f"🌟 星辰守望者管理面板启动中...")
    print(f"🌐 地址: http://{config.ADMIN_PANEL_HOST}:{config.ADMIN_PANEL_PORT}")
    print(f"🔐 登录: {config.ADMIN_PANEL_USERNAME} / {config.ADMIN_PANEL_PASSWORD}")
    app.run(
        host=config.ADMIN_PANEL_HOST,
        port=config.ADMIN_PANEL_PORT,
        debug=False
    )
