"""Tests for 007 agent frameworks."""

from __future__ import annotations

import pytest

from core.agentgpt_style import AgentGPTResult, BrowserGoalAgent
from core.agentic_loop import AgenticLoopState, AutoGPTAgent, LoopPhase
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


def test_agentic_loop_state_transition():
    state = AgenticLoopState(goal="test")
    state.phase = LoopPhase.EXECUTING
    assert state.phase.value == "executing"


def test_babyagi_state_default():
    state = BabyAGIState(objective="test")
    assert state.objective == "test"
    assert state.iteration == 0
    assert not state.done


def test_babyagi_state_done():
    state = BabyAGIState(objective="test")
    state.done = True
    state.stop_reason = "completed"
    assert state.done
    assert state.stop_reason == "completed"


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


def test_crewai_flow_multiple_tasks():
    crew = CrewDef(
        agents=[
            AgentDef(role="dev", goal="code"),
            AgentDef(role="tester", goal="test"),
        ],
        tasks=[
            TaskDef(description="write code", agent_role="dev"),
            TaskDef(description="run tests", agent_role="tester"),
        ],
        process="sequential",
    )
    flow = CrewAIFlow(crew)
    results = flow.run()
    assert len(results) == 2


def test_langgraph_run():
    graph = StateGraph()
    graph.add_node("start", lambda s: s)
    graph.add_edge("start", "end")
    graph.add_node("end", lambda s: s)
    graph.set_entry_point("start")
    state = graph.run(steps=5)
    assert isinstance(state, State)


def test_langgraph_checkpoint(tmp_path):
    path = str(tmp_path / "checkpoint.json")
    graph = StateGraph(checkpoint_path=path)
    graph.add_node("start", lambda s: s)
    graph.set_entry_point("start")
    _state = graph.run(steps=1)
    snap = graph.checkpoint()
    assert "state" in snap
    assert "checkpoints" in snap


def test_langgraph_state_get_set():
    state = State()
    state.set("key", "value")
    assert state.get("key") == "value"
    assert state.get("missing", "default") == "default"


def test_agentgpt_result_default():
    result = AgentGPTResult(goal="test")
    assert result.goal == "test"
    assert result.status == "pending"


def test_agentgpt_result_completed():
    result = AgentGPTResult(goal="test", status="completed")
    assert result.status == "completed"


def test_dev_task_default():
    task = DevTask(step="1", description="code")
    assert task.step == "1"
    assert task.status == "pending"


def test_dev_task_completed():
    task = DevTask(step="1", description="code", status="completed")
    assert task.status == "completed"


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


def test_autogpt_state_phases():
    for phase in LoopPhase:
        assert isinstance(phase.value, str)


def test_crewai_flow_empty():
    crew = CrewDef(agents=[], tasks=[], process="sequential")
    flow = CrewAIFlow(crew)
    results = flow.run()
    assert results == []


def test_state_graph_conditional():
    graph = StateGraph()
    graph.add_node("start", lambda s: s)
    graph.add_node("end", lambda s: s)

    def router(state: State) -> str:
        return "end"

    graph.add_conditional_edge("start", router)
    graph.set_entry_point("start")
    state = graph.run(steps=3)
    assert isinstance(state, State)
