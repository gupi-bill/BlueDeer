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

import logging
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from core.config import get_config

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
    5: ["沙盘皮肤·银", "低成本模型优先"],
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

    BRONZE = "bronze"  # 铜：入门，约 10-50 次任务
    SILVER = "silver"  # 银：进阶，约 50-200 次任务
    GOLD = "gold"  # 金：长期，约 200-1000+ 次任务


# ============== 成就定义（30 项） ==============
# 每项: id / name / desc / tier / dimension / check(stats_dict) -> bool


def _ach(
    aid: str,
    name: str,
    desc: str,
    tier: AchievementTier,
    dimension: str,
    threshold: str,
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
    _ach(
        "first_task",
        "初出茅庐",
        "完成第 1 个任务",
        AchievementTier.BRONZE,
        "通用",
        "total_tasks:1",
    ),
    _ach(
        "code_100",
        "百行代码",
        "累计生成代码 100+ 行",
        AchievementTier.BRONZE,
        "代码",
        "code_lines:100",
    ),
    _ach(
        "streak_5",
        "五连成功",
        "连续 5 次任务成功",
        AchievementTier.BRONZE,
        "通用",
        "streak:5",
    ),
    _ach(
        "coins_100",
        "小有积蓄",
        "金币累积 ≥ 100",
        AchievementTier.BRONZE,
        "通用",
        "coins:100",
    ),
    _ach(
        "dream_1",
        "初入梦乡",
        "梦境固化记忆 ≥ 1 条",
        AchievementTier.BRONZE,
        "梦境",
        "dream_memories:1",
    ),
    _ach(
        "scan_10",
        "安全新兵",
        "完成 10 次安全扫描",
        AchievementTier.BRONZE,
        "安全",
        "scan_count:10",
    ),
    _ach(
        "token_save_1k",
        "节俭起步",
        "累计节省 1000 Token",
        AchievementTier.BRONZE,
        "Token",
        "token_saved:1000",
    ),
    _ach("level_5", "初级员工", "达到 5 级", AchievementTier.BRONZE, "通用", "level:5"),
    _ach(
        "favor_100",
        "初获信任",
        "好感度达到 100",
        AchievementTier.BRONZE,
        "通用",
        "favor:100",
    ),
    _ach(
        "tasks_10",
        "十项全能",
        "完成 10 个任务",
        AchievementTier.BRONZE,
        "通用",
        "total_tasks:10",
    ),
    # ---- 银级 12 项 ----
    _ach(
        "code_1k",
        "千行代码",
        "累计生成代码 1000+ 行",
        AchievementTier.SILVER,
        "代码",
        "code_lines:1000",
    ),
    _ach(
        "streak_20",
        "二十连捷",
        "连续 20 次成功",
        AchievementTier.SILVER,
        "通用",
        "streak:20",
    ),
    _ach(
        "coins_500",
        "富甲一方",
        "金币累积 ≥ 500",
        AchievementTier.SILVER,
        "通用",
        "coins:500",
    ),
    _ach(
        "dream_10",
        "梦境行者",
        "梦境固化记忆 ≥ 10 条",
        AchievementTier.SILVER,
        "梦境",
        "dream_memories:10",
    ),
    _ach(
        "dream_quality_5",
        "精炼记忆",
        "5 条高质量梦境记忆",
        AchievementTier.SILVER,
        "梦境",
        "dream_quality_high:5",
    ),
    _ach(
        "scan_50",
        "安全卫士",
        "完成 50 次安全扫描",
        AchievementTier.SILVER,
        "安全",
        "scan_count:50",
    ),
    _ach(
        "block_10",
        "拦截能手",
        "拦截 10 次高危调用",
        AchievementTier.SILVER,
        "安全",
        "block_count:10",
    ),
    _ach(
        "token_save_10k",
        "量入为出",
        "累计节省 10000 Token",
        AchievementTier.SILVER,
        "Token",
        "token_saved:10000",
    ),
    _ach(
        "lowcost_30",
        "精打细算",
        "低成本模型占比 ≥ 30%",
        AchievementTier.SILVER,
        "Token",
        "lowcost_ratio:30",
    ),
    _ach(
        "level_10", "资深员工", "达到 10 级", AchievementTier.SILVER, "通用", "level:10"
    ),
    _ach(
        "favor_500",
        "深得人心",
        "好感度达到 500",
        AchievementTier.SILVER,
        "通用",
        "favor:500",
    ),
    _ach(
        "tasks_100",
        "百战不殆",
        "完成 100 个任务",
        AchievementTier.SILVER,
        "通用",
        "total_tasks:100",
    ),
    # ---- 金级 10 项 ----
    _ach(
        "code_10k",
        "万行代码",
        "累计生成代码 10000+ 行",
        AchievementTier.GOLD,
        "代码",
        "code_lines:10000",
    ),
    _ach(
        "streak_50",
        "五十连冠",
        "连续 50 次成功",
        AchievementTier.GOLD,
        "通用",
        "streak:50",
    ),
    _ach(
        "coins_2000",
        "富可敌国",
        "金币累积 ≥ 2000",
        AchievementTier.GOLD,
        "通用",
        "coins:2000",
    ),
    _ach(
        "dream_50",
        "梦境大师",
        "梦境固化记忆 ≥ 50 条",
        AchievementTier.GOLD,
        "梦境",
        "dream_memories:50",
    ),
    _ach(
        "dream_quality_20",
        "记忆宗师",
        "20 条高质量梦境记忆",
        AchievementTier.GOLD,
        "梦境",
        "dream_quality_high:20",
    ),
    _ach(
        "scan_200",
        "安全铁壁",
        "完成 200 次安全扫描",
        AchievementTier.GOLD,
        "安全",
        "scan_count:200",
    ),
    _ach(
        "block_100",
        "铜墙铁壁",
        "拦截 100 次高危调用",
        AchievementTier.GOLD,
        "安全",
        "block_count:100",
    ),
    _ach(
        "token_save_100k",
        "节俭大师",
        "累计节省 100000 Token",
        AchievementTier.GOLD,
        "Token",
        "token_saved:100000",
    ),
    _ach(
        "level_20", "核心骨干", "达到 20 级", AchievementTier.GOLD, "通用", "level:20"
    ),
    _ach(
        "tasks_500",
        "五百功成",
        "完成 500 个任务",
        AchievementTier.GOLD,
        "通用",
        "total_tasks:500",
    ),
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
    current_favor = max(current_favor, 0)
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
    streak: int = 0  # 连续成功次数
    consecutive_fails: int = 0  # 连续失败次数（用于递增惩罚）
    code_lines: int = 0  # 累计生成代码行数
    dream_memories: int = 0  # 梦境固化记忆数
    dream_quality_high: int = 0  # 高质量梦境记忆数
    scan_count: int = 0  # 安全扫描次数
    block_count: int = 0  # 高危拦截次数
    token_saved: int = 0  # 累计节省 Token
    lowcost_ratio: float = 0.0  # 低成本模型调用占比（0-100）
    achievements: list[str] = field(default_factory=list)
    # P4 扩容：岗位行为计数（用于差异化奖励）
    code_fix_count: int = 0  # 代码修复次数
    commit_count: int = 0  # 规范提交次数
    test_pass_count: int = 0  # 测试通过次数
    token_overspend_penalty: int = 0  # 累计超额扣减金币

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
