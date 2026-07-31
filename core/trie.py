"""BlueDeer Trie 前缀树：自动补全 + 前缀匹配。

evolution（数据维度 - R182）：
- dict 只能精确匹配，无法按前缀查找（搜索框输入"ap"想出"apple"/"application"）
- Trie 按字符分叉，公共前缀共享存储，前缀查询 O(L)
- 支持：插入/精确查找/前缀判定/自动补全/最长前缀匹配/删除
- 可挂 value（实现 key-value 字典），无 value 则视为集合
"""
from __future__ import annotations
import threading
from typing import Any, Iterator


class _Node:
    __slots__ = ("children", "value", "has_value", "prefix_count")

    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.value: Any = None
        self.has_value: bool = False
        self.prefix_count: int = 0  # 经过此节点的单词数（含已结束的）


class Trie:
    """前缀树。

    用法：
        t = Trie()
        t.insert("apple")
        t.insert("application", value=42)
        assert t.search("apple")
        assert t.starts_with("ap")
        assert t.autocomplete("ap", limit=5) == ["apple", "application"]
        assert t.longest_prefix("applesauce") == "apple"
    """

    def __init__(self) -> None:
        self._root = _Node()
        self._size = 0
        self._lock = threading.RLock()

    def __len__(self) -> int:
        return self._size

    def insert(self, word: str, value: Any = None) -> bool:
        """插入单词（可挂 value）。返回是否新增（False=已存在只更新 value）。"""
        if not isinstance(word, str):
            raise TypeError("word 必须 str")
        with self._lock:
            node = self._root
            for ch in word:
                child = node.children.get(ch)
                if child is None:
                    child = _Node()
                    node.children[ch] = child
                child.prefix_count += 1
                node = child
            is_new = not node.has_value
            if is_new:
                self._size += 1
                node.prefix_count += 1
            node.has_value = True
            node.value = value
            return is_new

    def search(self, word: str) -> Any:
        """精确查找。不存在返回 None；存在但无 value 返回 True；否则返回 value。"""
        with self._lock:
            node = self._find_node(word)
            if node is None or not node.has_value:
                return None
            return True if node.value is None else node.value

    def _find_node(self, word: str) -> _Node | None:
        node = self._root
        for ch in word:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def starts_with(self, prefix: str) -> bool:
        """是否存在以 prefix 开头的单词。"""
        with self._lock:
            return self._find_node(prefix) is not None

    def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        """返回以 prefix 开头的所有单词（最多 limit 个）。"""
        if limit <= 0:
            return []
        result: list[str] = []
        with self._lock:
            start = self._find_node(prefix)
            if start is None:
                return result
            # DFS 收集
            stack: list[tuple[_Node, str]] = [(start, prefix)]
            while stack:
                node, cur = stack.pop()
                if node.has_value:
                    result.append(cur)
                    if len(result) >= limit:
                        break
                # 字典序逆序入栈，正序出栈
                for ch in sorted(node.children.keys(), reverse=True):
                    stack.append((node.children[ch], cur + ch))
        return result

    def longest_prefix(self, word: str) -> str:
        """返回 word 中作为完整单词的最长前缀。无则空串。"""
        with self._lock:
            node = self._root
            longest = ""
            cur = ""
            for ch in word:
                child = node.children.get(ch)
                if child is None:
                    break
                cur += ch
                node = child
                if node.has_value:
                    longest = cur
            return longest

    def delete(self, word: str) -> bool:
        """删除单词。返回是否删除成功。"""
        if not word:
            return False
        with self._lock:
            # 先确认存在
            target = self._find_node(word)
            if target is None or not target.has_value:
                return False
            target.has_value = False
            target.value = None
            target.prefix_count -= 1
            self._size -= 1
            # 反向清理空分支
            # 重新遍历找各节点，删除 prefix_count==0 的子节点
            node = self._root
            path: list[tuple[_Node, str]] = []
            for ch in word:
                child = node.children.get(ch)
                path.append((node, ch))
                child.prefix_count -= 1
                node = child
            # 从尾到头删空节点
            for parent, ch in reversed(path):
                child = parent.children.get(ch)
                if child is not None and child.prefix_count <= 0 and not child.has_value and not child.children:
                    del parent.children[ch]
            return True

    def __contains__(self, word: str) -> bool:
        with self._lock:
            node = self._find_node(word)
            return node is not None and node.has_value

    def __iter__(self) -> Iterator[str]:
        with self._lock:
            yield from self._iter(self._root, "")

    def _iter(self, node: _Node, prefix: str) -> Iterator[str]:
        if node.has_value:
            yield prefix
        for ch in sorted(node.children.keys()):
            yield from self._iter(node.children[ch], prefix + ch)

    def fuzzy_search(self, pattern):
        results = []
        with self._lock:
            self._fuzzy(self._root, pattern, 0, "", results)
        return sorted(set(results))

    def _fuzzy(self, node, pattern, idx, cur, results):
        if idx == len(pattern):
            if node.has_value:
                results.append(cur)
            return
        ch = pattern[idx]
        if ch == '*':
            self._fuzzy(node, pattern, idx + 1, cur, results)
            for c in sorted(node.children.keys()):
                self._fuzzy(node.children[c], pattern, idx, cur + c, results)
        elif ch == '?':
            for c in sorted(node.children.keys()):
                self._fuzzy(node.children[c], pattern, idx + 1, cur + c, results)
        else:
            child = node.children.get(ch)
            if child is not None:
                self._fuzzy(child, pattern, idx + 1, cur + ch, results)

    def status(self) -> dict:
        with self._lock:
            return {
                "size": self._size,
                "root_children": len(self._root.children),
            }
