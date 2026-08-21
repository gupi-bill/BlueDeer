"""006-29: Ollama retry jitter —— compute_backoff_delay 与 request_with_retry 测试。"""

import logging

logger = logging.getLogger(__name__)
import asyncio
from unittest import mock

import pytest
from typing_extensions import Self

from core.config import AppConfig
from core.retry import RetryManager, compute_backoff_delay
from models.client import request_with_retry


def test_compute_backoff_delay_no_jitter() -> None:
    assert compute_backoff_delay(1, 2.0, 120.0, jitter=False) == 2.0
    assert compute_backoff_delay(2, 2.0, 120.0, jitter=False) == 4.0
    assert compute_backoff_delay(3, 2.0, 120.0, jitter=False) == 8.0


def test_compute_backoff_delay_jitter_ranges() -> None:
    with mock.patch("core.retry.random.random", return_value=0.0):
        assert compute_backoff_delay(1, 2.0, 120.0, jitter=True) == 2.0 * 0.5
    with mock.patch("core.retry.random.random", return_value=1.0):
        assert compute_backoff_delay(1, 2.0, 120.0, jitter=True) == 2.0 * 1.5


def test_compute_backoff_delay_capped() -> None:
    assert compute_backoff_delay(10, 2.0, 5.0, jitter=False) == 5.0
    assert compute_backoff_delay(4, 100.0, 10.0, jitter=False) == 10.0


def test_retry_manager_uses_new_function() -> None:
    cfg = AppConfig().task
    with mock.patch("core.retry.random.random", return_value=0.7):
        got = RetryManager._compute_delay(2, cfg)
        expected = compute_backoff_delay(
            2, cfg.retry_base_delay, cfg.retry_max_delay, cfg.retry_jitter
        )
        assert got == expected


class _FakeResp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_request_with_retry_sleeps_backoff() -> None:
    cfg = AppConfig().task
    calls = {"n": 0}

    def fake_urlopen(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("boom")
        return _FakeResp(b'{"ok": true}')

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), mock.patch(
        "asyncio.sleep", side_effect=fake_sleep
    ), mock.patch("core.retry.random.random", return_value=0.7):
                result = asyncio.run(
                    request_with_retry("GET", "http://x/", retries=3, timeout=5)
                )
                expected = [
                    compute_backoff_delay(
                        1, cfg.retry_base_delay, cfg.retry_max_delay, cfg.retry_jitter
                    ),
                    compute_backoff_delay(
                        2, cfg.retry_base_delay, cfg.retry_max_delay, cfg.retry_jitter
                    ),
                ]

    assert result == {"ok": True}
    assert calls["n"] == 3
    assert len(sleeps) == 2
    assert sleeps == expected


def test_request_with_retry_exhausted_raises() -> None:
    def fake_urlopen(req, timeout):
        raise OSError("always down")

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), mock.patch(
        "asyncio.sleep", side_effect=lambda s: None
    ), pytest.raises(RuntimeError, match="请求重试耗尽"):
                asyncio.run(
                    request_with_retry("GET", "http://x/", retries=2, timeout=5)
                )


def test_request_with_retry_success_first_try() -> None:
    sleeps: list[float] = []

    def fake_urlopen(req, timeout):
        return _FakeResp(b'{"ok": true}')

    with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen), mock.patch(
        "asyncio.sleep", side_effect=lambda s: sleeps.append(s)
    ):
            result = asyncio.run(
                request_with_retry("GET", "http://x/", retries=3, timeout=5)
            )

    assert result == {"ok": True}
    assert sleeps == []
