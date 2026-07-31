"""BlueDeer 一致性哈希环：虚拟节点 + 平滑迁移。

evolution（数据维度 - R190）：
- 普通 hash % N 在节点数变化时所有 key 都要迁移（N 变了模就变）
- 一致性哈希把节点和 key 都映射到 0~2^32 的环上，沿环顺时针找节点
- 节点变化只影响相邻段的 key（约 1/N 的 key 需迁移）
- 虚拟节点（每个物理节点对应多个虚拟节点）解决数据倾斜
- 典型用途：分布式缓存（Memcached/Redis Cluster）、CDN 路由、分片定位
"""
from __future__ import annotations
import hashlib
import threading
from typing import Any, Iterator


def _hash32(data: str | bytes) -> int:
    """32 位哈希（md5 取前 4 字节）。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    h = hashlib.md5(data).digest()
    return int.from_bytes(h[:4], "big", signed=False)


class ConsistentHash:
    """一致性哈希环。

    用法：
        ch = ConsistentHash(vnodes=150)
        ch.add_node("node-1")
        ch.add_node("node-2")
        node = ch.get_node("user:123")
        ch.add_node("node-3")
    """

    def __init__(self, vnodes: int = 150) -> None:
        if vnodes < 1:
            raise ValueError("vnodes 必须 >= 1")
        self._default_vnodes = vnodes
        self._ring: list[tuple[int, str]] = []
        self._hashes: list[int] = []
        self._nodes: dict[str, dict] = {}
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return len(self._nodes)

    def add_node(self, node: str, weight: int = 1, num_vnodes: int | None = None) -> int:
        """添加节点。weight 越大虚拟节点越多。num_vnodes 覆盖默认值。"""
        if weight < 1:
            raise ValueError("weight 必须 >= 1")
        with self._lock:
            if node in self._nodes:
                return 0
            actual_vnodes = self._default_vnodes if num_vnodes is None else num_vnodes
            n_vnodes = actual_vnodes * weight
            for i in range(n_vnodes):
                h = _hash32(f"{node}#{i}")
                self._ring.append((h, node))
            self._ring.sort(key=lambda x: x[0])
            self._hashes = [h for h, _ in self._ring]
            self._nodes[node] = {
                "vnodes": n_vnodes,
                "weight": weight,
                "num_vnodes": actual_vnodes,
            }
            return n_vnodes

    def remove_node(self, node: str) -> bool:
        with self._lock:
            if node not in self._nodes:
                return False
            self._ring = [(h, n) for h, n in self._ring if n != node]
            self._hashes = [h for h, _ in self._ring]
            del self._nodes[node]
            return True

    def get_node(self, key: Any) -> str | None:
        with self._lock:
            if not self._ring:
                return None
            k = _hash32(key if isinstance(key, (str, bytes)) else str(key))
            idx = self._bisect_left(k)
            if idx == len(self._ring):
                idx = 0
            return self._ring[idx][1]

    def get_nodes(self, key: Any, n: int = 1) -> list[str]:
        with self._lock:
            if not self._ring or n < 1:
                return []
            k = _hash32(key if isinstance(key, (str, bytes)) else str(key))
            idx = self._bisect_left(k)
            if idx == len(self._ring):
                idx = 0
            result: list[str] = []
            seen: set[str] = set()
            size = len(self._ring)
            for offset in range(size):
                node = self._ring[(idx + offset) % size][1]
                if node not in seen:
                    seen.add(node)
                    result.append(node)
                    if len(result) >= n:
                        break
            return result

    def _bisect_left(self, target: int) -> int:
        lo, hi = 0, len(self._hashes)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._hashes[mid] < target:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def nodes(self) -> list[str]:
        with self._lock:
            return list(self._nodes.keys())

    def __contains__(self, node: str) -> bool:
        with self._lock:
            return node in self._nodes

    def __iter__(self) -> Iterator[str]:
        return iter(self.nodes())

    def distribution(self, sample_size: int = 10000) -> dict[str, int]:
        result: dict[str, int] = {}
        with self._lock:
            for node in self._nodes:
                result[node] = 0
            for i in range(sample_size):
                node = self.get_node(f"key-{i}")
                if node is not None:
                    result[node] += 1
        return result

    def load_stats(self) -> dict[str, dict]:
        """返回每节点的虚拟节点数和负载占比。"""
        with self._lock:
            total_vnodes = len(self._ring)
            stats: dict[str, dict] = {}
            for node, info in self._nodes.items():
                node_vnodes = sum(1 for _, n in self._ring if n == node)
                load_pct = (node_vnodes / total_vnodes * 100) if total_vnodes > 0 else 0
                stats[node] = {
                    "weight": info["weight"],
                    "num_vnodes": info["num_vnodes"],
                    "virtual_nodes": node_vnodes,
                    "load_percent": round(load_pct, 2),
                }
            return stats

    def status(self) -> dict:
        with self._lock:
            return {
                "node_count": len(self._nodes),
                "default_vnodes": self._default_vnodes,
                "total_vnodes": len(self._ring),
            }
