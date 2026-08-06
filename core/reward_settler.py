"""奖励结算 Mixin：任务结果结算 / 岗位差异化奖励 / Token 超额扣减。

008-4 拆分自 core/reward.py —— 与 LeaderboardMixin / AchievementSystemMixin
组合成 RewardSystem。仅含结算相关逻辑，共享定义留在 core/reward.py 薄壳。
"""

from __future__ import annotations

import logging

from core.reward_shared import (
    _ROLE_BONUSES,
    AgentProfile,
    _cfg,
    favor_gain,
    get_level_perks,
)
from core.task import TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.reward")


class RewardSettlerMixin:
    """结算侧 Mixin：依赖宿主类提供 self._profiles 与 self._check_achievements。"""

    def get_profile(self, agent_id: str) -> AgentProfile:
        """获取员工档案，不存在则创建。"""
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
            profile.coins += _cfg.coins_success
            profile.exp += _cfg.exp_success
            gain = favor_gain(_cfg.favor_base_gain, profile.favor)
            profile.favor += gain
            profile.success_count += 1
            profile.streak += 1
            profile.consecutive_fails = 0  # 成功重置连续失败

            # 统计代码行数
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
            profile.coins += _cfg.coins_failed
            profile.exp += _cfg.exp_failed
            profile.favor = max(_cfg.favor_min, profile.favor - _cfg.favor_base_loss)
            profile.failed_count += 1
            profile.streak = 0
            profile.consecutive_fails += 1

            # 连续失败递增惩罚
            n = profile.consecutive_fails
            extra_penalty = min(
                _cfg.consecutive_fail_cap, _cfg.consecutive_fail_penalty * n
            )
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

        # 检查成就解锁
        self._check_achievements(agent_id)

        return profile

    def add_dream_memory(
        self,
        agent_id: str,
        count: int = 1,
        high_quality_count: int = 0,
    ) -> None:
        """增加梦境固化记忆计数。

        Args:
            agent_id: 员工 ID。
            count: 新增记忆总数。
            high_quality_count: 其中高质量记忆数。
        """
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

    # ============== P4 扩容：分岗位差异化奖励 ==============

    def grant_role_bonus(self, agent_id: str, action_type: str) -> int:
        """发放岗位差异化奖励。

        不同岗位的特定行为额外发金币：
        - squirrel + code_fix:    代码修复 +5
        - hedgehog + security_block: 安全拦截 +8
        - owl + dream_yield:      梦境产出 +6
        - beaver + commit_norm:   规范提交 +4
        - fox + test_pass:        测试通过 +5

        Args:
            agent_id: 员工 ID。
            action_type: 行为类型（code_fix/security_block/dream_yield/commit_norm/test_pass）。
        Returns:
            实际发放的金币数（0 表示无匹配规则）。
        """
        bonus = _ROLE_BONUSES.get((agent_id, action_type), 0)
        if bonus <= 0:
            return 0
        profile = self.get_profile(agent_id)
        profile.coins += bonus
        # 计数
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
        """Token 超额扣减奖励。

        超过 token_threshold 的部分，每 1000 Token 扣 1 金币。

        Args:
            agent_id: 员工 ID。
            tokens: 本次任务 Token 消耗。
        Returns:
            扣减的金币数（0 表示未超）。
        """
        if tokens <= _cfg.token_threshold:
            return 0
        over = tokens - _cfg.token_threshold
        penalty = over // 1000 * _cfg.token_overspend_penalty
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
