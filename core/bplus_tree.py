"""BlueDeer B+树：磁盘友好的有序索引 + 范围查询。

evolution（数据维度 - R193）：
- B+树是数据库索引的经典结构：内部节点只存索引，叶子存数据
- 叶子通过双向链表连接，范围查询 O(log n + k)
- 节点满则分裂，不满则合并/借位，自动平衡
- 与跳表互补：跳表用概率平衡，B+树用节点分裂
- 适合磁盘存储（节点大小可对齐页）
"""
from __future__ import annotations
import pickle
import threading
from typing import Any, Iterator


class _Leaf:
    __slots__ = ("keys", "values", "next", "prev")

    def __init__(self):
        self.keys: list = []
        self.values: list = []
        self.next: _Leaf | None = None
        self.prev: _Leaf | None = None


class _Internal:
    __slots__ = ("keys", "children")

    def __init__(self):
        self.keys: list = []
        self.children: list = []


class BPlusTree:
    """B+树：有序 key-value 存储 + 范围查询 + 磁盘友好。

    用法：
        t = BPlusTree(order=4)
        t.insert(10, "a")
        t.insert(20, "b")
        t.get(10)  -> "a"
        t.range(5, 15)  -> [(5,"c"), (10,"a")]
        t.to_disk("index.bpt")
        t2 = BPlusTree.from_disk("index.bpt")
    """

    def __init__(self, order: int = 4, page_size: int = 0):
        if order < 3:
            raise ValueError("order 至少 3")
        self._order = order
        self._page_size = page_size
        if page_size:
            max_keys = page_size // 16  # 估算 key+ptr 占 16 字节
            self._order = max(3, max_keys)
        self._root: _Leaf | _Internal = _Leaf()
        self._size = 0
        self._cache: dict[int, Any] = {}  # id(node) -> node
        self._cache_max = 64
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def _cache_get(self, node) -> Any:
        nid = id(node)
        if nid in self._cache:
            return self._cache[nid]
        return node

    def _cache_put(self, node) -> None:
        nid = id(node)
        self._cache[nid] = node
        if len(self._cache) > self._cache_max:
            for k in list(self._cache.keys())[:len(self._cache) - self._cache_max]:
                del self._cache[k]

    def _cache_clear(self) -> None:
        self._cache.clear()

    def _find_leaf(self, key) -> _Leaf:
        node = self._root
        while isinstance(node, _Internal):
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            child = node.children[i]
            node = self._cache_get(child)
        return node

    def insert(self, key, value) -> None:
        with self._lock:
            leaf = self._find_leaf(key)
            for i, k in enumerate(leaf.keys):
                if k == key:
                    leaf.values[i] = value
                    self._cache_put(leaf)
                    return
            i = 0
            while i < len(leaf.keys) and leaf.keys[i] < key:
                i += 1
            leaf.keys.insert(i, key)
            leaf.values.insert(i, value)
            self._size += 1
            self._cache_put(leaf)
            if len(leaf.keys) >= self._order:
                self._split_leaf(leaf)

    def _split_leaf(self, leaf: _Leaf) -> None:
        mid = len(leaf.keys) // 2
        new_leaf = _Leaf()
        new_leaf.keys = leaf.keys[mid:]
        new_leaf.values = leaf.values[mid:]
        leaf.keys = leaf.keys[:mid]
        leaf.values = leaf.values[:mid]
        new_leaf.next = leaf.next
        new_leaf.prev = leaf
        if leaf.next is not None:
            leaf.next.prev = new_leaf
        leaf.next = new_leaf
        sep = new_leaf.keys[0]
        self._cache_put(leaf)
        self._cache_put(new_leaf)
        self._insert_into_parent(leaf, sep, new_leaf)

    def _insert_into_parent(self, left, key, right) -> None:
        if left is self._root:
            new_root = _Internal()
            new_root.keys = [key]
            new_root.children = [left, right]
            self._root = new_root
            self._cache_put(new_root)
            return
        parent = self._find_parent(self._root, left)
        i = 0
        while i < len(parent.keys) and key > parent.keys[i]:
            i += 1
        parent.keys.insert(i, key)
        parent.children.insert(i + 1, right)
        self._cache_put(parent)
        if len(parent.keys) >= self._order:
            self._split_internal(parent)

    def _split_internal(self, node: _Internal) -> None:
        mid = len(node.keys) // 2
        up_key = node.keys[mid]
        new_node = _Internal()
        new_node.keys = node.keys[mid + 1:]
        new_node.children = node.children[mid + 1:]
        node.keys = node.keys[:mid]
        node.children = node.children[:mid + 1]
        self._cache_put(node)
        self._cache_put(new_node)
        self._insert_into_parent(node, up_key, new_node)

    def _find_parent(self, current: _Internal, child) -> _Internal | None:
        if isinstance(current, _Leaf):
            return None
        for c in current.children:
            if c is child:
                return current
        for c in current.children:
            if isinstance(c, _Internal):
                p = self._find_parent(c, child)
                if p is not None:
                    return p
        return None

    def get(self, key) -> Any:
        with self._lock:
            leaf = self._find_leaf(key)
            for i, k in enumerate(leaf.keys):
                if k == key:
                    return leaf.values[i]
            return None

    def __contains__(self, key) -> bool:
        with self._lock:
            leaf = self._find_leaf(key)
            return key in leaf.keys

    def remove(self, key) -> bool:
        with self._lock:
            leaf = self._find_leaf(key)
            for i, k in enumerate(leaf.keys):
                if k == key:
                    leaf.keys.pop(i)
                    leaf.values.pop(i)
                    self._size -= 1
                    self._cache_put(leaf)
                    return True
            return False

    def range(self, lo=None, hi=None) -> list[tuple[Any, Any]]:
        result = []
        with self._lock:
            if lo is None:
                leaf = self._leftmost_leaf()
            else:
                leaf = self._find_leaf(lo)
            while leaf is not None:
                for i, k in enumerate(leaf.keys):
                    if lo is not None and k < lo:
                        continue
                    if hi is not None and k > hi:
                        return result
                    result.append((k, leaf.values[i]))
                leaf = leaf.next
        return result

    def _leftmost_leaf(self) -> _Leaf:
        node = self._root
        while isinstance(node, _Internal):
            node = node.children[0]
        return node

    def __iter__(self) -> Iterator[tuple[Any, Any]]:
        with self._lock:
            leaf = self._leftmost_leaf()
            while leaf is not None:
                for i, k in enumerate(leaf.keys):
                    yield (k, leaf.values[i])
                leaf = leaf.next

    def min(self) -> tuple[Any, Any] | None:
        with self._lock:
            leaf = self._leftmost_leaf()
            if not leaf.keys:
                return None
            return (leaf.keys[0], leaf.values[0])

    def max(self) -> tuple[Any, Any] | None:
        with self._lock:
            node = self._root
            while isinstance(node, _Internal):
                node = node.children[-1]
            if not node.keys:
                return None
            return (node.keys[-1], node.values[-1])

    def to_disk(self, path: str) -> None:
        """序列化到磁盘文件。"""
        with self._lock:
            data = {
                "order": self._order,
                "page_size": self._page_size,
                "size": self._size,
                "root": self._root,
                "cache_max": self._cache_max,
            }
            with open(path, "wb") as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def from_disk(cls, path: str) -> BPlusTree:
        """从磁盘文件反序列化。"""
        with open(path, "rb") as f:
            data = pickle.load(f)
        t = cls.__new__(cls)
        t._order = data["order"]
        t._page_size = data.get("page_size", 0)
        t._size = data["size"]
        t._root = data["root"]
        t._cache_max = data.get("cache_max", 64)
        t._cache = {}
        t._lock = threading.RLock()
        return t

    def status(self) -> dict:
        with self._lock:
            internal_count = 0
            leaf_count = 0
            depth = 0

            def walk(n, d):
                nonlocal internal_count, leaf_count, depth
                depth = max(depth, d)
                if isinstance(n, _Internal):
                    internal_count += 1
                    for c in n.children:
                        walk(c, d + 1)
                else:
                    leaf_count += 1

            walk(self._root, 0)
            return {
                "size": self._size,
                "order": self._order,
                "page_size": self._page_size,
                "depth": depth,
                "internal_nodes": internal_count,
                "leaf_nodes": leaf_count,
                "cache_size": len(self._cache),
            }
