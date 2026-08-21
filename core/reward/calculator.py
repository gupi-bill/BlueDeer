"""BlueDeer 奖励计算器：可配置曲线、衰减、排行榜。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.reward.profile import AgentProfile


@dataclass
class RewardCurve:
    """可配置的奖励/经验值递进曲线。"""

    base_coins: int = 10
    base_exp: int = 20
    coins_multiplier: float = 1.0
    exp_multiplier: float = 1.0

    def coins_for_level(self, level: int) -> int:
        return int(self.base_coins * self.coins_multiplier * (1 + level * 0.1))

    def exp_for_level(self, level: int) -> int:
        return int(self.base_exp * self.exp_multiplier * (1 + level * 0.15))


def decay(value: float, rate: float = 0.9, interval: str = "daily") -> float:
    """按周期衰减分数值。

    Args:
        value: 当前值。
        rate: 衰减系数（默认 0.9）。
        interval: 'daily' | 'weekly' | 'monthly'。

    Returns:
        衰减后的值。
    """
    multipliers = {"daily": 1, "weekly": 7, "monthly": 30}
    n = multipliers.get(interval, 1)
    return value * (rate**n)


def leaderboard(
    profiles: list[AgentProfile], metric: str = "coins", top_k: int = 10
) -> list[dict[str, Any]]:
    """根据指标对档案做排名。

    Args:
        profiles: AgentProfile 列表。
        metric: 排序字段（coins/exp/favor/level/total_tasks）。
        top_k: 返回前 k 名（默认 10）。

    Returns:
        排名列表，每条含 rank / agent_id / metric_value。
    """
    valid_metrics = {"coins", "exp", "favor", "level", "total_tasks"}
    key = metric if metric in valid_metrics else "coins"

    def _val(p: AgentProfile) -> float:
        v = getattr(p, key, 0)
        if key == "level":
            v = p.level
        return float(v)

    sorted_profiles = sorted(profiles, key=_val, reverse=True)
    result = []
    for i, p in enumerate(sorted_profiles[:top_k]):
        result.append({"rank": i + 1, "agent_id": p.agent_id, metric: _val(p)})
    return result
