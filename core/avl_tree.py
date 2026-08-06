"""BlueDeer AVL 树：自平衡二叉搜索树。

evolution（数据维度 - R205）：
- AVL 树是首个自平衡 BST，保证 |平衡因子| <= 1
- 插入/删除后通过 4 种旋转（LL/RR/LR/RL）维持平衡
- 高度 O(log n)，查找/插入/删除均 O(log n)
- 应用：内存索引、关联数组、C++ std::map 基础
- 与 B+树互补：B+树磁盘友好，AVL 内存友好且严格平衡
- 与跳表互补：跳表概率平衡，AVL 确定性平衡
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any


class _Node:
    """AVL 节点。"""

    __slots__ = ("height", "key", "left", "right", "value")

    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left: _Node | None = None
        self.right: _Node | None = None
        self.height = 1


class AVLTree:
    """AVL 树：自平衡二叉搜索树。

    用法：
        t = AVLTree()
        t.insert(10, "a")
        t.insert(20, "b")
        t.insert(5, "c")
        t.get(10)  -> "a"
        t.range(5, 15)  -> [(5,"c"), (10,"a")]
    """

    def __init__(self):
        self._root: _Node | None = None
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    @staticmethod
    def _h(node: _Node | None) -> int:
        return node.height if node else 0

    @staticmethod
    def _update_height(node: _Node) -> None:
        node.height = 1 + max(AVLTree._h(node.left), AVLTree._h(node.right))

    @staticmethod
    def _balance_factor(node: _Node) -> int:
        return AVLTree._h(node.left) - AVLTree._h(node.right)

    @staticmethod
    def _rotate_right(y: _Node) -> _Node:
        x = y.left
        t2 = x.right
        x.right = y
        y.left = t2
        AVLTree._update_height(y)
        AVLTree._update_height(x)
        return x

    @staticmethod
    def _rotate_left(x: _Node) -> _Node:
        y = x.right
        t2 = y.left
        y.left = x
        x.right = t2
        AVLTree._update_height(x)
        AVLTree._update_height(y)
        return y

    @staticmethod
    def _balance(node: _Node) -> _Node:
        AVLTree._update_height(node)
        bf = AVLTree._balance_factor(node)
        # 左重
        if bf > 1:
            if AVLTree._balance_factor(node.left) < 0:
                # LR：先左旋左子，再右旋
                node.left = AVLTree._rotate_left(node.left)
            return AVLTree._rotate_right(node)
        # 右重
        if bf < -1:
            if AVLTree._balance_factor(node.right) > 0:
                # RL：先右旋右子，再左旋
                node.right = AVLTree._rotate_right(node.right)
            return AVLTree._rotate_left(node)
        return node

    def insert_iterative(self, key: Any, value: Any = None) -> bool:
        with self._lock:
            if self._root is None:
                self._root = _Node(key, value)
                self._size += 1
                return True
            path = []
            cur = self._root
            while True:
                if key < cur.key:
                    path.append((cur, True))
                    if cur.left is None:
                        cur.left = _Node(key, value)
                        self._size += 1
                        break
                    cur = cur.left
                elif key > cur.key:
                    path.append((cur, False))
                    if cur.right is None:
                        cur.right = _Node(key, value)
                        self._size += 1
                        break
                    cur = cur.right
                else:
                    cur.value = value
                    return False
            for i in range(len(path) - 1, -1, -1):
                node, _ = path[i]
                self._update_height(node)
                bf = self._balance_factor(node)
                if bf > 1:
                    if self._balance_factor(node.left) < 0:
                        node.left = self._rotate_left(node.left)
                    new_sub = self._rotate_right(node)
                elif bf < -1:
                    if self._balance_factor(node.right) > 0:
                        node.right = self._rotate_right(node.right)
                    new_sub = self._rotate_left(node)
                else:
                    continue
                if i == 0:
                    self._root = new_sub
                else:
                    gp, gp_left = path[i - 1]
                    if gp_left:
                        gp.left = new_sub
                    else:
                        gp.right = new_sub
            return True

    def delete_iterative(self, key) -> bool:
        with self._lock:
            if self._root is None:
                return False
            path = []
            cur = self._root
            while cur is not None and cur.key != key:
                if key < cur.key:
                    path.append((cur, True))
                    cur = cur.left
                else:
                    path.append((cur, False))
                    cur = cur.right
            if cur is None:
                return False
            self._size -= 1
            if cur.left is not None and cur.right is not None:
                succ_path = [(cur, False)]
                succ = cur.right
                while succ.left is not None:
                    succ_path.append((succ, True))
                    succ = succ.left
                cur.key = succ.key
                cur.value = succ.value
                sp, sp_dir = succ_path[-1]
                if sp_dir:
                    sp.left = succ.right
                else:
                    sp.right = succ.right
                path = path + succ_path
            else:
                child = cur.left if cur.left else cur.right
                if not path:
                    self._root = child
                    return True
                parent, is_left = path[-1]
                if is_left:
                    parent.left = child
                else:
                    parent.right = child
            for i in range(len(path) - 1, -1, -1):
                node, _ = path[i]
                self._update_height(node)
                bf = self._balance_factor(node)
                if bf > 1:
                    if self._balance_factor(node.left) < 0:
                        node.left = self._rotate_left(node.left)
                    new_sub = self._rotate_right(node)
                elif bf < -1:
                    if self._balance_factor(node.right) > 0:
                        node.right = self._rotate_right(node.right)
                    new_sub = self._rotate_left(node)
                else:
                    continue
                if i == 0:
                    self._root = new_sub
                else:
                    gp, gp_left = path[i - 1]
                    if gp_left:
                        gp.left = new_sub
                    else:
                        gp.right = new_sub
            return True

    def insert(self, key: Any, value: Any = None) -> bool:
        """插入。返回是否新增（False=更新）。"""
        with self._lock:
            result = [True]
            self._root = self._insert(self._root, key, value, result)
            if result[0]:
                self._size += 1
            return result[0]

    def _insert(self, node, key, value, result) -> _Node:
        if node is None:
            return _Node(key, value)
        if key < node.key:
            node.left = self._insert(node.left, key, value, result)
        elif key > node.key:
            node.right = self._insert(node.right, key, value, result)
        else:
            node.value = value
            result[0] = False
            return node
        return self._balance(node)

    def get(self, key) -> Any:
        """查找。"""
        with self._lock:
            node = self._root
            while node is not None:
                if key < node.key:
                    node = node.left
                elif key > node.key:
                    node = node.right
                else:
                    return node.value
            return None

    def __contains__(self, key) -> bool:
        return self.get(key) is not None

    def remove(self, key) -> bool:
        """删除。返回是否删除。"""
        with self._lock:
            result = [False]
            self._root = self._delete(self._root, key, result)
            if result[0]:
                self._size -= 1
            return result[0]

    def _delete(self, node, key, result) -> _Node | None:
        if node is None:
            return None
        if key < node.key:
            node.left = self._delete(node.left, key, result)
        elif key > node.key:
            node.right = self._delete(node.right, key, result)
        else:
            result[0] = True
            if node.left is None:
                return node.right
            if node.right is None:
                return node.left
            # 两子节点：用后继替换
            succ = node.right
            while succ.left is not None:
                succ = succ.left
            node.key = succ.key
            node.value = succ.value
            node.right = self._delete(node.right, succ.key, [False])
        return self._balance(node)

    def min(self) -> tuple[Any, Any] | None:
        with self._lock:
            node = self._root
            if node is None:
                return None
            while node.left is not None:
                node = node.left
            return (node.key, node.value)

    def max(self) -> tuple[Any, Any] | None:
        with self._lock:
            node = self._root
            if node is None:
                return None
            while node.right is not None:
                node = node.right
            return (node.key, node.value)

    def range(self, lo: Any = None, hi: Any = None) -> list[tuple[Any, Any]]:
        """返回 [lo, hi] 内的元素。"""
        result = []
        with self._lock:
            self._range(self._root, lo, hi, result)
        return result

    def _range(self, node, lo, hi, result: list) -> None:
        if node is None:
            return
        if lo is None or node.key > lo:
            self._range(node.left, lo, hi, result)
        if (lo is None or node.key >= lo) and (hi is None or node.key <= hi):
            result.append((node.key, node.value))
        if hi is None or node.key < hi:
            self._range(node.right, lo, hi, result)

    def __iter__(self) -> Iterator[tuple[Any, Any]]:
        with self._lock:
            yield from self._inorder(self._root)

    def _inorder(self, node) -> Iterator[tuple[Any, Any]]:
        if node is None:
            return
        yield from self._inorder(node.left)
        yield (node.key, node.value)
        yield from self._inorder(node.right)

    def height(self) -> int:
        with self._lock:
            return self._h(self._root)

    def is_balanced(self) -> bool:
        """验证所有节点平衡因子在 [-1, 1]。"""
        with self._lock:

            def check(n) -> Any:
                if n is None:
                    return True
                if abs(self._balance_factor(n)) > 1:
                    return False
                return check(n.left) and check(n.right)

            return check(self._root)

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "height": self._h(self._root),
                "balanced": self.is_balanced(),
            }
