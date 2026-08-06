"""P0: 统一配置中心（schema + env 覆盖 + 热重载）。"""

from __future__ import annotations

import pytest

from core.config import AppConfig, Environment, get_config, set_config

pytestmark = pytest.mark.p0


def test_defaults():
    cfg = AppConfig()
    assert cfg.environment == Environment.LOCAL
    assert cfg.task.timeout_seconds > 0
    assert cfg.model.default_model != ""


def test_get_nested_path():
    cfg = AppConfig()
    assert cfg.get("model.default_model") == cfg.model.default_model
    assert cfg.get("nope.missing", "fallback") == "fallback"


def test_apply_env_override(monkeypatch):
    monkeypatch.setenv("BLUEDEER_ENV", "cloud")
    monkeypatch.setenv("TASK_TIMEOUT_SECONDS", "42")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    cfg = AppConfig.from_env()
    assert cfg.environment == Environment.CLOUD
    assert cfg.task.timeout_seconds == 42
    assert cfg.log.level == "DEBUG"


def test_apply_env_ignores_bad_cast(monkeypatch):
    monkeypatch.setenv("TASK_TIMEOUT_SECONDS", "not-a-number")
    cfg = AppConfig.from_env()
    assert cfg.task.timeout_seconds > 0  # 原值保留


def test_validate_catches_bad_values():
    cfg = AppConfig()
    cfg.task.timeout_seconds = 0
    cfg.model.fail_threshold = 0
    errors = cfg.validate()
    assert any("timeout" in e for e in errors)
    assert any("threshold" in e for e in errors)


def test_get_config_singleton():
    a = get_config()
    b = get_config()
    assert a is b


def test_set_config_roundtrip():
    cfg = AppConfig()
    cfg.use_real_api = True
    set_config(cfg)
    assert get_config().use_real_api is True
