import asyncio
from unittest.mock import AsyncMock

import pytest

from core.agentic_loop import AgenticLoopState, AutoGPTAgent, LoopPhase
from core.task import TaskResult, TaskStatus, TokenUsage


@pytest.fixture
def agent():
    return AutoGPTAgent(
        agent_id="test-autogpt",
        role="general",
        event_bus=None,
        router=None,
        tool_registry=None,
        context=None,
        max_steps=3,
    )


class TestAgenticLoopState:
    def test_default_state(self):
        state = AgenticLoopState(goal="")
        assert state.goal == ""
        assert state.current_step == 0
        assert state.max_steps == 20
        assert state.completed_tasks == []
        assert state.pending_tasks == []
        assert state.observations == []
        assert state.phase == LoopPhase.PLANNING
        assert state.stop_reason == ""
        assert state.total_tokens_in == 0
        assert state.total_tokens_out == 0

    def test_with_args(self):
        state = AgenticLoopState(goal="写测试", max_steps=5)
        assert state.goal == "写测试"
        assert state.max_steps == 5


class TestParseHelpers:
    def test_parse_tasks_standard(self, agent):
        tasks = agent._parse_tasks_from_response("1. 做A\n2. 做B")
        assert len(tasks) == 2
        assert tasks[0] == {"description": "做A", "result": None}
        assert tasks[1] == {"description": "做B", "result": None}

    def test_parse_tasks_skips_junk_lines(self, agent):
        tasks = agent._parse_tasks_from_response("前言\n\n3. 有效任务\n不是任务行\n")
        assert len(tasks) == 1
        assert tasks[0]["description"] == "有效任务"

    def test_parse_tasks_no_separator_skipped(self, agent):
        tasks = agent._parse_tasks_from_response("1.描述无空格")
        assert tasks == []

    def test_parse_execution_result_with_marker(self, agent):
        parsed = agent._parse_execution_result("结果【完成】")
        assert parsed == "结果 [已完成]"

    def test_parse_execution_result_plain(self, agent):
        parsed = agent._parse_execution_result("  普通结果  ")
        assert parsed == "普通结果"

    def test_should_stop_keyword_done(self, agent):
        state = AgenticLoopState(goal="g", max_steps=5)
        state.current_step = 1
        assert agent._should_stop(state, "任务已完成") is True

    def test_should_stop_max_steps(self, agent):
        state = AgenticLoopState(goal="g", max_steps=5)
        state.current_step = 5
        assert agent._should_stop(state, "还在干") is True
        assert "达到最大步数限制" in state.stop_reason

    def test_should_stop_false(self, agent):
        state = AgenticLoopState(goal="g", max_steps=5)
        state.current_step = 1
        assert agent._should_stop(state, "继续执行") is False


class TestAutoGPTAgent:
    def test_init(self, agent):
        assert agent.agent_id == "test-autogpt"
        assert agent._max_steps == 3
        assert agent._tool_descriptions == "无可用工具"

    def test_run_autonomous_success(self, agent):
        call_side_effects = [
            {"content": "1. 子任务A\n2. 子任务B", "tokens_in": 10, "tokens_out": 5},
            {"content": "任务完成", "tokens_in": 3, "tokens_out": 2},
        ]
        agent._call_model = AsyncMock(side_effect=call_side_effects)
        agent._execute_via_bus = AsyncMock(
            return_value=TaskResult(
                task_id="exec-1",
                status=TaskStatus.SUCCESS,
                output={"model_response": "搞定A"},
                token_usage=TokenUsage(tokens_in=2, tokens_out=1),
            )
        )
        result = asyncio.run(agent.run_autonomous("测试目标"))
        assert result.status == TaskStatus.SUCCESS
        assert result.output["goal"] == "测试目标"
        assert result.output["steps_executed"] >= 1
        assert len(result.output["completed_tasks"]) >= 1
        assert result.output["total_tokens_in"] > 0

    def test_run_autonomous_planning_fails(self, agent):
        agent._call_model = AsyncMock(
            return_value={"content": "", "tokens_in": 0, "tokens_out": 0}
        )
        result = asyncio.run(agent.run_autonomous("无法分解"))
        assert result.output["status"] == "failed"
        assert result.output["stop_reason"] == "无法分解目标为可执行任务"

    def test_run_autonomous_model_error(self, agent):
        agent._call_model = AsyncMock(
            return_value={
                "content": "[错误] 模型调用失败: boom",
                "tokens_in": 0,
                "tokens_out": 0,
            }
        )
        result = asyncio.run(agent.run_autonomous("模型挂了"))
        assert result.output["status"] == "failed"

    def test_max_steps_enforced(self, agent):
        agent._call_model = AsyncMock(
            side_effect=[
                {"content": "1. 子任务A", "tokens_in": 5, "tokens_out": 2},
                {"content": "继续\n1. 再来", "tokens_in": 5, "tokens_out": 2},
            ]
        )
        agent._execute_via_bus = AsyncMock(
            return_value=TaskResult(
                task_id="exec-1",
                status=TaskStatus.SUCCESS,
                output={"model_response": "结果"},
                token_usage=TokenUsage(tokens_in=1, tokens_out=1),
            )
        )
        result = asyncio.run(agent.run_autonomous("目标", max_steps=1))
        assert result.output["steps_executed"] <= 1
