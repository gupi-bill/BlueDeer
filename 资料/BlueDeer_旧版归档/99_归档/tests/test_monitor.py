"""Tests for core.monitor module."""

from __future__ import annotations

import pytest

from core.monitor import HealthStatus, SystemMonitor


class TestHealthStatus:
    def test_create_health_status(self):
        status = HealthStatus(service="test", status="ok")
        assert status.service == "test"
        assert status.status == "ok"
        assert status.latency_ms == 0.0
        assert status.error == ""

    def test_health_status_with_error(self):
        status = HealthStatus(service="test", status="down", error="failed")
        assert status.error == "failed"


class TestSystemMonitor:
    @pytest.fixture
    def monitor(self):
        return SystemMonitor(check_interval=60.0)

    def test_create_monitor(self, monitor):
        assert monitor._interval == 60.0
        assert monitor._running is False
        assert monitor._history == []

    def test_check_harness(self, monitor):
        status = monitor.check_harness()
        assert status.service == "harness"
        assert status.status == "ok"

    def test_check_services(self, monitor):
        statuses = monitor.check_services()
        assert len(statuses) == 3
        assert all(s.service for s in statuses)

    def test_resource_usage(self, monitor):
        usage = monitor.resource_usage()
        assert "cpu_percent" in usage
        assert "memory_percent" in usage
        assert "disk" in usage
        assert "timestamp" in usage

    def test_evaluate_alerts_high_cpu(self, monitor):
        usage = {"cpu_percent": 95, "memory_percent": 50, "disk": {"percent": 50}}
        alerts = monitor._alert_evaluator.evaluate(usage)
        assert len(alerts) == 1
        assert alerts[0]["metric"] == "cpu"

    def test_evaluate_alerts_high_memory(self, monitor):
        usage = {"cpu_percent": 50, "memory_percent": 90, "disk": {"percent": 50}}
        alerts = monitor._alert_evaluator.evaluate(usage)
        assert len(alerts) == 1
        assert alerts[0]["metric"] == "memory"

    def test_evaluate_alerts_high_disk(self, monitor):
        usage = {"cpu_percent": 50, "memory_percent": 50, "disk": {"percent": 95}}
        alerts = monitor._alert_evaluator.evaluate(usage)
        assert len(alerts) == 1
        assert alerts[0]["metric"] == "disk"
