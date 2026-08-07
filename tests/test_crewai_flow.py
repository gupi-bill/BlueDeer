"""P1-3 CrewAI Flow: EventBus-based state machine tests."""

import logging

logger = logging.getLogger(__name__)
import asyncio

from core.base_agent import BaseAgent
from core.crewai_style import AgentDef, CrewAIFlow, CrewDef, TaskDef
from core.task import TaskResult, TaskStatus


class DummyBus:
    def __init__(self, fail: bool = False):
        self.topics = []
        self.events = []
        self.fail = fail

    def subscribe(self, *a, **kw):
        pass

    def unsubscribe(self, *a, **kw):
        return False

    async def publish(self, topic, message):
        self.topics.append(topic)
        self.events.append(message)

    async def request(self, task, assignee_topic, result_topic, timeout=None):
        if self.fail:
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error="boom",
                agent_id=task.assignee,
            )
        return TaskResult(
            task_id=task.id,
            status=TaskStatus.SUCCESS,
            output={"ok": True},
            agent_id=task.assignee,
        )


class DummyRouter:
    async def complete_with_failover(self, *a, **kw):
        class R:
            content = "ok"
            tokens_in = 1
            tokens_out = 1

        return R()


class DummyTools:
    def list_tools(self):
        return []


class DummyContext:
    def get_context(self):
        return {}


def make_crew(process: str = "sequential") -> CrewDef:
    return CrewDef(
        agents=[
            AgentDef(role="researcher", goal="research"),
            AgentDef(role="writer", goal="write"),
        ],
        tasks=[
            TaskDef(description="research topic", agent_role="researcher"),
            TaskDef(description="write article", agent_role="writer"),
        ],
        process=process,
    )


def make_agent(bus) -> BaseAgent:
    return BaseAgent(
        agent_id="a1",
        role="general",
        event_bus=bus,
        router=DummyRouter(),
        tool_registry=DummyTools(),
        context=DummyContext(),
    )


def test_state_idle_initial():
    flow = CrewAIFlow(make_crew())
    assert flow.state.phase == "idle"
    assert flow.state.total == 0
    assert flow.state.current_task == -1


def test_sync_run_compat():
    flow = CrewAIFlow(make_crew())
    results = flow.run()
    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)
    assert flow.state.phase == "completed"
    assert len(flow.state.completed) == 2


def test_sync_run_bound_agent_raises():
    flow = CrewAIFlow(make_crew(), agent=make_agent(DummyBus()))
    try:
        flow.run()
        assert False, "expected RuntimeError"
    except RuntimeError:
        logger.exception("Exception in block")


def test_run_async_state_machine_completed():
    bus = DummyBus()
    flow = CrewAIFlow(make_crew(), agent=make_agent(bus), bus=bus)

    async def go():
        return await flow.run_async()

    results = asyncio.run(go())
    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)
    assert flow.state.phase == "completed"
    assert len(flow.state.completed) == 2
    assert flow.state.failed == []


def test_bus_events_published():
    bus = DummyBus()
    flow = CrewAIFlow(make_crew(), agent=make_agent(bus), bus=bus)

    asyncio.run(flow.run_async())
    topics = set(bus.topics)
    prefix = f"{flow.flow_topic}."
    assert f"{flow.flow_topic}.started" in topics
    assert f"{flow.flow_topic}.task_started" in topics
    assert f"{flow.flow_topic}.task_completed" in topics
    assert f"{flow.flow_topic}.finished" in topics
    assert f"{flow.flow_topic}.task_failed" not in topics
    finished = next(e for e in bus.events if e.event_type == "finished")
    assert finished.payload["phase"] == "completed"
    assert finished.payload["completed"] == 2
    assert all(t.startswith(prefix) for t in topics)


def test_parallel_process():
    bus = DummyBus()
    flow = CrewAIFlow(make_crew(process="parallel"), agent=make_agent(bus), bus=bus)

    async def go():
        return await flow.run_async()

    results = asyncio.run(go())
    assert len(results) == 2
    assert all(r["status"] == "completed" for r in results)
    assert flow.state.phase == "completed"
    assert len(flow.state.completed) == 2


def test_unknown_role_fails_flow():
    crew = CrewDef(
        agents=[AgentDef(role="researcher", goal="research")],
        tasks=[TaskDef(description="x", agent_role="ghost")],
    )
    flow = CrewAIFlow(crew)
    results = flow.run()
    assert results[0]["error"].startswith("unknown agent role")
    assert flow.state.phase == "failed"
    assert len(flow.state.failed) == 1


def test_agent_failed_result_marks_failed():
    bus = DummyBus(fail=True)
    flow = CrewAIFlow(make_crew(), agent=make_agent(bus), bus=bus)

    async def go():
        return await flow.run_async()

    results = asyncio.run(go())
    assert all(r["status"] == "failed" for r in results)
    assert all(r["error"] == "boom" for r in results)
    assert flow.state.phase == "failed"
    assert len(flow.state.failed) == 2
