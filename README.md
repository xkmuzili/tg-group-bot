# 🤖 Telegram Group Management Bot

> A feature-rich Telegram group management bot with anti-spam, points system, verification, and admin tools.

> 功能丰富的 Telegram 群管理机器人，支持广告防护、积分系统、入群验证和管理工具。

---

## ✨ Features / 功能

### 🛡️ Anti-Spam & Verification / 广告防护与验证
- **Smart spam detection** — AI-powered content analysis + keyword filtering + link detection
- **New member verification** — Private chat verification before allowed to speak
- **Progressive punishment** — Warn → Mute → Ban with configurable thresholds
- **Custom banned words** — Add/remove keywords dynamically

### 🎮 Points & Rewards / 积分与奖励
- **Daily checkin** — Earn points with streak bonuses
- **Message rewards** — Earn points by participating in discussions
- **Invite rewards** — Earn points for inviting new members
- **Level system** — Level up based on total points earned

### 🛒 Shop System / 商城系统
- **Mute Card** — Unmute yourself after being muted
- **Double Points Card** — 24h double checkin rewards
- **VIP Card** — 7-day VIP membership
- **Anti-Spam Shield** — 24h immunity from spam detection

### 👑 Admin Tools / 管理工具
- `/mute` `/unmute` — Mute/unmute users
- `/ban` `/unban` — Ban/unban users
- `/kick` — Kick users from group
- `/userinfo` — View user details and violations
- `/stats` — Group statistics
- `/setwelcome` — Customize welcome message
- `/addword` `/delword` — Manage banned words

---

## 🚀 Quick Start / 快速开始

### 1. Clone the repository / 克隆仓库

```bash
git clone https://github.com/your-username/tg-group-bot.git
cd tg-group-bot
```

### 2. Install dependencies / 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. Configure / 配置

```bash
cp config.example.py config.py
```

Edit `config.py` with your settings:
- `BOT_TOKEN` — Get from [@BotFather](https://t.me/BotFather)
- `SUPER_ADMIN_IDS` — Your Telegram user ID

编辑 `config.py` 填入你的设置：
- `BOT_TOKEN` — 从 [@BotFather](https://t.me/BotFather) 获取
- `SUPER_ADMIN_IDS` — 你的 Telegram 用户 ID

### 4. Run / 运行

```bash
python bot.py
```

---

## 📋 Commands / 命令列表

| Command | Description | 中文说明 |
|---------|-------------|----------|
| `/start` | Start the bot | 启动机器人 |
| `/help` | Show all commands | 显示所有命令 |
| `/checkin` | Daily checkin | 每日签到 |
| `/rank` | View leaderboard | 查看排行榜 |
| `/shop` | View shop | 查看商城 |
| `/exchange <item>` | Exchange points for items | 积分兑换 |
| `/myitems` | View owned items | 查看已购物品 |
| `/userinfo [@user]` | View user info | 查看用户信息 |
| `/mute @user` | Mute user (admin) | 禁言用户 |
| `/unmute @user` | Unmute user (admin) | 解除禁言 |
| `/ban @user` | Ban user (admin) | 封禁用户 |
| `/unban @user` | Unban user (admin) | 解除封禁 |
| `/kick @user` | Kick user (admin) | 踢出用户 |
| `/stats` | Group statistics | 群组统计 |
| `/setwelcome <msg>` | Set welcome message (admin) | 设置欢迎消息 |
| `/welcome` | Preview welcome message | 预览欢迎消息 |
| `/antispam on/off` | Toggle anti-spam (admin) | 开关广告防护 |
| `/addword <word>` | Add banned word (admin) | 添加违禁词 |
| `/delword <word>` | Remove banned word (admin) | 删除违禁词 |
| `/wordlist` | View banned words | 查看违禁词列表 |

---

## 🏗️ Architecture / 架构

```
tg-group-bot/
├── bot.py              # Main bot logic / 主程序
├── database.py         # SQLite database operations / 数据库操作
├── anti_spam.py        # Spam detection engine / 广告检测引擎
├── config.py           # Configuration (git ignored) / 配置文件(不提交)
├── config.example.py   # Example configuration / 配置示例
├── requirements.txt    # Python dependencies / 依赖列表
└── README.md           # This file / 本文件
```

### Tech Stack / 技术栈

- **Python 3.10+**
- **python-telegram-bot** — Telegram Bot API wrapper
- **aiosqlite** — Async SQLite operations
- **SQLite** — Lightweight database

---

## 🔧 Deployment / 部署

### Systemd Service (Linux) / 系统服务

```ini
[Unit]
Description=Telegram Group Management Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/tg-group-bot
ExecStart=/opt/tg-group-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable tg-group-bot
sudo systemctl start tg-group-bot
```

---

## 📝 License / 许可证

MIT License - feel free to use and modify.

MIT 许可证 - 自由使用和修改。

---

## 🤝 Contributing / 贡献

Contributions are welcome! Feel free to open issues and pull requests.

欢迎贡献！欢迎提交 Issue 和 Pull Request。
