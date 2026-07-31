"""BlueDeer 资料库（Library）：森林公司知识中心。

基于 RAGSystem 封装，提供三层知识体系：
- 全局公共库：所有人可读
- 岗位私有库：按岗位隔离
- 临时任务库：按任务隔离
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.rag import RAGSystem, RagCapable

logger = logging.getLogger("bluedeer.library")


class LibraryScope(Enum):
    """资料库作用域。"""
    GLOBAL = "global"          # 全局公共库
    ROLE = "role"              # 岗位私有库
    TASK = "task"              # 临时任务库


@dataclass
class KnowledgeEntry:
    """知识条目。"""
    entry_id: str
    title: str
    content: str
    scope: LibraryScope
    scope_key: str             # role 时为岗位名，task 时为 task_id，global 为 "common"
    tags: list[str] = field(default_factory=list)
    author: str = ""
    created_at: float = field(default_factory=time.time)
    access_count: int = 0


class Library:
    """资料库 = 公司知识中心。

    封装 RAGSystem，提供三层知识管理：
    - 全局公共库：全员共享
    - 岗位私有库：按角色隔离
    - 临时任务库：任务级别隔离
    """

    def __init__(self, rag: RAGSystem | None = None) -> None:
        self._rag = rag or RAGSystem()
        self._entries: dict[str, KnowledgeEntry] = {}

    # ---- 知识入库 ----

    def store(
        self,
        title: str,
        content: str,
        scope: LibraryScope = LibraryScope.GLOBAL,
        scope_key: str = "common",
        tags: list[str] | None = None,
        author: str = "",
    ) -> str:
        """存入知识条目，同时写入 RAG 和本地索引。"""
        entry_id = f"lib_{int(time.time() * 1000)}_{hash(content) % 10000}"
        entry = KnowledgeEntry(
            entry_id=entry_id,
            title=title,
            content=content,
            scope=scope,
            scope_key=scope_key,
            tags=tags or [],
            author=author,
        )
        self._entries[entry_id] = entry

        # 写入 RAG 系统（适配实际 RAGSystem.ingest 签名）
        metadata = {
            "entry_id": entry_id,
            "scope": scope.value,
            "scope_key": scope_key,
            "tags": ",".join(entry.tags),
            "title": title,
            "author": author,
        }
        rag_sub_id = scope_key if scope in (LibraryScope.ROLE, LibraryScope.TASK) else ""
        self._rag.ingest(
            scope=scope.value,
            id=entry_id,
            text=content,
            metadata=metadata,
            sub_id=rag_sub_id,
        )
        logger.info("资料库新增: [%s/%s] %s", scope.value, scope_key, title)
        return entry_id

    # ---- 知识检索 ----

    def search(
        self,
        query: str,
        scope: LibraryScope | None = None,
        scope_key: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeEntry]:
        """检索知识条目，支持按 scope 过滤。"""
        if scope is not None:
            # 定向检索指定层
            rag_sub_id = (
                scope_key
                if scope in (LibraryScope.ROLE, LibraryScope.TASK)
                else (scope_key or "")
            )
            results = self._rag.retrieve(
                query=query,
                scope=scope.value,
                sub_id=rag_sub_id,
                top_k=top_k * 3,
            )
        else:
            # 跨层检索所有已知作用域
            scopes: list[tuple[str, str]] = []
            seen_scope: set[tuple[str, str]] = set()
            for e in self._entries.values():
                rag_scope = e.scope.value
                rag_sub_id = (
                    e.scope_key
                    if e.scope in (LibraryScope.ROLE, LibraryScope.TASK)
                    else ""
                )
                key = (rag_scope, rag_sub_id)
                if key not in seen_scope:
                    seen_scope.add(key)
                    scopes.append(key)
            if not scopes:
                return []
            results = self._rag.retrieve_cross(query, scopes, top_k=top_k * 3)

        matched: list[KnowledgeEntry] = []
        seen: set[str] = set()
        for r in results:
            entry_id = r.metadata.get("entry_id", "")
            if entry_id in seen:
                continue
            seen.add(entry_id)
            entry = self._entries.get(entry_id)
            if entry is None:
                continue
            # 按 scope 过滤
            if scope is not None and entry.scope != scope:
                continue
            if scope_key is not None and entry.scope_key != scope_key:
                continue
            entry.access_count += 1
            matched.append(entry)
            if len(matched) >= top_k:
                break
        return matched

    def search_by_name(self, query: str) -> list[KnowledgeEntry]:
        """按名称或标签本地搜索条目（不依赖 RAG）。"""
        q = query.lower()
        return [
            e for e in self._entries.values()
            if q in e.title.lower()
            or any(q in t.lower() for t in e.tags)
        ]

    def categorize(self, tags: list[str]) -> dict[str, list[KnowledgeEntry]]:
        """按标签分组条目。"""
        return {
            tag: [e for e in self._entries.values() if tag in e.tags]
            for tag in tags
        }

    def list_by_category(self) -> dict[str, list[KnowledgeEntry]]:
        """按 scope/scope_key 分组浏览。"""
        groups: dict[str, list[KnowledgeEntry]] = {}
        for e in self._entries.values():
            key = f"{e.scope.value}/{e.scope_key}"
            groups.setdefault(key, []).append(e)
        return groups

    def get_by_scope(self, scope: LibraryScope, scope_key: str = "common") -> list[KnowledgeEntry]:
        """按作用域获取所有条目。"""
        return [
            e for e in self._entries.values()
            if e.scope == scope and e.scope_key == scope_key
        ]

    # ---- 统计 ----

    def stats(self) -> dict[str, Any]:
        """资料库统计。"""
        counts: dict[str, int] = {}
        for e in self._entries.values():
            key = f"{e.scope.value}/{e.scope_key}"
            counts[key] = counts.get(key, 0) + 1
        # 各层文档数汇总
        doc_counts: dict[str, int] = {}
        for e in self._entries.values():
            key = f"{e.scope.value}/{e.scope_key}"
            rag_sub_id = (
                e.scope_key
                if e.scope in (LibraryScope.ROLE, LibraryScope.TASK)
                else ""
            )
            doc_counts[key] = self._rag.get_store_size(e.scope.value, rag_sub_id)
        return {
            "total_entries": len(self._entries),
            "by_scope": counts,
            "rag_store_sizes": doc_counts,
        }

    def to_dict(self) -> dict[str, Any]:
        """导出资料库状态。"""
        return {
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "title": e.title,
                    "scope": e.scope.value,
                    "scope_key": e.scope_key,
                    "tags": e.tags,
                    "author": e.author,
                    "access_count": e.access_count,
                    "created_at": e.created_at,
                }
                for e in self._entries.values()
            ],
            "stats": self.stats(),
        }