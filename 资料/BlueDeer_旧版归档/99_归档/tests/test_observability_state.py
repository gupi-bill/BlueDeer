"""Observability 单测。"""

from __future__ import annotations

from core.observability import Observability


def test_observability_setup_returns_instance() -> None:
    obs = Observability.setup("test-service")
    assert obs is not None


def test_observability_span_noop() -> None:
    obs = Observability.setup("test-service")
    span = obs.span("test-span", key="value")
    assert span is not None


def test_observability_counter_noop() -> None:
    obs = Observability.setup("test-service")
    counter = obs.counter("test-counter", "desc")
    assert counter is not None


def test_observability_shutdown() -> None:
    obs = Observability.setup("test-service")
    obs.shutdown()
    assert not Observability.is_enabled()
