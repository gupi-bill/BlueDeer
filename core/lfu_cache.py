"""BlueDeer LFU 缓存：freq_map + 同频率内 LRU。

特性：
- get / put 均 O(1)
- freq_map: {freq: 双向链表}（同频率按 LRU 排序）
- min_freq 维护：淘汰时从 min_freq 链表尾移除
- 线程安全
- 频率衰减 + 可配淘汰策略

用法：
    c = LFUCache(capacity=3)
    c.put("k1", "v1")
    c.get("k1")  # freq("k1")=2
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Any, Iterator, List, Optional, Tuple


class _Node:
    __slots__ = ("key", "value", "freq", "prev", "next")

    def __init__(self, key=None, value=None):
        self.key = key
        self.value = value
        self.freq = 1
        self.prev: Optional[_Node] = None
        self.next: Optional[_Node] = None


class _FreqList:
    """同频率节点的双向链表（带哨兵）。"""

    __slots__ = ("head", "tail")

    def __init__(self) -> None:
        self.head = _Node()
        self.tail = _Node()
        self.head.next = self.tail
        self.tail.prev = self.head

    def add_front(self, node: _Node) -> None:
        node.next = self.head.next
        node.prev = self.head
        self.head.next.prev = node
        self.head.next = node

    def remove(self, node: _Node) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev

    def pop_tail(self) -> Optional[_Node]:
        if self.head.next is self.tail:
            return None
        node = self.tail.prev
        self.remove(node)
        return node

    def is_empty(self) -> bool:
        return self.head.next is self.tail


class LFUCache:
    """LFU 缓存。

    Args:
        capacity: 最大容量。
        eviction_policy: 淘汰策略 "LFU" | "LRU" | "FIFO"。
        frequency_decay: 频率衰减因子 [0, 1)，每次 decay() 按比例降低所有频率。
    """

    def __init__(self, capacity: int = 128,
                 eviction_policy: str = "LFU",
                 frequency_decay: float = 0.0) -> None:
        if capacity <= 0:
            raise ValueError("capacity 必须 > 0")
        if eviction_policy.upper() not in ("LFU", "LRU", "FIFO"):
            raise ValueError("eviction_policy 必须为 LFU / LRU / FIFO")
        if not 0.0 <= frequency_decay < 1.0:
            raise ValueError("frequency_decay 必须在 [0, 1) 区间")
        self._capacity = capacity
        self._eviction_policy = eviction_policy.upper()
        self._frequency_decay = frequency_decay
        self._key_map: dict = {}
        self._freq_map: dict = {}
        self._min_freq = 0
        self._access_order: deque = deque()
        self._insert_order: deque = deque()
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return len(self._key_map)

    def __contains__(self, key) -> bool:
        return key in self._key_map

    def _get_freq_list(self, freq: int) -> _FreqList:
        fl = self._freq_map.get(freq)
        if fl is None:
            fl = _FreqList()
            self._freq_map[freq] = fl
        return fl

    def _touch(self, node: _Node) -> None:
        old_freq = node.freq
        self._freq_map[old_freq].remove(node)
        if self._freq_map[old_freq].is_empty():
            del self._freq_map[old_freq]
            if self._min_freq == old_freq:
                self._min_freq = old_freq + 1
        node.freq = old_freq + 1
        self._get_freq_list(node.freq).add_front(node)

    def get(self, key, default=None) -> Any:
        with self._lock:
            node = self._key_map.get(key)
            if node is None:
                return default
            self._touch(node)
            if self._eviction_policy == "LRU":
                self._access_order.remove(key)
                self._access_order.append(key)
            return node.value

    def peek(self, key, default=None) -> Any:
        with self._lock:
            node = self._key_map.get(key)
            return node.value if node else default

    def put(self, key, value: Any) -> None:
        with self._lock:
            node = self._key_map.get(key)
            if node:
                node.value = value
                self._touch(node)
                if self._eviction_policy == "LRU":
                    self._access_order.remove(key)
                    self._access_order.append(key)
                return
            if len(self._key_map) >= self._capacity:
                self._evict()
            node = _Node(key, value)
            self._key_map[key] = node
            self._get_freq_list(1).add_front(node)
            self._min_freq = 1
            if self._eviction_policy == "LRU":
                self._access_order.append(key)
            elif self._eviction_policy == "FIFO":
                self._insert_order.append(key)

    def _evict(self) -> None:
        if self._eviction_policy == "LRU":
            while self._access_order:
                lru_key = self._access_order.popleft()
                victim = self._key_map.pop(lru_key, None)
                if victim is not None:
                    self._freq_map[victim.freq].remove(victim)
                    if self._freq_map[victim.freq].is_empty():
                        del self._freq_map[victim.freq]
                    return
        elif self._eviction_policy == "FIFO":
            while self._insert_order:
                fifo_key = self._insert_order.popleft()
                victim = self._key_map.pop(fifo_key, None)
                if victim is not None:
                    self._freq_map[victim.freq].remove(victim)
                    if self._freq_map[victim.freq].is_empty():
                        del self._freq_map[victim.freq]
                    return
        else:
            fl = self._freq_map.get(self._min_freq)
            if fl is not None:
                victim = fl.pop_tail()
                if victim is not None:
                    del self._key_map[victim.key]
                    if fl.is_empty():
                        del self._freq_map[self._min_freq]

    def delete(self, key) -> bool:
        with self._lock:
            node = self._key_map.pop(key, None)
            if node is None:
                return False
            self._freq_map[node.freq].remove(node)
            if self._freq_map[node.freq].is_empty():
                del self._freq_map[node.freq]
                if self._min_freq == node.freq:
                    self._min_freq = min(self._freq_map.keys()) if self._freq_map else 0
            if self._eviction_policy == "LRU" and key in self._access_order:
                self._access_order.remove(key)
            elif self._eviction_policy == "FIFO" and key in self._insert_order:
                self._insert_order.remove(key)
            return True

    def decay(self) -> int:
        """对所有频率应用衰减。返回受影响的节点数。"""
        if self._frequency_decay <= 0:
            return 0
        with self._lock:
            affected = 0
            freqs = sorted(self._freq_map.keys(), reverse=True)
            for freq in freqs:
                decayed = max(1, int(freq * (1 - self._frequency_decay)))
                if decayed == freq:
                    continue
                fl = self._freq_map.pop(freq)
                node = fl.head.next
                while node is not fl.tail:
                    next_node = node.next
                    node.freq = decayed
                    self._get_freq_list(decayed).add_front(node)
                    node = next_node
                    affected += 1
            self._min_freq = min(self._freq_map.keys()) if self._freq_map else 0
            return affected

    def freq(self, key) -> int:
        with self._lock:
            node = self._key_map.get(key)
            return node.freq if node else 0

    @property
    def min_freq(self) -> int:
        return self._min_freq

    @property
    def eviction_policy(self) -> str:
        return self._eviction_policy

    @property
    def frequency_decay(self) -> float:
        return self._frequency_decay

    def keys(self) -> List:
        with self._lock:
            return list(self._key_map.keys())

    def items(self) -> Iterator[Tuple]:
        with self._lock:
            for k, n in self._key_map.items():
                yield (k, n.value)

    def clear(self) -> None:
        with self._lock:
            self._key_map = {}
            self._freq_map = {}
            self._min_freq = 0
            self._access_order.clear()
            self._insert_order.clear()

    def status(self) -> dict:
        return {
            "size": len(self._key_map),
            "capacity": self._capacity,
            "min_freq": self._min_freq,
            "num_freq_buckets": len(self._freq_map),
            "eviction_policy": self._eviction_policy,
            "frequency_decay": self._frequency_decay,
        }
