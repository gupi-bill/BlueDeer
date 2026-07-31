# BlueDeer 外部集成指南

> 让你的数字员工走出浏览器，通过桌面通知、企业微信、钉钉、飞书、Telegram、邮件与你互动。

---

## 目录

1. [快速开始](#1-快速开始)
2. [配置文件详解](#2-配置文件详解)
3. [渠道配置](#3-渠道配置)
   - [桌面通知](#31-桌面通知最轻量)
   - [企业微信 Webhook](#32-企业微信-webhook)
   - [钉钉 Webhook](#33-钉钉-webhook)
   - [飞书 Webhook](#34-飞书-webhook)
   - [Telegram Bot](#35-telegram-bot)
   - [邮件](#36-邮件)
4. [消息路由规则](#4-消息路由规则)
5. [免打扰时段](#5-免打扰时段)
6. [移动端使用](#6-移动端使用)
7. [API 接口](#7-api-接口)
8. [常见问题](#8-常见问题)

---

## 1. 快速开始

### 1.1 默认配置

系统启动后，默认只启用**桌面通知**渠道（零依赖，开箱即用）：

```json
{
  "channels": {
    "desktop_notify": {"enabled": true}
  }
}
```

打开管控台 `http://127.0.0.1:8080/` 后，员工产生的紧急消息会自动弹出到你的桌面。

### 1.2 启用更多渠道

1. 复制 `integrations_config.json` 为 `integrations_config.local.json`（已加入 .gitignore，不会泄露密钥）
2. 修改对应渠道的 `enabled: true` 并填入 token/URL
3. 重启服务，配置自动生效

---

## 2. 配置文件详解

配置文件位置：`/workspace/integrations_config.json`

```json
{
  "channels": { ... },          // 各渠道配置
  "quiet_hours": { ... },       // 免打扰时段
  "message_routing": { ... },   // 按优先级路由到哪些渠道
  "digest": { ... }             // 普通消息汇总设置
}
```

### 关键字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `channels.*.enabled` | bool | 是否启用该渠道 |
| `quiet_hours.enabled` | bool | 是否开启免打扰 |
| `quiet_hours.start/end` | "HH:MM" | 免打扰时段，支持跨夜（如 22:00→08:00） |
| `message_routing.urgent` | array | 紧急消息（high）走哪些渠道 |
| `message_routing.important` | array | 重要消息（medium）走哪些渠道 |
| `message_routing.normal` | array | 普通消息（low）走哪些渠道 |
| `message_routing.social` | array | 社交消息（默认空数组，不外部推送） |
| `digest.interval_hours` | int | 普通消息汇总间隔（默认 1 小时） |

---

## 3. 渠道配置

### 3.1 桌面通知（最轻量）

零依赖，开箱即用。

- **Linux**：调用 `notify-send`（libnotify 自带）
- **macOS**：调用 `osascript`（系统自带）
- **Windows**：调用 PowerShell 的 NotifyIcon（系统自带）

```json
{
  "channels": {
    "desktop_notify": {"enabled": true}
  }
}
```

**安装依赖（仅 Linux 精简版需要）：**

```bash
# Ubuntu/Debian
sudo apt install libnotify-bin

# CentOS/RHEL
sudo yum install libnotify
```

### 3.2 企业微信 Webhook

1. 在企业微信群聊中，点击右上角 `...` → 群机器人 → 添加机器人
2. 复制 Webhook 地址（形如 `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`）
3. 填入配置：

```json
{
  "channels": {
    "wechat_webhook": {
      "enabled": true,
      "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key"
    }
  }
}
```

### 3.3 钉钉 Webhook

1. 在钉钉群聊中，点击右上角 `...` → 智能群助手 → 添加机器人 → 自定义
2. 安全设置选择"加签"，复制 secret 和 Webhook URL
3. 填入配置：

```json
{
  "channels": {
    "dingtalk_webhook": {
      "enabled": true,
      "url": "https://oapi.dingtalk.com/robot/send?access_token=你的token",
      "secret": "SEC你的签名密钥"
    }
  }
}
```

### 3.4 飞书 Webhook

1. 在飞书群聊中，点击右上角 `...` → 群机器人 → 添加机器人 → 自定义机器人
2. 复制 Webhook URL
3. 填入配置：

```json
{
  "channels": {
    "feishu_webhook": {
      "enabled": true,
      "url": "https://open.feishu.cn/open-apis/bot/v2/hook/你的hook_id"
    }
  }
}
```

### 3.5 Telegram Bot

1. 在 Telegram 中找到 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot`，按提示创建 Bot，获取 `bot_token`
3. 启动 Bot，发送 `/start`，通过 [@userinfobot](https://t.me/userinfobot) 获取你的 `chat_id`
4. 填入配置：

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
      "chat_id": "你的chat_id"
    }
  }
}
```

**双向通信（可选）：**

启动 Bot 监听线程，接收你在 Telegram 中回复的消息：

```python
from core.digital_life.channels.telegram_bot import start_listener

def on_user_message(text, chat_id):
    print(f"用户回复：{text}")
    # 这里把消息路由回对应智能体

start_listener(config["channels"]["telegram"], on_message=on_user_message)
```

### 3.6 邮件

1. 准备一个 SMTP 发件邮箱（推荐 Gmail、QQ 邮箱、163 邮箱）
2. 开启 SMTP 服务并获取授权码（不是登录密码）
3. 填入配置：

```json
{
  "channels": {
    "email": {
      "enabled": true,
      "smtp_host": "smtp.qq.com",
      "smtp_port": 587,
      "sender": "your_email@qq.com",
      "password": "你的SMTP授权码",
      "recipient": "receive@example.com",
      "daily_report_time": "20:00"
    }
  }
}
```

**常见 SMTP 服务器：**

| 邮箱 | SMTP Host | Port |
|------|-----------|------|
| Gmail | smtp.gmail.com | 587 |
| QQ 邮箱 | smtp.qq.com | 587 |
| 163 邮箱 | smtp.163.com | 587 |
| Outlook | smtp.office365.com | 587 |
| 企业微信邮箱 | smtp.exmail.qq.com | 465 |

---

## 4. 消息路由规则

系统按消息优先级自动路由到不同渠道：

| 优先级 | 触发场景 | 默认路由渠道 |
|--------|----------|--------------|
| **urgent** (high) | 危机警报、员工死亡 | 所有已配置渠道同时推送 |
| **important** (medium) | 健康危机、关系里程碑、退休愿望 | 桌面通知 + Telegram |
| **normal** (low) | 工作完成、资源预警 | 桌面通知（实时）+ Webhook/邮件（每小时汇总） |
| **social** | 早安问候、分享发现、想念监工 | 仅管控台内显示，不外部推送 |

**自定义路由：**

```json
{
  "message_routing": {
    "urgent":    ["desktop_notify", "telegram", "wechat_webhook"],
    "important": ["desktop_notify", "telegram"],
    "normal":    ["desktop_notify"],
    "social":    []
  }
}
```

---

## 5. 免打扰时段

避免深夜被消息打扰：

```json
{
  "quiet_hours": {
    "enabled": true,
    "start": "22:00",
    "end": "08:00"
  }
}
```

- 免打扰时段内，**所有非紧急消息都不外部推送**（仍入管控台队列）
- **紧急消息（high 优先级）穿透免打扰**，确保你能收到死亡/警报
- 支持跨夜时段（如 22:00→08:00）

---

## 6. 移动端使用

### 6.1 访问移动端

打开 `http://你的服务器IP:8080/mobile` 即可访问移动端简化页面。

### 6.2 功能

- **员工列表**：竖版卡片，能量/健康/心情进度条
- **消息中心**：实时接收员工主动消息
- **对话窗口**：和员工聊天，支持语音输入
- **设置**：开启桌面通知、测试渠道、发送日报
- **快捷指令**：底部固定栏，喂食全体 / 刷新 / 紧急召集 / 发日报

### 6.3 PWA（添加到主屏幕）

1. 在手机浏览器打开移动端页面
2. iOS：Safari → 分享 → 添加到主屏幕
3. Android：Chrome → 三点菜单 → 添加到主屏幕
4. 之后从主屏幕启动，体验类似原生 App

### 6.4 语音输入

对话窗口的 🎤 按钮支持语音输入：
- 点击按钮 → 开始说话 → 自动识别为文字
- 需要浏览器支持 SpeechRecognition API（推荐 Chrome / Safari）

---

## 7. API 接口

### 7.1 查询集成配置（脱敏）

```
GET /api/integrations
```

返回所有渠道配置（敏感字段已脱敏）+ 路由状态。

### 7.2 测试某个渠道

```
GET /api/integrations/test?channel=desktop_notify
```

发送一条测试消息到指定渠道。

### 7.3 手动触发 digest 发送

```
GET /api/integrations/digest
```

立即发送累积的普通消息汇总到 Webhook/邮件渠道（不等待 1 小时间隔）。

### 7.4 手动发送日报邮件

```
GET /api/daily_report
```

立即发送今日工作日报邮件（需配置 email 渠道）。

### 7.5 查询最近消息

```
GET /api/messages?limit=50
```

返回最近 N 条主动消息（不清空队列）。

---

## 8. 常见问题

### Q1: 桌面通知不弹出来？

- **Linux**：检查是否安装 `libnotify-bin`，运行 `notify-send test` 测试
- **macOS**：检查"系统偏好设置 → 通知"是否允许终端/Python
- **Windows**：检查"设置 → 通知"是否允许 PowerShell
- **服务器无桌面环境**：桌面通知需要 GUI，纯命令行服务器无法弹出（建议改用 Webhook/邮件）

### Q2: 企业微信 Webhook 报错？

- 检查 URL 是否完整（包含 `?key=`）
- 钉钉机器人有频率限制（每分钟 20 条），超出会被屏蔽 1 小时
- 飞书机器人同样有频率限制

### Q3: 邮件发不出去？

- 检查 SMTP 授权码（不是登录密码）
- QQ/163 邮箱需要单独开启 SMTP 服务
- Gmail 需要开启"应用专用密码"（不是账户密码）
- 端口 465 用 SSL，端口 587 用 STARTTLS（系统默认 587）

### Q4: 配置改了不生效？

- 系统会自动检测配置文件修改时间，**5 秒内自动重载**
- 如果长时间不生效，重启服务

### Q5: 如何完全关闭外部集成？

把所有渠道的 `enabled` 设为 `false`，或删除 `integrations_config.json` 文件。系统会降级为仅管控台内消息。

### Q6: 隐私安全？

- 所有 token/密码仅存储在本地 `integrations_config.json`
- 该文件已加入 `.gitignore`，不会被提交到 git
- 系统不经过任何第三方服务器（Telegram Bot 除外，那是 Telegram 自身机制）
- API 接口返回配置时，所有敏感字段自动脱敏

---

## 文件结构

```
/workspace/
├── integrations_config.json          # 集成配置（含示例，已加入 .gitignore）
├── core/digital_life/
│   ├── message_router.py             # 消息路由层
│   ├── active_messaging.py           # 主动消息触发器（已集成 MessageRouter）
│   └── channels/
│       ├── __init__.py
│       ├── desktop_notify.py         # 桌面通知
│       ├── webhook_channel.py        # 企微/钉钉/飞书 Webhook
│       ├── telegram_bot.py           # Telegram Bot
│       └── email_digest.py           # 邮件日报
├── static/game/mobile.html           # 移动端简化页面
└── game_server.py                    # Web 服务器（已新增集成 API + /mobile 路由）
```

---

## 测试

运行以下命令验证集成是否正常：

```bash
# 1. 语法检查
python -c "import ast; ast.parse(open('core/digital_life/message_router.py').read())"

# 2. 单元测试（不依赖外部服务）
python -c "
from core.digital_life.message_router import get_router
from core.digital_life.channels import desktop_notify
print('已启用渠道:', get_router().get_status()['enabled_channels'])
print('桌面通知支持:', desktop_notify.is_supported())
"

# 3. 端到端测试（启动服务后，浏览器访问）
# 桌面通知测试：http://127.0.0.1:8080/api/integrations/test?channel=desktop_notify
# 日报测试：http://127.0.0.1:8080/api/daily_report
# 移动端：http://127.0.0.1:8080/mobile
```

---

如有问题，查看管控台日志或运行 `python -c "from core.digital_life.message_router import get_router; print(get_router().get_status())"` 排查。
