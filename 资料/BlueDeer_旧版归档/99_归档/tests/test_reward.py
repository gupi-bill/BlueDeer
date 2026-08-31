"""Tests for reward package."""

from __future__ import annotations

from core.reward import (
    AgentProfile,
    RewardSystem,
    compute_level,
    favor_gain,
    get_level_perks,
)
from core.task import TaskResult, TaskStatus


def test_compute_level():
    assert compute_level(0) == 1
    assert compute_level(200) == 2
    assert compute_level(2000) == 5
    assert compute_level(9000) == 10
    assert compute_level(38000) == 20


def test_favor_gain():
    assert favor_gain(100, 0) == 100
    assert favor_gain(100, 500) < 100
    assert favor_gain(100, 500) >= 1


def test_get_level_perks():
    perks = get_level_perks(5)
    assert "沙盘皮肤·银" in perks
    assert "低成本模型优先" in perks
    perks = get_level_perks(20)
    assert "核心骨干标识" in perks


def test_agent_profile_defaults():
    profile = AgentProfile(agent_id="test")
    assert profile.agent_id == "test"
    assert profile.level == 1
    assert profile.coins == 0
    assert profile.perks == []


def test_agent_profile_to_stats():
    profile = AgentProfile(agent_id="test")
    stats = profile.to_stats()
    assert "total_tasks" in stats
    assert "level" in stats


def test_reward_system_settle_success():
    system = RewardSystem()
    profile = system.settle(
        TaskResult(task_id="t1", status=TaskStatus.SUCCESS, output={"generated_code": "a\nb"}),
        agent_id="agent1",
    )
    assert profile.total_tasks == 1
    assert profile.success_count == 1
    assert profile.code_lines == 2


def test_reward_system_settle_failure():
    system = RewardSystem()
    profile = system.settle(
        TaskResult(task_id="t1", status=TaskStatus.FAILED),
        agent_id="agent1",
    )
    assert profile.total_tasks == 1
    assert profile.failed_count == 1


def test_reward_system_grant_role_bonus():
    system = RewardSystem()
    bonus = system.grant_role_bonus("squirrel", "code_fix")
    assert bonus == 5
    profile = system.get_profile("squirrel")
    assert profile.code_fix_count == 1


def test_reward_system_leaderboard():
    system = RewardSystem()
    system.settle(TaskResult(task_id="t1", status=TaskStatus.SUCCESS), agent_id="a1")
    system.settle(TaskResult(task_id="t2", status=TaskStatus.SUCCESS), agent_id="a2")
    board = system.leaderboard()
    assert len(board) == 2


def test_reward_system_save_load(tmp_path):
    system = RewardSystem()
    system.settle(TaskResult(task_id="t1", status=TaskStatus.SUCCESS), agent_id="a1")
    path = str(tmp_path / "reward.json")
    system.save(path)
    loaded = RewardSystem.load(path)
    assert loaded.get_profile("a1").total_tasks == 1
