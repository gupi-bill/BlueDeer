"""BlueDeer 伸展树：自底向上 splay。

特性：
- 访问过的节点会被 splay 到根
- 摊还 O(log n)
- 最近访问的数据更快

用法：
    tree = SplayTree()
    tree.insert(5, "v5")
    tree.get(5)  # "v5"（5 被 splay 到根）
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any


class _Node:
    __slots__ = ("key", "left", "right", "value")

    def __init__(self, key, value=None):
        self.key = key
        self.value = value
        self.left: _Node | None = None
        self.right: _Node | None = None


class SplayTree:
    """自底向上 Splay 伸展树（递归实现，简单可靠）。"""

    def __init__(self) -> None:
        self._root: _Node | None = None
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def _rotate_right(self, y: _Node) -> _Node:
        x = y.left
        y.left = x.right
        x.right = y
        return x

    def _rotate_left(self, x: _Node) -> _Node:
        y = x.right
        x.right = y.left
        y.left = x
        return y

    def _splay(self, node: _Node | None, key) -> _Node:
        """递归 splay：把 key 对应节点 splay 到根并返回。"""
        if node is None:
            return None
        if key < node.key:
            if node.left is None:
                return node
            if key < node.left.key:
                # zig-zig
                node.left.left = self._splay(node.left.left, key)
                node = self._rotate_right(node)
            elif key > node.left.key:
                # zig-zag
                node.left.right = self._splay(node.left.right, key)
                if node.left.right is not None:
                    node.left = self._rotate_left(node.left)
            return self._rotate_right(node) if node.left else node
        elif key > node.key:
            if node.right is None:
                return node
            if key > node.right.key:
                # zig-zig
                node.right.right = self._splay(node.right.right, key)
                node = self._rotate_left(node)
            elif key < node.right.key:
                # zig-zag
                node.right.left = self._splay(node.right.left, key)
                if node.right.left is not None:
                    node.right = self._rotate_right(node.right)
            return self._rotate_left(node) if node.right else node
        else:
            return node

    def insert(self, key: Any, value: Any = None) -> None:
        with self._lock:
            if self._root is None:
                self._root = _Node(key, value)
                self._size += 1
                return
            self._root = self._splay(self._root, key)
            if self._root.key == key:
                self._root.value = value
                return
            new = _Node(key, value)
            if key < self._root.key:
                new.right = self._root
                new.left = self._root.left
                self._root.left = None
            else:
                new.left = self._root
                new.right = self._root.right
                self._root.right = None
            self._root = new
            self._size += 1

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            if self._root is None:
                return default
            self._root = self._splay(self._root, key)
            if self._root and self._root.key == key:
                return self._root.value
            return default

    def delete(self, key) -> bool:
        with self._lock:
            if self._root is None:
                return False
            self._root = self._splay(self._root, key)
            if self._root is None or self._root.key != key:
                return False
            # 节点已在根
            node = self._root
            if node.left is None:
                self._root = node.right
            elif node.right is None:
                self._root = node.left
            else:
                # 找右子树最小节点的 key
                min_node = node.right
                while min_node.left is not None:
                    min_node = min_node.left
                # 把这个最小节点 splay 到右子树根
                right_root = self._splay(node.right, min_node.key)
                right_root.left = node.left
                self._root = right_root
            self._size -= 1
            return True

    def __contains__(self, key) -> bool:
        with self._lock:
            if self._root is None:
                return False
            self._root = self._splay(self._root, key)
            return self._root is not None and self._root.key == key

    def items(self) -> Iterator[tuple]:
        with self._lock:
            stack: list[_Node] = []
            n = self._root
            while n is not None or stack:
                while n is not None:
                    stack.append(n)
                    n = n.left
                n = stack.pop()
                yield (n.key, n.value)
                n = n.right

    def clear(self) -> None:
        with self._lock:
            self._root = None
            self._size = 0

    @staticmethod
    def _count(node):
        if node is None:
            return 0
        return 1 + SplayTree._count(node.left) + SplayTree._count(node.right)

    def split(self, key) -> Any:
        with self._lock:
            if self._root is None:
                return SplayTree(), SplayTree()
            self._root = self._splay(self._root, key)
            left = SplayTree()
            right = SplayTree()
            if self._root.key > key:
                left._root = self._root.left
                right._root = self._root
                right._root.left = None
            else:
                left._root = self._root
                right._root = self._root.right
                left._root.right = None
            left._size = self._count(left._root)
            right._size = self._count(right._root)
            return left, right

    @staticmethod
    def merge(left: Any, right) -> Any:
        if left._root is None:
            return right
        if right._root is None:
            return left
        max_node = left._root
        while max_node.right is not None:
            max_node = max_node.right
        left._root = left._splay(left._root, max_node.key)
        left._root.right = right._root
        left._size += right._size
        return left

    def status(self) -> dict:
        return {"size": self._size, "root_key": self._root.key if self._root else None}
