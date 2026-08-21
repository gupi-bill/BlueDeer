"""BlueDeer Memory Extractor：从对话中提取结构化记忆。

功能：
- 提取实体（人名、项目名、偏好等）
- 提取关系（谁喜欢什么、谁负责什么）
- 提取事实（可持久化的知识片段）

参考 OpenAI Memory 体系：用户级记忆 + 实体级记忆。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("bluedeer.memory_extractor")


@dataclass(slots=True)
class ExtractedEntity:
    name: str
    type: str = "unknown"
    attributes: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source_task_id: str = ""


@dataclass(slots=True)
class ExtractedRelation:
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0
    source_task_id: str = ""


@dataclass(slots=True)
class ExtractedFact:
    content: str
    category: str = "general"
    ttl: int | None = None
    confidence: float = 1.0
    source_task_id: str = ""


class MemoryExtractor:
    """从任务输出中提取结构化记忆。"""

    def __init__(self) -> None:
        self._entity_patterns = [
            re.compile(r"\b[A-Z][a-z]+\b"),
            re.compile(r"@([\w\-]+)"),
            re.compile(r"#([\w\-]+)"),
        ]

    def extract(self, task_id: str, payload: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
        entities: list[ExtractedEntity] = []
        relations: list[ExtractedRelation] = []
        facts: list[ExtractedFact] = []
        text = json.dumps(output, ensure_ascii=False)
        for pattern in self._entity_patterns:
            for match in pattern.findall(text):
                entities.append(ExtractedEntity(name=match, source_task_id=task_id))
        if "preferences" in payload and isinstance(payload["preferences"], dict):
            for key, value in payload["preferences"].items():
                relations.append(ExtractedRelation(
                    subject="user", predicate=f"prefers_{key}", object=str(value), source_task_id=task_id
                ))
                entities.append(ExtractedEntity(name=str(value), type="preference", source_task_id=task_id))
        if "project" in payload:
            entities.append(ExtractedEntity(name=str(payload["project"]), type="project", source_task_id=task_id))
        if "summary" in output and isinstance(output["summary"], str):
            facts.append(ExtractedFact(content=output["summary"][:200], category="summary", source_task_id=task_id))
        return {
            "entities": [asdict(e) for e in entities],
            "relations": [asdict(r) for r in relations],
            "facts": [asdict(f) for f in facts],
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        }
