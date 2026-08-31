"""Performance benchmarks for core data structures."""
from __future__ import annotations

import asyncio
import time


class TestLRUCachePerformance:
    def test_lru_cache_throughput(self):
        from core.lru_cache import LRUCache

        cache = LRUCache(capacity=1000)
        start = time.perf_counter()
        for i in range(10000):
            cache.put(f"key_{i}", i)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"LRU cache set too slow: {elapsed:.3f}s"

    def test_lru_cache_hit_rate(self):
        from core.lru_cache import LRUCache

        cache = LRUCache(capacity=100)
        for i in range(100):
            cache.put(f"key_{i}", i)
        hits = 0
        for i in range(1000):
            if cache.get(f"key_{i % 100}") is not None:
                hits += 1
        assert hits > 800


class TestBPlusTreePerformance:
    def test_bplus_tree_insert_and_search(self):
        from core.bplus_tree import BPlusTree

        tree = BPlusTree(order=4)
        start = time.perf_counter()
        for i in range(1000):
            tree.insert(i, f"value_{i}")
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"B+ tree insert too slow: {elapsed:.3f}s"

    def test_bplus_tree_range_query(self):
        from core.bplus_tree import BPlusTree

        tree = BPlusTree(order=4)
        for i in range(1000):
            tree.insert(i, f"value_{i}")
        results = tree.range(100, 200)
        assert len(results) == 101


class TestBloomFilterPerformance:
    def test_bloom_filter_throughput(self):
        from core.bloom_filter import BloomFilter

        bf = BloomFilter(capacity=10000, error_rate=0.01)
        start = time.perf_counter()
        for i in range(10000):
            bf.add(f"item_{i}")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Bloom filter add too slow: {elapsed:.3f}s"


class TestRateLimiterPerformance:
    def test_rate_limiter_throughput(self):
        from core.api_server import RateLimiter

        limiter = RateLimiter(max_requests=1000, window=60.0)
        start = time.perf_counter()
        for i in range(10000):
            allowed, _ = limiter.check(f"key_{i % 100}")
            assert allowed is True
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"RateLimiter too slow: {elapsed:.3f}s"


class TestEventBusPerformance:
    def test_event_bus_publish_throughput(self):
        from core.event_bus import EventBus

        bus = EventBus()
        received = []

        async def handler(msg):
            received.append(msg)

        bus.subscribe("bench", handler)
        start = time.perf_counter()
        for i in range(1000):
            asyncio.run(bus.publish("bench", f"msg_{i}"))
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"EventBus publish too slow: {elapsed:.3f}s"
