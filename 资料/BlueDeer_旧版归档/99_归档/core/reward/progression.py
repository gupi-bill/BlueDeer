"""BlueDeer 奖励进度系统：等级公式、经验值、好感度递减。"""

from __future__ import annotations

import math

# ============== P4 扩容：等级解锁特权 ==========
# 等级 -> 特权列表
_LEVEL_PERKS: dict[int, list[str]] = {
    5: ["沙盘皮肤·银", "低成本模型优先"],
    10: ["沙盘皮肤·金", "模型调度特权", "优先任务池"],
    15: ["沙盘皮肤·紫", "跨岗位协作权", "梦境深度推演"],
    20: ["核心骨干标识", "全模型调度权", "优先任务池", "梦境宗师特权"],
}


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


def favor_gain(base: int, current_favor: int, favor_decay_k: float = 500.0) -> int:
    """好感度递减增长。

    gain = base * (1 - favor / (favor + K))
    favor=0 时满额；favor 越高增量越小，但永不为 0。
    """
    current_favor = max(current_favor, 0)
    factor = 1 - current_favor / (current_favor + favor_decay_k)
    return max(1, int(base * factor))


def get_level_perks(level: int) -> list[str]:
    """获取指定等级已解锁的全部特权。

    Lv N 解锁所有 <= N 的特权。
    """
    perks: list[str] = []
    for lv, ps in sorted(_LEVEL_PERKS.items()):
        if level >= lv:
            perks.extend(ps)
    return perks

