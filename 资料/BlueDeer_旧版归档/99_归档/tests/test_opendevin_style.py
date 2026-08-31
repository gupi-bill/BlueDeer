"""Tests for core.opendevin_style module."""

from __future__ import annotations

import pytest

from core.opendevin_style import DeveloperAgent, DevTask


class TestDevTask:
    def test_create_dev_task(self):
        task = DevTask(step="1", description="write code")
        assert task.step == "1"
        assert task.description == "write code"
        assert task.status == "pending"
        assert task.result == ""

    def test_dev_task_defaults(self):
        task = DevTask(step="1", description="test")
        assert task.status == "pending"
        assert task.result == ""


class TestDeveloperAgent:
    @pytest.fixture
    def agent(self):
        return DeveloperAgent(
            agent_id="test-opendevin",
            role="developer",
            event_bus=None,
            router=None,
            tool_registry=None,
            context=None,
        )

    def test_init(self, agent):
        assert agent.agent_id == "test-opendevin"

    def test_needs_debug_with_error_keyword(self):
        agent = DeveloperAgent(
            agent_id="test",
            role="dev",
            event_bus=None,
            router=None,
            tool_registry=None,
            context=None,
        )
        assert agent._needs_debug("Error: something failed") is True

    def test_needs_debug_without_error_keyword(self):
        agent = DeveloperAgent(
            agent_id="test",
            role="dev",
            event_bus=None,
            router=None,
            tool_registry=None,
            context=None,
        )
        assert agent._needs_debug("All tests passed") is False
