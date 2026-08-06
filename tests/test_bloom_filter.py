"""P0: BloomFilter 布隆过滤器核心。"""

from __future__ import annotations

import random

import pytest

from core.bloom_filter import BloomFilter

pytestmark = pytest.mark.p0


def test_add_and_contains():
    bf = BloomFilter(capacity=1000)
    bf.add("hello")
    assert bf.contains("hello")
    assert "hello" in bf


def test_absent_item_not_found():
    bf = BloomFilter(capacity=1000)
    bf.add("present")
    assert not bf.contains("absent")
    assert "absent" not in bf


def test_add_many_and_contains_many():
    bf = BloomFilter(capacity=1000)
    items = [f"item-{i}" for i in range(50)]
    assert bf.add_many(items) == 50
    assert bf.contains_many(items) == [True] * 50
    assert len(bf) == 50


def test_serialization_roundtrip():
    bf = BloomFilter(capacity=1000, error_rate=0.01)
    bf.add_many([f"key-{i}" for i in range(100)])
    data = bf.to_bytes()
    bf2 = BloomFilter.from_bytes(data)
    assert bf2.capacity == bf.capacity
    assert bf2.num_bits == bf.num_bits
    assert bf2.num_hashes == bf.num_hashes
    assert bf2.contains_many([f"key-{i}" for i in range(100)]) == [True] * 100
    assert len(bf2) == 100


def test_from_bytes_rejects_bad_magic():
    with pytest.raises(ValueError):
        BloomFilter.from_bytes(b"XXXX" + b"\x00" * 32)


def test_merge_union():
    bf1 = BloomFilter(capacity=1000)
    bf2 = BloomFilter(capacity=1000)
    bf1.add("a")
    bf2.add("b")
    bf1.merge(bf2)
    assert bf1.contains("a") and bf1.contains("b")


def test_merge_rejects_mismatched_params():
    bf1 = BloomFilter(capacity=1000)
    bf2 = BloomFilter(capacity=5000)
    with pytest.raises(ValueError):
        bf1.merge(bf2)


def test_clear_resets():
    bf = BloomFilter(capacity=1000)
    bf.add("x")
    bf.clear()
    assert len(bf) == 0
    assert not bf.contains("x")


def test_invalid_params():
    with pytest.raises(ValueError):
        BloomFilter(capacity=0)
    with pytest.raises(ValueError):
        BloomFilter(capacity=100, error_rate=1.0)
    with pytest.raises(ValueError):
        BloomFilter(capacity=100, error_rate=0.0)


def test_estimated_fpr_within_budget():
    """插入满容量元素后，误判率实测应显著低于 1%。"""
    capacity = 2000
    bf = BloomFilter(capacity=capacity, error_rate=0.01)
    rng = random.Random(42)
    inserted = [f"in-{rng.randrange(10**9)}" for _ in range(capacity)]
    bf.add_many(inserted)
    probes = 2000
    false_positives = sum(
        1 for _ in range(probes) if bf.contains(f"out-{rng.randrange(10**9)}")
    )
    assert false_positives / probes < 0.05


def test_status_shape():
    bf = BloomFilter(capacity=1000, error_rate=0.01)
    bf.add("x")
    st = bf.status()
    assert st["capacity"] == 1000
    assert st["count"] == 1
    assert st["num_bits"] > 0
    assert st["num_hashes"] > 0
    assert 0 <= st["saturation"] <= 1
    assert st["estimated_fpr"] >= 0
