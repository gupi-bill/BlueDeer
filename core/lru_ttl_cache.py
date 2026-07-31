"""BlueDeer LRU + TTL 缓存（兼容层）。

现由 lru_cache.LRUCache 统一实现，ttl 参数直接传入即可。
此模块保留向后兼容。
"""
from __future__ import annotations

from core.lru_cache import LRUCache as LruTtlCache

__all__ = ["LruTtlCache"]