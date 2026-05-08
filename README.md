# 🌟 星辰守望者 (Stellar Warden)

> 🛡️ 智能 Telegram 群管理机器人 | 广告查杀 · 积分系统 · 入群验证 · 积分商城

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ 功能一览

| 模块 | 功能 | 说明 |
|------|------|------|
| 🛡️ 广告防护 | 智能检测 | AI分析 + 关键词 + 链接检测，自动处理 |
| 🔐 入群验证 | 私聊确认 | 新成员需私聊机器人验证后才能发言 |
| 🏆 积分系统 | 签到奖励 | 每日签到、连续奖励、消息积分 |
| 🛒 积分商城 | 道具兑换 | 禁言卡、双倍卡、VIP卡、防护盾 |
| 👑 管理工具 | 全面管控 | 禁言/封禁/踢出/统计/欢迎语/违禁词 |

---

## 🚀 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/xkmuzili/tg-group-bot.git
cd tg-group-bot
```

### 2. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. 配置

```bash
cp config.example.py config.py
```

编辑 `config.py`：

| 配置项 | 说明 | 获取方式 |
|--------|------|----------|
| `BOT_TOKEN` | 机器人 Token | [@BotFather](https://t.me/BotFather) |
| `SUPER_ADMIN_IDS` | 管理员 ID | [@userinfobot](https://t.me/userinfobot) |

### 4. 启动

```bash
# 启动机器人
python bot.py

# 启动管理面板（可选）
python admin_panel.py
```

---

## 📋 命令列表

### 用户命令

| 命令 | 说明 |
|------|------|
| `/start` | 打开主菜单 |
| `/help` | 查看所有命令 |
| `/about` | 机器人介绍 |
| `/checkin` | 每日签到 |
| `/points` | 查看积分 |
| `/rank` | 积分排行榜 |
| `/shop` | 积分商城 |
| `/exchange <ID>` | 兑换商品 |
| `/myitems` | 我的物品 |

### 管理员命令

| 命令 | 说明 |
|------|------|
| `/mute <用户>` | 禁言（1小时） |
| `/unmute <用户>` | 解除禁言 |
| `/ban <用户>` | 封禁用户 |
| `/unban <用户>` | 解封用户 |
| `/kick <用户>` | 踢出用户 |
| `/userinfo <用户>` | 查看用户详情 |
| `/stats` | 群组统计 |
| `/setwelcome <消息>` | 设置欢迎语 |
| `/antispam on/off` | 广告防护开关 |
| `/addword <词>` | 添加违禁词 |
| `/delword <词>` | 删除违禁词 |
| `/wordlist` | 查看违禁词列表 |

---

## 🏗️ 项目结构

```
tg-group-bot/
├── bot.py              # 🤖 机器人主程序
├── database.py         # 💾 数据库操作
├── anti_spam.py        # 🛡️ 广告检测引擎
├── admin_panel.py      # 🌐 后台管理面板
├── config.py           # ⚙️ 配置文件（不提交）
├── config.example.py   # 📝 配置示例
├── avatar.png          # 🖼️ 机器人头像
├── requirements.txt    # 📦 Python 依赖
└── README.md           # 📖 本文件
```

### 技术栈

- **Python 3.10+**
- **python-telegram-bot** — Telegram Bot API
- **aiosqlite** — 异步 SQLite
- **Flask** — 后台管理面板

---

## 🔧 部署

### 方式一：Systemd 服务（推荐）

```ini
# /etc/systemd/system/tg-group-bot.service
[Unit]
Description=Stellar Warden - Telegram Group Bot
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
sudo systemctl status tg-group-bot
```

### 方式二：后台运行

```bash
nohup python bot.py > bot.log 2>&1 &
```

---

## 🌐 管理面板

访问 `http://your-server:5000` 进入后台管理面板。

功能：
- 📊 仪表盘 — 群组统计、收入概览
- 🔐 授权管理 — 查看/续期群组授权
- 👥 群组管理 — 查看用户列表
- 💰 支付记录 — USDT 支付记录
- ⚙️ 系统设置 — 授权开关、支付配置

---

## 📝 许可证

MIT License - 自由使用和修改。
