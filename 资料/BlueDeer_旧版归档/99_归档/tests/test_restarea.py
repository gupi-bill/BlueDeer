"""Tests for core.restarea module."""

from __future__ import annotations

from core.restarea import RestArea


class TestRestArea:
    def test_start_and_end_rest(self):
        area = RestArea()
        session = area.start_rest("agent1", 30.0)
        assert session.agent_id == "agent1"
        assert area.end_rest(session.session_id, 1) is True
        assert area.end_rest("missing") is False

    def test_stats(self):
        area = RestArea()
        area.start_rest("a1", 10.0)
        stats = area.stats()
        assert stats["total_sessions"] == 1

    def test_rest_recovery(self):
        area = RestArea()
        result = area.rest("hero", 10.0)
        assert result["hp_restored"] > 0
        assert result["energy_restored"] > 0

    def test_get_recovery_stats(self):
        area = RestArea()
        area.rest("hero", 5.0)
        stats = area.get_recovery_stats("hero")
        assert stats["total_hp"] > 0
