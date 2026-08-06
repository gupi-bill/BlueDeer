"""BlueDeer 红黑树：自平衡 BST + 旋转着色。

evolution（数据维度 - R206）：
- 红黑树是工业级自平衡 BST，保证高度 O(log n)
- 五大性质：根黑、叶黑、红不连续、黑高相同
- 插入/删除通过旋转 + 重新着色维持平衡
- 应用：Linux CFS 调度、C++ std::map、Java TreeMap、epoll
- 与 AVL 互补：AVL 严格平衡查找快，红黑树宽松平衡写入快
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any


class _Node:
    __slots__ = ("color", "key", "left", "parent", "right", "value")

    def __init__(self, key, value=None, color="RED"):
        self.key = key
        self.value = value
        self.color = color
        self.left: _Node = None
        self.right: _Node = None
        self.parent: _Node = None


class RBTree:
    """红黑树（CLRS 经典实现，NIL sentinel，完整删修复）。

    用法：
        t = RBTree()
        t.insert(10, "a")
        t.insert(20, "b")
        t.get(10)   -> "a"
        t.delete(10)
        t.min()     -> (10, "a")
        t.max()     -> (20, "b")
    """

    RED = "RED"
    BLACK = "BLACK"

    def __init__(self) -> None:
        self._nil = _Node(None, None, self.BLACK)
        self._nil.left = self._nil
        self._nil.right = self._nil
        self._nil.parent = self._nil
        self._root = self._nil
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def _is_red(self, n: _Node) -> bool:
        return n is not self._nil and n.color == self.RED

    def _rotate_left(self, x: _Node) -> None:
        y = x.right
        x.right = y.left
        if y.left is not self._nil:
            y.left.parent = x
        y.parent = x.parent
        if x.parent is self._nil:
            self._root = y
        elif x is x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        y.left = x
        x.parent = y

    def _rotate_right(self, x: _Node) -> None:
        y = x.left
        x.left = y.right
        if y.right is not self._nil:
            y.right.parent = x
        y.parent = x.parent
        if x.parent is self._nil:
            self._root = y
        elif x is x.parent.right:
            x.parent.right = y
        else:
            x.parent.left = y
        y.right = x
        x.parent = y

    def _insert_fixup(self, z: _Node) -> None:
        while self._is_red(z.parent):
            if z.parent is z.parent.parent.left:
                y = z.parent.parent.right
                if self._is_red(y):
                    z.parent.color = self.BLACK
                    y.color = self.BLACK
                    z.parent.parent.color = self.RED
                    z = z.parent.parent
                else:
                    if z is z.parent.right:
                        z = z.parent
                        self._rotate_left(z)
                    z.parent.color = self.BLACK
                    z.parent.parent.color = self.RED
                    self._rotate_right(z.parent.parent)
            else:
                y = z.parent.parent.left
                if self._is_red(y):
                    z.parent.color = self.BLACK
                    y.color = self.BLACK
                    z.parent.parent.color = self.RED
                    z = z.parent.parent
                else:
                    if z is z.parent.left:
                        z = z.parent
                        self._rotate_right(z)
                    z.parent.color = self.BLACK
                    z.parent.parent.color = self.RED
                    self._rotate_left(z.parent.parent)
        self._root.color = self.BLACK

    def insert(self, key: Any, value: Any = None) -> bool:
        """插入 key-value。返回是否新增（False 表示更新已有）。"""
        with self._lock:
            z = _Node(key, value, self.RED)
            z.left = self._nil
            z.right = self._nil
            y = self._nil
            x = self._root
            while x is not self._nil:
                y = x
                if key < x.key:
                    x = x.left
                elif key > x.key:
                    x = x.right
                else:
                    x.value = value
                    return False
            z.parent = y
            if y is self._nil:
                self._root = z
            elif key < y.key:
                y.left = z
            else:
                y.right = z
            self._size += 1
            self._insert_fixup(z)
            return True

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            n = self._find(key)
            return n.value if n is not self._nil else default

    def _find(self, key) -> _Node:
        n = self._root
        while n is not self._nil:
            if key < n.key:
                n = n.left
            elif key > n.key:
                n = n.right
            else:
                return n
        return self._nil

    def __contains__(self, key) -> bool:
        return self._find(key) is not self._nil

    def _transplant(self, u: _Node, v: _Node) -> None:
        if u.parent is self._nil:
            self._root = v
        elif u is u.parent.left:
            u.parent.left = v
        else:
            u.parent.right = v
        v.parent = u.parent

    def _minimum(self, n: _Node) -> _Node:
        while n.left is not self._nil:
            n = n.left
        return n

    def _delete_fixup(self, x: _Node) -> None:
        while x is not self._root and not self._is_red(x):
            if x is x.parent.left:
                w = x.parent.right
                if self._is_red(w):
                    w.color = self.BLACK
                    x.parent.color = self.RED
                    self._rotate_left(x.parent)
                    w = x.parent.right
                if not self._is_red(w.left) and not self._is_red(w.right):
                    w.color = self.RED
                    x = x.parent
                else:
                    if not self._is_red(w.right):
                        w.left.color = self.BLACK
                        w.color = self.RED
                        self._rotate_right(w)
                        w = x.parent.right
                    w.color = x.parent.color
                    x.parent.color = self.BLACK
                    w.right.color = self.BLACK
                    self._rotate_left(x.parent)
                    x = self._root
            else:
                w = x.parent.left
                if self._is_red(w):
                    w.color = self.BLACK
                    x.parent.color = self.RED
                    self._rotate_right(x.parent)
                    w = x.parent.left
                if not self._is_red(w.left) and not self._is_red(w.right):
                    w.color = self.RED
                    x = x.parent
                else:
                    if not self._is_red(w.left):
                        w.right.color = self.BLACK
                        w.color = self.RED
                        self._rotate_left(w)
                        w = x.parent.left
                    w.color = x.parent.color
                    x.parent.color = self.BLACK
                    w.left.color = self.BLACK
                    self._rotate_right(x.parent)
                    x = self._root
        x.color = self.BLACK

    def delete(self, key) -> bool:
        """删除 key。返回是否曾存在。"""
        with self._lock:
            z = self._find(key)
            if z is self._nil:
                return False
            y = z
            y_orig_color = y.color
            if z.left is self._nil:
                x = z.right
                self._transplant(z, z.right)
            elif z.right is self._nil:
                x = z.left
                self._transplant(z, z.left)
            else:
                y = self._minimum(z.right)
                y_orig_color = y.color
                x = y.right
                if y.parent is z:
                    x.parent = y
                else:
                    self._transplant(y, y.right)
                    y.right = z.right
                    y.right.parent = y
                self._transplant(z, y)
                y.left = z.left
                y.left.parent = y
                y.color = z.color
            if y_orig_color == self.BLACK:
                self._delete_fixup(x)
            self._size -= 1
            return True

    def __iter__(self) -> Iterator[tuple]:
        return self.items()

    def items(self) -> Iterator[tuple]:
        """中序遍历（升序）。"""
        with self._lock:
            stack = []
            n = self._root
            while n is not self._nil or stack:
                while n is not self._nil:
                    stack.append(n)
                    n = n.left
                n = stack.pop()
                yield (n.key, n.value)
                n = n.right

    def min(self) -> tuple | None:
        with self._lock:
            if self._root is self._nil:
                return None
            n = self._minimum(self._root)
            return (n.key, n.value)

    def max(self) -> tuple | None:
        with self._lock:
            n = self._root
            if n is self._nil:
                return None
            while n.right is not self._nil:
                n = n.right
            return (n.key, n.value)

    def height(self) -> int:
        with self._lock:

            def h(n: _Node) -> int:
                if n is self._nil:
                    return 0
                return 1 + max(h(n.left), h(n.right))

            return h(self._root)

    def _bh(self, n: _Node) -> int:
        if n is self._nil:
            return 1
        l = self._bh(n.left)
        r = self._bh(n.right)
        if l != r or l == -1:
            return -1
        return l + (1 if n.color == self.BLACK else 0)

    def _check_red_children(self, n: _Node) -> bool:
        if n is self._nil:
            return True
        if self._is_red(n):
            if self._is_red(n.left) or self._is_red(n.right):
                return False
        return self._check_red_children(n.left) and self._check_red_children(n.right)

    def is_valid(self) -> bool:
        """验证红黑性质。"""
        with self._lock:
            if self._is_red(self._root):
                return False
            if self._bh(self._root) == -1:
                return False
            return self._check_red_children(self._root)

    def clear(self) -> None:
        with self._lock:
            self._root = self._nil
            self._size = 0

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "height": self.height(),
                "valid": self.is_valid(),
            }
