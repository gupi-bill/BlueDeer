"""BlueDeer 多渠道通知系统：Email / SMTP / DingTalk / 飞书 / Slack / 自定义 Webhook。

用法：
    notifier = Notifier()
    notifier.register("email", EmailChannel(smtp_host="..."))
    await notifier.send("email", "Subject", "Body")
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import smtplib
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger("bluedeer.notifier")

__all__ = ["NotificationChannel", "EmailConfig", "EmailChannel", "DingTalkChannel", "FeishuChannel", "SlackChannel", "Notif", "NotificationDispatcher", "Notifier"]


class NotificationChannel(ABC):
    """通知渠道基类。"""

    @abstractmethod
    async def send(self, title: str, body: str, **kwargs: Any) -> bool: ...


@dataclass(slots=True)
class EmailConfig:
    """SMTP 邮件配置。"""

    smtp_host: str = "localhost"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""
    from_addr: str = "bluedeer@localhost"
    to_addrs: list[str] = field(default_factory=list)
    use_tls: bool = False


class EmailChannel(NotificationChannel):
    """SMTP 邮件通知渠道。"""

    def __init__(self, config: EmailConfig) -> None:
        self._cfg = config

    async def send(self, title: str, body: str, **kwargs: Any) -> bool:
        to = kwargs.get("to") or self._cfg.to_addrs
        if not to:
            logger.warning("邮件未配置收件人")
            return False
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = self._cfg.from_addr
        msg["To"] = ", ".join(to) if isinstance(to, list) else str(to)

        loop = asyncio.get_event_loop()

        def _send() -> None:
            try:
                with smtplib.SMTP(
                    self._cfg.smtp_host, self._cfg.smtp_port, timeout=10
                ) as s:
                    if self._cfg.use_tls:
                        s.starttls()
                    if self._cfg.smtp_user:
                        s.login(self._cfg.smtp_user, self._cfg.smtp_password)
                    s.send_message(msg)
                return True
            except Exception as e:
                logger.error("邮件发送失败: %s", e)
                return False

        return await loop.run_in_executor(None, _send)


class DingTalkChannel(NotificationChannel):
    """钉钉机器人 Webhook 通知渠道。"""

    def __init__(self, webhook_url: str, secret: str = "") -> None:
        self._url = webhook_url
        self._secret = secret

    async def send(self, title: str, body: str, **kwargs: Any) -> bool:
        import aiohttp

        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": f"## {title}\n\n{body}"},
        }
        if self._secret:
            import base64
            import hashlib
            import time

            timestamp = str(round(time.time() * 1000))
            sign_str = f"{timestamp}\n{self._secret}"
            sign = base64.b64encode(hashlib.sha256(sign_str.encode()).digest()).decode()
            payload["sign"] = sign

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self._url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp,
            ):
                if resp.status == 200:
                    return True
                logger.warning("钉钉通知返回 %d", resp.status)
                return False
        except Exception as e:
            logger.error("钉钉通知失败: %s", e)
            return False


class FeishuChannel(NotificationChannel):
    """飞书机器人 Webhook 通知渠道。"""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    async def send(self, title: str, body: str, **kwargs: Any) -> bool:
        import aiohttp

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": title}},
                "elements": [{"tag": "markdown", "content": body}],
            },
        }
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self._url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp,
            ):
                return resp.status == 200
        except Exception as e:
            logger.error("飞书通知失败: %s", e)
            return False


class SlackChannel(NotificationChannel):
    """Slack Webhook 通知渠道。"""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    async def send(self, title: str, body: str, **kwargs: Any) -> bool:
        import aiohttp

        payload = {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": title}},
                {"type": "section", "text": {"type": "mrkdwn", "text": body}},
            ]
        }
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self._url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp,
            ):
                return resp.status == 200
        except Exception as e:
            logger.error("Slack 通知失败: %s", e)
            return False


@dataclass(slots=True)
class Notif:
    title: str
    body: str
    channel: str = ""
    kwargs: dict = field(default_factory=dict)


class NotificationDispatcher:
    """通知分发器：统一接口，封装去重、批量发送、广播逻辑。

    与 Notifier（渠道注册表）分离，专注发送策略与并发控制。
    """

    def __init__(self, channels: dict[str, NotificationChannel], dedup_ttl: float = 60.0, batch_gap: float = 0.5) -> None:
        self._channels = channels
        self._dedup_ttl = dedup_ttl
        self._batch_gap = batch_gap
        self._seen: OrderedDict[str, float] = OrderedDict()

    def _digest(self, title: str, body: str) -> str:
        return hashlib.md5(f"{title}|{body}".encode()).hexdigest()

    def is_dup(self, title: str, body: str) -> bool:
        d = self._digest(title, body)
        now = time.monotonic()
        self._seen[d] = now
        cutoff = now - self._dedup_ttl
        stale = [k for k, v in self._seen.items() if v < cutoff]
        for k in stale:
            del self._seen[k]
        return d in self._seen and (self._seen[d] != now)

    async def send(self, channel: str, title: str, body: str, dedup: bool = False, **kwargs) -> bool:
        if dedup and self.is_dup(title, body):
            logger.debug("去重跳过: [%s] %s", channel, title)
            return True
        ch = self._channels.get(channel)
        if ch is None:
            logger.warning("通知渠道 %s 未注册", channel)
            return False
        return await ch.send(title, body, **kwargs)

    async def send_batch(self, notifs: list[Notif], concurrency: int = 5) -> list[bool]:
        sem = asyncio.Semaphore(concurrency)

        async def _one(n: Notif) -> bool:
            async with sem:
                r = await self.send(n.channel, n.title, n.body, **n.kwargs)
                await asyncio.sleep(self._batch_gap)
                return r

        return await asyncio.gather(*[_one(n) for n in notifs])

    async def broadcast(self, title: str, body: str, dedup: bool = False, **kwargs) -> dict[str, bool]:
        if dedup and self.is_dup(title, body):
            logger.debug("去重跳过广播: %s", title)
            return {n: False for n in self._channels}
        results: dict[str, bool] = {}
        for name, ch in self._channels.items():
            results[name] = await ch.send(title, body, **kwargs)
        return results


class Notifier:
    """统一通知调度器（渠道注册表）。"""

    def __init__(self, dedup_ttl: float = 60.0, batch_gap: float = 0.5) -> None:
        self._channels: dict[str, NotificationChannel] = {}
        self._dedup_ttl = dedup_ttl
        self._batch_gap = batch_gap
        self._dispatcher: NotificationDispatcher | None = None

    def _invalidate_dispatcher(self) -> None:
        self._dispatcher = None

    def register(self, name: str, channel: NotificationChannel) -> None:
        self._channels[name] = channel
        self._invalidate_dispatcher()
        logger.info("通知渠道已注册: %s (%s)", name, type(channel).__name__)

    def unregister(self, name: str) -> bool:
        result = self._channels.pop(name, None) is not None
        self._invalidate_dispatcher()
        return result

    def list_channels(self) -> dict[str, str]:
        return {n: type(c).__name__ for n, c in self._channels.items()}

    def _get_dispatcher(self) -> NotificationDispatcher:
        if self._dispatcher is None:
            self._dispatcher = NotificationDispatcher(
                self._channels, dedup_ttl=self._dedup_ttl, batch_gap=self._batch_gap
            )
        return self._dispatcher

    async def send(
        self, channel: str, title: str, body: str, dedup: bool = False, **kwargs: Any
    ) -> bool:
        return await self._get_dispatcher().send(channel, title, body, dedup=dedup, **kwargs)

    async def send_batch(self, notifs: list[Notif], concurrency: int = 5) -> list[bool]:
        return await self._get_dispatcher().send_batch(notifs, concurrency=concurrency)

    async def broadcast(
        self, title: str, body: str, dedup: bool = False, **kwargs: Any
    ) -> dict[str, bool]:
        return await self._get_dispatcher().broadcast(title, body, dedup=dedup, **kwargs)
