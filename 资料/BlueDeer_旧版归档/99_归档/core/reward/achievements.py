"""BlueDeer 成就系统：成就梯次、成就定义、阈值检查。"""

from __future__ import annotations

from typing import Any


class AchievementTier:
    """成就梯次。"""

    BRONZE = "bronze"  # 铜：入门，约 10-50 次任务
    SILVER = "silver"  # 银：进阶，约 50-200 次任务
    GOLD = "gold"  # 金：长期，约 200-1000+ 次任务


def _ach(
    aid: str,
    name: str,
    desc: str,
    tier: str,
    dimension: str,
    threshold: str,
) -> dict[str, Any]:
    """构造成就定义。check 在运行时按 threshold 字段名动态生成。"""
    return {
        "id": aid,
        "name": name,
        "desc": desc,
        "tier": tier,
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
        "金币累积 >= 100",
        AchievementTier.BRONZE,
        "通用",
        "coins:100",
    ),
    _ach(
        "dream_1",
        "初入梦乡",
        "梦境固化记忆 >= 1 条",
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
        "金币累积 >= 500",
        AchievementTier.SILVER,
        "通用",
        "coins:500",
    ),
    _ach(
        "dream_10",
        "梦境行者",
        "梦境固化记忆 >= 10 条",
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
        "低成本模型占比 >= 30%",
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
        "金币累积 >= 2000",
        AchievementTier.GOLD,
        "通用",
        "coins:2000",
    ),
    _ach(
        "dream_50",
        "梦境大师",
        "梦境固化记忆 >= 50 条",
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
    - "field:N" -> stats[field] >= N
    - "field:N%" -> stats[field] >= N (百分比字段直接比较数值)
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


def get_all_achievements() -> list[dict[str, str]]:
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
