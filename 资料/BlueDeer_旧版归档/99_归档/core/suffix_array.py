"""BlueDeer 后缀数组：字符串索引 + 模式搜索。

evolution（数据维度 - R202）：
- 后缀数组是字符串处理的核心结构
- 把所有后缀排序，支持 O(m log n) 模式搜索、最长重复子串
- 应用：全文搜索、数据压缩、生物信息学序列比对
- 与 Trie/Radix 互补：Trie 前缀匹配，后缀数组子串匹配
"""

from __future__ import annotations

import threading
from collections.abc import Iterator


class SuffixArray:
    """后缀数组：字符串的所有后缀按字典序排序。

    用法：
        sa = SuffixArray("banana")
        sa.search("ana")   # [1, 3]（"ana" 出现位置）
        sa.count("ana")    # 2
        sa.longest_repeated()  # "ana"
    """

    def __init__(self, text: str = ""):
        self._text = text
        self._n = len(text)
        self._sa: list[int] = []
        self._lcp: list[int] = []
        self._lock = threading.RLock()
        if text:
            self._build()

    def __len__(self) -> int:
        return self._n

    @property
    def text(self) -> str:
        return self._text

    @property
    def lcp(self) -> list[int]:
        return self._lcp

    def build(self, text: str) -> None:
        with self._lock:
            self._text = text
            self._n = len(text)
            self._build()

    def _build(self) -> None:
        n = self._n
        indices = list(range(n))
        indices.sort(key=lambda i: self._text[i:])
        self._sa = indices
        self._build_lcp()

    def _build_lcp(self) -> None:
        """Kasai 算法 O(n) 计算 LCP 数组。"""
        n = self._n
        if n == 0:
            self._lcp = []
            return
        rank = [0] * n
        for i, sa_i in enumerate(self._sa):
            rank[sa_i] = i
        lcp = [0] * n
        k = 0
        for i in range(n):
            if rank[i] == 0:
                k = 0
                continue
            j = self._sa[rank[i] - 1]
            while i + k < n and j + k < n and self._text[i + k] == self._text[j + k]:
                k += 1
            lcp[rank[i]] = k
            if k > 0:
                k -= 1
        self._lcp = lcp

    def suffix(self, i: int) -> str:
        with self._lock:
            if i < 0 or i >= self._n:
                raise IndexError(i)
            return self._text[self._sa[i] :]

    def __getitem__(self, i: int) -> int:
        with self._lock:
            return self._sa[i]

    def __iter__(self) -> Iterator[int]:
        with self._lock:
            yield from self._sa

    def search(self, pattern: str) -> list[int]:
        if not pattern:
            return list(range(self._n))
        with self._lock:
            if not self._sa:
                return []
            lo = self._lower_bound(pattern)
            if lo == self._n or not self._suffix_at(lo).startswith(pattern):
                return []
            hi = self._upper_bound(pattern, lo)
            result = sorted(self._sa[lo:hi])
            return result

    def _suffix_at(self, sa_idx: int) -> str:
        return self._text[self._sa[sa_idx] :]

    def _lower_bound(self, pattern: str) -> int:
        lo, hi = 0, self._n
        while lo < hi:
            mid = (lo + hi) // 2
            if self._suffix_at(mid) < pattern:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _upper_bound(self, pattern: str, lower: int) -> int:
        lo, hi = lower, self._n
        while lo < hi:
            mid = (lo + hi) // 2
            s = self._suffix_at(mid)
            if s.startswith(pattern):
                lo = mid + 1
            else:
                hi = mid
        return lo

    def count(self, pattern: str) -> int:
        return len(self.search(pattern))

    def contains(self, pattern: str) -> bool:
        return len(self.search(pattern)) > 0

    def __contains__(self, pattern: str) -> bool:
        return self.contains(pattern)

    def build_lcp(self) -> list[int]:
        with self._lock:
            if not self._sa:
                return []
            self._build_lcp()
            return list(self._lcp)

    def lcp_array(self) -> list[int]:
        with self._lock:
            if not self._lcp:
                if self._sa:
                    self._build_lcp()
                else:
                    return []
            return list(self._lcp)

    def _lcp(self, i: int, j: int) -> int:
        n = self._n
        k = 0
        while i + k < n and j + k < n and self._text[i + k] == self._text[j + k]:
            k += 1
        return k

    def longest_repeated(self) -> str:
        with self._lock:
            if self._n < 2:
                return ""
            if not self._lcp:
                self._build_lcp()
            max_len = 0
            max_idx = 0
            for i, length in enumerate(self._lcp):
                if length > max_len:
                    max_len = length
                    max_idx = self._sa[i]
            return self._text[max_idx : max_idx + max_len]

    def distinct_substrings(self) -> int:
        with self._lock:
            if self._n == 0:
                return 0
            if not self._lcp:
                self._build_lcp()
            total = self._n * (self._n + 1) // 2
            return total - sum(self._lcp)

    def status(self) -> dict:
        with self._lock:
            return {
                "text_length": self._n,
                "array_size": len(self._sa),
                "lcp_available": len(self._lcp) > 0,
            }
