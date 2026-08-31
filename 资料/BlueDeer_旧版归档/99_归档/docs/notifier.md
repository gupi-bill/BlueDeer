# Notifier 多渠道通知配置文档

## 1. 通知渠道

Notifier 支持以下通知渠道：

| 渠道 | 类名 | 说明 |
|------|------|------|
| 邮件 | `EmailChannel` | SMTP 邮件通知 |
| 钉钉 | `DingTalkChannel` | 钉钉机器人 Webhook |
| 飞书 | `FeishuChannel` | 飞书机器人 Webhook |
| Slack | `SlackChannel` | Slack Webhook |
| 自定义 | `NotificationChannel` | 实现 `send` 方法的自定义渠道 |

## 2. 邮件配置

```python
from core.notifier import Notifier, EmailChannel, EmailConfig

notifier = Notifier()

config = EmailConfig(
    smtp_host="smtp.example.com",
    smtp_port=587,
    smtp_user="user@example.com",
    smtp_password="password",
    from_addr="bluedeer@example.com",
    to_addrs=["admin@example.com"],
    use_tls=True,
)
notifier.register("email", EmailChannel(config))

await notifier.send("email", "告警标题", "告警内容")
```

## 3. 钉钉配置

```python
from core.notifier import DingTalkChannel

notifier.register("dingtalk", DingTalkChannel(
    webhook_url="https://oapi.dingtalk.com/robot/send?access_token=...",
    secret="SEC...",  # 可选，用于加签
))

await notifier.send("dingtalk", "告警标题", "告警内容")
```

## 4. 飞书配置

```python
from core.notifier import FeishuChannel

notifier.register("feishu", FeishuChannel(
    webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/...",
))

await notifier.send("feishu", "告警标题", "告警内容")
```

## 5. Slack 配置

```python
from core.notifier import SlackChannel

notifier.register("slack", SlackChannel(
    webhook_url="https://hooks.slack.com/services/...",
))

await notifier.send("slack", "告警标题", "告警内容")
```

## 6. 批量发送

```python
from core.notifier import Notif

notifs = [
    Notif(channel="email", title="告警1", body="内容1"),
    Notif(channel="dingtalk", title="告警2", body="内容2"),
]
results = await notifier.send_batch(notifs, concurrency=5)
```

## 7. 广播发送

```python
# 向所有已注册渠道广播
results = await notifier.broadcast("系统告警", "CPU 使用率过高")
# 返回 {channel_name: bool}
```

## 8. 去重机制

```python
# 启用去重，60 秒内相同内容只发送一次
await notifier.send("email", "标题", "内容", dedup=True)
```

- 默认去重窗口：60 秒
- 基于标题 + 内容的 MD5 去重

## 9. 自定义渠道

```python
from core.notifier import NotificationChannel

class MyChannel(NotificationChannel):
    async def send(self, title: str, body: str, **kwargs) -> bool:
        # 自定义发送逻辑
        print(f"[{title}] {body}")
        return True

notifier.register("custom", MyChannel())
```

## 10. 注意事项

- 邮件发送在默认线程池中执行，避免阻塞事件循环
- 钉钉/飞书/Slack 使用 aiohttp 异步发送
- 渠道发送失败不影响其他渠道
- 建议为敏感渠道配置 secret（如钉钉加签）
