"""BlueDeer KD-Tree：多维空间索引 + 最近邻查询。

evolution（数据维度 - R198）：
- KD-Tree 是 k 维空间二叉树，每层按不同维度切分
- 支持最近邻（KNN）查询、范围查询
- 应用：空间索引、推荐系统 KNN、图像检索、异常检测
- 与区间树互补：区间树 1D 区间重叠，KD-Tree k 维近邻
"""
from __future__ import annotations
import heapq
import itertools
import math
import threading
from typing import Any, Iterator


class _Node:
    __slots__ = ("point", "value", "axis", "left", "right", "deleted")

    def __init__(self, point, value, axis):
        self.point = point
        self.value = value
        self.axis = axis
        self.left: _Node | None = None
        self.right: _Node | None = None
        self.deleted = False


def _sq_dist(a, b) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


class KDTree:
    """KD-Tree：k 维空间索引。

    用法：
        kd = KDTree(k=2)
        kd.insert((1, 2), "A")
        kd.insert((3, 4), "B")
        kd.insert((5, 6), "C")
        nn = kd.nearest((2, 3))
        knn = kd.knn_search((2, 3), k=2)
        pts = kd.range_query((0, 0), (4, 4))
        kd.delete((3, 4))
    """

    def __init__(self, k: int = 2):
        if k < 1:
            raise ValueError("k >= 1")
        self._k = k
        self._root: _Node | None = None
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def insert(self, point, value: Any = None) -> None:
        if len(point) != self._k:
            raise ValueError(f"点维度应为 {self._k}")
        with self._lock:
            self._root = self._insert(self._root, point, value, 0)
            self._size += 1

    def _insert(self, node, point, value, depth) -> _Node:
        if node is None:
            return _Node(point, value, depth % self._k)
        if node.deleted:
            node.deleted = False
            self._size += 1
            return node
        axis = node.axis
        if point[axis] < node.point[axis]:
            node.left = self._insert(node.left, point, value, depth + 1)
        else:
            node.right = self._insert(node.right, point, value, depth + 1)
        return node

    def delete(self, point) -> bool:
        """删除指定点（惰性删除）。返回是否存在。"""
        with self._lock:
            node = self._root
            while node is not None:
                if node.point == point and not node.deleted:
                    node.deleted = True
                    self._size -= 1
                    return True
                axis = node.axis
                if point[axis] < node.point[axis]:
                    node = node.left
                else:
                    node = node.right
            return False

    def nearest(self, point) -> tuple[tuple, Any, float] | None:
        with self._lock:
            if self._root is None:
                return None
            best = [None, float("inf")]
            self._nearest(self._root, point, best)
            if best[0] is None:
                return None
            d = math.sqrt(best[1])
            return (best[0].point, best[0].value, d)

    def _nearest(self, node, point, best: list) -> None:
        if node is None or node.deleted:
            return
        d = _sq_dist(point, node.point)
        if d < best[1]:
            best[0] = node
            best[1] = d
        axis = node.axis
        diff = point[axis] - node.point[axis]
        near = node.left if diff < 0 else node.right
        far = node.right if diff < 0 else node.left
        self._nearest(near, point, best)
        if diff * diff < best[1]:
            self._nearest(far, point, best)

    def knn(self, point, k: int) -> list[tuple]:
        return self.knn_search(point, k)

    def knn_search(self, point, k: int) -> list[tuple]:
        if k < 1:
            raise ValueError("k >= 1")
        with self._lock:
            if self._root is None:
                return []
            heap = []
            self._knn(self._root, point, k, heap)
            result = []
            for neg_d, _, node in sorted(heap, key=lambda x: -x[0]):
                result.append((node.point, node.value, math.sqrt(-neg_d)))
            return result

    def _knn(self, node, point, k, heap: list) -> None:
        if node is None or node.deleted:
            return
        d = _sq_dist(point, node.point)
        if len(heap) < k:
            heapq.heappush(heap, (-d, next(self._counter), node))
        elif d < -heap[0][0]:
            heapq.heapreplace(heap, (-d, next(self._counter), node))
        axis = node.axis
        diff = point[axis] - node.point[axis]
        near = node.left if diff < 0 else node.right
        far = node.right if diff < 0 else node.left
        self._knn(near, point, k, heap)
        if len(heap) < k or diff * diff < -heap[0][0]:
            self._knn(far, point, k, heap)

    _counter = itertools.count()

    def range_query(self, lo, hi) -> list[tuple]:
        with self._lock:
            result = []
            self._range(self._root, lo, hi, result)
            return result

    def _range(self, node, lo, hi, result: list) -> None:
        if node is None or node.deleted:
            return
        in_range = all(lo[i] <= node.point[i] <= hi[i] for i in range(self._k))
        if in_range:
            result.append((node.point, node.value))
        axis = node.axis
        if node.point[axis] >= lo[axis]:
            self._range(node.left, lo, hi, result)
        if node.point[axis] <= hi[axis]:
            self._range(node.right, lo, hi, result)

    def __iter__(self) -> Iterator[tuple]:
        with self._lock:
            yield from self._inorder(self._root)

    def _inorder(self, node) -> Iterator[tuple]:
        if node is None:
            return
        yield from self._inorder(node.left)
        if not node.deleted:
            yield (node.point, node.value)
        yield from self._inorder(node.right)

    def status(self) -> dict:
        with self._lock:
            def depth(n):
                if n is None:
                    return 0
                return 1 + max(depth(n.left), depth(n.right))
            return {
                "size": self._size,
                "dimensions": self._k,
                "depth": depth(self._root),
            }
