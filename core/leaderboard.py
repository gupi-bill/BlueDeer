"""排行榜 Mixin：员工排行榜 / 排名统计。

008-4 拆分自 core/reward.py —— 与 RewardSettlerMixin / AchievementSystemMixin
组合成 RewardSystem。仅含排行榜相关逻辑，共享定义留在 core/reward_shared.py。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("bluedeer.reward")


class LeaderboardMixin:
    """排行榜侧 Mixin：依赖宿主类提供 self._profiles。"""

    def leaderboard(self, sort_by: str = "composite") -> list[dict[str, Any]]:
        """生成排行榜。

        Args:
            sort_by: 排序维度
                - "composite"（默认）: level*1000 + coins 综合分
                - "coins" / "exp" / "favor" / "level" / "achievements" / "dream_memories"
        """
        profiles = [p.to_dict() for p in self._profiles.values()]

        def composite_score(p: dict[str, Any]) -> int:
            return p["level"] * 1000 + p["coins"]

        sort_keys = {
            "composite": composite_score,
            "coins": lambda p: p["coins"],
            "exp": lambda p: p["exp"],
            "favor": lambda p: p["favor"],
            "level": lambda p: p["level"],
            "achievements": lambda p: len(p["achievements"]),
            "dream_memories": lambda p: p["dream_memories"],
        }
        key_func = sort_keys.get(sort_by, composite_score)
        profiles.sort(key=key_func, reverse=True)
        return profiles

    def leaderboard_agent_ids(self) -> list[str]:
        """返回所有已注册 Agent 的 ID 列表（替代外部访问 _profiles）。"""
        return list(self._profiles.keys())
