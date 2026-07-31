"""BlueDeer 游戏化奖惩系统：金币/经验/好感度/成就/排行榜。

P6 前置优化版：
- 32 项成就三梯次（铜 10 / 银 12 / 金 10），覆盖代码/梦境/安全/Token/协作 5 维度
- 等级指数曲线（Lv5 需 2000 exp，Lv20 需 38000 exp）
- 好感度无上限，递减增长
- 连续失败递增惩罚
- 排行榜多维排序

P4 扩容新增：
- 分岗位差异化奖励：代码修复/安全拦截/梦境产出/规范提交单独发额外金币
- Token 超额扣减：超出阈值的 Token 消耗按比例扣减对应奖励
- 等级解锁特权：Lv5/10/15/20 解锁沙盘皮肤/模型调度特权/优先任务/核心标识
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

from core.config import get_config
from core.task import TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.reward")

# ============== 从统一配置读取奖惩数值 ==============
_cfg = get_config().reward

# ============== P4 扩容：分岗位差异化奖励规则 ==============
# 不同岗位的特定行为额外发放金币
# 键: (agent_id, action_type) → 额外金币
# action_type: code_fix / security_block / dream_yield / commit_norm / test_pass
_ROLE_BONUSES: dict[tuple[str, str], int] = {
    # 较真松鼠：代码修复 +5
    ("squirrel", "code_fix"): 5,
    # 戒备猬：安全拦截 +8
    ("hedgehog", "security_block"): 8,
    # 夜枭猫头鹰：梦境产出 +6
    ("owl", "dream_yield"): 6,
    # 勤恳海狸：规范提交 +4
    ("beaver", "commit_norm"): 4,
    # 狡黠狐狸：测试通过 +5
    ("fox", "test_pass"): 5,
}

# ============== P4 扩容：等级解锁特权 ==============
# 等级 → 特权列表
_LEVEL_PERKS: dict[int, list[str]] = {
    5:  ["沙盘皮肤·银", "低成本模型优先"],
    10: ["沙盘皮肤·金", "模型调度特权", "优先任务池"],
    15: ["沙盘皮肤·紫", "跨岗位协作权", "梦境深度推演"],
    20: ["核心骨干标识", "全模型调度权", "优先任务池", "梦境宗师特权"],
}


def get_level_perks(level: int) -> list[str]:
    """获取指定等级已解锁的全部特权。

    Lv N 解锁所有 ≤ N 的特权。
    """
    perks: list[str] = []
    for lv, ps in sorted(_LEVEL_PERKS.items()):
        if level >= lv:
            perks.extend(ps)
    return perks


# ============== 成就梯次 ==============

class AchievementTier(Enum):
    """成就梯次。"""
    BRONZE = "bronze"    # 铜：入门，约 10-50 次任务
    SILVER = "silver"    # 银：进阶，约 50-200 次任务
    GOLD = "gold"        # 金：长期，约 200-1000+ 次任务


# ============== 成就定义（30 项） ==============
# 每项: id / name / desc / tier / dimension / check(stats_dict) -> bool

def _ach(
    aid: str, name: str, desc: str, tier: AchievementTier,
    dimension: str, threshold: str,
) -> dict[str, Any]:
    """构造成就定义。check 在运行时按 threshold 字段名动态生成。"""
    return {
        "id": aid,
        "name": name,
        "desc": desc,
        "tier": tier.value,
        "dimension": dimension,
        "threshold": threshold,
    }


_ACHIEVEMENT_DEFS: list[dict[str, Any]] = [
    # ---- 铜级 10 项 ----
    _ach("first_task",      "初出茅庐", "完成第 1 个任务",            AchievementTier.BRONZE, "通用", "total_tasks:1"),
    _ach("code_100",        "百行代码", "累计生成代码 100+ 行",       AchievementTier.BRONZE, "代码", "code_lines:100"),
    _ach("streak_5",        "五连成功", "连续 5 次任务成功",          AchievementTier.BRONZE, "通用", "streak:5"),
    _ach("coins_100",       "小有积蓄", "金币累积 ≥ 100",             AchievementTier.BRONZE, "通用", "coins:100"),
    _ach("dream_1",         "初入梦乡", "梦境固化记忆 ≥ 1 条",        AchievementTier.BRONZE, "梦境", "dream_memories:1"),
    _ach("scan_10",         "安全新兵", "完成 10 次安全扫描",         AchievementTier.BRONZE, "安全", "scan_count:10"),
    _ach("token_save_1k",   "节俭起步", "累计节省 1000 Token",        AchievementTier.BRONZE, "Token", "token_saved:1000"),
    _ach("level_5",         "初级员工", "达到 5 级",                  AchievementTier.BRONZE, "通用", "level:5"),
    _ach("favor_100",       "初获信任", "好感度达到 100",             AchievementTier.BRONZE, "通用", "favor:100"),
    _ach("tasks_10",        "十项全能", "完成 10 个任务",             AchievementTier.BRONZE, "通用", "total_tasks:10"),

    # ---- 银级 12 项 ----
    _ach("code_1k",         "千行代码", "累计生成代码 1000+ 行",      AchievementTier.SILVER, "代码", "code_lines:1000"),
    _ach("streak_20",       "二十连捷", "连续 20 次成功",             AchievementTier.SILVER, "通用", "streak:20"),
    _ach("coins_500",       "富甲一方", "金币累积 ≥ 500",             AchievementTier.SILVER, "通用", "coins:500"),
    _ach("dream_10",        "梦境行者", "梦境固化记忆 ≥ 10 条",       AchievementTier.SILVER, "梦境", "dream_memories:10"),
    _ach("dream_quality_5", "精炼记忆", "5 条高质量梦境记忆",         AchievementTier.SILVER, "梦境", "dream_quality_high:5"),
    _ach("scan_50",         "安全卫士", "完成 50 次安全扫描",         AchievementTier.SILVER, "安全", "scan_count:50"),
    _ach("block_10",        "拦截能手", "拦截 10 次高危调用",         AchievementTier.SILVER, "安全", "block_count:10"),
    _ach("token_save_10k",  "量入为出", "累计节省 10000 Token",       AchievementTier.SILVER, "Token", "token_saved:10000"),
    _ach("lowcost_30",      "精打细算", "低成本模型占比 ≥ 30%",       AchievementTier.SILVER, "Token", "lowcost_ratio:30"),
    _ach("level_10",        "资深员工", "达到 10 级",                 AchievementTier.SILVER, "通用", "level:10"),
    _ach("favor_500",       "深得人心", "好感度达到 500",             AchievementTier.SILVER, "通用", "favor:500"),
    _ach("tasks_100",       "百战不殆", "完成 100 个任务",            AchievementTier.SILVER, "通用", "total_tasks:100"),

    # ---- 金级 10 项 ----
    _ach("code_10k",        "万行代码", "累计生成代码 10000+ 行",     AchievementTier.GOLD, "代码", "code_lines:10000"),
    _ach("streak_50",       "五十连冠", "连续 50 次成功",             AchievementTier.GOLD, "通用", "streak:50"),
    _ach("coins_2000",      "富可敌国", "金币累积 ≥ 2000",            AchievementTier.GOLD, "通用", "coins:2000"),
    _ach("dream_50",        "梦境大师", "梦境固化记忆 ≥ 50 条",       AchievementTier.GOLD, "梦境", "dream_memories:50"),
    _ach("dream_quality_20","记忆宗师", "20 条高质量梦境记忆",        AchievementTier.GOLD, "梦境", "dream_quality_high:20"),
    _ach("scan_200",        "安全铁壁", "完成 200 次安全扫描",        AchievementTier.GOLD, "安全", "scan_count:200"),
    _ach("block_100",       "铜墙铁壁", "拦截 100 次高危调用",        AchievementTier.GOLD, "安全", "block_count:100"),
    _ach("token_save_100k", "节俭大师", "累计节省 100000 Token",      AchievementTier.GOLD, "Token", "token_saved:100000"),
    _ach("level_20",        "核心骨干", "达到 20 级",                 AchievementTier.GOLD, "通用", "level:20"),
    _ach("tasks_500",       "五百功成", "完成 500 个任务",            AchievementTier.GOLD, "通用", "total_tasks:500"),
]


def _check_threshold(stats: dict[str, Any], threshold_spec: str) -> bool:
    """根据 'field:value' 字符串检查阈值。

    支持:
    - "field:N" → stats[field] >= N
    - "field:N%" → stats[field] >= N (百分比字段直接比较数值)
    """
    field_name, _, value_str = threshold_spec.partition(":")
    if not _:
        return False
    try:
        threshold_value = float(value_str.rstrip("%"))
    except ValueError:
        return False
    actual = stats.get(field_name, 0)
    try:
        return float(actual) >= threshold_value
    except (TypeError, ValueError):
        return False


# ============== 等级公式（指数曲线） ==============

def compute_level(exp: int) -> int:
    """根据经验值计算等级。

    公式：升到 Lv N 所需累计 exp = 100 * N * (N-1)
    反推：level = floor((1 + sqrt(1 + exp/25)) / 2)

    实测（每次成功任务 +20 exp）：
    - Lv1: 0 exp
    - Lv2: 200 exp（约 10 次成功任务）
    - Lv5: 2000 exp（约 100 次成功任务）
    - Lv10: 9000 exp（约 450 次成功任务）
    - Lv20: 38000 exp（约 1900 次成功任务）
    """
    if exp < 0:
        return 1
    return int((1 + math.sqrt(1 + exp / 25)) / 2)


def exp_to_next_level(exp: int) -> tuple[int, int]:
    """计算升到下一级还需多少经验。

    Returns:
        (当前等级, 距下一级还需 exp)
    """
    lvl = compute_level(exp)
    next_level_exp = 100 * (lvl + 1) * lvl  # 升到 lvl+1 所需累计 exp
    return lvl, max(0, next_level_exp - exp)


# ============== 好感度递减增长 ==============

def favor_gain(base: int, current_favor: int) -> int:
    """好感度递减增长。

    gain = base * (1 - favor / (favor + K))
    favor=0 时满额；favor 越高增量越小，但永不为 0。
    """
    if current_favor < 0:
        current_favor = 0
    factor = 1 - current_favor / (current_favor + _cfg.favor_decay_k)
    return max(1, int(base * factor))


# ============== AgentProfile ==============

@dataclass(slots=True)
class AgentProfile:
    """员工游戏化档案。"""
    agent_id: str
    coins: int = 0
    exp: int = 0
    favor: int = _cfg.favor_init
    total_tasks: int = 0
    success_count: int = 0
    failed_count: int = 0
    streak: int = 0                  # 连续成功次数
    consecutive_fails: int = 0       # 连续失败次数（用于递增惩罚）
    code_lines: int = 0              # 累计生成代码行数
    dream_memories: int = 0          # 梦境固化记忆数
    dream_quality_high: int = 0      # 高质量梦境记忆数
    scan_count: int = 0              # 安全扫描次数
    block_count: int = 0             # 高危拦截次数
    token_saved: int = 0             # 累计节省 Token
    lowcost_ratio: float = 0.0       # 低成本模型调用占比（0-100）
    achievements: list[str] = field(default_factory=list)
    # P4 扩容：岗位行为计数（用于差异化奖励）
    code_fix_count: int = 0          # 代码修复次数
    commit_count: int = 0            # 规范提交次数
    test_pass_count: int = 0         # 测试通过次数
    token_overspend_penalty: int = 0 # 累计超额扣减金币

    @property
    def level(self) -> int:
        """等级（指数曲线）。"""
        return compute_level(self.exp)

    @property
    def perks(self) -> list[str]:
        """已解锁特权。"""
        return get_level_perks(self.level)

    def to_dict(self) -> dict[str, Any]:
        """序列化。"""
        d = asdict(self)
        d["level"] = self.level
        d["perks"] = self.perks
        return d

    def to_stats(self) -> dict[str, Any]:
        """生成成就检查用的 stats 字典。"""
        return {
            "total_tasks": self.total_tasks,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "streak": self.streak,
            "consecutive_fails": self.consecutive_fails,
            "coins": self.coins,
            "exp": self.exp,
            "level": self.level,
            "favor": self.favor,
            "code_lines": self.code_lines,
            "dream_memories": self.dream_memories,
            "dream_quality_high": self.dream_quality_high,
            "scan_count": self.scan_count,
            "block_count": self.block_count,
            "token_saved": self.token_saved,
            "lowcost_ratio": self.lowcost_ratio,
            # P4 扩容字段
            "code_fix_count": self.code_fix_count,
            "commit_count": self.commit_count,
            "test_pass_count": self.test_pass_count,
        }


# ============== RewardSystem ==============

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
    return value * (rate ** n)


def leaderboard(profiles: list[AgentProfile], metric: str = "coins", top_k: int = 10) -> list[dict[str, Any]]:
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


class RewardSystem:
    """游戏化奖惩系统。

    根据任务结果实时结算金币/经验/好感度，检查成就解锁，生成排行榜。
    P6 前置优化：30 项成就三梯次 + 指数等级 + 递减好感 + 连续失败递增惩罚。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}

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
                agent_id, profile.coins, profile.exp, profile.favor, gain, profile.streak,
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
            extra_penalty = min(_cfg.consecutive_fail_cap, _cfg.consecutive_fail_penalty * n)
            if extra_penalty > 0:
                profile.coins -= extra_penalty
                logger.warning(
                    "连续失败惩罚: agent=%s, 第 %d 次连续失败, 额外扣 %d 金币",
                    agent_id, n, extra_penalty,
                )

            logger.info(
                "奖惩结算: agent=%s, FAILED, coins=%d, exp=%d, favor=%d, consecutive_fails=%d",
                agent_id, profile.coins, profile.exp, profile.favor, profile.consecutive_fails,
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
            agent_id, action_type, bonus,
        )
        self._check_achievements(agent_id)
        return bonus

    def penalize_token_overspend(self, agent_id: str, tokens: int) -> int:
        """Token 超额扣减奖励。

        超过 _TOKEN_THRESHOLD 的部分，每 1000 Token 扣 1 金币。

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
            agent_id, tokens, over, penalty,
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
                newly_unlocked.append({
                    "id": ach["id"],
                    "name": ach["name"],
                    "desc": ach["desc"],
                    "tier": ach["tier"],
                    "dimension": ach["dimension"],
                })
                logger.info(
                    "成就解锁[%s]: agent=%s, %s (%s)",
                    ach["tier"], agent_id, ach["name"], ach["desc"],
                )

        return newly_unlocked

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

    def get_achievements_detail(self, agent_id: str) -> list[dict[str, str]]:
        """获取员工已解锁成就详情。"""
        profile = self.get_profile(agent_id)
        result = []
        for ach in _ACHIEVEMENT_DEFS:
            if ach["id"] in profile.achievements:
                result.append({
                    "id": ach["id"],
                    "name": ach["name"],
                    "desc": ach["desc"],
                    "tier": ach["tier"],
                    "dimension": ach["dimension"],
                })
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

    def leaderboard_agent_ids(self) -> list[str]:
        """P0 修复：返回所有已注册 Agent 的 ID 列表（替代外部访问 _profiles）。"""
        return list(self._profiles.keys())

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
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        data = {
            agent_id: asdict(p)
            for agent_id, p in self._profiles.items()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> RewardSystem:
        """从 JSON 加载。"""
        system = cls()
        if not os.path.exists(path):
            return system
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for agent_id, profile_data in data.items():
            # 兼容旧数据：补默认字段
            profile = AgentProfile(agent_id=agent_id)
            for k, v in profile_data.items():
                if hasattr(profile, k):
                    setattr(profile, k, v)
            system._profiles[agent_id] = profile
        return system
