"""Tests for core.lru_cache module."""

from __future__ import annotations

from core.lru_cache import LRUCache, _Node


class TestNode:
    def test_create_node(self):
        node = _Node("key", "value")
        assert node.key == "key"
        assert node.value == "value"
        assert node.prev is None
        assert node.next is None
        assert node.expire_at is None


class TestLRUCache:
    def test_create_cache(self):
        cache = LRUCache(capacity=3)
        assert len(cache) == 0

    def test_put_and_get(self):
        cache = LRUCache(capacity=3)
        cache.put("k1", "v1")
        assert cache.get("k1") == "v1"
        assert len(cache) == 1

    def test_lru_eviction(self):
        cache = LRUCache(capacity=2)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")  # should evict k1
        assert cache.get("k1") is None
        assert cache.get("k2") == "v2"
        assert cache.get("k3") == "v3"

    def test_get_with_default(self):
        cache = LRUCache(capacity=3)
        assert cache.get("missing", "default") == "default"

    def test_contains(self):
        cache = LRUCache(capacity=3)
        cache.put("k1", "v1")
        assert "k1" in cache
        assert "missing" not in cache

    def test_delete(self):
        cache = LRUCache(capacity=3)
        cache.put("k1", "v1")
        assert cache.delete("k1") is True
        assert cache.delete("missing") is False

    def test_clear(self):
        cache = LRUCache(capacity=3)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.clear()
        assert len(cache) == 0

    def test_peek(self):
        cache = LRUCache(capacity=3)
        cache.put("k1", "v1")
        assert cache.peek("k1") == "v1"
        assert cache.peek("missing", "default") == "default"

    def test_resize(self):
        cache = LRUCache(capacity=3)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")
        cache.resize(5)
        assert cache._capacity == 5
        assert len(cache) == 3

    def test_resize_evicts(self):
        cache = LRUCache(capacity=5)
        cache.put("k1", "v1")
        cache.put("k2", "v2")
        cache.put("k3", "v3")
        cache.put("k4", "v4")
        cache.put("k5", "v5")
        cache.resize(3)
        assert len(cache) == 3
