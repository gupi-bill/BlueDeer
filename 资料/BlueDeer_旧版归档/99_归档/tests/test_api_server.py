"""Tests for core.api_server module."""

from __future__ import annotations

from core.api_server import (
    RateLimiter,
    _shutdown_event,
    graceful_shutdown,
    init_api,
    router,
)


class TestRateLimiter:
    def test_allows_requests_under_limit(self):
        limiter = RateLimiter(max_requests=2, window=60.0)
        assert limiter.check("k1")[0] is True
        assert limiter.check("k1")[0] is True
        assert limiter.check("k1")[0] is False


class TestGracefulShutdown:
    def test_shutdown_event_set(self):
        graceful_shutdown(drain_period=0.1)
        assert _shutdown_event.is_set() is True


class TestInitApi:
    def test_init_api_returns_router(self):
        from core.event_bus import EventBus

        bus = EventBus()
        result = init_api(bus)
        assert result is router
