"""BlueDeer 布隆过滤器：多哈希 + 误判率可配 + 序列化持久化。

用法：
    bf = BloomFilter(capacity=10000, error_rate=0.01)
    bf.add("hello")
    assert bf.contains("hello")

    # 序列化
    data = bf.to_bytes()
    bf2 = BloomFilter.from_bytes(data)
    assert bf2.contains("hello")

    # 合并
    bf.merge(other_bf)
"""
from __future__ import annotations
import hashlib
import math
import struct
import threading
from typing import Iterable


class BloomFilter:
    """标准布隆过滤器，支持序列化与合并。"""

    _MAGIC = b"BLMF"
    _VERSION = 1

    def __init__(
        self,
        capacity: int,
        error_rate: float = 0.01,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity 必须 >= 1")
        if not (0 < error_rate < 1):
            raise ValueError("error_rate 必须在 (0, 1)")
        self._capacity = capacity
        self._error_rate = error_rate
        self._m = max(8, int(math.ceil(-capacity * math.log(error_rate) / (math.log(2) ** 2))))
        self._k = max(1, int(round((self._m / capacity) * math.log(2))))
        self._bits = bytearray((self._m + 7) // 8)
        self._count = 0
        self._lock = threading.RLock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def error_rate(self) -> float:
        return self._error_rate

    @property
    def num_bits(self) -> int:
        return self._m

    @property
    def num_hashes(self) -> int:
        return self._k

    def __len__(self) -> int:
        return self._count

    def _hashes(self, item) -> list[int]:
        if isinstance(item, str):
            data = item.encode("utf-8")
        elif isinstance(item, bytes):
            data = item
        else:
            data = str(item).encode("utf-8")
        h = hashlib.sha256(data).digest()
        h1 = int.from_bytes(h[:8], "big")
        h2 = int.from_bytes(h[8:16], "big")
        if h2 == 0:
            h2 = 1
        return [(h1 + i * h2) % self._m for i in range(self._k)]

    def add(self, item) -> None:
        positions = self._hashes(item)
        with self._lock:
            for pos in positions:
                byte_idx = pos >> 3
                bit_idx = pos & 7
                self._bits[byte_idx] |= (1 << bit_idx)
            self._count += 1

    def add_many(self, items: Iterable) -> int:
        n = 0
        with self._lock:
            for item in items:
                positions = self._hashes(item)
                for pos in positions:
                    byte_idx = pos >> 3
                    bit_idx = pos & 7
                    self._bits[byte_idx] |= (1 << bit_idx)
                n += 1
            self._count += n
        return n

    def contains(self, item) -> bool:
        positions = self._hashes(item)
        with self._lock:
            for pos in positions:
                byte_idx = pos >> 3
                bit_idx = pos & 7
                if not (self._bits[byte_idx] & (1 << bit_idx)):
                    return False
            return True

    def contains_many(self, items: Iterable) -> list[bool]:
        return [self.contains(item) for item in items]

    def __contains__(self, item) -> bool:
        return self.contains(item)

    def clear(self) -> None:
        with self._lock:
            for i in range(len(self._bits)):
                self._bits[i] = 0
            self._count = 0

    def estimated_false_positive_rate(self) -> float:
        if self._count == 0:
            return 0.0
        return (1 - math.exp(-self._k * self._count / self._m)) ** self._k

    def saturation(self) -> float:
        with self._lock:
            set_bits = sum(bin(byte).count("1") for byte in self._bits)
        return set_bits / self._m

    def merge(self, other: BloomFilter) -> None:
        if self._m != other._m or self._k != other._k:
            raise ValueError("合并的两个 BloomFilter 参数不一致（m/k 不匹配）")
        with self._lock:
            for i in range(len(self._bits)):
                self._bits[i] |= other._bits[i]
            self._count = max(self._count, other._count)

    def to_bytes(self) -> bytes:
        """序列化为字节流。"""
        header = struct.pack(
            "!4sIIII", self._MAGIC, self._VERSION, self._capacity,
            int(self._error_rate * 1_000_000), self._count,
        )
        return header + bytes(self._bits)

    @classmethod
    def from_bytes(cls, data: bytes) -> BloomFilter:
        """从字节流反序列化。"""
        magic = data[:4]
        if magic != cls._MAGIC:
            raise ValueError(f"无效的 BloomFilter 数据: {magic!r}")
        version, capacity, error_rate_int, count = struct.unpack_from("!IIII", data, 4)
        if version != cls._VERSION:
            raise ValueError(f"不支持的版本: {version}")
        error_rate = error_rate_int / 1_000_000
        bf = cls.__new__(cls)
        bf._capacity = capacity
        bf._error_rate = error_rate
        bf._m = max(8, int(math.ceil(-capacity * math.log(error_rate) / (math.log(2) ** 2))))
        bf._k = max(1, int(round((bf._m / capacity) * math.log(2))))
        bits_len = (bf._m + 7) // 8
        bf._bits = bytearray(data[20:20 + bits_len])
        bf._count = count
        bf._lock = threading.RLock()
        return bf

    def status(self) -> dict:
        return {
            "capacity": self._capacity,
            "error_rate": self._error_rate,
            "num_bits": self._m,
            "num_hashes": self._k,
            "count": self._count,
            "estimated_fpr": self.estimated_false_positive_rate(),
            "saturation": self.saturation(),
            "bytes": len(self._bits),
        }