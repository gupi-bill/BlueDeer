"""Tests for core.healer_circuit and core.healer_retry modules."""

from __future__ import annotations

import time

import pytest

from core.healer import CircuitBreaker, auto_heal


class TestCircuitBreaker:
    def test_closed_state_allows_calls(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state.value == "closed"

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1.0)

        def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cb.call(fail)
        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state.value == "open"

    def test_open_state_rejects_calls(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)

        def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state.value == "open"

        with pytest.raises(RuntimeError, match="熔断器已断开"):
            cb.call(lambda: "should not run")

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.5)

        def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state.value == "open"

        time.sleep(0.6)
        assert cb.state.value == "half_open"

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.5, half_open_max_retries=2)

        def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cb.call(fail)
        time.sleep(0.6)
        assert cb.state.value == "half_open"

        result = cb.call(lambda: "recovered")
        assert result == "recovered"
        assert cb.state.value == "half_open"

        result = cb.call(lambda: "recovered2")
        assert result == "recovered2"
        assert cb.state.value == "closed"

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.5)

        def fail():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            cb.call(fail)
        time.sleep(0.6)
        assert cb.state.value == "half_open"

        with pytest.raises(RuntimeError):
            cb.call(fail)
        assert cb.state.value == "open"


class TestAutoHeal:
    def test_success_on_first_try(self):
        call_count = 0

        @auto_heal(max_retries=2, base_delay=0.01)
        def stable():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert stable() == "ok"
        assert call_count == 1

    def test_retries_on_failure_then_succeeds(self):
        call_count = 0

        @auto_heal(max_retries=3, base_delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return "recovered"

        assert flaky() == "recovered"
        assert call_count == 3

    def test_raises_after_max_retries(self):
        call_count = 0

        @auto_heal(max_retries=2, base_delay=0.01)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise RuntimeError(f"fail {call_count}")

        with pytest.raises(RuntimeError, match="fail 3"):
            always_fails()
        assert call_count == 3

    def test_uses_circuit_breaker_when_provided(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=10.0)

        @auto_heal(max_retries=0, circuit_breaker=cb)
        def guarded():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            guarded()
        assert cb.state.value == "open"

        with pytest.raises(RuntimeError, match="熔断器已断开"):
            guarded()
