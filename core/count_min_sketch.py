"""BlueDeer Count-Min Sketch：频率估算 + 固定内存。

evolution（数据维度 - R199）：
- 流式数据需统计元素频率，但元素种类无限（URL、IP、词）
- 用哈希表存全量太占内存
- Count-Min Sketch：d 个哈希函数 × w 个计数器矩阵
- 估算频率 = min(各行对应计数器)
- 永不低估（只可能高估），适合 top-k、热门统计
- 与 HyperLogLog 互补：HLL 估算基数（去重数），CMS 估算频率
"""

from __future__ import annotations

import hashlib
import math
import threading
from typing import Any


class CountMinSketch:
    """Count-Min Sketch：频率估算。

    用法：
        cms = CountMinSketch(width=1000, depth=5)
        for word in ["a", "b", "a", "c", "a"]:
            cms.add(word)
        cms.estimate("a")   # >= 3（可能略高，但不低于）
        cms.estimate("b")   # >= 1
    """

    def __init__(self, width: int = 1000, depth: int = 5, seed: int = 0):
        if width < 1 or depth < 1:
            raise ValueError("width 和 depth >= 1")
        self._width = width
        self._depth = depth
        self._seed = seed
        # d × w 计数矩阵（用 list of bytearray 提速）
        self._tables = [bytearray(width * 8) for _ in range(depth)]
        self._total = 0  # 总计数
        self._candidates: dict[Any, int] = {}  # item -> est count（top-k 候选集）
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._total

    def _hashes(self, item) -> list[int]:
        """生成 depth 个哈希位置。"""
        if isinstance(item, str):
            data = item.encode("utf-8")
        elif isinstance(item, bytes):
            data = item
        else:
            data = str(item).encode("utf-8")
        positions = []
        for i in range(self._depth):
            # 用 md5 + 行号生成独立哈希
            h = hashlib.md5(data + i.to_bytes(4, "big")).digest()
            pos = int.from_bytes(h[:8], "big") % self._width
            positions.append(pos)
        return positions

    def _get(self, table: bytearray, idx: int) -> int:
        """读取计数器（8 字节大端）。"""
        return int.from_bytes(table[idx * 8 : idx * 8 + 8], "big")

    def _set(self, table: bytearray, idx: int, val: int) -> None:
        table[idx * 8 : idx * 8 + 8] = val.to_bytes(8, "big")

    def _prune_candidates(self) -> None:
        """裁剪候选集，保留 top width 个（控制内存）。"""
        if len(self._candidates) <= self._width:
            return
        threshold = sorted(self._candidates.values(), reverse=True)[self._width - 1]
        self._candidates = {k: v for k, v in self._candidates.items() if v >= threshold}

    def add(self, item: Any, count: int = 1) -> None:
        """增加计数。"""
        if count < 0:
            raise ValueError("count 不能为负")
        positions = self._hashes(item)
        with self._lock:
            for i, pos in enumerate(positions):
                cur = self._get(self._tables[i], pos)
                self._set(self._tables[i], pos, cur + count)
            self._total += count
            # 更新候选集（用于 top-k / heavy_hitters）
            est = min(
                self._get(self._tables[i], pos) for i, pos in enumerate(positions)
            )
            self._candidates[item] = est
            if len(self._candidates) > self._width * 3:
                self._prune_candidates()

    def estimate(self, item) -> int:
        """估算频率（返回各行最小值）。"""
        positions = self._hashes(item)
        with self._lock:
            return min(
                self._get(self._tables[i], pos) for i, pos in enumerate(positions)
            )

    def __getitem__(self, item) -> int:
        return self.estimate(item)

    def merge(self, other: CountMinSketch) -> None:
        """合并另一个 sketch（同维度）。"""
        if self._width != other._width or self._depth != other._depth:
            raise ValueError("维度不匹配")
        with self._lock:
            for i in range(self._depth):
                for j in range(self._width):
                    cur = self._get(self._tables[i], j)
                    other_val = other._get(other._tables[i], j)
                    self._set(self._tables[i], j, cur + other_val)
            self._total += other._total

    def reset(self) -> None:
        """清零。"""
        with self._lock:
            for t in self._tables:
                for i in range(len(t)):
                    t[i] = 0
            self._total = 0

    def top_k(self, k: int) -> list[tuple[Any, int]]:
        """返回估算频率前 k 的元素。"""
        with self._lock:
            return sorted(self._candidates.items(), key=lambda x: -x[1])[:k]

    def heavy_hitters(self, threshold: int) -> list[tuple[Any, int]]:
        """返回估算频率 >= threshold 的（项, 估算频率）。"""
        with self._lock:
            return [
                (item, est)
                for item, est in self._candidates.items()
                if est >= threshold
            ]

    def estimated_error(self) -> float:
        """理论误差上界：epsilon = e * w（w=width, e=euler）。

        返回 epsilon，即估算值与真实值的差 <= epsilon * total（概率 >= 1-delta）。
        """
        # epsilon = e / width
        return math.e / self._width

    def confidence(self) -> float:
        """置信度：1 - delta = 1 - e^(-depth)。"""
        return 1 - math.exp(-self._depth)

    def status(self) -> dict:
        with self._lock:
            return {
                "width": self._width,
                "depth": self._depth,
                "total": self._total,
                "bytes": self._depth * self._width * 8,
                "estimated_error": self.estimated_error(),
                "confidence": self.confidence(),
            }
