"""BlueDeer Cuckoo Filter：支持删除的布隆过滤器。

evolution（数据维度 - R203）：
- 布隆过滤器不支持删除（标准版）
- Cuckoo Filter：用桶 + 指纹，支持 add/contains/delete
- 每元素两个候选桶（部分键 cuckoo 哈希），插入冲突时"踢出"已有元素
- 误判率可控，空间效率高
- 应用：缓存去重、黑名单、计数（需多版本）
- 与 Bloom Filter Chain 互补：BFC 滚动扩容，CF 支持删除
"""
from __future__ import annotations
import hashlib
import random
import threading
from typing import Any


class CuckooFilter:
    """Cuckoo Filter：支持删除的集合判重。

    用法：
        cf = CuckooFilter(capacity=10000)
        cf.add("a")
        cf.add("b")
        cf.contains("a")   # True
        cf.delete("a")
        cf.contains("a")   # False
    """

    def __init__(self, capacity: int, bucket_size: int = 4, fingerprint_size: int = 8):
        if capacity < 1:
            raise ValueError("capacity >= 1")
        if bucket_size < 2:
            raise ValueError("bucket_size >= 2")
        self._capacity = capacity
        self._bucket_size = bucket_size
        self._fp_size = fingerprint_size
        # 桶数（向上取 2 的幂）
        n = 1
        while n < capacity:
            n *= 2
        self._num_buckets = max(4, n)
        self._buckets: list[list[int]] = [[] for _ in range(self._num_buckets)]
        self._count = 0
        self._max_kicks = 500
        self._rng = random.Random()
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._count

    @property
    def capacity(self) -> int:
        return self._capacity

    def _fingerprint(self, item) -> int:
        """计算指纹。"""
        if isinstance(item, str):
            data = item.encode("utf-8")
        elif isinstance(item, bytes):
            data = item
        else:
            data = str(item).encode("utf-8")
        h = hashlib.sha256(data).digest()
        fp = int.from_bytes(h[:4], "big")
        # 确保非 0（0 表示空槽）
        return fp if fp != 0 else 1

    def _hash(self, item) -> int:
        """主哈希：桶索引。"""
        if isinstance(item, str):
            data = item.encode("utf-8")
        elif isinstance(item, bytes):
            data = item
        else:
            data = str(item).encode("utf-8")
        return int.from_bytes(hashlib.md5(data).digest()[:4], "big") % self._num_buckets

    def _alt_index(self, index: int, fingerprint: int) -> int:
        """部分键 cuckoo：i2 = i1 ^ hash(fp)。"""
        fp_bytes = fingerprint.to_bytes(4, "big")
        h = int.from_bytes(hashlib.md5(fp_bytes).digest()[:4], "big")
        return (index ^ h) % self._num_buckets

    def _indices(self, item) -> tuple[int, int, int]:
        """返回 (i1, i2, fingerprint)。"""
        fp = self._fingerprint(item)
        i1 = self._hash(item)
        i2 = self._alt_index(i1, fp)
        return (i1, i2, fp)

    def _relocate(self, idx: int, fp: int) -> bool:
        """重定位：从 idx 桶踢出指纹，尝试放入另一候选桶。
        
        带 max_relocate 限制 + 随机 reseed 策略避免无限循环。
        """
        for kick in range(self._max_kicks):
            slot = self._rng.randrange(self._bucket_size)
            fp, self._buckets[idx][slot] = self._buckets[idx][slot], fp
            idx = self._alt_index(idx, fp)
            if len(self._buckets[idx]) < self._bucket_size:
                self._buckets[idx].append(fp)
                self._count += 1
                return True
            # 每 100 次踢出 reseed 随机状态，打破循环
            if kick > 0 and kick % 100 == 0:
                self._rng = random.Random()
        return False

    def add(self, item) -> bool:
        """添加元素。满则返回 False。"""
        with self._lock:
            i1, i2, fp = self._indices(item)
            if len(self._buckets[i1]) < self._bucket_size:
                self._buckets[i1].append(fp)
                self._count += 1
                return True
            if len(self._buckets[i2]) < self._bucket_size:
                self._buckets[i2].append(fp)
                self._count += 1
                return True
            idx = i1 if self._rng.random() < 0.5 else i2
            return self._relocate(idx, fp)

    def contains(self, item) -> bool:
        """检查是否可能存在。"""
        with self._lock:
            i1, i2, fp = self._indices(item)
            return fp in self._buckets[i1] or fp in self._buckets[i2]

    def __contains__(self, item) -> bool:
        return self.contains(item)

    def delete(self, item) -> bool:
        """删除元素（若存在）。"""
        with self._lock:
            i1, i2, fp = self._indices(item)
            # 先查 i1
            if fp in self._buckets[i1]:
                self._buckets[i1].remove(fp)
                self._count -= 1
                return True
            if fp in self._buckets[i2]:
                self._buckets[i2].remove(fp)
                self._count -= 1
                return True
            return False

    def load_factor(self) -> float:
        """装载因子。"""
        with self._lock:
            total_slots = self._num_buckets * self._bucket_size
            return self._count / total_slots if total_slots else 0.0

    def status(self) -> dict:
        with self._lock:
            return {
                "count": self._count,
                "capacity": self._capacity,
                "num_buckets": self._num_buckets,
                "bucket_size": self._bucket_size,
                "load_factor": self.load_factor(),
            }
