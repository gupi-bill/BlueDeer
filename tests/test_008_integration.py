"""008-1/008-5: 007 框架统一集成层测试。

覆盖：
- crew_from_dict / build_langgraph_from_spec 反序列化
- FrameworkAgent 六框架分派（autogpt/babyagi/agentgpt/opendevin/crewai/langgraph）
- 真 EventBus + Harness 全链路：submit_and_wait -> agent.handle -> RESULT_TOPIC -> TaskResult
- 非法框架 -> FAILED
"""

from __future__ import annotations

import pytest

from core.agent_integration import (
    FrameworkAgent,
    build_langgraph_from_spec,
    crew_from_dict,
    run_langgraph_async,
)
from core.crewai_style import CrewDef
from core.event_bus import EventBus
from core.harness import Harness
from core.langgraph_style import StateGraph
from core.task import Task, TaskResult, TaskStatus


class _DummyRouter:
    """每次调用返回 ok 的假 router。"""

    async def complete_with_failover(self, task_type: str, prompt: str, **kwargs):
        class R:
            content = "ok"
            tokens_in = 1
            tokens_out = 1
            model_name = "dummy"

        return R()


class _DummyTools:
    def list_tools(self):
        return []

    async def call(self, name, params):
        return {"tool": name, "params": params}


class _DummyContext:
    def get_context(self, *a, **kw):
        return {}


def _make_agent(bus, agent_id: str = "fa1") -> FrameworkAgent:
    return FrameworkAgent(
        agent_id=agent_id,
        role="general",
        event_bus=bus,
        router=_DummyRouter(),
        tool_registry=_DummyTools(),
        context=_DummyContext(),
    )


def _make_harness(bus) -> Harness:
    return Harness(event_bus=bus)


# ---------------------------------------------------------------------------
# 反序列化
# ---------------------------------------------------------------------------


def test_crew_from_dict():
    crew = crew_from_dict(
        {
            "agents": [{"role": "dev", "goal": "code", "tools": ["run"]}],
            "tasks": [{"description": "write hello", "agent_role": "dev"}],
            "process": "sequential",
        }
    )
    assert isinstance(crew, CrewDef)
    assert crew.agents[0].role == "dev"
    assert crew.tasks[0].agent_role == "dev"
    assert crew.process == "sequential"


def test_build_langgraph_from_spec():
    graph = build_langgraph_from_spec(
        {
            "entry": "a",
            "nodes": ["a", "b"],
            "edges": {"a": "b"},
        },
        node_fn=lambda n, s: s,
    )
    assert graph._entry_point == "a"
    assert set(graph._nodes) == {"a", "b"}


@pytest.mark.asyncio
async def test_run_langgraph_async():
    graph = StateGraph()
    graph.add_node("a", lambda s: s.set("a", 1) or s)
    graph.add_node("b", lambda s: s.set("b", 2) or s)
    graph.add_edge("a", "b")
    graph.set_entry_point("a")
    state = await run_langgraph_async(graph, steps=5)
    assert state.data["a"] == 1
    assert state.data["b"] == 2


# ---------------------------------------------------------------------------
# FrameworkAgent 分派（非总线模式）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_loop_frameworks():
    bus = EventBus()
    agent = _make_agent(bus)
    for fw, goal_key in (
        ("autogpt", "goal"),
        ("babyagi", "objective"),
        ("agentgpt", "goal"),
        ("opendevin", "goal"),
    ):
        task = Task(type="general", payload={"framework": fw, goal_key: "hello world"})
        result = await agent.handle(task)
        assert result.status == TaskStatus.SUCCESS, f"{fw}: {result.error}"
        assert result.output["framework"] == fw


@pytest.mark.asyncio
async def test_dispatch_crewai():
    bus = EventBus()
    agent = _make_agent(bus)
    task = Task(
        type="general",
        payload={
            "framework": "crewai",
            "crew": {
                "agents": [{"role": "dev", "goal": "code"}],
                "tasks": [{"description": "write hello", "agent_role": "dev"}],
                "process": "sequential",
            },
        },
    )
    result = await agent.handle(task)
    assert result.status == TaskStatus.SUCCESS, result.error
    assert result.output["result"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_dispatch_langgraph():
    bus = EventBus()
    agent = _make_agent(bus)
    task = Task(
        type="general",
        payload={
            "framework": "langgraph",
            "graph": {
                "entry": "n1",
                "nodes": ["n1", "n2"],
                "edges": {"n1": "n2"},
                "prompts": {"n1": "first", "n2": "second"},
                "steps": 4,
            },
        },
    )
    result = await agent.handle(task)
    assert result.status == TaskStatus.SUCCESS, result.error
    assert "n2" in result.output["result"]["state"]


@pytest.mark.asyncio
async def test_unsupported_framework_failed():
    bus = EventBus()
    agent = _make_agent(bus)
    task = Task(type="general", payload={"framework": "skynet", "goal": "x"})
    result = await agent.handle(task)
    assert result.status == TaskStatus.FAILED
    assert "unsupported" in result.error


@pytest.mark.asyncio
async def test_non_framework_task_falls_back_to_base():
    """payload 无 framework -> 默认 BaseAgent 逻辑。"""
    bus = EventBus()
    agent = _make_agent(bus)
    task = Task(type="general", payload={"q": "hi"})
    result = await agent.handle(task)
    assert result.status == TaskStatus.SUCCESS
    assert "model_response" in result.output


# ---------------------------------------------------------------------------
# 008-5: Harness + EventBus 全链路
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_harness_full_cycle_autogpt():
    bus = EventBus()
    _make_agent(bus, "full_a")
    harness = _make_harness(bus)

    task = Task(
        type="general",
        assignee="full_a",
        payload={"framework": "autogpt", "goal": "say hi"},
    )
    result = await harness.submit_and_wait(task, timeout=10.0)
    assert isinstance(result, TaskResult)
    assert result.status == TaskStatus.SUCCESS, result.error
    assert result.task_id == task.id
    assert result.output["framework"] == "autogpt"


@pytest.mark.asyncio
async def test_harness_full_cycle_crewai():
    bus = EventBus()
    _make_agent(bus, "full_crew")
    harness = _make_harness(bus)

    task = Task(
        type="general",
        assignee="full_crew",
        payload={
            "framework": "crewai",
            "crew": {
                "agents": [{"role": "writer", "goal": "write"}],
                "tasks": [{"description": "draft", "agent_role": "writer"}],
            },
        },
    )
    result = await harness.submit_and_wait(task, timeout=10.0)
    assert result.status == TaskStatus.SUCCESS, result.error
    assert result.output["framework"] == "crewai"
