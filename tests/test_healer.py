"""Tests for core.healer module."""

from __future__ import annotations

import os
import tempfile

from core.healer import FixStrategy, Healer, TestFailure


class TestHealer:
    def test_analyze_deadlock(self):
        healer = Healer()
        failures = [TestFailure(error_type="DeadlockError")]
        plans = healer.analyze(failures)
        assert plans[0][1] == FixStrategy.FIX_DEADLOCK

    def test_analyze_timeout(self):
        healer = Healer()
        failures = [TestFailure(error_type="TimeoutError")]
        plans = healer.analyze(failures)
        assert plans[0][1] == FixStrategy.FIX_TIMEOUT

    def test_apply_fix_deadlock(self):
        healer = Healer()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("lock.acquire()\n")
            path = f.name
        try:
            record = healer.apply_fix(
                TestFailure(error_type="DeadlockError"),
                FixStrategy.FIX_DEADLOCK,
                path,
            )
            assert record.applied is True
        finally:
            os.unlink(path)
