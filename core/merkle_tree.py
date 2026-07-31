"""BlueDeer 默克尔树：哈希树 + 完整性校验 + 证明。

evolution（数据维度 - R196）：
- 默克尔树是数据完整性校验的核心结构
- 叶子节点存数据哈希，内部节点存子节点哈希的组合
- 根哈希（root hash）代表整体数据指纹
- 任一叶变更 → 根哈希变化
- 默克尔证明：给定叶子，提供兄弟路径，无需全量数据即可验证归属
- 应用：Git、区块链、分布式存储、文件同步
"""
from __future__ import annotations
import hashlib
import threading
from typing import Any


def _hash(data: bytes) -> str:
    """SHA-256 哈希（返回十六进制字符串）。"""
    return hashlib.sha256(data).hexdigest()


def _to_bytes(item: Any) -> bytes:
    """将任意项转为字节。"""
    if isinstance(item, bytes):
        return item
    if isinstance(item, str):
        return item.encode("utf-8")
    return str(item).encode("utf-8")


class _Node:
    """默克尔树节点。"""
    __slots__ = ("hash", "left", "right", "is_leaf", "data")

    def __init__(self, hash_val: str, is_leaf: bool, data: Any = None):
        self.hash = hash_val
        self.left: _Node | None = None
        self.right: _Node | None = None
        self.is_leaf = is_leaf
        self.data = data  # 仅叶子节点存原始数据


class MerkleTree:
    """默克尔树：哈希树 + 完整性校验。

    用法：
        mt = MerkleTree(["a", "b", "c", "d"])
        root = mt.root_hash()
        proof = mt.get_proof(0)  # 叶子 0 的默克尔证明
        MerkleTree.verify("a", proof, root)  # True
    """

    def __init__(self, items: list | None = None):
        self._lock = threading.RLock()
        self._leaves: list[_Node] = []
        self._root: _Node | None = None
        if items:
            self.build(items)

    def __len__(self) -> int:
        return len(self._leaves)

    def build(self, items: list) -> str:
        """从数据列表构建树，返回根哈希。"""
        with self._lock:
            # 构造叶子
            self._leaves = [_Node(_hash(_to_bytes(item)), True, item) for item in items]
            if not self._leaves:
                self._root = None
                return ""
            # 自底向上构造
            level = list(self._leaves)
            while len(level) > 1:
                next_level = []
                i = 0
                while i < len(level):
                    left = level[i]
                    right = level[i + 1] if i + 1 < len(level) else None
                    if right is None:
                        # 奇数个：复制左节点
                        combined = left.hash + left.hash
                    else:
                        combined = left.hash + right.hash
                    parent = _Node(_hash(combined.encode("utf-8")), False)
                    parent.left = left
                    parent.right = right if right is not None else left
                    next_level.append(parent)
                    i += 2
                level = next_level
            self._root = level[0]
            return self._root.hash

    def root_hash(self) -> str:
        """返回根哈希。"""
        with self._lock:
            return self._root.hash if self._root else ""

    def update_leaf(self, index: int, item: Any) -> bool:
        """更新叶子数据，重算路径哈希。"""
        with self._lock:
            if index < 0 or index >= len(self._leaves):
                return False
            # 更新叶子
            leaf = self._leaves[index]
            leaf.data = item
            leaf.hash = _hash(_to_bytes(item))
            # 重算：从根开始重算（简化版，直接 rebuild）
            # 更高效的做法是记录路径，但 rebuild 在叶子数不大时可接受
            data_list = [n.data for n in self._leaves]
            self.build(data_list)
            return True

    def append_leaf(self, item: Any) -> None:
        """追加一个叶子，重建树。"""
        with self._lock:
            data_list = [n.data for n in self._leaves] + [item]
            self.build(data_list)

    def get_proof(self, index: int) -> list[tuple[str, str]] | None:
        """获取叶子 index 的默克尔证明。

        返回兄弟路径：[(sibling_hash, direction), ...]
        direction: "left"=兄弟在左，"right"=兄弟在右
        验证时从叶子开始，按方向与兄弟哈希组合。
        """
        with self._lock:
            if index < 0 or index >= len(self._leaves) or self._root is None:
                return None
            proof = []
            # 从根向下找路径
            path = self._find_path(self._root, index, len(self._leaves))
            # path 是从根到叶的节点列表
            # 对每层，记录兄弟
            for i in range(len(path) - 1):
                node = path[i]
                child = path[i + 1]
                if node.left is child:
                    sibling = node.right
                    if sibling is None or sibling is child:
                        proof.append((node.left.hash, "right"))  # 复制情况
                    else:
                        proof.append((sibling.hash, "right"))
                else:
                    sibling = node.left
                    proof.append((sibling.hash, "left"))
            # 反转：从叶到根
            proof.reverse()
            return proof

    def _find_path(self, node: _Node, index: int, leaf_count: int) -> list[_Node]:
        """找从 node 到第 index 个叶子的路径。"""
        path = [node]
        if node.is_leaf:
            return path
        # 计算左子树叶子数
        left_count = self._leaf_count(node.left)
        if index < left_count:
            path.extend(self._find_path(node.left, index, left_count))
        else:
            path.extend(self._find_path(node.right, index - left_count, leaf_count - left_count))
        return path

    def _leaf_count(self, node: _Node | None) -> int:
        """计算子树叶子数。"""
        if node is None:
            return 0
        if node.is_leaf:
            return 1
        return self._leaf_count(node.left) + self._leaf_count(node.right)

    @staticmethod
    def verify(item: Any, proof: list[tuple[str, str]], root_hash: str) -> bool:
        """验证默克尔证明。

        从叶子哈希开始，按 proof 逐层组合，最终应等于 root_hash。
        """
        h = _hash(_to_bytes(item))
        for sibling_hash, direction in proof:
            if direction == "right":
                combined = h + sibling_hash
            else:  # left
                combined = sibling_hash + h
            h = _hash(combined.encode("utf-8"))
        return h == root_hash

    def verify_integrity(self, items: list) -> bool:
        """验证 items 是否与当前树一致。"""
        with self._lock:
            if len(items) != len(self._leaves):
                return False
            for i, item in enumerate(items):
                if self._leaves[i].data != item:
                    return False
            # 检查哈希
            other = MerkleTree(items)
            return other.root_hash() == self.root_hash()

    def diff(self, other: "MerkleTree") -> list[int]:
        """找出与 other 不同的叶子索引列表。

        利用默克尔树特性：子树哈希相同则该子树无差异。
        """
        with self._lock:
            if len(self._leaves) != len(other._leaves):
                # 长度不同，全部标记
                return list(range(max(len(self._leaves), len(other._leaves))))
            diffs = []
            self._diff_nodes(self._root, other._root, diffs, 0)
            return diffs

    def _diff_nodes(self, a: _Node | None, b: _Node | None, diffs: list, base: int) -> None:
        if a is None and b is None:
            return
        if a is None or b is None:
            diffs.append(base)
            return
        if a.hash == b.hash:
            return  # 子树相同，无差异
        if a.is_leaf or b.is_leaf:
            diffs.append(base)
            return
        left_count = self._leaf_count(a.left) if a.left else 0
        self._diff_nodes(a.left, b.left, diffs, base)
        self._diff_nodes(a.right, b.right, diffs, base + left_count)

    def generate_proof(self, index):
        return self.get_proof(index)

    def diff_sync(self, other):
        with self._lock:
            if len(self._leaves) != len(other._leaves):
                self.build([n.data for n in other._leaves])
                return True
            diffs = self.diff(other)
            if not diffs:
                return False
            other_data = [other._leaves[i].data for i in range(len(other._leaves))]
            self.build(other_data)
            return True

    def status(self) -> dict:
        with self._lock:
            def depth(n):
                if n is None:
                    return 0
                if n.is_leaf:
                    return 1
                return 1 + max(depth(n.left), depth(n.right))
            return {
                "leaf_count": len(self._leaves),
                "root_hash": self.root_hash()[:16] + "..." if self._root else "",
                "depth": depth(self._root),
                "full_root_hash": self.root_hash(),
            }
