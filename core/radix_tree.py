"""BlueDeer Radix Tree 基数树：路径压缩前缀树。

evolution（数据维度 - R183）：
- Trie 每个节点存一个字符，公共前缀长时浪费空间和查询时间
- Radix Tree 把单字符路径压缩成一段字符串（edge），分支处才分叉
- 典型用途：路由表（"/api/users" 与 "/api/posts" 共享 "/api/" 前缀）
- 支持：插入/查找/删除/最长前缀匹配/前缀枚举
"""
from __future__ import annotations
import threading
from typing import Any, Iterator


class _Node:
    __slots__ = ("edge", "children", "value", "has_value")

    def __init__(self, edge: str = "") -> None:
        # edge: 从父节点到本节点的字符串片段
        self.edge = edge
        self.children: dict[str, _Node] = {}
        self.value: Any = None
        self.has_value: bool = False


def _lcp(a: str, b: str) -> int:
    """最长公共前缀长度。"""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


class RadixTree:
    """基数树。

    用法：
        rt = RadixTree()
        rt.insert("/api/users", "users_handler")
        rt.insert("/api/posts", "posts_handler")
        rt.insert("/health", "health_handler")
        assert rt.get("/api/users") == "users_handler"
        assert rt.longest_prefix("/api/users/123") == "/api/users"
    """

    def __init__(self) -> None:
        self._root = _Node()
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def insert(self, key: str, value: Any = None) -> bool:
        """插入 key（可挂 value）。返回是否新增（False=已存在只更新 value）。"""
        if not isinstance(key, str):
            raise TypeError("key 必须 str")
        with self._lock:
            return self._insert(self._root, key, value)

    def _insert(self, node: _Node, key: str, value: Any) -> bool:
        if not key:
            is_new = not node.has_value
            if is_new:
                self._size += 1
            node.has_value = True
            node.value = value
            return is_new

        first = key[0]
        child = node.children.get(first)
        if child is None:
            # 直接挂新子节点
            new_node = _Node(edge=key)
            new_node.has_value = True
            new_node.value = value
            node.children[first] = new_node
            self._size += 1
            return True

        # 与 child.edge 求公共前缀
        common = _lcp(key, child.edge)
        if common == len(child.edge):
            # child.edge 全匹配，递归到 child
            return self._insert(child, key[common:], value)

        # 需要分裂 child.edge
        # 原 child 拆成 mid -> 原 child（edge=剩余部分）
        mid = _Node(edge=child.edge[:common])
        child.edge = child.edge[common:]
        # mid 接管原 child 的位置
        node.children[first] = mid
        mid.children[child.edge[0]] = child

        rest_key = key[common:]
        if not rest_key:
            # key 正好到 mid 结束
            is_new = not mid.has_value
            if is_new:
                self._size += 1
            mid.has_value = True
            mid.value = value
            return is_new
        else:
            # 新建一个子节点挂到 mid
            new_node = _Node(edge=rest_key)
            new_node.has_value = True
            new_node.value = value
            mid.children[rest_key[0]] = new_node
            self._size += 1
            return True

    def get(self, key: str) -> Any:
        """精确查找。"""
        with self._lock:
            node = self._find_exact(self._root, key)
            if node is None or not node.has_value:
                return None
            return True if node.value is None else node.value

    def _find_exact(self, node: _Node, key: str) -> _Node | None:
        if not key:
            return node
        child = node.children.get(key[0])
        if child is None:
            return None
        if not key.startswith(child.edge):
            return None
        return self._find_exact(child, key[len(child.edge):])

    def __contains__(self, key: str) -> bool:
        with self._lock:
            node = self._find_exact(self._root, key)
            return node is not None and node.has_value

    def longest_prefix(self, key: str) -> str:
        """返回树中作为 key 前缀的最长完整 key。无则空串。"""
        with self._lock:
            best = ""
            accumulated = ""
            node = self._root
            if node.has_value:
                best = ""
            remaining = key
            while remaining:
                child = node.children.get(remaining[0])
                if child is None:
                    break
                if not remaining.startswith(child.edge):
                    # 部分匹配，无法继续
                    break
                accumulated += child.edge
                remaining = remaining[len(child.edge):]
                node = child
                if node.has_value:
                    best = accumulated
            return best

    def starts_with(self, prefix: str) -> bool:
        """是否存在以 prefix 开头的 key。"""
        with self._lock:
            return self._find_prefix_node(self._root, prefix) is not None

    def _find_prefix_node(self, node: _Node, prefix: str) -> _Node | None:
        """定位前缀所在节点（可能 prefix 落在某 edge 中间）。"""
        if not prefix:
            return node
        child = node.children.get(prefix[0])
        if child is None:
            return None
        common = _lcp(prefix, child.edge)
        if common == len(prefix):
            # prefix 是 child.edge 的前缀
            return child
        if common == len(child.edge):
            # child.edge 是 prefix 的前缀，继续递归
            return self._find_prefix_node(child, prefix[common:])
        return None

    def keys_with_prefix(self, prefix: str, limit: int = 100) -> list[str]:
        """返回所有以 prefix 开头的 key。"""
        result: list[str] = []
        if limit <= 0:
            return result
        with self._lock:
            start, base = self._find_prefix_with_base(self._root, prefix, "")
            if start is None:
                return result
            self._collect(start, base, result, limit)
        return result

    def _find_prefix_with_base(
        self, node: _Node, prefix: str, accumulated: str,
    ) -> tuple[_Node | None, str]:
        """返回 (前缀所在节点, 该节点的完整 key)。"""
        if not prefix:
            return node, accumulated
        child = node.children.get(prefix[0])
        if child is None:
            return None, accumulated
        common = _lcp(prefix, child.edge)
        new_accumulated = accumulated + child.edge
        if common == len(prefix):
            # prefix 是 child.edge 的前缀（含相等）
            return child, new_accumulated
        if common == len(child.edge):
            # child.edge 是 prefix 的前缀，递归
            return self._find_prefix_with_base(child, prefix[common:], new_accumulated)
        return None, accumulated

    def _collect(self, node: _Node, base: str, result: list[str], limit: int) -> None:
        if len(result) >= limit:
            return
        if node.has_value:
            result.append(base)
        for first in sorted(node.children.keys()):
            child = node.children[first]
            self._collect(child, base + child.edge, result, limit)
            if len(result) >= limit:
                return

    def delete(self, key: str) -> bool:
        """删除 key。返回是否成功。"""
        if not key:
            return False
        with self._lock:
            # 走一遍收集路径，便于回溯合并
            path: list[tuple[_Node, _Node]] = []  # (parent, child)
            node = self._root
            remaining = key
            while remaining:
                child = node.children.get(remaining[0])
                if child is None or not remaining.startswith(child.edge):
                    return False
                path.append((node, child))
                remaining = remaining[len(child.edge):]
                node = child
            if not node.has_value:
                return False
            node.has_value = False
            node.value = None
            self._size -= 1
            # 从叶子向上合并
            # 反向遍历 path
            for parent, child in reversed(path):
                if not child.has_value and not child.children:
                    del parent.children[child.edge[0]]
                elif len(child.children) == 1 and not child.has_value:
                    # 合并 child 与其唯一子节点
                    only = next(iter(child.children.values()))
                    child.edge = child.edge + only.edge
                    child.value = only.value
                    child.has_value = only.has_value
                    child.children = only.children
            return True

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            result: list[str] = []
            self._collect(self._root, "", result, 1 << 30)
            return iter(result)

    def delete_prefix(self, prefix):
        with self._lock:
            keys_to_delete = self.keys_with_prefix(prefix, limit=1 << 30)
            if not keys_to_delete:
                return False
            for key in keys_to_delete:
                self.delete(key)
            return True

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "root_children": len(self._root.children),
            }
