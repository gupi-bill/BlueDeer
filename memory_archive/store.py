"""BlueDeer 记忆存储：基于现有 vector_db 的持久化层。"""

from __future__ import annotations

import json
import os
import time

from memory_archive.schemas import MemoryEntry, MemoryType, RetrievalResult

try:
    from vector_db.vector_store import (
        SearchResult as VSResult,  # noqa: F401 (availability check)
    )
    from vector_db.vector_store import VectorStore

    _VECTOR_DB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _VECTOR_DB_AVAILABLE = False



class MemoryStore:
    """记忆存储后端。

    优先复用 vector_db 做向量检索；回退到内存 dict。
    同时维护独立的时间序列表（用于 episodic 检索）。
    """

    def __init__(self, data_dir: str = "memory_archive/data") -> None:
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self._entries: dict[str, MemoryEntry] = {}
        self._agent_index: dict[str, list[str]] = {}
        self._type_index: dict[str, list[str]] = {}
        self._vs: VectorStore | None = None
        if _VECTOR_DB_AVAILABLE:
            self._vs = VectorStore()
            self._load_vector_store()

    def _load_vector_store(self) -> None:
        path = os.path.join(self._data_dir, "vectors.json")
        if os.path.exists(path) and self._vs is not None:
            try:
                self._vs = VectorStore.from_dict(json.loads(open(path, encoding="utf-8").read()))
            except Exception:
                pass

    def _save_vector_store(self) -> None:
        if self._vs is None:
            return
        path = os.path.join(self._data_dir, "vectors.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._vs.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, entry: MemoryEntry) -> None:
        self._entries[entry.id] = entry
        self._agent_index.setdefault(entry.agent_id, []).append(entry.id)
        self._type_index.setdefault(entry.memory_type.value, []).append(entry.id)
        if self._vs is not None:
            self._vs.insert(entry.id, entry.content, entry.metadata)

    def get(self, memory_id: str) -> MemoryEntry | None:
        return self._entries.get(memory_id)

    def get_by_agent(self, agent_id: str) -> list[MemoryEntry]:
        ids = self._agent_index.get(agent_id, [])
        return [self._entries[i] for i in ids if i in self._entries]

    def get_by_type(self, memory_type: MemoryType | str) -> list[MemoryEntry]:
        key = memory_type.value if isinstance(memory_type, MemoryType) else memory_type
        ids = self._type_index.get(key, [])
        return [self._entries[i] for i in ids if i in self._entries]

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        if self._vs is None:
            return []
        results = self._vs.search(query, top_k=top_k)
        out: list[RetrievalResult] = []
        for r in results:
            entry = self._entries.get(r.id)
            if entry is not None:
                entry.touch()
                out.append(RetrievalResult(entry=entry, score=r.score))
        return out

    def delete(self, memory_id: str) -> bool:
        entry = self._entries.pop(memory_id, None)
        if entry is None:
            return False
        self._agent_index.get(entry.agent_id, []).remove(memory_id)
        self._type_index.get(entry.memory_type.value, []).remove(memory_id)
        if self._vs is not None:
            try:
                self._vs.delete(memory_id)
            except Exception:
                pass
        return True

    def persist(self) -> None:
        self._save_vector_store()
        path = os.path.join(self._data_dir, "memories.json")
        try:
            data = {
                e.id: {
                    "agent_id": e.agent_id,
                    "memory_type": e.memory_type.value,
                    "content": e.content,
                    "importance": e.importance,
                    "created_at": e.created_at,
                    "updated_at": e.updated_at,
                    "access_count": e.access_count,
                    "last_accessed_at": e.last_accessed_at,
                    "metadata": e.metadata,
                    "related_ids": e.related_ids,
                }
                for e in self._entries.values()
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load(self) -> None:
        path = os.path.join(self._data_dir, "memories.json")
        if not os.path.exists(path):
            return
        try:
            raw = json.loads(open(path, encoding="utf-8").read())
            for mid, m in raw.items():
                entry = MemoryEntry(
                    id=mid,
                    agent_id=m["agent_id"],
                    memory_type=MemoryType(m["memory_type"]),
                    content=m["content"],
                    importance=m.get("importance", 0.5),
                    created_at=m.get("created_at", time.time()),
                    updated_at=m.get("updated_at", time.time()),
                    access_count=m.get("access_count", 0),
                    last_accessed_at=m.get("last_accessed_at", time.time()),
                    metadata=m.get("metadata", {}),
                    related_ids=m.get("related_ids", []),
                )
                self._entries[mid] = entry
                self._agent_index.setdefault(entry.agent_id, []).append(mid)
                self._type_index.setdefault(entry.memory_type.value, []).append(mid)
                if self._vs is not None:
                    self._vs.add_document(mid, entry.content, entry.metadata)
        except Exception:
            pass

    @property
    def count(self) -> int:
        return len(self._entries)
