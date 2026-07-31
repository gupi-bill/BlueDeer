"""BlueDeer 二叉堆：数组实现 + O(n) 建堆。

特性：
- 完全二叉树，用数组存储
- 小顶堆：父 <= 子
- sift_up / sift_down 优化（记录 item 后单次赋值）
- O(n) 建堆（自底向下 sift_down）
- decrease_key / make_heap / k_way_merge

用法：
    h = BinaryHeap()
    h.push(3, "v3")
    h.push(1, "v1")
    h.pop()  # (1, "v1")
"""
from __future__ import annotations

import threading
from typing import Any, Iterator, List, Optional, Tuple


class _Entry:
    __slots__ = ("key", "value")

    def __init__(self, key, value):
        self.key = key
        self.value = value


class BinaryHeap:
    """小顶二叉堆。"""

    def __init__(self) -> None:
        self._data: List[_Entry] = []
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return len(self._data)

    def _sift_up(self, i: int) -> None:
        data = self._data
        item = data[i]
        while i > 0:
            parent = (i - 1) >> 1
            if data[parent].key <= item.key:
                break
            data[i] = data[parent]
            i = parent
        data[i] = item

    def _sift_down(self, i: int) -> None:
        data = self._data
        n = len(data)
        item = data[i]
        half = n >> 1
        while i < half:
            child = (i << 1) + 1
            right = child + 1
            if right < n and data[right].key < data[child].key:
                child = right
            if data[child].key >= item.key:
                break
            data[i] = data[child]
            i = child
        data[i] = item

    def push(self, key, value: Any = None) -> None:
        with self._lock:
            self._data.append(_Entry(key, value))
            self._sift_up(len(self._data) - 1)

    def pop(self) -> Tuple:
        """弹出最小元素。"""
        with self._lock:
            if not self._data:
                raise IndexError("pop from empty heap")
            data = self._data
            top = data[0]
            last = data.pop()
            if data:
                data[0] = last
                self._sift_down(0)
            return (top.key, top.value)

    def peek(self) -> Tuple:
        with self._lock:
            if not self._data:
                raise IndexError("peek from empty heap")
            e = self._data[0]
            return (e.key, e.value)

    def replace(self, key, value: Any = None) -> Tuple:
        """弹出最小并插入新元素（比 pop+push 快）。"""
        with self._lock:
            if not self._data:
                self._data.append(_Entry(key, value))
                raise IndexError("replace from empty heap")
            top = self._data[0]
            self._data[0] = _Entry(key, value)
            self._sift_down(0)
            return (top.key, top.value)

    def decrease_key(self, idx: int, new_key) -> None:
        """降低 idx 位置的 key（小顶堆，新 key 必须更小）。"""
        with self._lock:
            if idx < 0 or idx >= len(self._data):
                raise IndexError("index out of range")
            if new_key > self._data[idx].key:
                raise ValueError("new_key must be <= old key")
            self._data[idx].key = new_key
            self._sift_up(idx)

    def heapify(self, items) -> None:
        """O(n) 批量建堆。"""
        with self._lock:
            self._data = [_Entry(k, v) for k, v in items]
            for i in range((len(self._data) >> 1) - 1, -1, -1):
                self._sift_down(i)

    def sorted_items(self) -> Iterator[Tuple]:
        """返回排序后的元素（不破坏原堆，拷贝）。"""
        with self._lock:
            data = list(self._data)
        n = len(data)
        result = []
        temp = BinaryHeap()
        temp._data = data
        for _ in range(n):
            result.append(temp.pop())
        return iter(result)

    def clear(self) -> None:
        with self._lock:
            self._data = []

    def status(self) -> dict:
        return {"size": len(self._data)}

    @staticmethod
    def make_heap(arr: list[Tuple]) -> BinaryHeap:
        """O(n) 从任意 (key, value) 列表构建堆。"""
        h = BinaryHeap()
        h.heapify(arr)
        return h

    @staticmethod
    def k_way_merge(*heaps: BinaryHeap) -> Iterator[Tuple]:
        """合并 k 个有序堆的输出为一个有序迭代器。"""
        from heapq import heappush, heappop
        heap = []
        for hi, h in enumerate(heaps):
            if len(h) > 0:
                k, v = h.pop()
                heappush(heap, (k, v, hi))
        while heap:
            k, v, hi = heappop(heap)
            yield (k, v)
            h = heaps[hi]
            if len(h) > 0:
                k2, v2 = h.pop()
                heappush(heap, (k2, v2, hi))
