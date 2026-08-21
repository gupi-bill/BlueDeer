"""BlueDeer Webhook 集成：任务事件推送到外部 URL。

支持事件类型：
- task.completed   — 任务成功完成
- task.failed      — 任务失败
- task.started     — 任务开始执行
- task.allocated   — 任务重分配
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import threading
from dataclasses import asdict, dataclass, field
from typing import Any

from core.event_bus import EventBus
from core.task import RESULT_TOPIC, Message, TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.webhook")

_WEBHOOK_FILE = "data/webhooks.json"

# 支持的 Webhook 事件类型
EVENT_TASK_COMPLETED = "task.completed"
EVENT_TASK_FAILED = "task.failed"
EVENT_TASK_STARTED = "task.started"
EVENT_TASK_ALLOCATED = "task.allocated"
EVENT_DAG_COMPLETED = "dag.completed"
EVENT_DAG_BLOCKED = "dag.blocked"

_ALL_EVENTS = (
    EVENT_TASK_COMPLETED,
    EVENT_TASK_FAILED,
    EVENT_TASK_STARTED,
    EVENT_TASK_ALLOCATED,
    EVENT_DAG_COMPLETED,
    EVENT_DAG_BLOCKED,
)


@dataclass(slots=True)
class WebhookDef:
    """Webhook 定义。"""

    id: str
    url: str
    events: list[str] = field(default_factory=lambda: list(_ALL_EVENTS))
    enabled: bool = True
    secret: str = ""
    description: str = ""
    timeout_seconds: float = 10.0
    max_retries: int = 3


class WebhookDispatcher:
    """Webhook 分发器。

    订阅 EventBus，在任务事件发生时向匹配的 Webhook URL 发送 HTTP POST。
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._hooks: dict[str, WebhookDef] = {}
        self._session: Any | None = None  # aiohttp.ClientSession
        self._handler_registered = False
        self._lock = threading.Lock()
        self._load_hooks()

    # ---- 钩子管理 ----

    def add_hook(self, hook: WebhookDef) -> str:
        with self._lock:
            self._hooks[hook.id] = hook
            self._save_hooks()
        logger.info("Webhook 已添加: %s → %s (%s)", hook.id, hook.url, hook.events)
        return hook.id

    def remove_hook(self, hook_id: str) -> bool:
        with self._lock:
            if hook_id in self._hooks:
                del self._hooks[hook_id]
                self._save_hooks()
                logger.info("Webhook 已删除: %s", hook_id)
                return True
            return False

    def get_hook(self, hook_id: str) -> WebhookDef | None:
        return self._hooks.get(hook_id)

    def list_hooks(self) -> dict[str, WebhookDef]:
        return dict(self._hooks)

    def enable_hook(self, hook_id: str) -> bool:
        with self._lock:
            hook = self._hooks.get(hook_id)
            if hook is None:
                return False
            hook.enabled = True
            self._save_hooks()
            return True

    def disable_hook(self, hook_id: str) -> bool:
        with self._lock:
            hook = self._hooks.get(hook_id)
            if hook is None:
                return False
            hook.enabled = False
            self._save_hooks()
            return True

    # ---- 启动/停止 ----

    async def start(self) -> None:
        """订阅事件总线，开始监听任务事件。"""
        if self._handler_registered:
            return
        self._bus.subscribe(RESULT_TOPIC, self._on_task_result)
        self._handler_registered = True
        logger.info("WebhookDispatcher 已启动 (%d 个钩子)", len(self._hooks))

    async def stop(self) -> None:
        """清理。"""
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("WebhookDispatcher 已停止")

    # ---- 事件处理 ----

    async def fire_dag_event(self, event: str, data: dict[str, Any]) -> None:
        """触发 DAG 事件（dag.completed / dag.blocked）。"""
        payload = {
            "event": event,
            "timestamp": __import__("time").time(),
            **data,
        }
        for hook in self._hooks.values():
            if not hook.enabled:
                continue
            if event not in hook.events:
                continue
            logger.debug("Webhook DAG 事件 %s → %s", event, hook.url)
            await self._post(hook, payload)

    async def _on_task_result(self, msg: Message) -> None:
        if not isinstance(msg, TaskResult):
            return

        event = (
            EVENT_TASK_COMPLETED
            if msg.status == TaskStatus.SUCCESS
            else EVENT_TASK_FAILED
        )
        payload = self._build_payload(event, msg)
        tasks = []
        for hook in self._hooks.values():
            if hook.enabled and event in hook.events:
                tasks.append(self._send(hook, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def fire_event(self, event: str, data: dict[str, Any]) -> None:
        """手动触发一个 webhook 事件（供 scheduler 或其他模块调用）。"""
        if event not in _ALL_EVENTS:
            logger.warning("未知 webhook 事件: %s", event)
            return
        payload = {
            "event": event,
            "timestamp": __import__("time").time(),
            "data": data,
        }
        tasks = []
        for hook in self._hooks.values():
            if hook.enabled and event in hook.events:
                tasks.append(self._send(hook, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # ---- HTTP 发送 ----

    async def _send(self, hook: WebhookDef, payload: dict[str, Any]) -> None:
        import aiohttp

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        headers = {"Content-Type": "application/json"}
        if hook.secret:
            headers["X-Webhook-Secret"] = hook.secret

        for attempt in range(1, hook.max_retries + 1):
            try:
                async with self._session.post(
                    hook.url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=hook.timeout_seconds),
                ) as resp:
                    if resp.status < 500:
                        logger.debug("Webhook %s → %d", hook.id, resp.status)
                        return
                    else:
                        logger.warning(
                            "Webhook %s 返回 %d（第 %d/%d 次）",
                            hook.id,
                            resp.status,
                            attempt,
                            hook.max_retries,
                        )
            except TimeoutError:
                logger.warning(
                    "Webhook %s 超时（第 %d/%d 次）", hook.id, attempt, hook.max_retries
                )
            except Exception as e:
                logger.warning(
                    "Webhook %s 发送失败（第 %d/%d 次）: %s",
                    hook.id,
                    attempt,
                    hook.max_retries,
                    e,
                )
            if attempt < hook.max_retries:
                await asyncio.sleep(2**attempt)

    # ---- 辅助 ----

    def _build_payload(self, event: str, result: TaskResult) -> dict[str, Any]:
        return {
            "event": event,
            "timestamp": result.timestamp,
            "data": {
                "task_id": result.task_id,
                "trace_id": result.trace_id,
                "status": result.status.value,
                "task_type": result.task_type,
                "agent_id": result.agent_id,
                "error": result.error,
                "token_usage": {
                    "tokens_in": result.token_usage.tokens_in,
                    "tokens_out": result.token_usage.tokens_out,
                    "total": result.token_usage.total,
                },
            },
        }

    # ---- 独立工具函数 ----

    @staticmethod
    async def deliver_with_retry(
        event: str, url: str, max_retries: int = 3
    ) -> tuple[bool, str]:
        """带指数退避重试的事件投递。
        Args:
            event: 事件数据（JSON 序列化）。
            url: 目标 URL。
            max_retries: 最大重试次数（默认 3）。
        Returns:
            (成功?, 消息)。
        """
        import aiohttp

        for attempt in range(1, max_retries + 1):
            try:
                async with aiohttp.ClientSession() as session, session.post(
                        url,
                        json={"event": event},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status < 500:
                            return True, f"投递成功 (HTTP {resp.status})"
            except Exception as e:
                if attempt == max_retries:
                    return False, f"投递失败: {e}"
                await asyncio.sleep(2**attempt)
        return False, "重试耗尽"

    @staticmethod
    def sign_payload(data: str, secret: str) -> str:
        """HMAC-SHA256 签名负载。
        Args:
            data: 待签名字符串（JSON）。
            secret: 共享密钥。
        Returns:
            hex 签名。
        """
        return hmac.new(
            secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    @staticmethod
    def verify_signature(payload: str, signature: str, secret: str) -> bool:
        """验证 HMAC 签名。
        Args:
            payload: 原始负载字符串。
            signature: 待验证的签名 hex。
            secret: 共享密钥。
        Returns:
            是否匹配。
        """
        expected = WebhookDispatcher.sign_payload(payload, secret)
        return hmac.compare_digest(expected, signature)

    # ---- 持久化 ----

    def _load_hooks(self) -> None:
        try:
            from core.database import Database

            rows = Database().load_webhooks()
            for item in rows:
                hook = WebhookDef(**item)
                self._hooks[hook.id] = hook
        except Exception as e:
            logger.warning("从数据库加载 webhook 失败: %s", e)

    def _save_hooks(self) -> None:
        try:
            raw = {hid: asdict(h) for hid, h in self._hooks.items()}
            from core.database import Database

            Database().save_webhooks(raw)
        except Exception as e:
            logger.warning("保存 webhook 到数据库失败: %s", e)
