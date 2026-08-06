"""Tests for core.crewai_style module."""

from __future__ import annotations

from core.crewai_style import AgentDef, CrewAIFlow, CrewDef, TaskDef


class TestAgentDef:
    def test_create_agent_def(self):
        agent = AgentDef(role="coder", goal="write code")
        assert agent.role == "coder"
        assert agent.goal == "write code"
        assert agent.backstory == ""
        assert agent.tools == []

    def test_agent_def_with_tools(self):
        agent = AgentDef(role="coder", goal="write code", tools=["python", "git"])
        assert agent.tools == ["python", "git"]


class TestTaskDef:
    def test_create_task_def(self):
        task = TaskDef(description="write tests", agent_role="tester")
        assert task.description == "write tests"
        assert task.agent_role == "tester"
        assert task.expected_output == ""


class TestCrewDef:
    def test_create_crew_def(self):
        crew = CrewDef(
            agents=[AgentDef(role="coder", goal="code")],
            tasks=[TaskDef(description="code", agent_role="coder")],
        )
        assert len(crew.agents) == 1
        assert len(crew.tasks) == 1
        assert crew.process == "sequential"


class TestCrewAIFlow:
    def test_run_sequential(self):
        crew = CrewDef(
            agents=[AgentDef(role="coder", goal="code")],
            tasks=[TaskDef(description="code", agent_role="coder")],
        )
        flow = CrewAIFlow(crew)
        results = flow.run()
        assert len(results) == 1
        assert results[0]["status"] == "completed"
