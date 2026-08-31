"""BlueDeer 休息区（RestArea）：森林公司员工放松和回顾的场所。

功能：
- 梦境记忆回放：展示最近的梦境记忆
- 成功/失败记录回顾
- 放松/冥想模式
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.dream import DreamMemory, DreamQuality, DreamSystem

logger = logging.getLogger("bluedeer.restarea")


@dataclass
class RestSession:
    """休息会话记录。"""

    session_id: str
    agent_id: str
    duration: float  # 休息时长（秒）
    memories_reviewed: int = 0
    timestamp: float = field(default_factory=time.time)


RECOVERY_RATE_PER_SECOND = 0.5


class RestArea:
    """休息区 = 员工放松和回顾的场所。

    森林公司员工可以在休息区：
    - 回顾梦境记忆
    - 查看历史任务记录
    - 放松冥想
    """

    def __init__(self, dream_system: DreamSystem | None = None) -> None:
        self._dream = dream_system
        self._sessions: list[RestSession] = []
        self._recovery_log: dict[str, dict[str, float]] = {}

    # ---- 梦境回放 ----

    def review_dreams(
        self,
        agent_id: str,
        min_quality: DreamQuality = DreamQuality.NORMAL,
        max_count: int = 5,
    ) -> list[DreamMemory]:
        """回顾梦境记忆。"""
        if not self._dream:
            return []
        memories = self._dream.recent_memories(agent_id, max_count)
        return [
            m
            for m in memories
            if self._quality_rank(m.quality) >= self._quality_rank(min_quality)
        ]

    def review_highlights(self, max_count: int = 10) -> list[DreamMemory]:
        """回顾所有高质量梦境记忆（HIGH 及以上）。"""
        if not self._dream:
            return []
        return self._dream.recent_memories("", max_count * 2)[:max_count]

    @staticmethod
    def _quality_rank(q: DreamQuality) -> int:
        mapping = {
            DreamQuality.NORMAL: 0,
            DreamQuality.HIGH: 1,
            DreamQuality.LEGENDARY: 2,
        }
        return mapping.get(q, 0)

    # ---- 休息会话 ----

    def start_rest(self, agent_id: str, duration: float = 60.0) -> RestSession:
        """开始休息会话。"""
        session = RestSession(
            session_id=f"rest_{int(time.time() * 1000)}_{agent_id}",
            agent_id=agent_id,
            duration=duration,
        )
        self._sessions.append(session)
        logger.info("休息区: %s 开始休息 %.0fs", agent_id, duration)
        return session

    def end_rest(self, session_id: str, memories_reviewed: int = 0) -> bool:
        """结束休息会话。"""
        for session in self._sessions:
            if session.session_id == session_id:
                session.memories_reviewed = memories_reviewed
                logger.info(
                    "休息区: %s 结束休息，回顾了 %d 条记忆",
                    session.agent_id,
                    memories_reviewed,
                )
                return True
        return False

    # ---- 统计 ----

    def stats(self) -> dict[str, Any]:
        """休息区统计。"""
        return {
            "total_sessions": len(self._sessions),
            "total_rest_time": sum(s.duration for s in self._sessions),
            "unique_visitors": len({s.agent_id for s in self._sessions}),
        }

    # ---- 恢复 ----

    def rest(self, character: str, duration: float) -> dict[str, float]:
        """执行休息，返回恢复的 HP/Energy。"""
        recovered_hp = duration * RECOVERY_RATE_PER_SECOND
        recovered_energy = duration * RECOVERY_RATE_PER_SECOND * 0.8
        stats = self._recovery_log.setdefault(
            character, {"total_hp": 0.0, "total_energy": 0.0}
        )
        stats["total_hp"] += recovered_hp
        stats["total_energy"] += recovered_energy
        return {
            "hp_restored": recovered_hp,
            "energy_restored": recovered_energy,
            "duration": duration,
        }

    def get_recovery_stats(self, character: str) -> dict[str, float]:
        """获取角色的累计恢复统计。"""
        return self._recovery_log.get(character, {"total_hp": 0.0, "total_energy": 0.0})

    def to_dict(self) -> dict[str, Any]:
        """导出休息区状态。"""
        return {
            "recent_sessions": [
                {
                    "session_id": s.session_id,
                    "agent_id": s.agent_id,
                    "duration": s.duration,
                    "memories_reviewed": s.memories_reviewed,
                    "timestamp": s.timestamp,
                }
                for s in self._sessions[-10:]
            ],
            "stats": self.stats(),
        }
