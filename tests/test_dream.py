"""Tests for core.dream module."""

from __future__ import annotations

from core.dream import DreamSystem
from core.task import TaskResult, TaskStatus


class TestDreamSystem:
    def test_dream_generates_report(self):
        system = DreamSystem()
        results = [
            TaskResult(task_id="t1", status=TaskStatus.SUCCESS, output="ok"),
        ]
        report, _memories = system.dream(results)
        assert report.phase == "complete"
        assert report.memories_extracted >= 0

    def test_reports_history(self):
        system = DreamSystem()
        results = [
            TaskResult(task_id="t1", status=TaskStatus.SUCCESS, output="ok"),
            TaskResult(task_id="t2", status=TaskStatus.SUCCESS, output="ok"),
        ]
        report1, _ = system.dream(results[:1])
        report2, _ = system.dream(results[1:])
        assert report1.phase == "complete"
        assert report2.phase == "complete"
