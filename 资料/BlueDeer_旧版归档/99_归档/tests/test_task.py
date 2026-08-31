"""P0: Task 状态机与序列化。"""

from __future__ import annotations

import pytest

from core.task import Task, TaskResult, TaskStatus, TokenUsage

pytestmark = pytest.mark.p0


def test_task_default_state():
    t = Task(type="code", payload={"lang": "python"})
    assert t.status == TaskStatus.PENDING
    assert t.id
    assert t.created_at > 0


def test_task_status_transition_valid():
    t = Task()
    t.status = TaskStatus.RUNNING
    assert t.status == TaskStatus.RUNNING
    t.status = TaskStatus.COMPLETED
    assert t.status == TaskStatus.COMPLETED


def test_task_priority_and_assignee():
    t = Task(assignee="squirrel", priority=5)
    assert t.assignee == "squirrel"
    assert t.priority == 5


def test_task_to_dict_from_dict_roundtrip():
    t = Task(type="code", payload={"lang": "rust"}, assignee="fox", priority=3)
    d = t.to_dict()
    t2 = Task.from_dict(d)
    assert t2.id == t.id
    assert t2.type == t.type
    assert t2.payload == t.payload
    assert t2.assignee == t.assignee
    assert t2.priority == t.priority
    assert t2.status == t.status


def test_task_result_fields():
    r = TaskResult(task_id="t1", status=TaskStatus.FAILED, error="timeout")
    assert r.task_id == "t1"
    assert r.status == TaskStatus.FAILED
    assert r.error == "timeout"
    assert r.token_usage.total == 0


def test_token_usage_total():
    tu = TokenUsage(tokens_in=100, tokens_out=50)
    assert tu.total == 150
