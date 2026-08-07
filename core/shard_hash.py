"""BlueDeer 双层哈希表：分片 + 扩容 + 增量 rehash。

evolution（数据维度 - R186）：
- 单层 dict 没法并发：写时全表锁阻塞所有读
- Redis 用两层 hash：外层 bucket 数组（通常 2 个表，rehash 时双写）
  - 主表 ht[0]，扩容时建 ht[1]，每次操作迁移一个 bucket（增量 rehash）
  - 读：先查 ht[0]，找不到再查 ht[1]
  - 写：写 ht[1]，并迁移 ht[0] 一个 bucket 到 ht[1]
- 这里实现简化版：M 个分片（每个分片一个 dict + 锁），扩容时 M 翻倍
- 用 rehash_idx 跟踪迁移进度，每次 put/get 触发迁移 N 个分片
- 写锁是分片级（细粒度），扩容是全局的
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any


class ShardHash:
    """分片哈希表 + 增量扩容。

    用法：
        sh = ShardHash(shard_count=8, max_load=4)
        sh.put("k", "v")
        assert sh.get("k") == "v"
        # 超过 max_load * shard_count 自动触发扩容
    """

    def __init__(self, shard_count: int = 8, max_load: int = 16) -> None:
        if shard_count < 1:
            raise ValueError("shard_count 必须 >= 1")
        if max_load < 1:
            raise ValueError("max_load 必须 >= 1")
        self._shard_count = shard_count
        self._max_load = max_load
        self._shards: list[dict[Any, Any]] = [{} for _ in range(shard_count)]
        self._shard_locks: list[threading.RLock] = [
            threading.RLock() for _ in range(shard_count)
        ]
        self._weights: list[float] = [1.0] * shard_count
        self._global_lock = threading.RLock()
        self._rehash_idx = -1
        self._new_shards: list[dict[Any, Any]] = []
        self._new_count = 0
        self._total_puts = 0
        self._total_gets = 0
        self._rehash_steps = 0
        self._rehash_count = 0

    def __len__(self) -> int:
        return sum(len(s) for s in self._shards) + sum(len(s) for s in self._new_shards)

    def _shard_for(self, key: Any, count: int) -> int:
        return abs(hash(key)) % count

    def _weighted_shard_for(self, key: Any) -> int:
        """带权重的分片选择：按权重分配概率。"""
        h = abs(hash(key))
        total_weight = sum(self._weights)
        r = (h % 10000) / 10000.0 * total_weight
        cumulative = 0.0
        for i, w in enumerate(self._weights):
            cumulative += w
            if r < cumulative:
                return i
        return len(self._weights) - 1

    def set_weight(self, shard_idx: int, weight: float) -> None:
        """设置分片权重（影响 rebalance 后的分布）。"""
        if shard_idx < 0 or shard_idx >= self._shard_count:
            raise ValueError("shard_idx 越界")
        if weight <= 0:
            raise ValueError("weight 必须 > 0")
        with self._global_lock:
            self._weights[shard_idx] = weight

    def get_weights(self) -> list[float]:
        with self._global_lock:
            return list(self._weights)

    def put(self, key: Any, value: Any) -> bool:
        self._total_puts += 1
        with self._global_lock:
            self._rehash_step()
            if self._rehash_idx >= 0:
                old_idx = self._shard_for(key, self._shard_count)
                with self._shard_locks[old_idx]:
                    in_old = key in self._shards[old_idx]
                    if in_old:
                        del self._shards[old_idx][key]
                new_idx = self._shard_for(key, self._new_count)
                is_new = key not in self._new_shards[new_idx] and not in_old
                self._new_shards[new_idx][key] = value
                return is_new
            total = sum(len(s) for s in self._shards)
            if total >= self._shard_count * self._max_load:
                self._start_rehash()
                return self.put(key, value)
            shard_idx = self._shard_for(key, self._shard_count)
            with self._shard_locks[shard_idx]:
                is_new = key not in self._shards[shard_idx]
                self._shards[shard_idx][key] = value
            return is_new

    def _new_shard_lock(self, idx: int) -> threading.RLock:
        return self._global_lock

    def _start_rehash(self) -> None:
        self._new_count = self._shard_count * 2
        self._new_shards = [{} for _ in range(self._new_count)]
        self._rehash_idx = 0
        self._rehash_count += 1

    def _rehash_step(self, batch: int = 1) -> None:
        if self._rehash_idx < 0:
            return
        for _ in range(batch):
            if self._rehash_idx >= self._shard_count:
                break
            old_idx = self._rehash_idx
            with self._shard_locks[old_idx]:
                old_shard = self._shards[old_idx]
                for k, v in list(old_shard.items()):
                    new_idx = self._shard_for(k, self._new_count)
                    self._new_shards[new_idx][k] = v
                old_shard.clear()
            self._rehash_idx += 1
            self._rehash_steps += 1
        if self._rehash_idx >= self._shard_count:
            self._finish_rehash()

    def _finish_rehash(self) -> None:
        self._shards = self._new_shards
        self._shard_count = self._new_count
        self._shard_locks = [threading.RLock() for _ in range(self._shard_count)]
        self._weights = [1.0] * self._shard_count
        self._new_shards = []
        self._new_count = 0
        self._rehash_idx = -1

    def rebalance(self) -> dict[str, int]:
        """动态重分片：按权重重新分配 key，最小化迁移。
        返回 {key: 新 shard_idx} 映射。
        """
        with self._global_lock:
            if self._rehash_idx >= 0:
                self.force_rehash()
            all_items: dict[Any, Any] = {}
            for s in self._shards:
                all_items.update(s)
            for s in self._shards:
                s.clear()
            n = self._shard_count
            new_shards = [{} for _ in range(n)]
            migration: dict[str, int] = {}
            for k, v in all_items.items():
                new_idx = self._weighted_shard_for(k)
                new_shards[new_idx][k] = v
                migration[str(k)] = new_idx
            self._shards = new_shards
            return migration

    def get(self, key: Any, default: Any = None) -> Any:
        self._total_gets += 1
        with self._global_lock:
            self._rehash_step()
            if self._rehash_idx >= 0:
                new_idx = self._shard_for(key, self._new_count)
                if key in self._new_shards[new_idx]:
                    return self._new_shards[new_idx][key]
            old_idx = self._shard_for(key, self._shard_count)
            with self._shard_locks[old_idx]:
                return self._shards[old_idx].get(key, default)

    def delete(self, key: Any) -> bool:
        with self._global_lock:
            self._rehash_step()
            deleted = False
            if self._rehash_idx >= 0:
                new_idx = self._shard_for(key, self._new_count)
                if key in self._new_shards[new_idx]:
                    del self._new_shards[new_idx][key]
                    deleted = True
            old_idx = self._shard_for(key, self._shard_count)
            with self._shard_locks[old_idx]:
                if key in self._shards[old_idx]:
                    del self._shards[old_idx][key]
                    deleted = True
            return deleted

    def __contains__(self, key: Any) -> bool:
        with self._global_lock:
            if self._rehash_idx >= 0:
                new_idx = self._shard_for(key, self._new_count)
                if key in self._new_shards[new_idx]:
                    return True
            old_idx = self._shard_for(key, self._shard_count)
            with self._shard_locks[old_idx]:
                return key in self._shards[old_idx]

    def keys(self) -> list[Any]:
        with self._global_lock:
            ks = []
            for s in self._shards:
                ks.extend(s.keys())
            for s in self._new_shards:
                ks.extend(s.keys())
            return ks

    def items(self) -> list[tuple[Any, Any]]:
        with self._global_lock:
            result = []
            for s in self._shards:
                result.extend(s.items())
            for s in self._new_shards:
                result.extend(s.items())
            return result

    def __iter__(self) -> Iterator[Any]:
        return iter(self.keys())

    def force_rehash(self) -> None:
        with self._global_lock:
            while self._rehash_idx >= 0:
                self._rehash_step(batch=max(1, self._shard_count // 4 + 1))

    def status(self) -> dict:
        with self._global_lock:
            return {
                "shard_count": self._shard_count,
                "size": len(self),
                "max_load": self._max_load,
                "rehashing": self._rehash_idx >= 0,
                "rehash_idx": self._rehash_idx,
                "rehash_count": self._rehash_count,
                "rehash_steps": self._rehash_steps,
                "total_puts": self._total_puts,
                "total_gets": self._total_gets,
                "shard_sizes": [len(s) for s in self._shards],
                "weights": list(self._weights),
            }
