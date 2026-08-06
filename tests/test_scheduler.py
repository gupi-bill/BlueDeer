"""Tests for core.scheduler module."""

from __future__ import annotations

from core.scheduler import JobDef, Scheduler


class TestJobDef:
    def test_create_job_def(self):
        job = JobDef(id="job1", cron="0 * * * *", task_type="cleanup")
        assert job.id == "job1"
        assert job.cron == "0 * * * *"
        assert job.task_type == "cleanup"
        assert job.enabled is True

    def test_job_def_defaults(self):
        job = JobDef(id="job1")
        assert job.cron == ""
        assert job.interval_seconds == 0
        assert job.task_type == "general"
        assert job.enabled is True


class TestSchedulerMatchField:
    def test_match_wildcard(self):
        assert Scheduler._match_field("*", 5) is True

    def test_match_exact(self):
        assert Scheduler._match_field("5", 5) is True
        assert Scheduler._match_field("3", 5) is False

    def test_match_range(self):
        assert Scheduler._match_field("1-5", 3) is True
        assert Scheduler._match_field("1-5", 6) is False

    def test_match_step(self):
        assert Scheduler._match_field("*/5", 0) is True
        assert Scheduler._match_field("*/5", 5) is True
        assert Scheduler._match_field("*/5", 3) is False

    def test_match_step_with_base(self):
        assert Scheduler._match_field("1-10/2", 1) is True
        assert Scheduler._match_field("1-10/2", 3) is True
        assert Scheduler._match_field("1-10/2", 11) is False

    def test_match_list(self):
        assert Scheduler._match_field("1,3,5", 3) is True
        assert Scheduler._match_field("1,3,5", 4) is False
