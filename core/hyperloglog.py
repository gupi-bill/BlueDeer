"""BlueDeer HyperLogLog 基数估计：常数内存近似去重计数。

evolution（数据维度 - R188）：
- 用 set 存所有元素去重，1 亿用户要 8GB 内存
- HyperLogLog 用固定 m 个桶（典型 16384 个）即可估算任意基数
  - 误差 ~1.04/sqrt(m)，约 0.81%
  - 内存：m * 1 字节（典型 16KB）
- 原理：hash 后低位前导零最大值反映"独立"程度
- 支持 merge（多实例合并）、reset、序列化
- 典型用途：UV 统计、独立访客计数、Distinct 计数
"""
from __future__ import annotations
import hashlib
import math
import threading
from typing import Any, Iterator


class HyperLogLog:
    """HyperLogLog 基数估计器。

    用法：
        hll = HyperLogLog(precision=14)
        for i in range(1_000_000):
            hll.add(f"user-{i}")
        estimated = hll.estimate()
        # 误差约 0.81%
        hll2 = HyperLogLog(precision=14)
        hll2.add("x")
        hll.merge(hll2)
    """

    def __init__(self, precision: int = 14) -> None:
        if not 4 <= precision <= 16:
            raise ValueError("precision 必须在 [4, 16] 之间")
        self._b = precision
        self._m = 1 << precision
        # 修正因子
        if self._m == 16:
            self._alpha = 0.673
        elif self._m == 32:
            self._alpha = 0.697
        elif self._m == 64:
            self._alpha = 0.709
        else:
            self._alpha = 0.7213 / (1.0 + 1.079 / self._m)
        self._registers = bytearray(self._m)
        self._lock = threading.RLock()
        self._added = 0  # 总添加次数（含重复）

    @property
    def precision(self) -> int:
        return self._b

    @property
    def m(self) -> int:
        return self._m

    def __len__(self) -> int:
        return self._added

    @staticmethod
    def _hash64(item: Any) -> int:
        """64 位哈希。"""
        if isinstance(item, str):
            data = item.encode("utf-8")
        elif isinstance(item, bytes):
            data = item
        elif isinstance(item, bytearray):
            data = bytes(item)
        else:
            data = str(item).encode("utf-8")
        # md5 取前 8 字节（够用且快）
        h = hashlib.md5(data).digest()
        return int.from_bytes(h[:8], "big", signed=False)

    def _rho(self, w: int) -> int:
        """计算 w 中前导零 + 1（即从最高位开始的连续 0 数 + 1）。"""
        bits = 64 - self._b
        if w == 0:
            return bits + 1
        # 找最高位的 1
        rho = 1
        mask = 1 << (bits - 1)
        while mask and (w & mask) == 0:
            rho += 1
            mask >>= 1
        return rho

    def add(self, item: Any) -> None:
        """添加一个元素。重复添加不影响估计（最大值语义）。"""
        with self._lock:
            h = self._hash64(item)
            idx = h >> (64 - self._b)  # 前 b 位作桶索引
            w = h & ((1 << (64 - self._b)) - 1)  # 剩余位
            rho = self._rho(w)
            if rho > self._registers[idx]:
                self._registers[idx] = rho
            self._added += 1

    def add_many(self, items: Iterator[Any]) -> int:
        """批量添加。返回添加次数。"""
        n = 0
        with self._lock:
            for item in items:
                h = self._hash64(item)
                idx = h >> (64 - self._b)
                w = h & ((1 << (64 - self._b)) - 1)
                rho = self._rho(w)
                if rho > self._registers[idx]:
                    self._registers[idx] = rho
                n += 1
        self._added += n
        return n

    def estimate(self) -> int:
        """估算去重基数（HLL++ 偏差校正）。"""
        with self._lock:
            m = self._m
            sum_inv = 0.0
            zeros = 0
            for r in self._registers:
                if r == 0:
                    zeros += 1
                sum_inv += 2.0 ** (-r)
            E = self._alpha * m * m / sum_inv
            # 小基数修正：LinearCounting
            if E <= 2.5 * m:
                if zeros > 0:
                    E = m * math.log(m / zeros)
            # 中等基数 HLL++ 偏差校正
            if E <= 5 * m:
                bias = 0.005 * math.log(max(1.0, E / m))
                E *= 1.0 + bias * (1.0 - E / (5 * m))
            # 大基数修正
            elif E > (1 << 32) / 30.0:
                E = -(1 << 32) * math.log(1 - E / (1 << 32))
            return int(E)

    def merge(self, other: "HyperLogLog") -> None:
        """合并另一个 HLL（用于分片合并）。"""
        if self._b != other._b:
            raise ValueError("precision 不一致，无法合并")
        with self._lock:
            for i in range(self._m):
                if other._registers[i] > self._registers[i]:
                    self._registers[i] = other._registers[i]
            self._added += other._added

    def reset(self) -> None:
        with self._lock:
            for i in range(self._m):
                self._registers[i] = 0
            self._added = 0

    def serialize(self) -> bytes:
        """序列化（precision + registers）。"""
        with self._lock:
            return bytes([self._b]) + bytes(self._registers)

    @classmethod
    def deserialize(cls, data: bytes) -> "HyperLogLog":
        if len(data) < 1:
            raise ValueError("空数据")
        precision = data[0]
        hll = cls(precision=precision)
        if len(data) - 1 != hll._m:
            raise ValueError(f"register 数不匹配: 期望 {hll._m}, 实际 {len(data) - 1}")
        hll._registers = bytearray(data[1:])
        return hll

    def __or__(self, other: "HyperLogLog") -> "HyperLogLog":
        """并集（合并两个 HLL）。"""
        result = HyperLogLog(precision=self._b)
        result.merge(self)
        result.merge(other)
        return result

    def status(self) -> dict:
        with self._lock:
            return {
                "precision": self._b,
                "m": self._m,
                "added": self._added,
                "estimated": self.estimate(),
                "register_bytes": len(self._registers),
            }
