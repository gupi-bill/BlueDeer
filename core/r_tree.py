"""BlueDeer R-Tree：空间矩形索引 + 范围查询。

evolution（数据维度 - R201）：
- R-Tree 存储矩形/点，支持范围查询、空间包含查询
- 节点存 MBR（最小外接矩形）+ 子节点
- 插入选择扩展面积最小的子树，满了分裂
- 应用：GIS 空间索引、数据库空间查询、碰撞检测
- 与 KD-Tree 互补：KD-Tree 点近邻，R-Tree 矩形范围
"""
from __future__ import annotations
import math
import threading
from typing import Any, Iterator


def _area(rect) -> float:
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def _mbr(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]),
            max(a[2], b[2]), max(a[3], b[3]))


def _contains(outer, inner) -> bool:
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def _intersects(a, b) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _rect_center(rect):
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def _point_dist2(pt, rect):
    cx = max(rect[0], min(pt[0], rect[2]))
    cy = max(rect[1], min(pt[1], rect[3]))
    return (pt[0] - cx) ** 2 + (pt[1] - cy) ** 2


class _Entry:
    __slots__ = ("mbr", "value", "child")

    def __init__(self, mbr, value=None, child=None):
        self.mbr = mbr
        self.value = value
        self.child = child


class _Node:
    __slots__ = ("entries", "is_leaf")

    def __init__(self, is_leaf=True):
        self.entries: list[_Entry] = []
        self.is_leaf = is_leaf

    def mbr(self):
        if not self.entries:
            return None
        m = self.entries[0].mbr
        for e in self.entries[1:]:
            m = _mbr(m, e.mbr)
        return m


class RTree:
    """R-Tree：2D 空间矩形索引。

    用法：
        rt = RTree(max_entries=8)
        rt.insert((0, 0, 10, 10), "A")
        rt.insert_point((5, 5), "B")
        rt.search_point((3, 3))   # [A]
        rt.search_rect((2, 2, 8, 8))  # [A, B]
        rt.nearest_neighbors((1, 1), 2)  # 最近邻
    """

    def __init__(self, max_entries: int = 8, min_entries: int = 3):
        if max_entries < 4 or min_entries < 1 or min_entries > max_entries // 2:
            raise ValueError("max>=4, 1<=min<=max/2")
        self._M = max_entries
        self._m = min_entries
        self._root = _Node(is_leaf=True)
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def insert(self, rect, value: Any = None) -> None:
        if len(rect) != 4:
            raise ValueError("rect 长度 4")
        if rect[0] > rect[2] or rect[1] > rect[3]:
            raise ValueError("min <= max")
        with self._lock:
            entry = _Entry(rect, value=value)
            self._insert_entry(self._root, entry)
            self._size += 1
            if len(self._root.entries) > self._M:
                left, right = self._split(self._root)
                new_root = _Node(is_leaf=False)
                new_root.entries = [
                    _Entry(left.mbr(), child=left),
                    _Entry(right.mbr(), child=right),
                ]
                self._root = new_root

    def insert_point(self, point, value: Any = None) -> None:
        x, y = point
        self.insert((x, y, x, y), value)

    def bulk_insert(self, rects: list, data: list | None = None) -> None:
        """STR 批量插入：Sort-Tile-Recursive 算法。

        rects: [(min_x, min_y, max_x, max_y), ...]
        data:  [value, ...] 或 None
        """
        if data is None:
            data = [None] * len(rects)
        if len(rects) != len(data):
            raise ValueError("rects 与 data 长度必须一致")
        if not rects:
            return
        nodes = self._str_build(rects, data, self._M)
        with self._lock:
            self._root = nodes[0] if len(nodes) == 1 else self._str_make_internal(nodes)
            self._size += len(rects)

    def _str_build(self, rects: list, data: list, fanout: int) -> list[_Node]:
        """STR 递归构建：返回叶子或内部节点列表。"""
        n = len(rects)
        if n <= fanout:
            leaf = _Node(is_leaf=True)
            leaf.entries = [_Entry(rects[i], value=data[i]) for i in range(n)]
            return [leaf]

        p = max(1, int(math.sqrt(n / fanout * fanout)))
        s = max(1, int(math.ceil(n / p / fanout)))
        slices = []
        idx = sorted(range(n), key=lambda i: _rect_center(rects[i])[0])
        for sl in range(p):
            start = sl * (n // p)
            end = n if sl == p - 1 else (sl + 1) * (n // p)
            slice_idx = idx[start:end]
            slice_idx.sort(key=lambda i: _rect_center(rects[i])[1])
            for t in range(0, len(slice_idx), s):
                tile = slice_idx[t:t + s]
                if len(tile) <= fanout:
                    leaf = _Node(is_leaf=True)
                    leaf.entries = [_Entry(rects[i], value=data[i]) for i in tile]
                    slices.append(leaf)
                else:
                    slices.extend(self._str_build(
                        [rects[i] for i in tile],
                        [data[i] for i in tile],
                        fanout,
                    ))
        return slices

    def _str_make_internal(self, children: list[_Node]) -> _Node:
        n = len(children)
        if n <= self._M:
            node = _Node(is_leaf=False)
            node.entries = [_Entry(c.mbr(), child=c) for c in children]
            return node
        p = max(1, int(math.sqrt(n / self._M * self._M)))
        s = max(1, int(math.ceil(n / p / self._M)))
        groups = []
        children.sort(key=lambda c: _rect_center(c.mbr())[0])
        for sl in range(p):
            start = sl * (n // p)
            end = n if sl == p - 1 else (sl + 1) * (n // p)
            group = children[start:end]
            group.sort(key=lambda c: _rect_center(c.mbr())[1])
            for t in range(0, len(group), s):
                tile = group[t:t + s]
                if len(tile) <= self._M:
                    node = _Node(is_leaf=False)
                    node.entries = [_Entry(c.mbr(), child=c) for c in tile]
                    groups.append(node)
                else:
                    sub = self._str_make_internal(tile)
                    groups.append(sub)
        return self._str_make_internal(groups) if len(groups) > 1 else groups[0]

    def _insert_entry(self, node: _Node, entry: _Entry) -> None:
        if node.is_leaf:
            node.entries.append(entry)
            return
        best_idx = self._choose_subtree(node, entry.mbr)
        child = node.entries[best_idx].child
        before_mbr = node.entries[best_idx].mbr
        self._insert_entry(child, entry)
        new_mbr = _mbr(before_mbr, entry.mbr)
        node.entries[best_idx].mbr = new_mbr
        if len(child.entries) > self._M:
            left, right = self._split(child)
            node.entries.pop(best_idx)
            node.entries.append(_Entry(left.mbr(), child=left))
            node.entries.append(_Entry(right.mbr(), child=right))

    def _choose_subtree(self, node: _Node, mbr) -> int:
        best_idx = 0
        best_enlarge = float("inf")
        for i, e in enumerate(node.entries):
            cur_area = _area(e.mbr)
            new_area = _area(_mbr(e.mbr, mbr))
            enlarge = new_area - cur_area
            if enlarge < best_enlarge:
                best_enlarge = enlarge
                best_idx = i
        return best_idx

    def _split(self, node: _Node) -> tuple[_Node, _Node]:
        entries = node.entries
        entries.sort(key=lambda e: (e.mbr[0], e.mbr[1]))
        mid = len(entries) // 2
        left = _Node(is_leaf=node.is_leaf)
        right = _Node(is_leaf=node.is_leaf)
        left.entries = entries[:mid]
        right.entries = entries[mid:]
        return left, right

    def search_point(self, point) -> list:
        x, y = point
        return self.search_rect((x, y, x, y))

    def search_rect(self, rect) -> list:
        result = []
        with self._lock:
            self._search(self._root, rect, result)
        return result

    def _search(self, node: _Node, rect, result: list) -> None:
        for e in node.entries:
            if not _intersects(e.mbr, rect):
                continue
            if node.is_leaf:
                result.append((e.mbr, e.value))
            else:
                self._search(e.child, rect, result)

    def nearest_neighbors(self, pt, k: int = 1) -> list[tuple]:
        """k 最近邻查询。返回 [(rect, value, distance), ...] 按距离升序。"""
        if k < 1:
            raise ValueError("k >= 1")
        result = []
        with self._lock:
            if self._root is None or not self._root.entries:
                return result
            heap = []  # [(-dist2, entry, node, is_leaf), ...] 最大堆
            import heapq
            for e in self._root.entries:
                d2 = _point_dist2(pt, e.mbr)
                heapq.heappush(heap, (d2, 0, e, self._root.is_leaf, id(e)))
            while heap and len(result) < k:
                d2, _, e, is_leaf, _ = heapq.heappop(heap)
                if is_leaf:
                    result.append((e.mbr, e.value, math.sqrt(d2)))
                else:
                    for ce in e.child.entries:
                        cd2 = _point_dist2(pt, ce.mbr)
                        heapq.heappush(heap, (cd2, 0, ce, e.child.is_leaf, id(ce)))
        return result

    def __iter__(self) -> Iterator[tuple]:
        with self._lock:
            yield from self._iter_node(self._root)

    def _iter_node(self, node: _Node) -> Iterator[tuple]:
        for e in node.entries:
            if node.is_leaf:
                yield (e.mbr, e.value)
            else:
                yield from self._iter_node(e.child)

    def status(self) -> dict:
        with self._lock:
            def count(n: _Node) -> tuple[int, int, int]:
                if n.is_leaf:
                    return (1, 1, 0)
                total = 1
                leaves = 0
                internals = 0
                for e in n.entries:
                    t, l, i = count(e.child)
                    total += t
                    leaves += l
                    internals += i
                return (total, leaves, internals + 1)
            def depth(n: _Node) -> int:
                if n.is_leaf:
                    return 1
                return 1 + max(depth(e.child) for e in n.entries)
            total_nodes, leaves, internals = count(self._root)
            return {
                "size": self._size,
                "max_entries": self._M,
                "depth": depth(self._root),
                "total_nodes": total_nodes,
                "leaf_nodes": leaves,
                "internal_nodes": internals,
            }
