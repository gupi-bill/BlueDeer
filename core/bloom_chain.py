"""BlueDeer Bloom Filter Chain：分层滚动布隆 + 自动降误判。

evolution（数据维度 - R195）：
- 单个 BloomFilter 超容量后误判率飙升
- Bloom Filter Chain：当一层满了就冻结，新建下一层
- 查询：任一层命中即"可能存在"（OR 语义，覆盖不同时间段数据）
- 添加：只写当前活跃层，满了滚动新建
- 与 R180 互补：R180 固定容量，本模块无限增长
- Cassandra/ScyllaDB 用类似机制管理 SSTable 的布隆过滤器
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from core.bloom_filter import BloomFilter


class BloomFilterChain:
    """分层滚动布隆过滤器。

    用法：
        bc = BloomFilterChain(capacity_per_level=1000, error_rate=0.01)
        for i in range(5000):
            bc.add(f"key{i}")
        bc.contains("key100")   # True
        bc.contains("missing")  # False 或误判 True
    """

    def __init__(
        self,
        capacity_per_level: int = 1000,
        error_rate: float = 0.01,
    ):
        if capacity_per_level < 1:
            raise ValueError("capacity_per_level >= 1")
        if not (0 < error_rate < 1):
            raise ValueError("error_rate in (0,1)")
        self._cap = capacity_per_level
        self._err = error_rate
        self._levels: list[BloomFilter] = [BloomFilter(capacity_per_level, error_rate)]
        self._lock = threading.RLock()
        self._total_added = 0

    def __len__(self) -> int:
        return self._total_added

    def levels(self) -> int:
        """当前层数。"""
        with self._lock:
            return len(self._levels)

    def add(self, item) -> None:
        """添加元素到当前活跃层；满了新建一层。"""
        with self._lock:
            cur = self._levels[-1]
            if len(cur) >= self._cap:
                cur = BloomFilter(self._cap, self._err)
                self._levels.append(cur)
            cur.add(item)
            self._total_added += 1

    def add_many(self, items: Iterable) -> int:
        """批量添加。"""
        n = 0
        for item in items:
            self.add(item)
            n += 1
        return n

    def contains(self, item) -> bool:
        """任一层命中即返回 True。"""
        with self._lock:
            for bf in self._levels:
                if bf.contains(item):
                    return True
            return False

    def contains_many(self, items: Iterable) -> list[bool]:
        return [self.contains(item) for item in items]

    def __contains__(self, item) -> bool:
        return self.contains(item)

    def estimated_false_positive_rate(self) -> float:
        """估算总误判率：1 - ∏(1 - p_i)。

        每层独立误判率 p_i，整体 OR 后为 1 - ∏(1-p_i)。
        """
        with self._lock:
            prod = 1.0
            for bf in self._levels:
                p = bf.estimated_false_positive_rate()
                prod *= 1 - p
            return 1.0 - prod

    def ensure_capacity(self, n: int) -> None:
        """确保总容量 >= n，不足时自动新增层。"""
        with self._lock:
            current = self._cap * len(self._levels)
            while current < n:
                self._levels.append(BloomFilter(self._cap, self._err))
                current += self._cap

    def rebuild(self) -> None:
        """压缩所有层为单层（通过 OR 位数组合并）。"""
        with self._lock:
            if len(self._levels) <= 1:
                return
            base = self._levels[0]
            for bf in self._levels[1:]:
                base.merge(bf)
            self._levels = [base]

    def clear(self) -> None:
        """清空所有层。"""
        with self._lock:
            self._levels = [BloomFilter(self._cap, self._err)]
            self._total_added = 0

    def merge(self, other: BloomFilterChain) -> None:
        """合并另一个 chain（追加其所有层）。

        注意：要求 capacity 和 error_rate 相同。
        """
        if not isinstance(other, BloomFilterChain):
            raise TypeError("只能合并 BloomFilterChain")
        with self._lock:
            for bf in other._levels:
                # 复制一份，避免共享引用
                new_bf = BloomFilter(self._cap, self._err)
                new_bf._bits = bytearray(bf._bits)
                new_bf._count = bf._count
                self._levels.append(new_bf)
            self._total_added += other._total_added

    def status(self) -> dict:
        with self._lock:
            return {
                "total_added": self._total_added,
                "levels": len(self._levels),
                "capacity_per_level": self._cap,
                "error_rate": self._err,
                "estimated_fpr": self.estimated_false_positive_rate(),
                "level_sizes": [len(bf) for bf in self._levels],
            }
