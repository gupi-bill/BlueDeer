"""BlueDeer 奖励系统核心：RewardSystem。"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

from core.reward.achievements import _ACHIEVEMENT_DEFS, _check_threshold
from core.reward.profile import AgentProfile
from core.reward.progression import favor_gain, get_level_perks
from core.task import TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.reward")

# 分岗位差异化奖励规则
_ROLE_BONUSES: dict[tuple[str, str], int] = {
    ("squirrel", "code_fix"): 5,
    ("hedgehog", "security_block"): 8,
    ("owl", "dream_yield"): 6,
    ("beaver", "commit_norm"): 4,
    ("fox", "test_pass"): 5,
}


class RewardSystem:
    """游戏化奖惩系统。

    根据任务结果实时结算金币/经验/好感度，检查成就解锁，生成排行榜。
    P6 前置优化：30 项成就三梯次 + 指数等级 + 递减好感 + 连续失败递增惩罚。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        self._lock = threading.Lock()

    def get_profile(self, agent_id: str) -> AgentProfile:
        """获取员工档案，不存在则创建。"""
        with self._lock:
            if agent_id not in self._profiles:
                self._profiles[agent_id] = AgentProfile(agent_id=agent_id)
            return self._profiles[agent_id]

    def settle(self, result: TaskResult, agent_id: str) -> AgentProfile:
        """结算任务结果，更新数值。

        Args:
            result: 任务结果。
            agent_id: 员工 ID。

        Returns:
            更新后的员工档案。
        """
        profile = self.get_profile(agent_id)
        profile.total_tasks += 1

        if result.status == TaskStatus.SUCCESS:
            profile.coins += 10
            profile.exp += 20
            gain = favor_gain(500, profile.favor)
            profile.favor += gain
            profile.success_count += 1
            profile.streak += 1
            profile.consecutive_fails = 0

            if result.output and isinstance(result.output, dict):
                code = result.output.get("generated_code", "")
                if code:
                    profile.code_lines += code.count("\n") + 1

            logger.info(
                "奖惩结算: agent=%s, SUCCESS, coins=%d, exp=%d, favor=%d(+%d), streak=%d",
                agent_id,
                profile.coins,
                profile.exp,
                profile.favor,
                gain,
                profile.streak,
            )
        else:
            profile.coins += 2
            profile.exp += 5
            profile.favor = max(100, profile.favor - 50)
            profile.failed_count += 1
            profile.streak = 0
            profile.consecutive_fails += 1

            n = profile.consecutive_fails
            extra_penalty = min(50, 10 * n)
            if extra_penalty > 0:
                profile.coins -= extra_penalty
                logger.warning(
                    "连续失败惩罚: agent=%s, 第 %d 次连续失败, 额外扣 %d 金币",
                    agent_id,
                    n,
                    extra_penalty,
                )

            logger.info(
                "奖惩结算: agent=%s, FAILED, coins=%d, exp=%d, favor=%d, consecutive_fails=%d",
                agent_id,
                profile.coins,
                profile.exp,
                profile.favor,
                profile.consecutive_fails,
            )

        self._check_achievements(agent_id)
        return profile

    def add_dream_memory(
        self,
        agent_id: str,
        count: int = 1,
        high_quality_count: int = 0,
    ) -> None:
        """增加梦境固化记忆计数。"""
        profile = self.get_profile(agent_id)
        profile.dream_memories += count
        profile.dream_quality_high += high_quality_count
        self._check_achievements(agent_id)

    def add_scan(self, agent_id: str, count: int = 1) -> None:
        """增加安全扫描计数。"""
        profile = self.get_profile(agent_id)
        profile.scan_count += count
        self._check_achievements(agent_id)

    def add_block(self, agent_id: str, count: int = 1) -> None:
        """增加高危拦截计数。"""
        profile = self.get_profile(agent_id)
        profile.block_count += count
        self._check_achievements(agent_id)

    def add_token_saved(self, agent_id: str, tokens: int) -> None:
        """增加累计节省 Token。"""
        if tokens <= 0:
            return
        profile = self.get_profile(agent_id)
        profile.token_saved += tokens
        self._check_achievements(agent_id)

    def update_lowcost_ratio(self, agent_id: str, ratio: float) -> None:
        """更新低成本模型调用占比（0-100）。"""
        profile = self.get_profile(agent_id)
        profile.lowcost_ratio = max(0.0, min(100.0, ratio))
        self._check_achievements(agent_id)

    def grant_role_bonus(self, agent_id: str, action_type: str) -> int:
        """发放岗位差异化奖励。"""
        bonus = _ROLE_BONUSES.get((agent_id, action_type), 0)
        if bonus <= 0:
            return 0
        profile = self.get_profile(agent_id)
        profile.coins += bonus
        if action_type == "code_fix":
            profile.code_fix_count += 1
        elif action_type == "commit_norm":
            profile.commit_count += 1
        elif action_type == "test_pass":
            profile.test_pass_count += 1
        logger.info(
            "岗位奖励: agent=%s, action=%s, +%d 金币",
            agent_id,
            action_type,
            bonus,
        )
        self._check_achievements(agent_id)
        return bonus

    def penalize_token_overspend(self, agent_id: str, tokens: int) -> int:
        """Token 超额扣减奖励。"""
        if tokens <= 5000:
            return 0
        over = tokens - 5000
        penalty = over // 1000
        if penalty <= 0:
            return 0
        profile = self.get_profile(agent_id)
        profile.coins -= penalty
        profile.token_overspend_penalty += penalty
        logger.warning(
            "Token 超额扣减: agent=%s, tokens=%d, 超 %d, 扣 %d 金币",
            agent_id,
            tokens,
            over,
            penalty,
        )
        return penalty

    def get_perks(self, agent_id: str) -> list[str]:
        """获取员工已解锁的全部特权。"""
        return get_level_perks(self.get_profile(agent_id).level)

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

    def leaderboard(self, sort_by: str = "composite") -> list[dict[str, Any]]:
        """生成排行榜。"""
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

    def save(self, path: str) -> None:
        """持久化到 JSON。"""
        import json as _json
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {}
        for agent_id, p in self._profiles.items():
            d = {
                "agent_id": p.agent_id,
                "coins": p.coins,
                "exp": p.exp,
                "favor": p.favor,
                "total_tasks": p.total_tasks,
                "success_count": p.success_count,
                "failed_count": p.failed_count,
                "streak": p.streak,
                "consecutive_fails": p.consecutive_fails,
                "code_lines": p.code_lines,
                "dream_memories": p.dream_memories,
                "dream_quality_high": p.dream_quality_high,
                "scan_count": p.scan_count,
                "block_count": p.block_count,
                "token_saved": p.token_saved,
                "lowcost_ratio": p.lowcost_ratio,
                "achievements": p.achievements,
                "code_fix_count": p.code_fix_count,
                "commit_count": p.commit_count,
                "test_pass_count": p.test_pass_count,
                "token_overspend_penalty": p.token_overspend_penalty,
            }
            data[agent_id] = d
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> RewardSystem:
        """从 JSON 加载。"""
        system = cls()
        if not os.path.exists(path):
            return system
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for agent_id, profile_data in data.items():
            profile = AgentProfile(agent_id=agent_id)
            for k, v in profile_data.items():
                if hasattr(profile, k):
                    setattr(profile, k, v)
            system._profiles[agent_id] = profile
        return system
