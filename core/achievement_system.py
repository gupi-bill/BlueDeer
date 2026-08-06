"""成就系统 Mixin：成就检查解锁 / 详情 / 进度统计。

008-4 拆分自 core/reward.py —— 与 RewardSettlerMixin / LeaderboardMixin
组合成 RewardSystem。仅含成就相关逻辑，共享定义留在 core/reward_shared.py。
"""

from __future__ import annotations

import logging
from typing import Any

from core.reward_shared import (
    _ACHIEVEMENT_DEFS,
    _check_threshold,
)

logger = logging.getLogger("bluedeer.reward")


class AchievementSystemMixin:
    """成就系统侧 Mixin：依赖宿主类提供 self._profiles。"""

    def _check_achievements(self, agent_id: str) -> list[dict[str, str]]:
        """检查并解锁成就。

        Returns:
            本次新解锁的成就列表。
        """
        profile = self.get_profile(agent_id)
        stats = profile.to_stats()
        newly_unlocked: list[dict[str, str]] = []

        for ach in _ACHIEVEMENT_DEFS:
            if ach["id"] in profile.achievements:
                continue
            if _check_threshold(stats, ach["threshold"]):
                profile.achievements.append(ach["id"])
                newly_unlocked.append(
                    {
                        "id": ach["id"],
                        "name": ach["name"],
                        "desc": ach["desc"],
                        "tier": ach["tier"],
                        "dimension": ach["dimension"],
                    }
                )
                logger.info(
                    "成就解锁[%s]: agent=%s, %s (%s)",
                    ach["tier"],
                    agent_id,
                    ach["name"],
                    ach["desc"],
                )

        return newly_unlocked

    def get_achievements_detail(self, agent_id: str) -> list[dict[str, str]]:
        """获取员工已解锁成就详情。"""
        profile = self.get_profile(agent_id)
        result = []
        for ach in _ACHIEVEMENT_DEFS:
            if ach["id"] in profile.achievements:
                result.append(
                    {
                        "id": ach["id"],
                        "name": ach["name"],
                        "desc": ach["desc"],
                        "tier": ach["tier"],
                        "dimension": ach["dimension"],
                    }
                )
        return result

    def get_all_achievements(self) -> list[dict[str, str]]:
        """获取全部成就定义（含已解锁状态可由调用方判断）。"""
        return [
            {
                "id": a["id"],
                "name": a["name"],
                "desc": a["desc"],
                "tier": a["tier"],
                "dimension": a["dimension"],
                "threshold": a["threshold"],
            }
            for a in _ACHIEVEMENT_DEFS
        ]

    def achievement_progress(self, agent_id: str) -> dict[str, Any]:
        """成就进度统计。"""
        profile = self.get_profile(agent_id)
        unlocked = set(profile.achievements)
        by_tier: dict[str, dict[str, int]] = {}
        for ach in _ACHIEVEMENT_DEFS:
            tier = ach["tier"]
            by_tier.setdefault(tier, {"total": 0, "unlocked": 0})
            by_tier[tier]["total"] += 1
            if ach["id"] in unlocked:
                by_tier[tier]["unlocked"] += 1
        return {
            "total": len(_ACHIEVEMENT_DEFS),
            "unlocked": len(unlocked),
            "by_tier": by_tier,
        }
