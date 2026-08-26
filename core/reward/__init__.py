"""BlueDeer 游戏化奖惩系统（向后兼容入口）。

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

# 向后兼容：所有原 core.reward 的公共 API 继续可从本模块导入
from core.reward.achievements import (
    _ACHIEVEMENT_DEFS,
    AchievementTier,
    _check_threshold,
    get_all_achievements,
)
from core.reward.calculator import (
    RewardCurve,
    decay,
    leaderboard,
)
from core.reward.profile import (
    AgentProfile,
)
from core.reward.progression import (
    compute_level,
    exp_to_next_level,
    favor_gain,
    get_level_perks,
)
from core.reward.system import (
    RewardSystem,
)

__all__ = [
    "_ACHIEVEMENT_DEFS",
    "AchievementTier",
    "AgentProfile",
    "RewardCurve",
    "RewardSystem",
    "_check_threshold",
    "compute_level",
    "decay",
    "exp_to_next_level",
    "favor_gain",
    "get_all_achievements",
    "get_level_perks",
    "leaderboard",
]
