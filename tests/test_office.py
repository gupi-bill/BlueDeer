"""Tests for core.office module."""

from __future__ import annotations

from core.office import Office, OfficeManager, WorkStatus


class TestOffice:
    def test_create_office(self):
        office = Office("agent1", name="Alice", role="dev")
        assert office.badge.agent_id == "agent1"
        assert office.badge.name == "Alice"
        assert office.badge.role == "dev"

    def test_set_status(self):
        office = Office("agent1")
        office.set_status(WorkStatus.BUSY)
        assert office.status == WorkStatus.BUSY

    def test_register_skill(self):
        office = Office("agent1")
        office.register_skill("coding", "Write code")
        assert len(office.skills) == 1

    def test_to_dict(self):
        office = Office("agent1")
        data = office.to_dict()
        assert "badge" in data
        assert "status" in data


class TestOfficeManager:
    def test_get_or_create(self):
        mgr = OfficeManager()
        office = mgr.get_or_create("agent1", "Alice")
        assert office.badge.agent_id == "agent1"
        assert mgr.get("agent1") is office

    def test_stats(self):
        mgr = OfficeManager()
        mgr.get_or_create("a1")
        mgr.get_or_create("a2")
        stats = mgr.stats()
        assert stats["total_offices"] == 2
