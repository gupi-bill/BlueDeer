"""Tests for core.task_orchestrator module."""

from __future__ import annotations

import asyncio

import pytest

from core.exceptions import TaskDependencyError, TaskTimeoutError
from core.task_orchestrator import TaskNode, TaskOrchestrator


class TestTaskNode:
    def test_create_node(self):
        node = TaskNode("test", lambda: "result")
        assert node.name == "test"
        assert node.deps == []
        assert node.state == "pending"

    def test_create_node_with_deps(self):
        node = TaskNode("test", lambda: "result", deps=["dep1"])
        assert node.deps == ["dep1"]


class TestTaskOrchestrator:
    def test_create_orchestrator(self):
        orch = TaskOrchestrator(max_workers=2)
        assert orch._max_workers == 2
        assert orch._tasks == {}

    def test_add_task(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("task1", lambda: "result1")
        assert "task1" in orch._tasks

    def test_add_duplicate_task_raises(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("task1", lambda: "result1")
        with pytest.raises(ValueError, match="任务已存在"):
            orch.add_task("task1", lambda: "result2")

    def test_run_simple_tasks(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("task1", lambda: "result1")
        orch.add_task("task2", lambda: "result2")
        results = orch.run(timeout=10.0)
        assert "task1" in results
        assert "task2" in results

    def test_run_with_deps(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("task1", lambda: "result1")
        orch.add_task("task2", lambda x: f"result2-{x}", deps=["task1"])
        results = orch.run(timeout=10.0)
        assert "task1" in results
        assert "task2" in results

    def test_circular_dependency_raises(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("a", lambda: "a", deps=["b"])
        orch.add_task("b", lambda: "b", deps=["a"])
        with pytest.raises(TaskDependencyError):
            orch.run(timeout=10.0)

    def test_task_status(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("task1", lambda: "result1")
        status = orch.task_status("task1")
        assert status is not None
        assert status["name"] == "task1"

    def test_get_result_not_found(self):
        orch = TaskOrchestrator(max_workers=2)
        with pytest.raises(KeyError):
            orch.get_result("nonexistent")


class TestAsyncOrchestrator:
    @pytest.mark.asyncio
    async def test_run_async_simple_tasks(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("task1", lambda: "result1")
        orch.add_task("task2", lambda: "result2")
        results = await orch.run_async(timeout=10.0)
        assert "task1" in results
        assert "task2" in results

    @pytest.mark.asyncio
    async def test_run_async_async_funcs(self):
        orch = TaskOrchestrator(max_workers=2)

        async def afetch():
            await asyncio.sleep(0.01)
            return "async-a"

        orch.add_task("a", afetch)
        orch.add_task("b", lambda x: f"{x}-b", deps=["a"])
        results = await orch.run_async(timeout=10.0)
        assert results["a"] == "async-a"
        assert results["b"] == "async-a-b"

    @pytest.mark.asyncio
    async def test_run_async_deps(self):
        orch = TaskOrchestrator(max_workers=2)
        orch.add_task("task1", lambda: "result1")
        orch.add_task("task2", lambda x: f"result2-{x}", deps=["task1"])
        results = await orch.run_async(timeout=10.0)
        assert "task1" in results
        assert "task2" in results
        assert results["task2"] == "result2-result1"

    @pytest.mark.asyncio
    async def test_run_async_timeout_cancels(self):
        orch = TaskOrchestrator(max_workers=2)

        async def slow():
            await asyncio.sleep(1.0)
            return "late"

        orch.add_task("slow", slow)
        with pytest.raises(TaskTimeoutError):
            await orch.run_async(timeout=0.05)

        assert orch.task_status("slow")["state"] in ("pending", "cancelled")

    def test_run_within_loop_raises(self):
        async def inner():
            orch = TaskOrchestrator(max_workers=2)
            orch.add_task("t", lambda: 1)
            with pytest.raises(RuntimeError, match="run_async"):
                orch.run(timeout=5.0)

        asyncio.run(inner())

    @pytest.mark.asyncio
    async def test_run_async_failed_task_state(self):
        orch = TaskOrchestrator(max_workers=2)

        def boom():
            raise ValueError("boom")

        def ok():
            return "ok"

        orch.add_task("a", boom)
        orch.add_task("b", ok)
        results = await orch.run_async(timeout=10.0)
        # b 成功，a 失败（异常在收集中记录，results 只含成功的）
        assert orch.task_status("a")["state"] == "failed"
        assert results["b"] == "ok"
