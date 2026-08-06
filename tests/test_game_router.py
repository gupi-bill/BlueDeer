"""Tests for core.game_router module."""

from __future__ import annotations

from core.game_router import (
    clear_servers,
    fallback_handler,
    register_server,
    route_to_best,
    set_backups,
)


class TestRouteToBest:
    def setup_method(self):
        clear_servers()

    def test_route_to_best(self):
        register_server("s1", capacity=10, load=0.5)
        register_server("s2", capacity=10, load=0.2)
        best = route_to_best("game1", 5)
        assert best == "s2"

    def test_route_to_best_over_capacity(self):
        register_server("s1", capacity=5, load=0.0)
        best = route_to_best("game1", 10)
        assert best is None


class TestFallbackHandler:
    def setup_method(self):
        clear_servers()

    def test_fallback(self):
        set_backups(["backup1"])
        assert fallback_handler("game1") == "backup1"

    def test_fallback_empty(self):
        set_backups([])
        assert fallback_handler("game1") is None
