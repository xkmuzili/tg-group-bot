# 🌟 星辰守望者 (Stellar Warden)

> 🛡️ 智能 Telegram 群管理机器人 | 广告查杀 · 积分系统 · 入群验证 · 积分商城

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ 功能一览

| 模块 | 功能 | 说明 |
|------|------|------|
| 🛡️ 广告防护 | 智能检测 | AI分析 + 关键词 + 链接检测，自动处理 |
| 🔐 入群验证 | 群内弹按钮 | 新成员点击按钮跳转Bot私聊验证，自动解除限制 |
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

### 👤 用户命令

| 命令 | 说明 |
|------|------|
| `/start` | 打开主菜单（支持深度链接 `verify_{chat_id}`） |
| `/help` | 查看所有命令 |
| `/checkin` | 每日签到 |
| `/points` | 查看积分 |
| `/rank` | 积分排行榜 |
| `/shop` | 积分商城 |
| `/exchange <ID>` | 兑换商品 |
| `/myitems` | 我的物品 |
| `/verify` | 群内触发验证（弹出按钮跳转私聊） |

### 👑 管理员命令

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
| `/welcome` | 查看当前欢迎语 |
| `/antispam on/off` | 广告防护开关 |
| `/addword <词>` | 添加违禁词 |
| `/delword <词>` | 删除违禁词 |
| `/wordlist` | 查看违禁词列表 |

---

## 🔐 验证系统 v2（最新）

### 工作流程

```
用户加入群组
    ↓
Bot 检测到新成员
    ↓
发送验证消息（InlineKeyboard 按钮）
    ↓
用户点击 "✅ 点击验证" 按钮
    ↓
跳转 Bot 私聊（深度链接 verify_{chat_id}）
    ↓
用户在私聊点击 "确认验证"
    ↓
Bot 自动解除群内发言限制（restrict/unrestrict）
```

### 技术实现

1. **群内触发**：`/verify` 命令或新成员加入时自动触发
2. **InlineKeyboard 按钮**：群内弹出验证按钮，用户点击跳转私聊
3. **深度链接**：`/start verify_{chat_id}` 支持从群组跳转到私聊
4. **自动解除限制**：验证成功后自动调用 `restrict`/`unrestrict` 解除群内发言限制

### 修复内容（v2）

- ✅ 修复旧版本私聊发送失败的问题
- ✅ 优化按钮样式和交互体验
- ✅ 支持深度链接跳转
- ✅ 自动解除群内发言限制

---

## 🏗️ 项目结构

```
tg-group-bot/
├── bot.py              # 🤖 机器人主程序（含验证系统v2）
├── database.py         # 💾 数据库操作
├── anti_spam.py        # 🛡️ 广告检测引擎
├── admin_panel.py      # 🌐 后台管理面板
├── config.py           # ⚙️ 配置文件（不提交）
├── config.example.py   # 📝 配置示例
├── avatar.png          # 🖼️ 机器人头像
├── requirements.txt    # 📦 Python 依赖
├── LICENSE             # 📄 MIT 许可证
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
- 📊 仪表盘 — 群组统计、用户概览
- 👥 群组管理 — 查看用户列表
- ⚠️ 违规记录 — 管理违规用户
- 📅 签到记录 — 查看签到数据
- 🛒 商品管理 — 管理商城商品
- 🔄 兑换记录 — 查看兑换历史
- ⚙️ 群组设置 — 系统配置

---

## 📝 更新日志

### v5.0.0 (2026-05-13)
- ✨ 美化README排版，添加徽章和图标
- ✨ 添加MIT许可证文件
- ✨ 优化命令列表分类（用户/管理员分开）
- ✨ 完善项目结构说明

### v4.0.0 (2026-05-13)
- ✨ 兑换卡管理功能
- ✨ 群组设置页面
- ✨ 商品开关控制

### v3.0.0 (2026-05-12)
- ✨ 模板系统升级
- ✨ 管理面板全面重构
- ✨ 新增兑换卡管理页面

### v2.0.0 (2026-05-10)
- ✨ 全新验证系统：群内弹按钮跳转Bot验证
- ✨ 支持深度链接 `verify_{chat_id}`
- ✨ 验证后自动解除群内发言限制
- 🐛 修复旧版本私聊发送失败的问题

### v1.0.0 (2026-05-07)
- 🎉 初始版本发布
- ✨ 广告防护系统
- ✨ 积分系统和商城
- ✨ 后台管理面板

---

## 📄 许可证

MIT License - 自由使用和修改。

详见 [LICENSE](LICENSE) 文件。
