"""BlueDeer 区间树：重叠查询 + 增强 BST。

evolution（数据维度 - R197）：
- 区间树存储 [low, high] 区间，支持查询与给定区间重叠的所有区间
- 经典实现：增强 BST，按 low 排序，每节点额外存子树最大 max_end
- 查询剪枝：若左子树 max_end < low，跳过左子树
- 应用：日程冲突检测、内存分配、IP 范围查找、基因组重叠
- 与 B+树互补：B+树点查询，区间树区间查询
"""
from __future__ import annotations
import threading
from typing import Any, Iterator


def _overlaps(a_low, a_high, b_low, b_high) -> bool:
    """判断两区间是否重叠（闭区间）。"""
    return a_low <= b_high and b_low <= a_high


class _Node:
    """区间树节点。"""
    __slots__ = ("low", "high", "value", "max_end", "left", "right")

    def __init__(self, low, high, value):
        self.low = low
        self.high = high
        self.value = value
        self.max_end = high  # 子树中最大的 high
        self.left: _Node | None = None
        self.right: _Node | None = None


class IntervalTree:
    """区间树：存储区间 + 重叠查询。

    用法：
        it = IntervalTree()
        it.insert(1, 5, "A")
        it.insert(10, 20, "B")
        it.insert(15, 25, "C")
        it.query(12, 18)  # [B, C]（与 [12,18] 重叠）
        it.query_point(3)  # [A]（包含点 3）
    """

    def __init__(self):
        self._root: _Node | None = None
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def insert(self, low, high, value: Any = None) -> None:
        """插入区间 [low, high]。"""
        if low > high:
            raise ValueError("low 不能大于 high")
        with self._lock:
            self._root = self._insert(self._root, low, high, value)
            self._size += 1

    def _insert(self, node, low, high, value) -> _Node:
        if node is None:
            return _Node(low, high, value)
        if low < node.low:
            node.left = self._insert(node.left, low, high, value)
        else:
            node.right = self._insert(node.right, low, high, value)
        # 更新 max_end
        if high > node.max_end:
            node.max_end = high
        return node

    def query(self, low, high) -> list[tuple]:
        """查询与 [low, high] 重叠的所有区间。返回 [(low, high, value), ...]。"""
        if low > high:
            raise ValueError("low 不能大于 high")
        result = []
        with self._lock:
            self._query(self._root, low, high, result)
        return result

    def _query(self, node, low, high, result: list) -> None:
        if node is None:
            return
        # 当前节点是否重叠
        if _overlaps(node.low, node.high, low, high):
            result.append((node.low, node.high, node.value))
        # 左子树可能重叠：左子树 max_end >= low
        if node.left is not None and node.left.max_end >= low:
            self._query(node.left, low, high, result)
        # 右子树可能重叠：当前 low <= high 且右子树最小 low 可能 <= high
        # 简化：若 node.low <= high，右子树可能有重叠
        if node.right is not None and node.low <= high:
            self._query(node.right, low, high, result)

    def query_point(self, point) -> list[tuple]:
        """查询包含 point 的所有区间。"""
        return self.query(point, point)

    def remove(self, low, high) -> bool:
        """删除区间 [low, high]（按 low+high 匹配）。"""
        with self._lock:
            found = [False]
            self._root = self._remove(self._root, low, high, found)
            if found[0]:
                self._size -= 1
                # 重算 max_end
                self._root = self._recompute_max(self._root)
            return found[0]

    def _remove(self, node, low, high, found: list):
        if node is None:
            return None
        if low < node.low:
            node.left = self._remove(node.left, low, high, found)
        elif low > node.low:
            node.right = self._remove(node.right, low, high, found)
        else:
            # low 相同，检查 high
            if node.high != high:
                node.right = self._remove(node.right, low, high, found)
            else:
                # 找到了
                found[0] = True
                if node.left is None:
                    return node.right
                if node.right is None:
                    return node.left
                # 两个子节点：用后继替换
                succ = node.right
                while succ.left is not None:
                    succ = succ.left
                node.low = succ.low
                node.high = succ.high
                node.value = succ.value
                node.right = self._remove(node.right, succ.low, succ.high, [False])
        return node

    def _recompute_max(self, node):
        if node is None:
            return None
        node.left = self._recompute_max(node.left)
        node.right = self._recompute_max(node.right)
        node.max_end = node.high
        if node.left is not None and node.left.max_end > node.max_end:
            node.max_end = node.left.max_end
        if node.right is not None and node.right.max_end > node.max_end:
            node.max_end = node.right.max_end
        return node

    def __iter__(self) -> Iterator[tuple]:
        with self._lock:
            yield from self._inorder(self._root)

    def _inorder(self, node) -> Iterator[tuple]:
        if node is None:
            return
        yield from self._inorder(node.left)
        yield (node.low, node.high, node.value)
        yield from self._inorder(node.right)

    def _inorder_walk(self, node):
        if node is None:
            return
        yield from self._inorder_walk(node.left)
        yield (node.low, node.high, node.value)
        yield from self._inorder_walk(node.right)

    def merge_overlaps(self):
        with self._lock:
            items = list(self._inorder_walk(self._root))
            if not items:
                return []
            items.sort(key=lambda x: x[0])
            merged = []
            cur_low, cur_high, cur_vals = items[0][0], items[0][1], [items[0][2]]
            for lo, hi, val in items[1:]:
                if lo <= cur_high:
                    cur_high = max(cur_high, hi)
                    cur_vals.append(val)
                else:
                    merged.append((cur_low, cur_high, cur_vals))
                    cur_low, cur_high, cur_vals = lo, hi, [val]
            merged.append((cur_low, cur_high, cur_vals))
            return merged

    def covering(self, target_low, target_high):
        with self._lock:
            items = sorted(self._inorder_walk(self._root), key=lambda x: x[0])
            cover = []
            cur_end = target_low
            i, n = 0, len(items)
            while cur_end < target_high and i < n:
                best, best_end = None, cur_end
                while i < n and items[i][0] <= cur_end:
                    if items[i][1] > best_end:
                        best_end = items[i][1]
                        best = items[i]
                    i += 1
                if best is None:
                    return None
                cover.append(best)
                cur_end = best_end
            return cover if cur_end >= target_high else None

    def status(self) -> dict:
        with self._lock:
            def depth(n):
                if n is None:
                    return 0
                return 1 + max(depth(n.left), depth(n.right))
            return {
                "size": self._size,
                "depth": depth(self._root),
                "root_max_end": self._root.max_end if self._root else None,
            }
