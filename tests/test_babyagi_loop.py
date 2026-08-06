"""Tests for core.babyagi_loop module."""

from __future__ import annotations

import pytest

from core.babyagi_loop import BabyAGILoopAgent, BabyAGIState


class TestBabyAGIState:
    def test_default_state(self):
        state = BabyAGIState()
        assert state.objective == ""
        assert state.completed == []
        assert state.pending == []
        assert state.iteration == 0
        assert state.max_iterations == 10
        assert state.done is False
        assert state.stop_reason == ""


class TestBabyAGILoopAgent:
    @pytest.fixture
    def agent(self):
        return BabyAGILoopAgent(
            agent_id="test-babyagi",
            role="general",
            event_bus=None,
            router=None,
            tool_registry=None,
            context=None,
        )

    def test_init(self, agent):
        assert agent.agent_id == "test-babyagi"
        assert agent.max_iterations == 10
