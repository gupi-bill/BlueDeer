"""BlueDeer Treap 树堆：BST 按 key + 堆按随机 priority。

特性：
- 二叉搜索树性质：左 < 根 < 右
- 堆性质：父 priority >= 子 priority（大顶堆）
- 期望高度 O(log n)
- 支持 split / merge

用法：
    t = Treap(seed=42)
    t.insert(5, "v5")
    t.get(5)
"""
from __future__ import annotations

import random
import threading
from typing import Any, Iterator, List, Optional, Tuple


class _Node:
    __slots__ = ("key", "value", "priority", "left", "right")

    def __init__(self, key, value, priority):
        self.key = key
        self.value = value
        self.priority = priority
        self.left: Optional[_Node] = None
        self.right: Optional[_Node] = None


class Treap:
    """Treap 树堆。"""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._root: Optional[_Node] = None
        self._rng = random.Random(seed)
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

    def _insert(self, node: Optional[_Node], key, value) -> _Node:
        if node is None:
            return _Node(key, value, self._rng.random())
        if key < node.key:
            node.left = self._insert(node.left, key, value)
            if node.left.priority > node.priority:
                node = self._rotate_right(node)
        elif key > node.key:
            node.right = self._insert(node.right, key, value)
            if node.right.priority > node.priority:
                node = self._rotate_left(node)
        else:
            node.value = value
        return node

    def insert(self, key, value: Any = None) -> None:
        with self._lock:
            new_before = self._size
            self._root = self._insert(self._root, key, value)
            # size 更新：检查是否真的新增
            # 简化：用一个 flag
            if self._count(self._root) > new_before:
                self._size = new_before + 1
            else:
                self._size = new_before

    def _count(self, node: Optional[_Node]) -> int:
        if node is None:
            return 0
        return 1 + self._count(node.left) + self._count(node.right)

    def _delete(self, node: Optional[_Node], key) -> Optional[_Node]:
        if node is None:
            return None
        if key < node.key:
            node.left = self._delete(node.left, key)
        elif key > node.key:
            node.right = self._delete(node.right, key)
        else:
            # 找到，下旋到叶
            if node.left is None:
                return node.right
            if node.right is None:
                return node.left
            if node.left.priority > node.right.priority:
                node = self._rotate_right(node)
                node.right = self._delete(node.right, key)
            else:
                node = self._rotate_left(node)
                node.left = self._delete(node.left, key)
        return node

    def delete(self, key) -> bool:
        with self._lock:
            if not self._contains(self._root, key):
                return False
            self._root = self._delete(self._root, key)
            self._size -= 1
            return True

    def _contains(self, node: Optional[_Node], key) -> bool:
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return True
        return False

    def get(self, key, default=None) -> Any:
        with self._lock:
            node = self._root
            while node is not None:
                if key < node.key:
                    node = node.left
                elif key > node.key:
                    node = node.right
                else:
                    return node.value
            return default

    def __contains__(self, key) -> bool:
        with self._lock:
            return self._contains(self._root, key)

    def split(self, key) -> Tuple["Treap", "Treap"]:
        """split 成两个：<= key 的和 > key 的。"""
        with self._lock:
            left_root, right_root = self._split(self._root, key)
            left = Treap()
            left._root = left_root
            left._size = self._count(left_root)
            right = Treap()
            right._root = right_root
            right._size = self._count(right_root)
            return left, right

    def _split(self, node: Optional[_Node], key) -> Tuple[Optional[_Node], Optional[_Node]]:
        if node is None:
            return None, None
        if key < node.key:
            l, r = self._split(node.left, key)
            node.left = r
            return l, node
        else:
            l, r = self._split(node.right, key)
            node.right = l
            return node, r

    def merge(self, other: "Treap") -> None:
        """合并另一个 treap（要求 other 所有 key > self 所有 key）。"""
        with self._lock:
            self._root = self._merge(self._root, other._root)
            self._size += other._size

    def _merge(self, a: Optional[_Node], b: Optional[_Node]) -> Optional[_Node]:
        if a is None:
            return b
        if b is None:
            return a
        if a.priority > b.priority:
            a.right = self._merge(a.right, b)
            return a
        else:
            b.left = self._merge(a, b.left)
            return b

    def items(self) -> Iterator[Tuple]:
        with self._lock:
            stack: List[_Node] = []
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

    def status(self) -> dict:
        return {"size": self._size, "root_priority": self._root.priority if self._root else None}

    def _pclone(self, node):
        if node is None:
            return None
        n = _Node(node.key, node.value, node.priority)
        n.left = node.left
        n.right = node.right
        return n

    def _pinsert(self, node, key, value):
        if node is None:
            return _Node(key, value, self._rng.random())
        node = self._pclone(node)
        if key < node.key:
            node.left = self._pinsert(node.left, key, value)
            if node.left.priority > node.priority:
                node = self._rotate_right(node)
        elif key > node.key:
            node.right = self._pinsert(node.right, key, value)
            if node.right.priority > node.priority:
                node = self._rotate_left(node)
        else:
            node.value = value
        return node

    def _pdelete(self, node, key):
        if node is None:
            return None
        node = self._pclone(node)
        if key < node.key:
            node.left = self._pdelete(node.left, key)
        elif key > node.key:
            node.right = self._pdelete(node.right, key)
        else:
            if node.left is None:
                return node.right
            if node.right is None:
                return node.left
            if node.left.priority > node.right.priority:
                node = self._rotate_right(node)
                node.right = self._pdelete(node.right, key)
            else:
                node = self._rotate_left(node)
                node.left = self._pdelete(node.left, key)
        return node

    def _psplit(self, node, key):
        if node is None:
            return None, None
        node = self._pclone(node)
        if key < node.key:
            l, r = self._psplit(node.left, key)
            node.left = r
            return l, node
        else:
            l, r = self._psplit(node.right, key)
            node.right = l
            return node, r

    def _pcontains(self, node, key):
        while node is not None:
            if key < node.key:
                node = node.left
            elif key > node.key:
                node = node.right
            else:
                return True
        return False

    def persistent_insert(self, key, value=None):
        new_root = self._pinsert(self._root, key, value)
        t = Treap()
        t._root = new_root
        exists = self._pcontains(self._root, key)
        t._size = self._size + (0 if exists else 1)
        return t

    def persistent_delete(self, key):
        if not self._pcontains(self._root, key):
            return self
        new_root = self._pdelete(self._root, key)
        t = Treap()
        t._root = new_root
        t._size = self._size - 1
        return t

    def persistent_split(self, key):
        l, r = self._psplit(self._root, key)
        left = Treap()
        left._root = l
        left._size = self._count(l)
        right = Treap()
        right._root = r
        right._size = self._count(r)
        return left, right
