"""BlueDeer 开放寻址哈希表：Robin Hood 哈希 + 动态扩容。

特性：
- 容量取 2 的幂，用 mask 代替取模
- Robin Hood hashing：跟踪探测距离，远者优先，插入时交换
- tombstone 标记已删除槽（不立即回收，下次 rehash 清理）
- 负载因子超 0.75 自动扩容 2 倍

用法：
    ht = HashTable(capacity=8)
    ht.put("k1", "v1")
    ht.get("k1")  # "v1"
    ht.delete("k1")
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

_EMPTY = 0
_FILLED = 1
_TOMB = 2


class _Slot:
    __slots__ = ("dist", "hash", "key", "state", "value")

    def __init__(self) -> None:
        self.state = _EMPTY
        self.key = None
        self.value = None
        self.hash = 0
        self.dist = 0


class HashTable:
    """开放寻址哈希表（Robin Hood hashing）。"""

    def __init__(self, capacity: int = 16, load_factor: float = 0.75) -> None:
        capacity = max(capacity, 4)
        cap = 1
        while cap < capacity:
            cap <<= 1
        self._capacity = cap
        self._mask = cap - 1
        self._load_factor_threshold = load_factor
        self._slots: list = [_Slot() for _ in range(cap)]
        self._size = 0
        self._used = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def __contains__(self, key) -> bool:
        return self.get(key, _MISSING) is not _MISSING

    @property
    def load_factor(self) -> float:
        """当前负载因子。"""
        return self._used / self._capacity if self._capacity else 0.0

    @staticmethod
    def _hash(key) -> int:
        return hash(key)

    def _probe(self, key, h: int) -> tuple[int, int | None]:
        """返回 (找到的槽 idx or -1, 插入位置 idx or None)。

        Robin Hood：寻找时跟踪探测距离，找到第一个 dist < cur_dist 的槽即为插入点。
        """
        idx = h & self._mask
        first_tomb = None
        for cur_dist in range(self._capacity):
            slot = self._slots[idx]
            if slot.state == _EMPTY:
                insert_pos = first_tomb if first_tomb is not None else idx
                return -1, insert_pos
            if slot.state == _TOMB:
                if first_tomb is None:
                    first_tomb = idx
            elif slot.state == _FILLED:  # noqa: SIM102
                if slot.hash == h and self._keys_equal(slot.key, key):
                    return idx, None
            idx = (idx + 1) & self._mask
        return -1, first_tomb

    def _probe_insert(self, key, h: int) -> int:
        """Robin Hood 插入：找到合适位置，必要时交换。

        返回实际插入的槽 idx。
        """
        idx = h & self._mask
        cur_dist = 0
        while True:
            slot = self._slots[idx]
            if slot.state == _EMPTY or slot.state == _TOMB:
                return idx
            if (
                slot.state == _FILLED
                and slot.hash == h
                and self._keys_equal(slot.key, key)
            ):
                return idx
            if slot.state == _FILLED and slot.dist < cur_dist:
                self._slots[idx], key, h, cur_dist = (
                    _Slot(),
                    slot.key,
                    slot.hash,
                    slot.dist,
                )
                self._slots[idx].state = _FILLED
                self._slots[idx].key = key
                self._slots[idx].hash = h
                self._slots[idx].dist = cur_dist
                key = slot.key
                h = slot.hash
                cur_dist = slot.dist
            idx = (idx + 1) & self._mask
            cur_dist += 1

    def _find(self, key, h: int) -> int:
        """Robin Hood 查找：按探测距离搜索。"""
        idx = h & self._mask
        for dist in range(self._capacity):
            slot = self._slots[idx]
            if slot.state == _EMPTY:
                return -1
            if (
                slot.state == _FILLED
                and slot.hash == h
                and self._keys_equal(slot.key, key)
            ):
                return idx
            idx = (idx + 1) & self._mask
        return -1

    @staticmethod
    def _keys_equal(a, b) -> bool:
        if type(a) is not type(b):
            return False
        return a == b

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            idx = self._find(key, self._hash(key))
            if idx < 0:
                return default
            return self._slots[idx].value

    def put(self, key: Any, value: Any) -> None:
        with self._lock:
            h = self._hash(key)
            idx = self._find(key, h)
            if idx >= 0:
                self._slots[idx].value = value
                return
            insert_idx = self._probe_insert(key, h)
            slot = self._slots[insert_idx]
            was_empty = slot.state == _EMPTY
            slot.state = _FILLED
            slot.key = key
            slot.value = value
            slot.hash = h
            slot.dist = (insert_idx - (h & self._mask)) & self._mask
            self._size += 1
            if was_empty:
                self._used += 1
            if self.load_factor > self._load_factor_threshold:
                self.resize(self._capacity << 1)

    def delete(self, key) -> bool:
        with self._lock:
            h = self._hash(key)
            idx = self._find(key, h)
            if idx < 0:
                return False
            slot = self._slots[idx]
            slot.state = _TOMB
            slot.key = None
            slot.value = None
            slot.dist = 0
            self._size -= 1
            if self._size > 0 and self._used > self._size * 4:
                self.resize(self._capacity)
            return True

    def resize(self, new_capacity: int) -> None:
        """调整哈希表容量（公开方法）。"""
        self._rehash(new_capacity)

    def _rehash(self, new_cap: int) -> None:
        cap = 1
        while cap < new_cap:
            cap <<= 1
        old_slots = self._slots
        self._capacity = cap
        self._mask = cap - 1
        self._slots = [_Slot() for _ in range(cap)]
        self._size = 0
        self._used = 0
        for slot in old_slots:
            if slot.state == _FILLED:
                self.put(slot.key, slot.value)

    def keys(self) -> Iterator:
        with self._lock:
            for slot in self._slots:
                if slot.state == _FILLED:
                    yield slot.key

    def items(self) -> Iterator[tuple]:
        with self._lock:
            for slot in self._slots:
                if slot.state == _FILLED:
                    yield (slot.key, slot.value)

    def clear(self) -> None:
        with self._lock:
            self._slots = [_Slot() for _ in range(self._capacity)]
            self._size = 0
            self._used = 0

    def status(self) -> dict:
        return {
            "size": self._size,
            "capacity": self._capacity,
            "used": self._used,
            "load_factor": self.load_factor,
        }


_MISSING = object()
