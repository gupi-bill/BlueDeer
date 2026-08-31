"""Tests for core.breakroom module."""

from __future__ import annotations

from core.breakroom import BreakRoom, MessageType


class TestBreakRoom:
    def test_post_message(self):
        room = BreakRoom()
        msg_id = room.post("Hello", author="Alice")
        assert msg_id.startswith("br_")
        recent = room.recent(1)
        assert len(recent) == 1
        assert recent[0].content == "Hello"

    def test_announce(self):
        room = BreakRoom()
        msg_id = room.announce("System update")
        assert msg_id.startswith("br_")
        recent = room.recent(1)
        assert recent[0].msg_type == MessageType.SYSTEM

    def test_like(self):
        room = BreakRoom()
        msg_id = room.post("Nice", author="Bob")
        assert room.like(msg_id) is True
        assert room.recent(1)[0].likes == 1

    def test_stats(self):
        room = BreakRoom()
        room.post("A", author="Alice")
        stats = room.stats()
        assert stats["total_messages"] == 1
        assert stats["active_authors"] == 1
