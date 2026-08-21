"""BlueDeer 梦境记忆生命周期管理：归档 / 清理 / 快照回滚。

P2-1 拆分自 core/dream.py。
"""

from __future__ import annotations

import time
from typing import Any

from core.dream_models import DreamMemory, DreamQuality


def archive_expired(memories: list[DreamMemory]) -> int:
    """归档过期记忆。

    Args:
        memories: 待检查的记忆列表（原地修改 archived 字段）。

    Returns:
        归档数量。
    """
    count = 0
    for m in memories:
        if m.is_expired and not m.archived:
            m.archived = True
            count += 1
    if count:

        logger = __import__("logging").getLogger("bluedeer.dream")
        logger.info("记忆归档: %d 条过期记忆已归档", count)
    return count


def clean_fragments(memories: list[DreamMemory]) -> int:
    """清理低价值碎片记忆。

    Args:
        memories: 待清理列表（从列表中移除碎片）。

    Returns:
        清理数量。
    """
    before = len(memories)
    memories[:] = [m for m in memories if not m.is_fragment]
    cleaned = before - len(memories)
    if cleaned:
        logger = __import__("logging").getLogger("bluedeer.dream")
        logger.info("碎片清理: 移除 %d 条低价值记忆", cleaned)
    return cleaned


def snapshot(memories: list[DreamMemory]) -> list[dict[str, Any]]:
    """生成记忆快照（用于回滚）。

    Args:
        memories: 当前记忆列表。

    Returns:
        可序列化的快照数据。
    """
    return [
        {
            "source_task_id": m.source_task_id,
            "agent_id": m.agent_id,
            "task_type": m.task_type,
            "content": m.content,
            "quality": m.quality.value,
            "metadata": m.metadata,
            "created_at": m.created_at,
            "archived": m.archived,
        }
        for m in memories
    ]


def restore_snapshot(
    snapshot_data: list[dict[str, Any]],
) -> list[DreamMemory]:
    """从快照回滚记忆。

    Args:
        snapshot_data: snapshot() 返回的数据。

    Returns:
        恢复后的记忆列表。
    """
    memories: list[DreamMemory] = []
    for item in snapshot_data:
        quality = DreamQuality(item.get("quality", "normal"))
        memories.append(
            DreamMemory(
                source_task_id=item["source_task_id"],
                agent_id=item["agent_id"],
                task_type=item["task_type"],
                content=item["content"],
                quality=quality,
                metadata=item.get("metadata", {}),
                created_at=item.get("created_at", time.time()),
                archived=item.get("archived", False),
            )
        )
    return memories
