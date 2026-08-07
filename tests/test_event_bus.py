"""EventBus 单元测试：订阅/通配符/优先级/过滤/重试/定向/历史/回放/request 超时。"""

import logging
logger = logging.getLogger(__name__)
import asyncio

from core.event_bus import EventBus
from core.task import Message, Task, TaskResult, TaskStatus


def _msg(topic: str, payload: str = "") -> Message:
    suffix = f"-{payload}" if payload else ""
    return Message(trace_id=f"trace-{topic}{suffix}")


class TestSubscribe:
    def test_subscribe_and_publish_calls_handler(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(msg.trace_id)

        bus.subscribe("agent.fox", handler)
        asyncio.run(bus.publish("agent.fox", _msg("agent.fox", "a")))
        assert received == ["trace-agent.fox-a"]

    def test_priority_order_higher_first(self):
        bus = EventBus()
        order = []

        async def low(msg: Message) -> None:
            order.append("low")

        async def high(msg: Message) -> None:
            order.append("high")

        bus.subscribe("t", low, priority=-5)
        bus.subscribe("t", high, priority=10)
        asyncio.run(bus.publish("t", _msg("t")))
        assert order == ["high", "low"]

    def test_same_priority_insertion_order(self):
        bus = EventBus()
        order = []

        async def first(msg: Message) -> None:
            order.append(1)

        async def second(msg: Message) -> None:
            order.append(2)

        bus.subscribe("t", first)
        bus.subscribe("t", second)
        asyncio.run(bus.publish("t", _msg("t")))
        assert order == [1, 2]

    def test_unsubscribe_removes_handler(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(1)

        bus.subscribe("t", handler)
        assert bus.unsubscribe("t", handler) is True
        assert bus.unsubscribe("t", handler) is False
        asyncio.run(bus.publish("t", _msg("t")))
        assert received == []

    def test_subscriber_count_direct_and_wildcard(self):
        bus = EventBus()

        async def handler(msg: Message) -> None:
            pass

        bus.subscribe("agent.fox", handler)
        bus.subscribe("agent.*", handler)
        assert bus.subscriber_count("agent.fox") == 2

    def test_topic_list(self):
        bus = EventBus()

        async def handler(msg: Message) -> None:
            pass

        bus.subscribe("a.b", handler)
        bus.subscribe("c", handler)
        assert sorted(bus.topic_list()) == ["a.b", "c"]


class TestWildcard:
    def test_wildcard_matches_subtopic(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(msg.trace_id)

        bus.subscribe("agent.*", handler)
        asyncio.run(bus.publish("agent.squirrel", _msg("agent.squirrel")))
        asyncio.run(bus.publish("agent.fox", _msg("agent.fox")))
        assert len(received) == 2

    def test_wildcard_prefix_suffix_only(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(msg.trace_id)

        bus.subscribe("agent.*.done", handler)
        asyncio.run(bus.publish("agent.fox.done", _msg("agent.fox.done")))
        asyncio.run(bus.publish("agent.fox.start", _msg("agent.fox.start")))
        asyncio.run(bus.publish("agent.done", _msg("agent.done")))
        assert received == ["trace-agent.fox.done"]

    def test_wildcard_subscriber_gets_history_topic_order(self):
        bus = EventBus()

        async def handler(msg: Message) -> None:
            pass

        bus.subscribe("event.*", handler)
        assert bus.subscriber_count("event.alpha") == 1


class TestFilter:
    def test_filter_blocks_message(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(msg.trace_id)

        bus.subscribe("t", handler, filter=lambda m: m.trace_id.endswith("-keep"))
        asyncio.run(bus.publish("t", _msg("t", "drop")))
        asyncio.run(bus.publish("t", _msg("t", "keep")))
        assert received == ["trace-t-keep"]

    def test_filter_exception_passes_through(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(msg.trace_id)

        def bad_filter(msg: Message) -> bool:
            raise ValueError("boom")

        bus.subscribe("t", handler, filter=bad_filter)
        asyncio.run(bus.publish("t", _msg("t")))
        assert received == ["trace-t"]


class TestPublishVariants:
    def test_publish_delayed(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(msg.trace_id)

        bus.subscribe("t", handler)
        asyncio.run(bus.publish_delayed("t", _msg("t"), 0.01))
        assert received == ["trace-t"]

    def test_publish_with_retry_success_after_failure(self):
        bus = EventBus()
        attempts = {"n": 0}

        async def flaky(msg: Message) -> None:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionError("temporary")

        bus.subscribe("t", flaky)
        completed = asyncio.run(bus.publish_with_retry("t", _msg("t"), max_retries=3))
        assert completed == 1
        assert attempts["n"] == 3

    def test_publish_with_retry_exhausted_counts_zero(self):
        bus = EventBus()

        async def always_fail(msg: Message) -> None:
            raise RuntimeError("permanent")

        bus.subscribe("t", always_fail)
        completed = asyncio.run(bus.publish_with_retry("t", _msg("t"), max_retries=2))
        assert completed == 0

    def test_publish_directed_reaches_recipient(self):
        bus = EventBus()
        received = []

        async def target(msg: Message) -> None:
            received.append("target")

        async def other(msg: Message) -> None:
            received.append("other")

        bus.subscribe("t", other)
        bus.subscribe("t", target)
        ok = asyncio.run(bus.publish_directed("t", _msg("t"), target))
        assert ok is True
        assert received == ["target"]

    def test_publish_directed_missing_recipient(self):
        bus = EventBus()

        async def target(msg: Message) -> None:
            pass

        ok = asyncio.run(bus.publish_directed("t", _msg("t"), target))
        assert ok is False

    def test_handler_exception_does_not_break_gather(self):
        bus = EventBus()
        order = []

        async def bad(msg: Message) -> None:
            raise RuntimeError("boom")

        async def good(msg: Message) -> None:
            order.append("good")

        bus.subscribe("t", bad)
        bus.subscribe("t", good)
        asyncio.run(bus.publish("t", _msg("t")))
        assert order == ["good"]


class TestHistoryAndStats:
    def test_history_records_recent(self):
        bus = EventBus(max_history=100)

        async def handler(msg: Message) -> None:
            pass

        bus.subscribe("t", handler)
        for i in range(5):
            asyncio.run(bus.publish("t", _msg("t", str(i))))
        hist = bus.history("t", limit=3)
        assert [m.trace_id for m in hist] == ["trace-t-2", "trace-t-3", "trace-t-4"]

    def test_history_capped_by_max_history(self):
        bus = EventBus(max_history=2)

        async def handler(msg: Message) -> None:
            pass

        bus.subscribe("t", handler)
        for i in range(5):
            asyncio.run(bus.publish("t", _msg("t", str(i))))
        hist = bus.history("t")
        assert [m.trace_id for m in hist] == ["trace-t-3", "trace-t-4"]

    def test_history_empty_topic(self):
        bus = EventBus()
        assert bus.history("nope") == []

    def test_publish_stats_counts(self):
        bus = EventBus()

        async def handler(msg: Message) -> None:
            pass

        bus.subscribe("t", handler)
        asyncio.run(bus.publish("t", _msg("t")))
        asyncio.run(bus.publish("t", _msg("t")))
        assert bus.publish_stats() == {"t": 2}

    def test_replay_redelivers_history(self):
        bus = EventBus()
        received = []

        async def handler(msg: Message) -> None:
            received.append(msg.trace_id)

        bus.subscribe("t", handler)
        asyncio.run(bus.publish("t", _msg("t", "a")))
        asyncio.run(bus.publish("t", _msg("t", "b")))
        count = bus.replay("t", count=1)
        assert count == 1
        assert received[-1] == "trace-t-b"

    def test_replay_empty_returns_zero(self):
        bus = EventBus()
        assert bus.replay("t", count=3) == 0


class TestRequest:
    def test_request_roundtrip(self):
        bus = EventBus()
        task = Task(id="job-1", type="code", payload={"q": 1})

        async def worker(msg: Message) -> None:
            result = TaskResult(
                trace_id=msg.trace_id,
                task_id=msg.id,
                status=TaskStatus.COMPLETED,
                output="done",
            )
            await bus.publish("agent.fox.result", result)

        bus.subscribe("agent.fox.task", worker)

        async def run():
            return await bus.request(
                task,
                "agent.fox.task",
                "agent.fox.result",
                timeout=2.0,
            )

        result = asyncio.run(run())
        assert isinstance(result, TaskResult)
        assert result.task_id == "job-1"
        assert result.status == TaskStatus.COMPLETED
        assert result.output == "done"

    def test_request_timeout_returns_failed(self):
        bus = EventBus()
        task = Task(id="job-2", type="code")

        async def run():
            return await bus.request(
                task,
                "agent.silent.task",
                "agent.silent.result",
                timeout=0.1,
            )

        result = asyncio.run(run())
        assert result.task_id == "job-2"
        assert result.status == TaskStatus.FAILED
        assert "超时" in (result.error or "")

    def test_request_unsubscribes_after_done(self):
        bus = EventBus()
        task = Task(id="job-3", type="code")

        async def worker(msg: Message) -> None:
            result = TaskResult(trace_id=msg.trace_id, task_id=msg.id)
            await bus.publish("w.result", result)

        bus.subscribe("w.task", worker)
        asyncio.run(bus.request(task, "w.task", "w.result", timeout=2.0))
        assert bus.subscriber_count("w.result") == 0
