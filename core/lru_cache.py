"""BlueDeer LRU + TTL 缓存：哈希表 + 双向链表 O(1)，支持 TTL 过期。

特性：
- get / put / delete 均 O(1)
- TTL 过期（惰性删除 + 后台线程）
- 淘汰回调 on_evict(key, value)
- 容量超限警告日志
- 线程安全

用法：
    c = LRUCache(capacity=3, ttl=60, on_evict=lambda k,v: print(f"淘汰 {k}"))
    c.put("k1", "v1")
    c.get("k1")
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

logger = logging.getLogger("bluedeer.cache")


class _Node:
    __slots__ = ("expire_at", "key", "next", "prev", "value")

    def __init__(self, key=None, value=None):
        self.key = key
        self.value = value
        self.prev: _Node | None = None
        self.next: _Node | None = None
        self.expire_at: float | None = None


class LRUCache:
    """LRU + TTL 缓存。"""

    def __init__(
        self,
        capacity: int = 128,
        ttl: float | None = None,
        on_evict: Callable[[Any, Any], None] | None = None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity 必须 > 0")
        self._capacity = capacity
        self._default_ttl = ttl
        self._on_evict = on_evict
        self._map: dict = {}
        self._head = _Node()
        self._tail = _Node()
        self._head.next = self._tail
        self._tail.prev = self._head
        self._hits = 0
        self._misses = 0
        self._evicted = 0
        self._expired = 0
        self._lock = threading.RLock()
        self._clock = time.monotonic

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, key) -> bool:
        return key in self._map

    def _remove(self, node: _Node) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev

    def _add_front(self, node: _Node) -> None:
        node.next = self._head.next
        node.prev = self._head
        self._head.next.prev = node
        self._head.next = node

    def _move_to_front(self, node: _Node) -> None:
        self._remove(node)
        self._add_front(node)

    def _is_expired(self, node: _Node) -> bool:
        return node.expire_at is not None and self._clock() >= node.expire_at

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self._misses += 1
                return default
            if self._is_expired(node):
                self._remove_entry(node)
                self._expired += 1
                self._misses += 1
                return default
            self._hits += 1
            self._move_to_front(node)
            return node.value

    def peek(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            node = self._map.get(key)
            if node is None or self._is_expired(node):
                return default
            return node.value

    def put(self, key: Any, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            now = self._clock()
            expire_at: float | None
            if ttl is not None:
                expire_at = None if ttl == 0 else now + ttl
            elif self._default_ttl is not None:
                expire_at = now + self._default_ttl
            else:
                expire_at = None

            node = self._map.get(key)
            if node:
                node.value = value
                node.expire_at = expire_at
                self._move_to_front(node)
                return
            node = _Node(key, value)
            node.expire_at = expire_at
            self._map[key] = node
            self._add_front(node)
            self._shrink()

    def _shrink(self) -> None:
        if len(self._map) <= self._capacity:
            return
        n = len(self._map) - self._capacity
        if n >= self._capacity // 2:
            logger.warning("LRU 容量 %d 达上限，淘汰 %d 项", self._capacity, n)
        for _ in range(n):
            lru = self._tail.prev
            if lru is self._head:
                break
            self._remove_entry(lru)

    def _remove_entry(self, node: _Node) -> None:
        self._remove(node)
        del self._map[node.key]
        self._evicted += 1
        if self._on_evict:
            try:
                self._on_evict(node.key, node.value)
            except Exception:
                logger.exception("淘汰回调异常 key=%s", node.key)

    def delete(self, key) -> bool:
        with self._lock:
            node = self._map.pop(key, None)
            if node is None:
                return False
            self._remove(node)
            return True

    def evict_expired(self) -> int:
        n = 0
        with self._lock:
            now = self._clock()
            cur = self._tail.prev
            while cur is not self._head:
                prev = cur.prev
                if cur.expire_at is not None and now >= cur.expire_at:
                    self._remove_entry(cur)
                    self._expired += 1
                    n += 1
                cur = prev
        return n

    def keys(self) -> Any:
        with self._lock:
            result = []
            n = self._head.next
            while n is not self._tail:
                result.append(n.key)
                n = n.next
            return result

    def items(self) -> Iterator:
        with self._lock:
            n = self._head.next
            while n is not self._tail:
                yield (n.key, n.value)
                n = n.next

    def values(self) -> Any:
        with self._lock:
            return [n.value for n in self._iter_nodes()]

    def _iter_nodes(self):
        n = self._head.next
        while n is not self._tail:
            yield n
            n = n.next

    @property
    def lru_key(self) -> Any:
        with self._lock:
            n = self._tail.prev
            return n.key if n is not self._head else None

    @property
    def mru_key(self) -> Any:
        with self._lock:
            n = self._head.next
            return n.key if n is not self._tail else None

    def resize(self, new_capacity: int) -> None:
        with self._lock:
            if new_capacity <= 0:
                raise ValueError("capacity 必须 > 0")
            self._capacity = new_capacity
            self._shrink()

    def clear(self) -> None:
        with self._lock:
            self._map = {}
            self._head.next = self._tail
            self._tail.prev = self._head
            self._hits = 0
            self._misses = 0
            self._evicted = 0
            self._expired = 0

    def status(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._map),
            "capacity": self._capacity,
            "default_ttl": self._default_ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_ratio": self._hits / total if total else 0.0,
            "evicted": self._evicted,
            "expired": self._expired,
        }
