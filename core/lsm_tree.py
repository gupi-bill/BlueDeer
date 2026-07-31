"""BlueDeer LSM 树：写优化存储 + 分层合并。

evolution（数据维度 - R194）：
- LSM 树是写密集场景的核心结构
- 写入只追加到内存 memtable，达到阈值 flush 成不可变 SSTable
- 读取：memtable → 新 SSTable → 旧 SSTable（多层归并）
- compaction：合并多个 SSTable，去重 + 清理 tombstone
- 与 B+树互补：B+树读优写劣，LSM 写优读劣
- LevelDB/RocksDB/Cassandra/HBase 都基于 LSM
"""
from __future__ import annotations
import bisect
import threading
from typing import Any, Iterator

from .bloom_filter import BloomFilter


_TOMBSTONE = object()


class CompactionStrategy:
    """合并策略配置。"""
    SIZE_TIERED = "size-tiered"
    LEVELED = "leveled"

    @staticmethod
    def tier_sizes(base: int, fan: int, levels: int) -> list[int]:
        return [base * (fan ** i) for i in range(levels)]


class _SSTable:
    __slots__ = ("entries", "keys", "min_key", "max_key", "bloom", "level")

    def __init__(self, entries: list[tuple[Any, Any]], level: int = 0):
        self.entries = entries
        self.keys = [k for k, _ in entries]
        self.min_key = entries[0][0] if entries else None
        self.max_key = entries[-1][0] if entries else None
        self.level = level
        self.bloom: BloomFilter | None = None

    def ensure_bloom(self, capacity: int = 0, error_rate: float = 0.01) -> None:
        if self.bloom is not None:
            return
        cap = max(capacity or len(self.keys), 1)
        self.bloom = BloomFilter(cap, error_rate)
        for k in self.keys:
            self.bloom.add(k)

    def get(self, key) -> Any:
        if self.bloom is not None and key not in self.bloom:
            return None
        i = bisect.bisect_left(self.keys, key)
        if i < len(self.keys) and self.keys[i] == key:
            return self.entries[i][1]
        return None


class LsmTree:
    """LSM 树：memtable + 多层 SSTable。

    用法：
        t = LsmTree(memtable_limit=100)
        t.put("k1", "v1")
        t.get("k1")  -> "v1"
        t.delete("k1")
        t.get("k1")  -> None
        t.compact()
    """

    def __init__(
        self,
        memtable_limit: int = 100,
        compaction_strategy: str = CompactionStrategy.SIZE_TIERED,
        tier_fan: int = 4,
        tier_base: int = 100,
        bloom_error_rate: float = 0.01,
    ):
        if memtable_limit < 1:
            raise ValueError("memtable_limit 至少 1")
        self._memtable: dict[Any, Any] = {}
        self._sstables: list[_SSTable] = []
        self._mem_limit = memtable_limit
        self._size = 0
        self._lock = threading.RLock()
        self._flush_count = 0
        self._compact_count = 0
        self._compaction_strategy = compaction_strategy
        self._tier_fan = tier_fan
        self._tier_base = tier_base
        self._bloom_error_rate = bloom_error_rate
        self._bloom_enabled = True

    def __len__(self) -> int:
        return self._size

    def put(self, key, value) -> None:
        with self._lock:
            is_new = key not in self._memtable
            self._memtable[key] = value
            if is_new:
                self._size += 1
            if len(self._memtable) >= self._mem_limit:
                self._flush()

    def delete(self, key) -> None:
        with self._lock:
            if key not in self._memtable:
                self._size += 1
            self._memtable[key] = _TOMBSTONE
            if len(self._memtable) >= self._mem_limit:
                self._flush()

    def get(self, key) -> Any:
        with self._lock:
            if key in self._memtable:
                v = self._memtable[key]
                return None if v is _TOMBSTONE else v
            for sst in self._sstables:
                v = sst.get(key)
                if v is not None:
                    return None if v is _TOMBSTONE else v
            return None

    def __contains__(self, key) -> bool:
        return self.get(key) is not None

    def _flush(self) -> None:
        if not self._memtable:
            return
        entries = sorted(self._memtable.items())
        sst = _SSTable(entries)
        if self._bloom_enabled:
            sst.ensure_bloom(len(entries), self._bloom_error_rate)
        self._sstables.insert(0, sst)
        self._memtable = {}
        self._flush_count += 1

    def flush(self) -> None:
        with self._lock:
            self._flush()

    def compact(self) -> None:
        with self._lock:
            if self._compaction_strategy == CompactionStrategy.SIZE_TIERED:
                self._compact_size_tiered()
            else:
                self._compact_full()

    def _compact_full(self) -> None:
        merged: dict[Any, Any] = {}
        for sst in reversed(self._sstables):
            for k, v in sst.entries:
                merged[k] = v
        for k, v in self._memtable.items():
            merged[k] = v
        entries = sorted((k, v) for k, v in merged.items() if v is not _TOMBSTONE)
        self._sstables = []
        self._memtable = {}
        if entries:
            sst = _SSTable(entries)
            if self._bloom_enabled:
                sst.ensure_bloom(len(entries), self._bloom_error_rate)
            self._sstables.append(sst)
        self._size = len(entries)
        self._compact_count += 1

    def _compact_size_tiered(self) -> None:
        """大小分层合并：同层 SSTable 数量达 fan-out 时合并。"""
        tiers: dict[int, list[_SSTable]] = {}
        for sst in self._sstables:
            tiers.setdefault(sst.level, []).append(sst)
        to_compact = []
        for level, ssts in tiers.items():
            target = self._tier_fan ** (level + 1)
            if len(ssts) >= target:
                to_compact.extend(ssts)
        if not to_compact:
            return
        merged: dict[Any, Any] = {}
        for sst in to_compact:
            for k, v in sst.entries:
                merged[k] = v
        for sst in to_compact:
            self._sstables.remove(sst)
        entries = sorted((k, v) for k, v in merged.items() if v is not _TOMBSTONE)
        if entries:
            next_level = max(s.level for s in to_compact) + 1
            sst = _SSTable(entries, level=next_level)
            if self._bloom_enabled:
                sst.ensure_bloom(len(entries), self._bloom_error_rate)
            self._sstables.insert(0, sst)
        self._compact_count += 1

    def set_bloom_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._bloom_enabled = enabled

    def scan(self) -> Iterator[tuple[Any, Any]]:
        with self._lock:
            merged: dict[Any, Any] = {}
            for sst in reversed(self._sstables):
                for k, v in sst.entries:
                    merged[k] = v
            for k, v in self._memtable.items():
                merged[k] = v
            for k in sorted(merged.keys()):
                v = merged[k]
                if v is not _TOMBSTONE:
                    yield (k, v)

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "memtable_size": len(self._memtable),
                "memtable_limit": self._mem_limit,
                "sstable_count": len(self._sstables),
                "flush_count": self._flush_count,
                "compact_count": self._compact_count,
                "compaction_strategy": self._compaction_strategy,
                "bloom_enabled": self._bloom_enabled,
                "levels": max((s.level for s in self._sstables), default=0) + 1,
            }
