"""Tests for core.agentgpt_style module."""

from __future__ import annotations

import pytest

from core.agentgpt_style import AgentGPTResult, BrowserGoalAgent


class TestAgentGPTResult:
    def test_create_result(self):
        result = AgentGPTResult()
        assert result.goal == ""
        assert result.tasks == []
        assert result.results == []
        assert result.status == "pending"
        assert result.error == ""

    def test_result_with_data(self):
        result = AgentGPTResult(goal="test", status="completed")
        assert result.goal == "test"
        assert result.status == "completed"


class TestBrowserGoalAgent:
    @pytest.fixture
    def agent(self):
        return BrowserGoalAgent(
            agent_id="test-agentgpt",
            role="general",
            event_bus=None,
            router=None,
            tool_registry=None,
            context=None,
        )

    def test_init(self, agent):
        assert agent.agent_id == "test-agentgpt"
