"""BaseAgent 子类化单测。"""

from __future__ import annotations

from typing import ClassVar

from core.base_agent import BaseAgent


class ConcreteAgent(BaseAgent):
    def _build_prompt(self, task: ConcreteTask) -> str:
        return "concrete"

    def _self_check(self, task: ConcreteTask, output: dict) -> None:
        return None


class ConcreteTask:
    id = "task-1"
    trace_id = "trace-1"
    type = "test"
    payload: ClassVar[dict] = {}


def test_subclass_instantiation() -> None:
    agent = ConcreteAgent(
        agent_id="agent-1",
        role="test",
        event_bus=None,
        router=None,
        tool_registry=None,
        context=None,
    )
    assert agent.agent_id == "agent-1"
    assert agent.role == "test"


def test_subclass_build_prompt() -> None:
    agent = ConcreteAgent(
        agent_id="agent-1",
        role="test",
        event_bus=None,
        router=None,
        tool_registry=None,
        context=None,
    )
    task = ConcreteTask()
    prompt = agent._build_prompt(task)
    assert prompt == "concrete"


def test_subclass_self_check_passes() -> None:
    agent = ConcreteAgent(
        agent_id="agent-1",
        role="test",
        event_bus=None,
        router=None,
        tool_registry=None,
        context=None,
    )
    task = ConcreteTask()
    agent._self_check(task, {"ok": True})


def test_subclass_state_created() -> None:
    agent = ConcreteAgent(
        agent_id="agent-1",
        role="test",
        event_bus=None,
        router=None,
        tool_registry=None,
        context=None,
    )
    assert agent.get_status().value == "created"
