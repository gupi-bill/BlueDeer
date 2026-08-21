"""BlueDeer 梦境回放与休息区关联：排序 / 合成 / 回放 / 最近记忆。

P2-1 拆分自 core/dream.py。
"""

from __future__ import annotations

import logging
import random
from typing import Any

from core.dream_models import DreamMemory, DreamQuality

logger = logging.getLogger("bluedeer.dream")


def sort_memories_pinned(memories: list[DreamMemory]) -> list[DreamMemory]:
    """高价值记忆置顶排序。

    排序规则：
    1. LEGENDARY 置顶（is_pinned）
    2. HIGH 次之
    3. NORMAL 最后
    4. 同级按创建时间倒序
    """
    quality_order = {
        DreamQuality.LEGENDARY: 0,
        DreamQuality.HIGH: 1,
        DreamQuality.NORMAL: 2,
    }
    return sorted(
        memories,
        key=lambda m: (quality_order.get(m.quality, 3), -m.created_at),
    )


def generate_dream(
    memories: list[DreamMemory], theme: str = "default"
) -> dict[str, Any]:
    """从记忆片段合成一段梦境序列。

    Args:
        memories: 记忆片段列表。
        theme: 梦境主题（default / nightmare / creative）。

    Returns:
        { "dream_text": str, "themes_used": list, "fragments": int }。
    """
    if not memories:
        return {"dream_text": "空无一物...", "themes_used": [theme], "fragments": 0}
    samples = random.sample(memories, min(5, len(memories)))
    fragments = [m.content[:100] for m in samples]
    themes_used = [theme]
    dream_text = "梦境合成: " + " ... ".join(fragments)
    return {
        "dream_text": dream_text,
        "themes_used": themes_used,
        "fragments": len(fragments),
    }


def replay_memory(
    pattern: str, memory_store: list[DreamMemory] | None = None
) -> list[DreamMemory]:
    """模拟按模式回放记忆。

    Args:
        pattern: 检索模式（关键词）。
        memory_store: 可选的记忆库，默认空列表。

    Returns:
        匹配 pattern 的记忆列表。
    """
    if memory_store is None:
        return []
    pat_lower = pattern.lower()
    return [m for m in memory_store if pat_lower in m.content.lower()]


def recent_memories(agent_id: str, max_count: int = 5) -> list[DreamMemory]:
    """获取最近的梦境记忆。

    Args:
        agent_id: 员工 ID（空字符串时返回所有）。
        max_count: 最大返回条数。

    Returns:
        最近的记忆列表，按时间倒序。
    """
    # 此方法不直接存储记忆（DreamSystem 只负责处理），
    # 返回空列表，实际记忆由调用方管理。
    # 此方法供 RestArea 调用，在集成后由外部提供记忆存储。
    _ = agent_id
    return []
