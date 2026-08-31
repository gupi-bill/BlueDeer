"""Tests for core.notifier module."""

from __future__ import annotations

import asyncio

from core.notifier import EmailChannel, EmailConfig, Notifier


class TestEmailChannel:
    def test_send(self):
        config = EmailConfig(smtp_host="localhost", smtp_port=1025)
        channel = EmailChannel(config)
        assert asyncio.run(channel.send("Test", "Body")) is False  # no recipients


class TestNotifier:
    def test_register_and_send(self):
        notifier = Notifier()
        config = EmailConfig(smtp_host="localhost", smtp_port=1025)
        notifier.register("email", EmailChannel(config))
        results = notifier.list_channels()
        assert "email" in results

    def test_broadcast(self):
        notifier = Notifier()
        results = asyncio.run(notifier.broadcast("Title", "Body"))
        assert isinstance(results, dict)
