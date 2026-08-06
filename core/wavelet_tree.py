"""BlueDeer Wavelet Tree：序列索引 + rank/select。

evolution（数据维度 - R204）：
- Wavelet Tree 对序列按字符集递归二分，支持高效 rank/select
- rank(i, c)：前 i 位置中 c 的数量
- select(k, c)：第 k 个 c 的位置
- access(i)：第 i 位置的字符
- range_count(l, r, c)：[l,r) 中 c 的数量
- 应用：全文索引、序列压缩、基因组分析
- 与后缀数组互补：后缀数组子串搜索，Wavelet Tree 字符频率
"""

from __future__ import annotations

import threading
from typing import Any


class _WaveletNode:
    """Wavelet Tree 节点。"""

    __slots__ = ("bits", "hi", "left", "lo", "right")

    def __init__(self, lo, hi):
        self.lo = lo  # 字符范围下界
        self.hi = hi  # 字符范围上界
        self.bits = []  # 位图：1 = 走右，0 = 走左
        self.left: _WaveletNode | None = None
        self.right: _WaveletNode | None = None


class WaveletTree:
    """Wavelet Tree：序列的 rank/select 索引。

    用法：
        wt = WaveletTree([3, 1, 4, 1, 5, 9, 2, 6])
        wt.access(0)          # 3
        wt.rank(5, 1)         # 2（前 5 个中 1 出现 2 次）
        wt.select(2, 1)       # 3（第 2 个 1 的位置）
        wt.range_count(0, 6, 1)  # 2（[0,6) 中 1 出现 2 次）
    """

    def __init__(self, data=None):
        self._data = list(data) if data else []
        self._lock = threading.RLock()
        self._root: _WaveletNode | None = None
        if self._data:
            self._build()

    def __len__(self) -> int:
        return len(self._data)

    def build(self, data) -> None:
        """构建。"""
        with self._lock:
            self._data = list(data)
            self._build()

    def _build(self) -> None:
        if not self._data:
            self._root = None
            return
        lo = min(self._data)
        hi = max(self._data)
        if lo == hi:
            # 所有字符相同，单节点
            self._root = _WaveletNode(lo, hi)
            self._root.bits = [0] * len(self._data)
            return
        self._root = self._build_node(self._data, lo, hi)

    def _build_node(self, data, lo, hi) -> _WaveletNode:
        node = _WaveletNode(lo, hi)
        if lo == hi:
            node.bits = [0] * len(data)
            return node
        mid = (lo + hi) // 2
        bits = []
        left_data = []
        right_data = []
        for v in data:
            if v <= mid:
                bits.append(0)
                left_data.append(v)
            else:
                bits.append(1)
                right_data.append(v)
        node.bits = bits
        if left_data:
            node.left = self._build_node(left_data, lo, mid)
        if right_data:
            node.right = self._build_node(right_data, mid + 1, hi)
        return node

    def access(self, i: int) -> Any:
        """第 i 位置的字符。"""
        if i < 0 or i >= len(self._data):
            raise IndexError(i)
        with self._lock:
            node = self._root
            while node is not None and node.lo != node.hi:
                bit = node.bits[i]
                mid = (node.lo + node.hi) // 2
                # 计算 i 在子树中的新位置
                if bit == 0:
                    # 走左：前 i+1 位中 0 的数量
                    i = node.bits[:i].count(0)
                    node = node.left
                else:
                    i = node.bits[:i].count(1)
                    node = node.right
            if node is None:
                raise ValueError("数据不一致")
            return node.lo

    def rank(self, i: int, c) -> int:
        """前 i 位置中字符 c 的数量（i 是位置上限，不含）。"""
        if i < 0 or i > len(self._data):
            raise IndexError(i)
        if i == 0:
            return 0
        with self._lock:
            return self._rank(self._root, i, c)

    def _rank(self, node, i, c) -> int:
        if node is None:
            return 0
        if node.lo == node.hi:
            return i if node.lo == c else 0
        mid = (node.lo + node.hi) // 2
        if c <= mid:
            # 走左：前 i 位中 0 的数量
            new_i = node.bits[:i].count(0)
            return self._rank(node.left, new_i, c)
        else:
            new_i = node.bits[:i].count(1)
            return self._rank(node.right, new_i, c)

    def select(self, k: int, c) -> int:
        """第 k 个 c 的位置（0-based，k 从 1 开始）。"""
        if k < 1:
            raise ValueError("k >= 1")
        with self._lock:
            pos = self._select(self._root, k, c)
            if pos is None:
                raise ValueError(f"字符 {c} 不足 {k} 个")
            return pos

    def _select(self, node, k, c):
        if node is None:
            return None
        if node.lo == node.hi:
            if node.lo == c and k <= len(node.bits):
                return k - 1
            return None
        mid = (node.lo + node.hi) // 2
        if c <= mid:
            # 在左子树找第 k 个
            sub_pos = self._select(node.left, k, c)
            if sub_pos is None:
                return None
            # 把左子树位置映射回原位置
            return self._map_back(node, sub_pos, 0)
        else:
            sub_pos = self._select(node.right, k, c)
            if sub_pos is None:
                return None
            return self._map_back(node, sub_pos, 1)

    def _map_back(self, node, sub_pos, bit_val) -> int:
        """把子树位置映射回原位置。找第 (sub_pos+1) 个 bit_val。"""
        count = 0
        for i, b in enumerate(node.bits):
            if b == bit_val:
                if count == sub_pos:
                    return i
                count += 1
        return -1  # 不应到达

    def range_count(self, l: int, r: int, c) -> int:
        """[l, r) 中 c 的数量。"""
        l = max(l, 0)
        r = min(r, len(self._data))
        if l >= r:
            return 0
        with self._lock:
            return self._rank(self._root, r, c) - self._rank(self._root, l, c)

    def rank_c(self, c: Any, pos: int) -> int:
        """(c, pos) 接口的 rank。"""
        return self.rank(pos, c)

    def select_c(self, c: Any, k: int) -> int:
        """(c, k) 接口的 select。"""
        return self.select(k, c)

    def range_count_c(self, c: Any, l: int, r: int) -> int:
        """(c, l, r) 接口的 range_count。"""
        return self.range_count(l, r, c)

    def __getitem__(self, i: int) -> Any:
        return self.access(i)

    def __iter__(self):
        for i in range(len(self._data)):
            yield self.access(i)

    def status(self) -> dict:
        with self._lock:

            def count_nodes(n) -> Any:
                if n is None:
                    return 0
                return 1 + count_nodes(n.left) + count_nodes(n.right)

            def depth(n) -> Any:
                if n is None:
                    return 0
                return 1 + max(depth(n.left), depth(n.right))

            return {
                "length": len(self._data),
                "nodes": count_nodes(self._root),
                "depth": depth(self._root),
            }
