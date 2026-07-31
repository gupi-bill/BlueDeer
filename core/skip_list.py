"""BlueDeer 跳表：有序集合 + 范围查询 + 随机层数。

evolution（数据维度 - R181）：
- 有序集合是缓存/排行榜/范围查询的核心数据结构
- 平衡树实现复杂，跳表用概率平衡达到 O(log n) 查找/插入/删除
- 每个节点随机出层数，多层索引加速查找
- 支持 score + member（成员唯一，score 可重复）
- 范围查询：[min, max] 内的元素
"""
from __future__ import annotations
import random
import threading
from typing import Any, Iterator


class _Node:
    """跳表节点。"""
    __slots__ = ("score", "member", "forward", "backward")

    def __init__(self, score: float, member: Any, level: int):
        self.score = score
        self.member = member
        self.forward: list[_Node | None] = [None] * level  # 各层后继
        self.backward: _Node | None = None  # 前驱（最底层）


class SkipList:
    """跳表实现的有序集合。

    用法：
        sl = SkipList()
        sl.add(1.5, "alice")
        sl.add(3.0, "bob")
        sl.add(2.0, "carol")
        # 范围查询
        items = sl.range(1.0, 2.5)  # [(1.5,"alice"), (2.0,"carol")]
        # 排名
        rank = sl.rank("alice")  # 0（第一名）
    """

    MAX_LEVEL = 32
    P = 0.25  # Redis 默认

    def __init__(self) -> None:
        self._head = _Node(float("-inf"), None, self.MAX_LEVEL)
        self._tail: _Node | None = None
        self._level = 1  # 当前最高层
        self._size = 0
        self._member_index: dict[Any, _Node] = {}  # member -> node（去重）
        self._lock = threading.RLock()
        self._rng = random.Random()

    def _random_level(self) -> int:
        """随机层数：P 概率升一层。"""
        level = 1
        while level < self.MAX_LEVEL and self._rng.random() < self.P:
            level += 1
        return level

    def __len__(self) -> int:
        return self._size

    def add(self, score: float, member: Any) -> bool:
        """添加或更新成员的 score。返回是否新增（False=更新）。"""
        with self._lock:
            # 已存在：更新 score（先删后插）
            existing = self._member_index.get(member)
            if existing is not None:
                if existing.score == score:
                    return False
                self._delete_node(existing)
            # 插入
            level = self._random_level()
            new_node = _Node(score, member, level)
            # 找各层插入位置
            update = [self._head] * self.MAX_LEVEL
            x = self._head
            for i in range(self._level - 1, -1, -1):
                while (x.forward[i] is not None
                       and (x.forward[i].score < score
                            or (x.forward[i].score == score
                                and self._cmp_member(x.forward[i].member, member) < 0))):
                    x = x.forward[i]
                update[i] = x
            # 提升层数
            if level > self._level:
                for i in range(self._level, level):
                    update[i] = self._head
                self._level = level
            # 链接
            for i in range(level):
                new_node.forward[i] = update[i].forward[i]
                update[i].forward[i] = new_node
            new_node.backward = update[0]
            if new_node.forward[0] is not None:
                new_node.forward[0].backward = new_node
            else:
                self._tail = new_node
            self._member_index[member] = new_node
            self._size += 1 if existing is None else 0
            return existing is None

    @staticmethod
    def _cmp_member(a: Any, b: Any) -> int:
        """成员排序：保证同 score 也能区分。"""
        if a == b:
            return 0
        try:
            return -1 if a < b else 1
        except TypeError:
            sa, sb = str(a), str(b)
            return -1 if sa < sb else (1 if sa > sb else 0)

    def _delete_node(self, node: _Node) -> None:
        """从链表中删除指定节点（必须持锁）。"""
        # 找到各层前驱
        update: list[_Node | None] = [None] * self.MAX_LEVEL
        x = self._head
        for i in range(self._level - 1, -1, -1):
            while (x.forward[i] is not None
                   and (x.forward[i].score < node.score
                        or (x.forward[i].score == node.score
                            and x.forward[i] is not node))):
                x = x.forward[i]
            update[i] = x
        # 断链
        for i in range(self._level):
            if update[i].forward[i] is node:
                update[i].forward[i] = node.forward[i]
        if node.forward[0] is not None:
            node.forward[0].backward = node.backward
        else:
            self._tail = node.backward
        # 降层
        while self._level > 1 and self._head.forward[self._level - 1] is None:
            self._level -= 1

    def remove(self, member: Any) -> bool:
        """删除成员。返回是否删除。"""
        with self._lock:
            node = self._member_index.get(member)
            if node is None:
                return False
            self._delete_node(node)
            self._member_index.pop(node.member, None)
            self._size -= 1
            return True

    def get_score(self, member: Any) -> float | None:
        with self._lock:
            node = self._member_index.get(member)
            return node.score if node else None

    def __contains__(self, member: Any) -> bool:
        with self._lock:
            return member in self._member_index

    def range(
        self,
        min_score: float = float("-inf"),
        max_score: float = float("inf"),
        limit: int = -1,
    ) -> list[tuple[float, Any]]:
        """返回 [min_score, max_score] 内的元素。limit 限制数量。"""
        result = []
        with self._lock:
            # 找起点
            x = self._head
            for i in range(self._level - 1, -1, -1):
                while x.forward[i] is not None and x.forward[i].score < min_score:
                    x = x.forward[i]
            x = x.forward[0]
            count = 0
            while x is not None and x.score <= max_score:
                if limit >= 0 and count >= limit:
                    break
                result.append((x.score, x.member))
                x = x.forward[0]
                count += 1
        return result

    def range_by_member(
        self, start_member: Any, end_member: Any,
    ) -> list[tuple[float, Any]]:
        """按成员顺序返回 [start, end]（按 score+member 排序）。"""
        with self._lock:
            result = []
            x = self._head.forward[0]
            started = False
            while x is not None:
                if not started:
                    if x.member == start_member:
                        started = True
                if started:
                    result.append((x.score, x.member))
                    if x.member == end_member:
                        break
                x = x.forward[0]
            return result

    def rank(self, member: Any) -> int | None:
        """返回成员排名（0-based）。不存在返回 None。"""
        with self._lock:
            node = self._member_index.get(member)
            if node is None:
                return None
            # 从头数到 node
            rank = 0
            x = self._head.forward[0]
            while x is not None and x is not node:
                rank += 1
                x = x.forward[0]
            return rank if x is node else None

    def get_by_rank(self, rank: int) -> tuple[float, Any] | None:
        """按排名取（0-based）。"""
        if rank < 0 or rank >= self._size:
            return None
        with self._lock:
            x = self._head.forward[0]
            for _ in range(rank):
                if x is None:
                    return None
                x = x.forward[0]
            return (x.score, x.member) if x else None

    def min(self) -> tuple[float, Any] | None:
        with self._lock:
            x = self._head.forward[0]
            return (x.score, x.member) if x else None

    def max(self) -> tuple[float, Any] | None:
        with self._lock:
            return (self._tail.score, self._tail.member) if self._tail else None

    def pop_min(self) -> tuple[float, Any] | None:
        with self._lock:
            x = self._head.forward[0]
            if x is None:
                return None
            self._delete_node(x)
            self._member_index.pop(x.member, None)
            self._size -= 1
            return (x.score, x.member)

    def pop_max(self) -> tuple[float, Any] | None:
        with self._lock:
            if self._tail is None:
                return None
            t = self._tail
            self._delete_node(t)
            self._member_index.pop(t.member, None)
            self._size -= 1
            return (t.score, t.member)

    def __iter__(self) -> Iterator[tuple[float, Any]]:
        with self._lock:
            x = self._head.forward[0]
            while x is not None:
                yield (x.score, x.member)
                x = x.forward[0]

    def range_query(self, lo, hi, limit=-1):
        return self.range(lo, hi, limit)

    def iter_reverse(self):
        with self._lock:
            x = self._tail
            while x is not None and x is not self._head:
                yield (x.score, x.member)
                x = x.backward

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "level": self._level,
                "max_level": self.MAX_LEVEL,
                "p": self.P,
            }
