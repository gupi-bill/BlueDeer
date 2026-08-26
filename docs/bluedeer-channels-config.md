# BlueDeer 频道（Channels）配置字段全量清单

> 说明：本文档把 BlueDeer「频道」页面里可能接入的聊天 / 通讯 / 语音平台全部列出，包含每个平台官方 Bot/API 要求的必填字段、字段类型、示例值、最小可运行 JSON 配置以及官方文档/申请入口。你直接复制对应平台的 JSON 示例，填上自己的密钥即可。
>
> 标注规则：
> - **必填** = 不填就无法启动
> - 可选 = 影响功能或安全性，但不填也能跑
> - 高级 = 大部分场景不用管

---

## 通用字段（几乎所有频道都支持）

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `enabled` | boolean | 是 | 是否启用该频道 | `true` |
| `name` | string | 是 | 频道显示名称 | `"BlueDeer 飞书助手"` |
| `allowFrom` | string[] | 否 | 允许交互的 ID 白名单（用户/群/频道 ID） | `["ou_xxx", "oc_xxx"]` |
| `systemPrompt` | string | 否 | 该频道专属系统提示词 | `"你是一个专业的客服助手..."` |
| `markdownSupport` | boolean | 否 | 该频道是否支持 Markdown | `true` |
| `callbackUrl` | string | 视平台 | 事件订阅/ webhook 回调地址 | `https://your-domain.com/webhook/feishu` |

---

## 一、国内 / 亚洲主力平台

### 1. 飞书 / Lark

接入方式：飞书自建应用（机器人）+ 事件订阅；也支持群 webhook 机器人。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `appId` | string | 是 | 飞书自建应用 App ID | `cli_xxxxxxxxxx` |
| `appSecret` | string | 是 | 飞书自建应用 App Secret | `xxxxxx...` |
| `encryptKey` | string | 否 | 事件订阅加密密钥（启用加密时必填） | `xxxxxx...` |
| `verificationToken` | string | 否 | 旧版校验 Token（新应用可不用） | `xxxxxx...` |
| `callbackUrl` | string | 是 | 事件订阅回调 URL，需公网可访问 | `https://api.yourdomain.com/webhook/feishu` |
| `webhookUrl` | string | 否 | 群机器人 Webhook 地址（仅 webhook 模式） | `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx` |
| `webhookSecret` | string | 否 | 群机器人签名密钥 | `xxxxxx...` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer 飞书助手",
  "appId": "cli_xxxxxxxxxx",
  "appSecret": "your-app-secret",
  "encryptKey": "your-encrypt-key",
  "callbackUrl": "https://api.yourdomain.com/webhook/feishu",
  "allowFrom": ["ou_xxx"],
  "systemPrompt": "你是 BlueDeer 的飞书智能助手。"
}
```

官方入口：
- 开放平台：https://open.feishu.cn/app
- 机器人文档：https://open.feishu.cn/document/home/develop-a-bot-in-5-minutes/create-an-app

---

### 2. 钉钉

接入方式：钉钉企业内部机器人 / 群机器人；消息接收需要回调。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `appKey` | string | 是 | 企业内部应用 AppKey | `dingxxxxxx` |
| `appSecret` | string | 是 | 企业内部应用 AppSecret | `xxxxxx...` |
| `robotCode` | string | 否 | 机器人 Code（新版机器人） | `xxxxxx` |
| `webhookUrl` | string | 否 | 群机器人 Webhook 地址 | `https://oapi.dingtalk.com/robot/send?access_token=xxx` |
| `webhookSecret` | string | 否 | 群机器人加签密钥 | `SECxxxxxx` |
| `callbackToken` | string | 是 | 消息接收回调 Token | `xxxxxx` |
| `callbackAesKey` | string | 是 | 消息接收回调 AES Key | `xxxxxx...` |
| `callbackUrl` | string | 是 | 回调 URL | `https://api.yourdomain.com/webhook/dingtalk` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer 钉钉助手",
  "appKey": "dingxxxxxx",
  "appSecret": "your-app-secret",
  "robotCode": "your-robot-code",
  "callbackToken": "your-token",
  "callbackAesKey": "your-aes-key",
  "callbackUrl": "https://api.yourdomain.com/webhook/dingtalk",
  "allowFrom": ["userId_xxx"],
  "systemPrompt": "你是 BlueDeer 的钉钉智能助手。"
}
```

官方入口：
- 开放平台：https://open.dingtalk.com/
- 机器人文档：https://open.dingtalk.com/document/isv/robot-overview

---

### 3. 企业微信

接入方式：自建应用 / 群机器人 / 微信客服。

#### 3.1 自建应用消息

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `corpId` | string | 是 | 企业 ID | `wwxxxxxx` |
| `agentId` | string | 是 | 应用 AgentId | `1000002` |
| `secret` | string | 是 | 应用 Secret | `xxxxxx...` |
| `token` | string | 是 | 回调配置 Token | `xxxxxx` |
| `encodingAesKey` | string | 是 | 回调配置 EncodingAESKey | `xxxxxx...` |
| `callbackUrl` | string | 是 | 回调 URL | `https://api.yourdomain.com/webhook/wecom` |

```json
{
  "enabled": true,
  "name": "BlueDeer 企微助手",
  "corpId": "wwxxxxxx",
  "agentId": "1000002",
  "secret": "your-app-secret",
  "token": "your-token",
  "encodingAesKey": "your-encoding-aes-key",
  "callbackUrl": "https://api.yourdomain.com/webhook/wecom",
  "allowFrom": ["ZhangSan"],
  "systemPrompt": "你是 BlueDeer 的企业微信智能助手。"
}
```

#### 3.2 群机器人 Webhook

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `webhookKey` | string | 是 | 群机器人 key | `xxxxx-xxxx-xxxx` |

```json
{
  "enabled": true,
  "name": "BlueDeer 企微群机器人",
  "webhookKey": "xxxxx-xxxx-xxxx"
}
```

官方入口：
- 企业管理后台：https://work.weixin.qq.com/wework_admin
- 开发者文档：https://developer.work.weixin.qq.com/document/path/90487

---

### 4. QQ 官方 Bot

接入方式：QQ 官方机器人（Gateway / WebSocket Intents）。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `appId` | string | 是 | 机器人 App ID | `123456789` |
| `token` | string | 是 | 机器人 Token | `xxxxxx...` |
| `secret` | string | 是 | 机器人 Secret | `xxxxxx...` |
| `sandbox` | boolean | 否 | 是否使用沙箱环境 | `false` |
| `intents` | number[] | 否 | 订阅的 Intents（1=私聊，2=群聊...） | `[0, 1]` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer QQ 机器人",
  "appId": "123456789",
  "token": "your-bot-token",
  "secret": "your-bot-secret",
  "sandbox": false,
  "intents": [0, 1],
  "allowFrom": ["USER_OPENID_xxx", "GROUP_OPENID_xxx"],
  "systemPrompt": "你是 BlueDeer 的 QQ 智能助手。"
}
```

官方入口：
- 开放平台：https://q.qq.com/#/home
- 机器人文档：https://bot.q.qq.com/wiki/

---

### 5. 微信公众号

接入方式：订阅号/服务号 + 服务器配置回调。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `appId` | string | 是 | 公众号 AppID | `wx_xxxxxx` |
| `appSecret` | string | 是 | 公众号 AppSecret | `xxxxxx...` |
| `token` | string | 是 | 服务器配置 Token | `xxxxxx` |
| `encodingAesKey` | string | 否 | 消息加密密钥（安全模式必填） | `xxxxxx...` |
| `callbackUrl` | string | 是 | 服务器配置 URL | `https://api.yourdomain.com/webhook/wechat-mp` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer 公众号",
  "appId": "wx_xxxxxx",
  "appSecret": "your-app-secret",
  "token": "your-token",
  "encodingAesKey": "your-encoding-aes-key",
  "callbackUrl": "https://api.yourdomain.com/webhook/wechat-mp",
  "systemPrompt": "你是 BlueDeer 的微信公众号助手。"
}
```

官方入口：
- 公众平台：https://mp.weixin.qq.com/
- 接入文档：https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Access_Overview.html

---

### 6. 微信小程序客服消息

接入方式：小程序后台开启消息推送。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `appId` | string | 是 | 小程序 AppID | `wx_xxxxxx` |
| `appSecret` | string | 是 | 小程序 AppSecret | `xxxxxx...` |
| `token` | string | 是 | 消息推送 Token | `xxxxxx` |
| `encodingAesKey` | string | 否 | 消息加密密钥 | `xxxxxx...` |
| `callbackUrl` | string | 是 | 消息推送 URL | `https://api.yourdomain.com/webhook/wechat-mini` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer 小程序客服",
  "appId": "wx_xxxxxx",
  "appSecret": "your-app-secret",
  "token": "your-token",
  "encodingAesKey": "your-encoding-aes-key",
  "callbackUrl": "https://api.yourdomain.com/webhook/wechat-mini",
  "systemPrompt": "你是 BlueDeer 的小程序客服助手。"
}
```

官方入口：
- 小程序后台：https://mp.weixin.qq.com/
- 客服消息文档：https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/customer-message/customer-message.html

---

### 7. LINE

接入方式：LINE Messaging API。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `channelAccessToken` | string | 是 | Channel Access Token | `xxxxxx...` |
| `channelSecret` | string | 是 | Channel Secret | `xxxxxx...` |
| `callbackUrl` | string | 是 | Webhook URL | `https://api.yourdomain.com/webhook/line` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer LINE 助手",
  "channelAccessToken": "your-channel-access-token",
  "channelSecret": "your-channel-secret",
  "callbackUrl": "https://api.yourdomain.com/webhook/line",
  "allowFrom": ["U_xxx"],
  "systemPrompt": "你是 BlueDeer 的 LINE 智能助手。"
}
```

官方入口：
- LINE Console：https://developers.line.biz/console/
- Messaging API：https://developers.line.biz/en/docs/messaging-api/

---

## 二、国际主流平台

### 8. Telegram

接入方式：Telegram Bot API；支持轮询或 webhook。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `botToken` | string | 是 | Bot Token（从 @BotFather 获取） | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `webhookUrl` | string | 否 | Webhook URL（不填则轮询） | `https://api.yourdomain.com/webhook/telegram` |
| `allowedUpdates` | string[] | 否 | 只接收指定类型更新 | `["message", "callback_query"]` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Telegram 助手",
  "botToken": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
  "webhookUrl": "https://api.yourdomain.com/webhook/telegram",
  "allowedUpdates": ["message", "edited_message"],
  "allowFrom": ["123456789"],
  "systemPrompt": "你是 BlueDeer 的 Telegram 智能助手。"
}
```

官方入口：
- @BotFather（Telegram 内搜索）
- Bot API 文档：https://core.telegram.org/bots/api

---

### 9. Discord

接入方式：Discord Bot API / Gateway Intents；也支持 Application Interactions。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `botToken` | string | 是 | Bot Token | `MTAw0...` |
| `applicationId` | string | 否 | Application ID（ slash command 需要） | `123456789012345678` |
| `publicKey` | string | 否 | Public Key（Interactions 校验需要） | `xxxxxx...` |
| `intents` | number | 否 | Gateway Intents 位掩码 | `32767` |
| `callbackUrl` | string | 否 | Interactions Endpoint URL | `https://api.yourdomain.com/webhook/discord` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Discord 助手",
  "botToken": "your-bot-token",
  "applicationId": "123456789012345678",
  "publicKey": "your-public-key",
  "intents": 32767,
  "allowFrom": ["user_xxx", "channel_xxx"],
  "systemPrompt": "你是 BlueDeer 的 Discord 智能助手。"
}
```

官方入口：
- Developer Portal：https://discord.com/developers/applications
- Bot 文档：https://discord.com/developers/docs/topics/oauth2

---

### 10. Slack

接入方式：Slack Bot + Socket Mode 或 HTTP Event Subscriptions。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `botToken` | string | 是 | Bot User OAuth Token（xoxb-） | `xoxb-xxx-xxx-xxx` |
| `signingSecret` | string | 是 | Signing Secret（校验请求） | `xxxxxx...` |
| `appToken` | string | 否 | App-Level Token（Socket Mode 必填） | `xapp-1-xxx` |
| `socketMode` | boolean | 否 | 是否使用 Socket Mode | `false` |
| `callbackUrl` | string | 否 | Event Subscriptions URL | `https://api.yourdomain.com/webhook/slack` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Slack 助手",
  "botToken": "xoxb-your-bot-token",
  "signingSecret": "your-signing-secret",
  "appToken": "xapp-your-app-token",
  "socketMode": true,
  "allowFrom": ["U_xxx", "C_xxx"],
  "systemPrompt": "你是 BlueDeer 的 Slack 智能助手。"
}
```

官方入口：
- Slack API：https://api.slack.com/apps
- Bolt 文档：https://slack.dev/bolt-js/tutorial/getting-started

---

### 11. WhatsApp

接入方式有两种：官方 WhatsApp Cloud API，或 Baileys 等第三方库扫码登录。

#### 11.1 WhatsApp Cloud API（官方）

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `phoneNumberId` | string | 是 | WhatsApp 电话号码 ID | `123456789012345` |
| `accessToken` | string | 是 | Meta 永久 Access Token | `EAAXxx...` |
| `webhookVerifyToken` | string | 是 | Webhook Verify Token | `your-verify-token` |
| `callbackUrl` | string | 是 | Webhook URL | `https://api.yourdomain.com/webhook/whatsapp` |

```json
{
  "enabled": true,
  "name": "BlueDeer WhatsApp 助手",
  "phoneNumberId": "123456789012345",
  "accessToken": "EAAX-your-access-token",
  "webhookVerifyToken": "your-verify-token",
  "callbackUrl": "https://api.yourdomain.com/webhook/whatsapp",
  "systemPrompt": "你是 BlueDeer 的 WhatsApp 智能助手。"
}
```

#### 11.2 Baileys / WhatsApp Web（第三方，扫码登录）

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `sessionName` | string | 是 | 本地 session 名称 | `bluedeer-wa` |
| `authFolder` | string | 否 | 认证信息保存目录 | `./auth/whatsapp` |

```json
{
  "enabled": true,
  "name": "BlueDeer WhatsApp Web",
  "sessionName": "bluedeer-wa",
  "authFolder": "./auth/whatsapp"
}
```

官方入口：
- Meta Cloud API：https://developers.facebook.com/docs/whatsapp/cloud-api
- Baileys：https://github.com/WhiskeySockets/Baileys

---

### 12. Google Chat

接入方式：Google Chat App（Service Account 或 HTTP webhook）。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `projectId` | string | 是 | Google Cloud Project ID | `bluedeer-chat` |
| `serviceAccountJsonPath` | string | 是 | 服务账号 JSON 文件路径 | `./secrets/google-chat-sa.json` |
| `privateKey` | string | 否 | 服务账号 Private Key（可直接填） | `-----BEGIN PRIVATE KEY-----...` |
| `clientEmail` | string | 否 | 服务账号 Client Email | `bluedeer@bluedeer-chat.iam.gserviceaccount.com` |
| `callbackUrl` | string | 是 | Chat app endpoint URL | `https://api.yourdomain.com/webhook/googlechat` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Google Chat",
  "projectId": "bluedeer-chat",
  "serviceAccountJsonPath": "./secrets/google-chat-sa.json",
  "callbackUrl": "https://api.yourdomain.com/webhook/googlechat",
  "systemPrompt": "你是 BlueDeer 的 Google Chat 智能助手。"
}
```

官方入口：
- Google Chat API：https://developers.google.com/chat/api/guides
- 创建 Chat App：https://developers.google.com/chat/apps/guides/directory-structure

---

### 13. Microsoft Teams

接入方式：Teams Bot Framework / Teams Toolkit。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `appId` | string | 是 | Microsoft App ID | `12345678-1234-1234-1234-123456789012` |
| `appPassword` | string | 是 | Client Secret | `xxxxxx...` |
| `tenantId` | string | 否 | 租户 ID（单租户必填） | `12345678-1234-1234-1234-123456789012` |
| `callbackUrl` | string | 是 | Bot Endpoint | `https://api.yourdomain.com/webhook/msteams` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Teams 助手",
  "appId": "12345678-1234-1234-1234-123456789012",
  "appPassword": "your-client-secret",
  "tenantId": "common",
  "callbackUrl": "https://api.yourdomain.com/webhook/msteams",
  "systemPrompt": "你是 BlueDeer 的 Teams 智能助手。"
}
```

官方入口：
- Azure Portal：https://portal.azure.com/
- Teams Bot 文档：https://learn.microsoft.com/en-us/microsoftteams/platform/bots/what-are-bots

---

## 三、开源 / 自托管 / 去中心化平台

### 14. Matrix

接入方式：Matrix Client-Server API + access token。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `homeserverUrl` | string | 是 | Matrix Homeserver URL | `https://matrix.org` |
| `accessToken` | string | 是 | 用户 Access Token | `syt_xxx...` |
| `userId` | string | 是 | 用户 ID | `@bluedeer:matrix.org` |
| `deviceId` | string | 否 | 设备 ID | `BLUEDEER_BOT` |
| `roomId` | string | 否 | 默认监听房间 ID | `!xxx:matrix.org` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Matrix 助手",
  "homeserverUrl": "https://matrix.org",
  "accessToken": "syt-your-access-token",
  "userId": "@bluedeer:matrix.org",
  "deviceId": "BLUEDEER_BOT",
  "allowFrom": ["!roomId:matrix.org"],
  "systemPrompt": "你是 BlueDeer 的 Matrix 智能助手。"
}
```

官方入口：
- Matrix 文档：https://spec.matrix.org/latest/
- Element：https://element.io/

---

### 15. Signal

接入方式：signal-cli REST API（需要本地运行 signal-cli）。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `signalCliRestApiUrl` | string | 是 | signal-cli REST API 地址 | `http://localhost:8080/v1` |
| `phoneNumber` | string | 是 | 已注册 Signal 的手机号 | `+8613800138000` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Signal 助手",
  "signalCliRestApiUrl": "http://localhost:8080/v1",
  "phoneNumber": "+8613800138000",
  "allowFrom": ["+8613900139000"],
  "systemPrompt": "你是 BlueDeer 的 Signal 智能助手。"
}
```

官方入口：
- signal-cli：https://github.com/AsamK/signal-cli
- REST API wrapper：https://github.com/bbernhard/signal-cli-rest-api

---

### 16. IRC

接入方式：IRC 客户端协议。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `server` | string | 是 | IRC 服务器地址 | `irc.libera.chat` |
| `port` | number | 是 | 端口 | `6697` |
| `tls` | boolean | 是 | 是否 TLS | `true` |
| `nickname` | string | 是 | 机器人昵称 | `BlueDeerBot` |
| `username` | string | 否 | 用户名 | `bluedeer` |
| `password` | string | 否 | NickServ 密码 | `xxxxxx` |
| `channels` | string[] | 否 | 自动加入频道 | `["#bluedeer"]` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer IRC 助手",
  "server": "irc.libera.chat",
  "port": 6697,
  "tls": true,
  "nickname": "BlueDeerBot",
  "channels": ["#bluedeer"],
  "systemPrompt": "你是 BlueDeer 的 IRC 智能助手。"
}
```

官方入口：
- Libera Chat：https://libera.chat/

---

### 17. Mattermost

接入方式：Mattermost Bot Account + Personal Access Token。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `serverUrl` | string | 是 | Mattermost 服务器地址 | `https://mattermost.yourdomain.com` |
| `botAccessToken` | string | 是 | Bot Access Token | `xxxxxx...` |
| `teamName` | string | 否 | 默认 Team 名称 | `bluedeer` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Mattermost 助手",
  "serverUrl": "https://mattermost.yourdomain.com",
  "botAccessToken": "your-bot-access-token",
  "teamName": "bluedeer",
  "allowFrom": ["user_xxx"],
  "systemPrompt": "你是 BlueDeer 的 Mattermost 智能助手。"
}
```

官方入口：
- Mattermost：https://mattermost.com/
- Bot 文档：https://developers.mattermost.com/integrate/reference/bot-accounts/

---

### 18. Nextcloud Talk

接入方式：Nextcloud Talk Webhook Bot。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `serverUrl` | string | 是 | Nextcloud 地址 | `https://cloud.yourdomain.com` |
| `username` | string | 是 | 用户名 | `bluedeer-bot` |
| `appPassword` | string | 是 | 应用专用密码 | `xxxxxx...` |
| `roomToken` | string | 否 | 默认房间 Token | `abc123def` |
| `callbackUrl` | string | 是 | Webhook 回调地址 | `https://api.yourdomain.com/webhook/nextcloud` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Nextcloud Talk",
  "serverUrl": "https://cloud.yourdomain.com",
  "username": "bluedeer-bot",
  "appPassword": "your-app-password",
  "roomToken": "abc123def",
  "callbackUrl": "https://api.yourdomain.com/webhook/nextcloud",
  "systemPrompt": "你是 BlueDeer 的 Nextcloud Talk 智能助手。"
}
```

官方入口：
- Nextcloud Talk：https://nextcloud.com/talk/
- Webhook Bot：https://nextcloud-talk.readthedocs.io/en/latest/commands/

---

### 19. Nostr

接入方式：Nostr 协议，使用 nsec 私钥和 relays。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `privateKey` | string | 是 | Nostr 私钥（nsec1... 或 hex） | `nsec1...` |
| `relays` | string[] | 是 | Relay 地址列表 | `["wss://relay.damus.io", "wss://nos.lol"]` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Nostr",
  "privateKey": "nsec1yourprivatekey",
  "relays": ["wss://relay.damus.io", "wss://nos.lol"],
  "allowFrom": ["npub1..."],
  "systemPrompt": "你是 BlueDeer 的 Nostr 智能助手。"
}
```

官方入口：
- Nostr：https://nostr.com/
- NIPs：https://github.com/nostr-protocol/nips

---

### 20. Tlon / Urbit

接入方式：Urbit %gall agent 或 Tlon API。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `shipUrl` | string | 是 | Urbit 飞船 URL | `http://localhost:8080` |
| `code` | string | 是 | Urbit +code | `lidlut-tabwed-pillex-ridrup` |
| `desk` | string | 否 | Desk 名称 | `garden` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Tlon",
  "shipUrl": "http://localhost:8080",
  "code": "lidlut-tabwed-pillex-ridrup",
  "desk": "garden",
  "systemPrompt": "你是 BlueDeer 的 Tlon 智能助手。"
}
```

官方入口：
- Tlon：https://tlon.io/
- Urbit：https://urbit.org/

---

## 四、小众 / 平台特化

### 21. Synology Chat

接入方式：Synology Chat 机器人 Incoming / Outgoing Webhook。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `serverUrl` | string | 是 | Synology NAS 地址 | `https://nas.yourdomain.com:5001` |
| `botToken` | string | 是 | Bot Token | `xxxxxx...` |
| `incomingUrl` | string | 否 | Incoming Webhook URL | `https://nas.yourdomain.com/webapi/entry.cgi?api=SYNO.Chat.External&method=incoming&version=2&token=xxx` |
| `callbackUrl` | string | 否 | Outgoing Webhook URL | `https://api.yourdomain.com/webhook/synology` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Synology Chat",
  "serverUrl": "https://nas.yourdomain.com:5001",
  "botToken": "your-bot-token",
  "incomingUrl": "https://nas.yourdomain.com/webapi/entry.cgi?...",
  "callbackUrl": "https://api.yourdomain.com/webhook/synology"
}
```

官方入口：
- Synology Chat：https://www.synology.com/en-us/dsm/feature/chat

---

### 22. Twitch

接入方式：Twitch IRC + OAuth。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `botUsername` | string | 是 | 机器人 Twitch 用户名 | `BlueDeerBot` |
| `oauthToken` | string | 是 | OAuth Token（irc 密码） | `oauth:xxxxxx...` |
| `channelName` | string | 是 | 默认监听频道 | `#bluedeer` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Twitch 助手",
  "botUsername": "BlueDeerBot",
  "oauthToken": "oauth:your-oauth-token",
  "channelName": "bluedeer",
  "systemPrompt": "你是 BlueDeer 的 Twitch 聊天助手。"
}
```

官方入口：
- Twitch Chat OAuth：https://twitchapps.com/tmi/
- IRC 文档：https://dev.twitch.tv/docs/irc/

---

### 23. BlueBubbles

接入方式：macOS BlueBubbles 服务器 + REST API。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `serverUrl` | string | 是 | BlueBubbles 服务器地址 | `http://localhost:1234` |
| `password` | string | 否 | 服务器密码 | `xxxxxx...` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer BlueBubbles",
  "serverUrl": "http://localhost:1234",
  "password": "your-server-password",
  "systemPrompt": "你是 BlueDeer 的 iMessage 助手。"
}
```

官方入口：
- BlueBubbles：https://bluebubbles.app/

---

### 24. iMessage

接入方式：依赖 macOS + BlueBubbles 或本地 AppleScript relay。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `relayUrl` | string | 是 | iMessage relay 地址 | `http://localhost:3000` |
| `authToken` | string | 否 | relay 认证 token | `xxxxxx...` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer iMessage",
  "relayUrl": "http://localhost:3000",
  "authToken": "your-auth-token",
  "systemPrompt": "你是 BlueDeer 的 iMessage 助手。"
}
```

---

### 25. Zalo（Bot API）

接入方式：Zalo Official Account Bot API。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `appId` | string | 是 | Zalo App ID | `123456789` |
| `accessToken` | string | 是 | OA Access Token | `xxxxxx...` |
| `callbackUrl` | string | 是 | Webhook URL | `https://api.yourdomain.com/webhook/zalo` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Zalo 助手",
  "appId": "123456789",
  "accessToken": "your-access-token",
  "callbackUrl": "https://api.yourdomain.com/webhook/zalo",
  "systemPrompt": "你是 BlueDeer 的 Zalo 智能助手。"
}
```

官方入口：
- Zalo Developers：https://developers.zalo.me/

---

### 26. Zalo Personal（个人账号）

接入方式：zca-js 库扫码登录，使用 cookie / IMEI。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `cookie` | string | 是 | Zalo cookie（登录后导出） | `zpw_sek=...` |
| `imei` | string | 是 | 设备 IMEI | `xxxxxx` |
| `userAgent` | string | 否 | 浏览器 UA | `Mozilla/5.0...` |

最小 JSON 示例：

```json
{
  "enabled": true,
  "name": "BlueDeer Zalo 个人号",
  "cookie": "your-zalo-cookie",
  "imei": "your-device-imei",
  "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
```

参考：
- zca-js：https://github.com/ThuongHai/zca-js

---

## 五、语音 / 电话频道

### 27. Voice Call（电话通话）

接入方式：通过 Twilio / Telnyx / Plivo 等云通信平台实现 AI 电话通话。

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `provider` | string | 是 | 提供商：`twilio` / `telnyx` / `plivo` / `mock` | `twilio` |
| `fromNumber` | string | 是 | 主叫号码（E.164 格式） | `+15550001234` |
| `toNumber` | string | 否 | 默认被叫号码 | `+15550005678` |
| `serve.port` | number | 否 | 本地 webhook 端口 | `3001` |
| `serve.path` | string | 否 | webhook 路径 | `/webhook/voice` |
| `publicUrl` | string | 否 | 公网 webhook URL（Twilio/Telnyx 回调用） | `https://api.yourdomain.com/webhook/voice` |

#### Twilio 专属

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `twilio.accountSid` | string | 是 | Account SID | `ACxxxxxx` |
| `twilio.authToken` | string | 是 | Auth Token | `xxxxxx...` |

#### Telnyx 专属

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `telnyx.apiKey` | string | 是 | API Key | `KEYxxxxxx...` |
| `telnyx.connectionId` | string | 是 | Call Control Application ID | `uuid-xxxxxx` |
| `telnyx.publicKey` | string | 否 | Public Key | `xxxxxx...` |

#### Plivo 专属

| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| `plivo.authId` | string | 是 | Auth ID | `MAxxxxxx` |
| `plivo.authToken` | string | 是 | Auth Token | `xxxxxx...` |

最小 JSON 示例（Twilio）：

```json
{
  "enabled": true,
  "name": "BlueDeer 语音通话",
  "provider": "twilio",
  "fromNumber": "+15550001234",
  "toNumber": "+15550005678",
  "twilio": {
    "accountSid": "ACxxxxxx",
    "authToken": "your-auth-token"
  },
  "serve": {
    "port": 3001,
    "path": "/webhook/voice"
  },
  "publicUrl": "https://api.yourdomain.com/webhook/voice",
  "responseModel": "openai/gpt-4o-mini",
  "responseSystemPrompt": "你是一个电话客服助手。"
}
```

官方入口：
- Twilio：https://www.twilio.com/
- Telnyx：https://telnyx.com/
- Plivo：https://www.plivo.com/

---

## 快速选择建议

| 你的场景 | 推荐平台 | 原因 |
|----------|----------|------|
| 国内办公 / 团队协作 | 飞书、钉钉、企业微信 | 国内最主流，API 成熟 |
| 海外社区 / 公开机器人 | Telegram、Discord | 免费、API 简单、生态成熟 |
| 企业海外办公 | Slack、Microsoft Teams、Google Chat | 企业集成强 |
| 隐私 / 去中心化 | Matrix、Signal、Nostr | 开源、数据自主 |
| 客服 / 用户触达 | 微信公众号、微信小程序、WhatsApp | 用户基数大 |
| 技术玩家 / 自托管 | Mattermost、Nextcloud Talk、IRC | 完全可控 |
| 需要 AI 打电话 | Voice Call（Twilio/Telnyx） | 直接对接 PSTN |

---

## 附：通用回调路由建议

如果你给每个平台都配一个 webhook，建议统一路由前缀：

```
https://api.yourdomain.com/webhook/{channel}
```

例如：
- 飞书：`/webhook/feishu`
- 钉钉：`/webhook/dingtalk`
- Telegram：`/webhook/telegram`
- Discord：`/webhook/discord`
- Slack：`/webhook/slack`
- WhatsApp：`/webhook/whatsapp`
- LINE：`/webhook/line`
- 企业微信：`/webhook/wecom`
- Google Chat：`/webhook/googlechat`
- Microsoft Teams：`/webhook/msteams`

---

*文档生成时间：2026-08-17*
*基于 OpenClaw 频道扩展清单 + 各平台官方 Bot/API 文档整理*
