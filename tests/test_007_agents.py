"""Tests for 007 agent frameworks."""

from __future__ import annotations

import pytest

from core.agentgpt_style import AgentGPTResult, BrowserGoalAgent
from core.agentic_loop import AgenticLoopState, AutoGPTAgent
from core.babyagi_loop import BabyAGILoopAgent, BabyAGIState
from core.crewai_style import AgentDef, CrewAIFlow, CrewDef, TaskDef
from core.langgraph_style import State, StateGraph
from core.opendevin_style import DeveloperAgent, DevTask


@pytest.fixture()
def dummy_deps():
    class DummyBus:
        def subscribe(self, *a, **kw):
            pass

        def publish(self, *a, **kw):
            pass

        def unsubscribe(self, *a, **kw):
            return False

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
        def get_context(self, *a, **kw):
            return {}

    return {
        "event_bus": DummyBus(),
        "router": DummyRouter(),
        "tool_registry": DummyTools(),
        "context": DummyContext(),
    }


def test_agentic_loop_state_default():
    state = AgenticLoopState(goal="test")
    assert state.goal == "test"
    assert state.current_step == 0
    assert state.phase.value == "planning"


def test_babyagi_state_default():
    state = BabyAGIState(objective="test")
    assert state.objective == "test"
    assert state.iteration == 0
    assert not state.done


def test_crewai_flow_run():
    crew = CrewDef(
        agents=[AgentDef(role="dev", goal="code")],
        tasks=[TaskDef(description="write hello", agent_role="dev")],
        process="sequential",
    )
    flow = CrewAIFlow(crew)
    results = flow.run()
    assert len(results) == 1
    assert results[0]["status"] == "completed"


def test_langgraph_run():
    graph = StateGraph()
    graph.add_node("start", lambda s: s)
    graph.add_edge("start", "end")
    graph.add_node("end", lambda s: s)
    graph.set_entry_point("start")
    state = graph.run(steps=5)
    assert isinstance(state, State)


def test_agentgpt_result_default():
    result = AgentGPTResult(goal="test")
    assert result.goal == "test"
    assert result.status == "pending"


def test_dev_task_default():
    task = DevTask(step="1", description="code")
    assert task.step == "1"
    assert task.status == "pending"


def test_autogpt_agent_init(dummy_deps):
    agent = AutoGPTAgent(agent_id="a1", role="general", **dummy_deps)
    assert agent.agent_id == "a1"


def test_babyagi_agent_init(dummy_deps):
    agent = BabyAGILoopAgent(agent_id="b1", role="general", **dummy_deps)
    assert agent.agent_id == "b1"


def test_browser_goal_agent_init(dummy_deps):
    agent = BrowserGoalAgent(agent_id="g1", role="general", **dummy_deps)
    assert agent.agent_id == "g1"


def test_developer_agent_init(dummy_deps):
    agent = DeveloperAgent(agent_id="d1", role="developer", **dummy_deps)
    assert agent.agent_id == "d1"
