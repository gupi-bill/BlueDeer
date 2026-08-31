"""SessionStore / GuardrailConfig / TokenBudget P0 测试。"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import time

import pytest

from core.guardrail_config import (
    GuardrailConfig,
    GuardrailEngine,
    GuardrailTripwire,
    GuardrailViolationType,
)
from core.session_store import Session, SessionMessage, SessionStore
from core.token_budget import AgentBudget, TokenBudget, TokenRecord


def _run(coro):
    return asyncio.run(coro)


# ==================== SessionStore ====================


class TestSessionStore:
    """SQLite-backed 会话持久化测试。"""

    def test_create_and_get_session(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        sess = _run(store.create_session("s1", "deer-001", metadata={"key": "val"}))
        assert sess is not None
        assert sess.agent_id == "deer-001"
        assert sess.metadata == {"key": "val"}
        assert sess.message_count == 0

        fetched = _run(store.get_session("s1"))
        assert fetched is not None
        assert fetched.session_id == "s1"

    def test_append_and_get_history(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001"))
        _run(store.append_message("s1", "user", "hello"))
        _run(store.append_message("s1", "assistant", "hi there"))

        history = _run(store.get_history("s1"))
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[0].content == "hello"
        assert history[1].role == "assistant"
        assert history[1].content == "hi there"

    def test_get_recent(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001"))
        for i in range(5):
            _run(store.append_message("s1", "user", f"msg{i}"))

        recent = _run(store.get_recent("s1", n=3))
        assert len(recent) == 3
        assert recent[0].content == "msg2"
        assert recent[-1].content == "msg4"

    def test_clear_session(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001"))
        _run(store.append_message("s1", "user", "hello"))
        assert _run(store.get_history("s1")) != []

        result = _run(store.clear_session("s1"))
        assert result is True
        assert _run(store.get_history("s1")) == []

    def test_delete_session(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001"))

        result = _run(store.delete_session("s1"))
        assert result is True
        assert _run(store.get_session("s1")) is None

    def test_list_sessions(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001"))
        _run(store.create_session("s2", "fox-001"))
        _run(store.create_session("s3", "hare-001"))

        all_sessions = _run(store.list_sessions())
        assert len(all_sessions) == 3

        deer_sessions = _run(store.list_sessions(agent_id="deer-001"))
        assert len(deer_sessions) == 1
        assert deer_sessions[0].agent_id == "deer-001"

    def test_session_exists(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001"))
        assert _run(store.session_exists("s1")) is True
        assert _run(store.session_exists("missing")) is False

    def test_update_metadata(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001", metadata={"a": 1}))
        updated = _run(store.update_metadata("s1", {"b": 2}))
        assert updated is not None
        assert updated.metadata == {"a": 1, "b": 2}

    def test_thread_safety(self, tmp_path):
        db = tmp_path / "sessions.db"
        store = SessionStore(f"sqlite:///{db}")
        _run(store.create_session("s1", "deer-001"))

        errors = []

        def writer():
            for i in range(20):
                try:
                    _run(store.append_message("s1", "user", f"msg{i}"))
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        history = _run(store.get_history("s1"))
        assert len(history) == 80


# ==================== GuardrailConfig ====================


class TestGuardrailConfig:
    """声明式护栏配置测试。"""

    def test_from_dict_input_rules(self):
        data = {
            "input": [
                {"id": "inj-1", "type": "injection", "enabled": True, "config": {"patterns": ["<script>"]}},
                {"id": "sens-1", "type": "sensitive", "enabled": False, "config": {"keywords": ["secret"]}},
            ]
        }
        cfg = GuardrailConfig.from_dict(data)
        assert len(cfg.input_rules) == 2
        assert cfg.input_rules[0].rule_id == "inj-1"
        assert cfg.input_rules[0].type == "injection"
        assert cfg.input_rules[0].enabled is True
        assert cfg.input_rules[1].enabled is False

    def test_from_dict_output_rules(self):
        data = {
            "output": [
                {"id": "len-1", "type": "length", "enabled": True, "config": {"max_chars": 500}}
            ]
        }
        cfg = GuardrailConfig.from_dict(data)
        assert len(cfg.output_rules) == 1
        assert cfg.output_rules[0].rule_id == "len-1"

    def test_to_dict_roundtrip(self):
        data = {
            "input": [{"id": "r1", "type": "injection", "config": {"patterns": ["foo"]}}],
            "output": [{"id": "r2", "type": "length", "config": {"max_chars": 100}}],
            "global": {"strict_mode": True},
        }
        cfg = GuardrailConfig.from_dict(data)
        result = cfg.to_dict()
        assert result["input"][0]["id"] == "r1"
        assert result["output"][0]["id"] == "r2"
        assert result["global"] == {"strict_mode": True}

    def test_from_file_json(self, tmp_path):
        config_file = tmp_path / "guardrails.json"
        config_file.write_text(
            json.dumps({
                "input": [{"id": "inj-1", "type": "injection", "config": {"patterns": ["<script>"]}}],
                "output": [],
            })
        )
        cfg = GuardrailConfig.from_file(str(config_file))
        assert len(cfg.input_rules) == 1
        assert cfg.input_rules[0].rule_id == "inj-1"

    def test_from_file_yaml(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        config_file = tmp_path / "guardrails.yaml"
        config_file.write_text(
            "input:\n  - id: inj-1\n    type: injection\n    config:\n      patterns: ['<script>']\n"
        )
        cfg = GuardrailConfig.from_file(str(config_file))
        assert len(cfg.input_rules) == 1

    def test_from_file_unsupported_format(self, tmp_path):
        config_file = tmp_path / "guardrails.toml"
        config_file.write_text("")
        with pytest.raises(ValueError, match="不支持的护栏配置文件格式"):
            GuardrailConfig.from_file(str(config_file))


class TestGuardrailEngine:
    """护栏执行引擎测试。"""

    def test_input_injection_detected(self):
        cfg = GuardrailConfig.from_dict({
            "input": [{"id": "inj", "type": "injection", "config": {"patterns": ["<script>"]}}],
            "output": [],
        })
        engine = GuardrailEngine(cfg)
        with pytest.raises(GuardrailTripwire) as exc_info:
            _run(engine.check_input("deer-001", {"query": "<script>alert(1)</script>"}))
        assert exc_info.value.violation_type == GuardrailViolationType.INPUT_INJECTION

    def test_input_safe_passes(self):
        cfg = GuardrailConfig.from_dict({
            "input": [{"id": "inj", "type": "injection", "config": {"patterns": ["<script>"]}}],
            "output": [],
        })
        engine = GuardrailEngine(cfg)
        _run(engine.check_input("deer-001", {"query": "normal text"}))

    def test_output_sensitive_detected(self):
        cfg = GuardrailConfig.from_dict({
            "input": [],
            "output": [{"id": "sens", "type": "sensitive", "config": {"keywords": ["password"]}}],
        })
        engine = GuardrailEngine(cfg)
        with pytest.raises(GuardrailTripwire) as exc_info:
            _run(engine.check_output("deer-001", {"content": "my password is 123"}))
        assert exc_info.value.violation_type == GuardrailViolationType.OUTPUT_SENSITIVE

    def test_output_length_exceeded(self):
        cfg = GuardrailConfig.from_dict({
            "input": [],
            "output": [{"id": "len", "type": "length", "config": {"max_chars": 5}}],
        })
        engine = GuardrailEngine(cfg)
        with pytest.raises(GuardrailTripwire) as exc_info:
            _run(engine.check_output("deer-001", {"content": "too long text"}))
        assert exc_info.value.violation_type == GuardrailViolationType.OUTPUT_LENGTH

    def test_output_schema_missing_fields(self):
        cfg = GuardrailConfig.from_dict({
            "input": [],
            "output": [{"id": "schema", "type": "schema", "config": {"required_fields": ["status", "result"]}}],
        })
        engine = GuardrailEngine(cfg)
        with pytest.raises(GuardrailTripwire) as exc_info:
            _run(engine.check_output("deer-001", {"content": "missing fields"}))
        assert exc_info.value.violation_type == GuardrailViolationType.OUTPUT_SCHEMA

    def test_disabled_rule_skipped(self):
        cfg = GuardrailConfig.from_dict({
            "input": [{"id": "inj", "type": "injection", "enabled": False, "config": {"patterns": ["<script>"]}}],
            "output": [],
        })
        engine = GuardrailEngine(cfg)
        _run(engine.check_input("deer-001", {"query": "<script>alert(1)</script>"}))

    def test_unknown_rule_type_logs_warning(self):
        cfg = GuardrailConfig.from_dict({
            "input": [{"id": "unk", "type": "unknown_type", "config": {}}],
            "output": [],
        })
        engine = GuardrailEngine(cfg)
        _run(engine.check_input("deer-001", {"query": "test"}))

    def test_rate_limit_triggered(self):
        cfg = GuardrailConfig.from_dict({
            "input": [{"id": "rl", "type": "rate_limit", "config": {"window_seconds": 1, "max_requests": 2}}],
            "output": [],
        })
        engine = GuardrailEngine(cfg)
        _run(engine.check_input("deer-001", {"query": "msg1"}))
        _run(engine.check_input("deer-001", {"query": "msg2"}))
        with pytest.raises(GuardrailTripwire) as exc_info:
            _run(engine.check_input("deer-001", {"query": "msg3"}))
        assert exc_info.value.violation_type == GuardrailViolationType.INPUT_RATE_LIMIT

    def test_reload_config(self):
        cfg1 = GuardrailConfig.from_dict({
            "input": [{"id": "r1", "type": "injection", "config": {"patterns": ["<script>"]}}],
            "output": [],
        })
        engine = GuardrailEngine(cfg1)
        cfg2 = GuardrailConfig.from_dict({
            "input": [{"id": "r2", "type": "injection", "config": {"patterns": ["<iframe>"]}}],
            "output": [],
        })
        engine.reload(cfg2)
        with pytest.raises(GuardrailTripwire):
            _run(engine.check_input("deer-001", {"query": "<iframe>test"}))


# ==================== TokenBudget ====================


class TestTokenBudget:
    """Token 预算测试。"""

    def test_record_tokens(self):
        budget = TokenBudget()
        budget.set_agent_budget("deer-001", daily_token_limit=1000)
        record = budget.record("deer-001", "task-001", tokens_in=100, tokens_out=200)
        assert record.agent_id == "deer-001"
        assert record.task_id == "task-001"
        assert record.tokens_in == 100
        assert record.tokens_out == 200
        assert record.tokens_in + record.tokens_out == 300

    def test_cost_calculation(self):
        budget = TokenBudget()
        budget.set_agent_budget(
            "deer-001",
            daily_token_limit=1000,
            cost_per_1k_tokens_in=0.001,
            cost_per_1k_tokens_out=0.002,
        )
        record = budget.record("deer-001", "task-001", tokens_in=1000, tokens_out=1000)
        expected = (1000 / 1000) * 0.001 + (1000 / 1000) * 0.002
        assert abs(record.cost_usd - expected) < 1e-6

    def test_check_alerts_below_threshold(self):
        budget = TokenBudget()
        budget.set_agent_budget("deer-001", daily_token_limit=1000, alert_threshold=0.8)
        budget.record("deer-001", "task-001", tokens_in=100, tokens_out=100)
        alerts = budget.check_alerts()
        assert alerts == []

    def test_check_alerts_above_threshold(self):
        budget = TokenBudget()
        budget.set_agent_budget("deer-001", daily_token_limit=1000, alert_threshold=0.5)
        budget.record("deer-001", "task-001", tokens_in=600, tokens_out=0)
        alerts = budget.check_alerts()
        assert len(alerts) == 1
        assert alerts[0]["agent_id"] == "deer-001"
        assert alerts[0]["ratio"] == 0.6

    def test_get_agent_stats(self):
        budget = TokenBudget()
        budget.set_agent_budget("deer-001", daily_token_limit=5000)
        budget.record("deer-001", "task-001", tokens_in=100, tokens_out=200)
        budget.record("deer-001", "task-002", tokens_in=50, tokens_out=50)

        stats = budget.get_agent_stats("deer-001")
        assert stats["total_tokens_in"] == 150
        assert stats["total_tokens_out"] == 250
        assert stats["total_tokens"] == 400
        assert stats["daily_limit"] == 5000
        assert stats["remaining_today"] == 4600

    def test_get_agent_stats_unknown(self):
        budget = TokenBudget()
        stats = budget.get_agent_stats("unknown-agent")
        assert stats["total_tokens"] == 0
        assert stats["daily_limit"] is None

    def test_reset_agent(self):
        budget = TokenBudget()
        budget.set_agent_budget("deer-001", daily_token_limit=1000)
        budget.record("deer-001", "task-001", tokens_in=800, tokens_out=0)
        stats_before = budget.get_agent_stats("deer-001")
        assert stats_before["used_today"] == 800

        budget.reset_agent("deer-001")
        stats_after = budget.get_agent_stats("deer-001")
        assert stats_after["used_today"] == 0

    def test_record_count_limit(self):
        budget = TokenBudget()
        budget._max_records = 10
        for i in range(20):
            budget.record("deer-001", f"task-{i}", tokens_in=1, tokens_out=1)
        assert budget.record_count == 10

    def test_multi_agent_isolation(self):
        budget = TokenBudget()
        budget.set_agent_budget("deer-001", daily_token_limit=1000)
        budget.set_agent_budget("fox-001", daily_token_limit=2000)
        budget.record("deer-001", "task-001", tokens_in=500, tokens_out=0)
        budget.record("fox-001", "task-002", tokens_in=1000, tokens_out=0)

        stats_deer = budget.get_agent_stats("deer-001")
        stats_fox = budget.get_agent_stats("fox-001")
        assert stats_deer["used_today"] == 500
        assert stats_fox["used_today"] == 1000
