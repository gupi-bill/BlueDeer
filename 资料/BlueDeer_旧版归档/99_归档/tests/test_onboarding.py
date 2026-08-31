"""P0: Onboarding 新手引导五阶段流转 + 奖励发放。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.digital_life.onboarding import (
    ONBOARDING_REWARD_MARKS,
    STAGE_DONE,
    STAGE_FIRST_INTERACT,
    STAGE_FIRST_TASK,
    STAGE_FREE_EXPLORE,
    STAGE_MEET_TEAM,
    STAGE_ORDER,
    STAGE_WELCOME,
    OnboardingManager,
)

pytestmark = pytest.mark.p0


def _make_bio(marks: float = 0.0):
    return SimpleNamespace(env=SimpleNamespace(marks=marks))


def test_stage_order_is_linear(isolated_data):
    assert STAGE_ORDER == [
        STAGE_WELCOME,
        STAGE_MEET_TEAM,
        STAGE_FIRST_INTERACT,
        STAGE_FIRST_TASK,
        STAGE_FREE_EXPLORE,
        STAGE_DONE,
    ]


def test_start_resets_to_welcome(isolated_data):
    m = OnboardingManager()
    m.set_stage(STAGE_DONE)
    status = m.start()
    assert status["current_stage"] == STAGE_WELCOME
    assert status["completed"] is False
    assert status["skipped"] is False


def test_full_progression_to_done(isolated_data):
    m = OnboardingManager()
    m.start()
    for i in range(1, len(STAGE_ORDER)):
        status = m.next_stage()
        assert status["current_stage"] == STAGE_ORDER[i]
    assert m.get_status()["completed"] is True


def test_skip_marks_completed_without_reward(isolated_data):
    bio = _make_bio()
    m = OnboardingManager()
    m.set_biosphere(bio)
    status = m.skip()
    assert status["completed"] is True
    assert status["skipped"] is True
    assert bio.env.marks == 0.0


def test_grant_reward_on_completion(isolated_data):
    bio = _make_bio()
    m = OnboardingManager()
    m.set_biosphere(bio)
    m.start()
    for _ in range(len(STAGE_ORDER) - 1):
        m.next_stage()
    assert bio.env.marks == ONBOARDING_REWARD_MARKS


def test_set_stage_done_grants_reward(isolated_data):
    bio = _make_bio()
    m = OnboardingManager()
    m.set_biosphere(bio)
    m.set_stage(STAGE_DONE)
    assert bio.env.marks == ONBOARDING_REWARD_MARKS


def test_no_double_reward_on_repeat_done(isolated_data):
    """回归：next_stage 与 set_stage(done) 均触发领奖，重复调用不得双倍。"""
    bio = _make_bio()
    m = OnboardingManager()
    m.set_biosphere(bio)
    m.next_stage()  # welcome -> meet_team
    m.set_stage(STAGE_DONE)
    m.set_stage(STAGE_DONE)  # 再次设置 done
    m.next_stage()  # done 之后 next_stage 不应再触发
    assert bio.env.marks == ONBOARDING_REWARD_MARKS


def test_status_shape(isolated_data):
    m = OnboardingManager()
    status = m.get_status()
    for key in ("current_stage", "completed", "skipped"):
        assert key in status
    assert status["current_stage"] in STAGE_ORDER
