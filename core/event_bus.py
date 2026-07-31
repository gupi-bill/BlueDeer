"""BlueDeer 异步事件总线：优先级调度 + 通配符订阅。

用法：
    bus = EventBus()
    bus.subscribe("agent.*", handler, priority=10)
    await bus.publish("agent.fox", message)
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Awaitable, Callable

from core.task import Message, Task, TaskResult, TaskStatus
from core.tracer import Tracer
from core.config import get_config

logger = logging.getLogger("bluedeer.event_bus")

MessageFilter = Callable[[Message], bool]
Handler = Callable[[Message], Awaitable[None]]


class _Subscription:
    __slots__ = ("handler", "filter", "priority")

    def __init__(
        self, handler: Handler, priority: int = 0,
        filter: MessageFilter | None = None,
    ) -> None:
        self.handler = handler
        self.filter = filter
        self.priority = priority


class EventBus:
    """异步事件总线，支持优先级调度与通配符订阅。"""

    def __init__(self, tracer: Tracer | None = None, max_history: int = 100) -> None:
        self._subscribers: dict[str, list[_Subscription]] = defaultdict(list)
        self._tracer = tracer
        self._max_history = max_history
        self._history: dict[str, list[Message]] = defaultdict(list)
        self._publish_count: dict[str, int] = defaultdict(int)

    def subscribe(
        self, topic: str, handler: Handler, priority: int = 0,
        filter: MessageFilter | None = None,
    ) -> None:
        """订阅 topic。

        优先级高的 handler 优先执行，同优先级按插入顺序。
        通配符 `*` 匹配任意层级：
            subscribe("agent.*", handler) → agent.squirrel, agent.fox
        """
        subs = self._subscribers[topic]
        sub = _Subscription(handler, priority, filter)
        insert_idx = len(subs)
        for i, s in enumerate(subs):
            if s.priority < priority:
                insert_idx = i
                break
        subs.insert(insert_idx, sub)

    def _match_topics(self, pattern: str) -> list[str]:
        if "*" not in pattern:
            return [pattern]
        parts = pattern.split("*")
        matched: list[str] = []
        for t in self._subscribers:
            if len(parts) == 2:
                prefix, suffix = parts
                if t.startswith(prefix) and t.endswith(suffix):
                    matched.append(t)
            elif len(parts) == 1:
                if t == pattern:
                    matched.append(t)
        return matched

    def _find_subscribers(self, topic: str) -> list[_Subscription]:
        direct = list(self._subscribers.get(topic, []))
        for pattern, subs in self._subscribers.items():
            if "*" in pattern and pattern != topic:
                parts = pattern.split("*")
                if len(parts) == 2:
                    prefix, suffix = parts
                    if topic.startswith(prefix) and topic.endswith(suffix):
                        direct.extend(subs)
        direct.sort(key=lambda s: -s.priority)
        return direct

    def unsubscribe(self, topic: str, handler: Handler) -> bool:
        subs = self._subscribers.get(topic, [])
        for i, sub in enumerate(subs):
            if sub.handler == handler:
                subs.pop(i)
                if not subs:
                    del self._subscribers[topic]
                return True
        return False

    async def publish(self, topic: str, message: Message) -> None:
        if self._tracer:
            self._tracer.span(
                message.trace_id, component="EventBus", action="publish", topic=topic,
            )
        self._history[topic].append(message)
        if len(self._history[topic]) > self._max_history:
            self._history[topic] = self._history[topic][-self._max_history:]
        self._publish_count[topic] += 1

        subs = self._find_subscribers(topic)
        tasks = []
        for sub in subs:
            if sub.filter is not None:
                try:
                    if not sub.filter(message):
                        continue
                except Exception as e:
                    logger.warning("事件过滤器异常（按放行处理）: %s", e)
            tasks.append(asyncio.create_task(sub.handler(message)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def publish_delayed(self, topic: str, message: Message, delay: float) -> None:
        await asyncio.sleep(delay)
        await self.publish(topic, message)

    async def publish_with_retry(
        self, topic: str, message: Message,
        max_retries: int = 3, filter: MessageFilter | None = None,
    ) -> int:
        subs = self._subscribers.get(topic, [])
        completed = 0
        for sub in subs:
            if filter is not None:
                try:
                    if not filter(message):
                        continue
                except Exception:
                    pass
            ok = False
            for attempt in range(1, max_retries + 1):
                try:
                    await sub.handler(message)
                    ok = True
                    break
                except Exception as e:
                    logger.warning(
                        "事件 handler 失败（第 %d/%d 次，topic=%s）: %s",
                        attempt, max_retries, topic, e,
                    )
            if ok:
                completed += 1
        return completed

    async def publish_directed(self, topic: str, message: Message, recipient: Handler) -> bool:
        subs = self._subscribers.get(topic, [])
        for sub in subs:
            if sub.handler == recipient:
                await sub.handler(message)
                return True
        return False

    def subscriber_count(self, topic: str) -> int:
        return len(self._find_subscribers(topic))

    def topic_list(self) -> list[str]:
        return list(self._subscribers.keys())

    def history(self, topic: str, limit: int = 10) -> list[Message]:
        events = self._history.get(topic, [])
        return events[-limit:]

    def replay(self, topic: str, count: int = 1) -> int:
        events = self._history.get(topic, [])
        target = events[-count:]
        if not target:
            return 0
        subs = self._find_subscribers(topic)
        tasks = []
        for msg in target:
            for sub in subs:
                if sub.filter is not None:
                    try:
                        if not sub.filter(msg):
                            continue
                    except Exception:
                        pass
                tasks.append(asyncio.create_task(sub.handler(msg)))
        if tasks:
            asyncio.get_event_loop().run_until_complete(
                asyncio.gather(*tasks, return_exceptions=True)
            )
        return len(target)

    def publish_stats(self) -> dict[str, int]:
        return dict(self._publish_count)

    async def request(
        self, task: Task, assignee_topic: str, result_topic: str,
        timeout: float | None = None,
    ) -> TaskResult:
        if timeout is None:
            timeout = get_config().task.default_wait_timeout
        future: asyncio.Future[TaskResult] = asyncio.get_event_loop().create_future()

        async def _result_handler(msg: Message) -> None:
            if isinstance(msg, TaskResult) and msg.task_id == task.id:
                if not future.done():
                    future.set_result(msg)

        self.subscribe(result_topic, _result_handler)
        await self.publish(assignee_topic, task)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            result = TaskResult(
                trace_id=task.trace_id, task_id=task.id,
                status=TaskStatus.FAILED, error=f"任务超时（{timeout}s）",
            )
        finally:
            self.unsubscribe(result_topic, _result_handler)

        return result