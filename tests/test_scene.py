"""Tests for core.scene module."""

from __future__ import annotations

from core.scene import CEOOffice


class TestCEOOffice:
    def test_create_ceo_office(self):
        office = CEOOffice()
        assert office.get_current_scene() == "office"

    def test_transition_to(self):
        office = CEOOffice()
        result = office.transition_to("breakroom", effect="fade")
        assert result["to"] == "breakroom"
        assert office.get_current_scene() == "breakroom"

    def test_push_pop_scene(self):
        office = CEOOffice()
        office.push_scene("library")
        assert office.get_current_scene() == "library"
        office.pop_scene()
        assert office.get_current_scene() == "office"

    def test_status(self):
        office = CEOOffice()
        status = office.status()
        assert "library" in status
        assert "breakroom" in status
