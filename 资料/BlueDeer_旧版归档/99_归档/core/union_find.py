"""BlueDeer Union-Find 并查集：路径压缩 + 按秩合并 + 快照冻结。

用法：
    uf = UnionFind()
    uf.union("a", "b")
    assert uf.connected("a", "b")
    snap = uf.freeze()
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Iterator
from typing import Any


class UnionFind:
    """并查集，支持路径压缩与按秩合并。"""

    def __init__(self) -> None:
        self._parent: dict[Any, Any] = {}
        self._rank: dict[Any, int] = {}
        self._size: dict[Any, int] = {}
        self._frozen: bool = False
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return len(self._parent)

    def add(self, x: Any) -> bool:
        with self._lock:
            if self._frozen:
                raise RuntimeError("并查集已冻结")
            if x in self._parent:
                return False
            self._parent[x] = x
            self._rank[x] = 0
            self._size[x] = 1
            return True

    def __contains__(self, x: Any) -> bool:
        with self._lock:
            return x in self._parent

    def find(self, x: Any) -> Any:
        with self._lock:
            if x not in self._parent:
                self.add(x)
            root = x
            while self._parent[root] != root:
                root = self._parent[root]
            cur = x
            while self._parent[cur] != root:
                nxt = self._parent[cur]
                self._parent[cur] = root
                cur = nxt
            return root

    def union(self, x: Any, y: Any) -> bool:
        with self._lock:
            if self._frozen:
                raise RuntimeError("并查集已冻结")
            rx = self.find(x)
            ry = self.find(y)
            if rx == ry:
                return False
            if self._rank[rx] < self._rank[ry]:
                rx, ry = ry, rx
            self._parent[ry] = rx
            self._size[rx] += self._size[ry]
            if self._rank[rx] == self._rank[ry]:
                self._rank[rx] += 1
            self._size.pop(ry, None)
            self._rank.pop(ry, None)
            return True

    def connected(self, x: Any, y: Any) -> bool:
        with self._lock:
            return self.find(x) == self.find(y)

    def component_count(self) -> int:
        with self._lock:
            return sum(1 for x, p in self._parent.items() if p == x)

    def component_size(self, x: Any) -> int:
        with self._lock:
            root = self.find(x)
            return self._size.get(root, 1)

    def is_singleton(self, x: Any) -> bool:
        with self._lock:
            return self.component_size(x) == 1

    def freeze(self) -> dict[str, Any]:
        """冻结并返回快照。冻结后不能再 union/add。"""
        with self._lock:
            self._frozen = True
            return {
                "parent": copy.deepcopy(self._parent),
                "size": copy.deepcopy(self._size),
                "components": self.component_count(),
                "elements": len(self._parent),
            }

    def reset(self) -> None:
        with self._lock:
            self._parent.clear()
            self._rank.clear()
            self._size.clear()
            self._frozen = False

    def components(self) -> dict[Any, list[Any]]:
        with self._lock:
            groups: dict[Any, list[Any]] = {}
            for x in self._parent:
                root = self.find(x)
                groups.setdefault(root, []).append(x)
            return groups

    def iter_components(self) -> Iterator[list[Any]]:
        with self._lock:
            for group in self.components().values():
                yield list(group)

    def status(self) -> dict:
        with self._lock:
            return {
                "elements": len(self._parent),
                "components": self.component_count(),
                "frozen": self._frozen,
            }
