"""忧郁鹿 Deer：第一个示范物种。

继承 DigitalLifeForm，提供：
- SPECIES_TEMPLATE：物种默认基因模板
- _build_genome：基于模板 + ±5% 变异 + sleep_config + 用户 override 构造最终 genome
- job_skill：鹿的岗位技能（调度任务）
- _create_child：繁殖时构造子代鹿
- create_default：类方法快捷构造

commit 28：行为池——巡视领地 / 月光冥想 / 鹿鸣
"""

from __future__ import annotations

import random
from typing import ClassVar

from .digital_life_form import DigitalLifeForm
from .environment import Environment

# ruff: noqa: S110


class Deer(DigitalLifeForm):
    """忧郁鹿：BlueDeer 总经理原型，第一个示范物种。"""

    # 物种模板：所有鹿的"出厂设置"。具体个体的 genome 是它的拷贝 + ±5% 变异 + override。
    SPECIES_TEMPLATE: ClassVar[dict] = {
        "species": "deer",
        "default_name": "忧郁鹿",
        "metabolic_rate": 0.5,  # 每小时能量消耗
        "hunger_rate": 0.4,  # 每小时饥饿增长
        "max_age_days": 365 * 30,  # 寿命 30 年
        "reproduction_age_min_days": 365 * 4,  # 4 岁起可繁殖
        "reproduction_age_max_days": 365 * 20,  # 繁殖到 20 岁
        "litter_size_min": 1,
        "litter_size_max": 2,
        "temperament": {"active": 0.4, "social": 0.6, "curious": 0.5},
        "color_variation": 0.1,
    }

    # commit 28：鹿特有行为池
    # 1. 巡视领地：早晚各一次（6-9 / 18-21），沿固定路线走一圈，途中遇同事点头致意
    # 2. 月光冥想：晴夜 22-02（跨夜），鹿角发微光，能量缓慢恢复
    # 3. 鹿鸣：检测到两员工冲突时鸣叫，冲突双方冷静（简化为：低 mood 时随机触发）
    BEHAVIOR_POOL: ClassVar[list[dict]] = [
        {
            "name": "patrol_territory_morning",
            "label": "巡视领地",
            "trigger": {
                "time_range": [6, 9],
                "energy_min": 40,
                "hunger_max": 70,
                "life_stages": ["ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.06,
            },
            "duration_sec": 300,  # 5 分钟
            "cooldown_sec": 7200,  # 2 小时一次
            "animation": "walk",
            "particles": "sparkle",
        },
        {
            "name": "patrol_territory_evening",
            "label": "巡视领地",
            "trigger": {
                "time_range": [18, 21],
                "energy_min": 40,
                "hunger_max": 70,
                "life_stages": ["ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.06,
            },
            "duration_sec": 300,
            "cooldown_sec": 7200,
            "animation": "walk",
            "particles": "sparkle",
        },
        {
            "name": "moon_meditation",
            "label": "月光冥想",
            "trigger": {
                "time_range": [22, 2],  # 跨夜 22-02
                "energy_min": 20,
                "hunger_max": 70,
                "life_stages": ["ADULT", "MIDDLE", "ELDERLY"],
                "probability": 0.04,
            },
            "duration_sec": 900,  # 15 分钟
            "cooldown_sec": 10800,  # 3 小时一次
            "animation": "idle",
            "particles": "feather_shine",
        },
        {
            "name": "deer_call",
            "label": "鹿鸣",
            "trigger": {
                "energy_min": 30,
                "hunger_max": 70,
                "life_stages": ["ADULT", "MIDDLE"],
                "probability": 0.008,  # 稀有
            },
            "duration_sec": 10,  # 即时
            "cooldown_sec": 1800,
            "animation": "react",
            "particles": "story_bubble",
        },
    ]

    def __init__(
        self,
        name: str = "忧郁鹿",
        gender: str = "female",
        environment: Environment | None = None,
        birth_time: float | None = None,
        genome_override: dict | None = None,
    ) -> None:
        """初始化一只鹿。

        Args:
            name: 名字，默认"忧郁鹿"。
            gender: 性别，默认 female。
            environment: 所属环境（可空，测试时常用 None）。
            birth_time: 出生时间戳，None=现在；测试时可手动指定让其"已经活了 N 年"。
            genome_override: 顶层基因覆盖（例如子代继承的重组基因）。
        """
        genome = self._build_genome(genome_override)
        super().__init__(
            name=name,
            species=genome.get("species", "deer"),
            gender=gender,
            genome=genome,
            environment=environment,
            birth_time=birth_time,
        )

    # ------------------------------------------------------------------
    # 岗位技能
    # ------------------------------------------------------------------

    def job_skill(self) -> None:
        """鹿的岗位技能：调度任务。"""
        # 实际不下发任何 print，避免污染日志

    # ----- commit 28：行为钩子 -----

    def _on_behavior_start(self, cfg: dict) -> None:
        """行为开始：鹿鸣时找冲突双方（简化：找两个低 mood 同事）。"""
        if cfg["name"] == "deer_call" and self._environment is not None:
            # 找两个 mood 最低的清醒同事当"冲突双方"
            with self._environment._lock:
                others = [
                    lf
                    for lf in self._environment.population
                    if lf is not self
                    and getattr(lf, "_alive", False)
                    and not getattr(lf, "sleeping", False)
                ]
            others.sort(key=lambda x: getattr(x, "mood_score", 50))
            self._deer_call_targets = others[:2]

    def _on_behavior_tick(self, cfg: dict) -> None:
        """每秒效果。"""
        bname = cfg["name"]
        if bname == "patrol_territory_morning" or bname == "patrol_territory_evening":
            # 巡视：能量消耗，遇同事点头（mood +0.5）
            self.energy = max(0.0, self.energy - 0.1)
            if self._environment is not None and random.random() < 0.1:
                others = [
                    lf
                    for lf in self._environment.population
                    if lf is not self
                    and getattr(lf, "_alive", False)
                    and getattr(lf, "current_zone_id", "") == self.current_zone_id
                ]
                if others:
                    target = random.choice(others)
                    try:
                        with target._lock:
                            target.mood_score = min(100.0, target.mood_score + 0.5)
                    except Exception:
                        pass
        elif bname == "moon_meditation":
            # 月光冥想：能量恢复 +0.2/秒，mood +0.05
            self.energy = min(100.0, self.energy + 0.2)
            self.mood_score = min(100.0, self.mood_score + 0.05)
        elif bname == "deer_call":
            # 鹿鸣：给冲突双方 +mood（冷静下来）
            for target in getattr(self, "_deer_call_targets", []):
                if target is None:
                    continue
                try:
                    with target._lock:
                        target.mood_score = min(100.0, target.mood_score + 3.0)
                except Exception:
                    pass

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """结束时记录事件。"""
        bname = cfg["name"]
        if bname in ("patrol_territory_morning", "patrol_territory_evening"):
            self._remember("巡视领地一圈，途中向同事点头致意", importance="normal")
        elif bname == "moon_meditation":
            self._remember("在天井下仰头望月，鹿角发微光", importance="high")
        elif bname == "deer_call":
            self._remember("发出一声低沉鹿鸣，平息了冲突", importance="high")
            self._deer_call_targets = None

    def _create_child(self, genome: dict, environment, birth_time: float) -> Deer:
        """繁殖时构造子代鹿。"""
        return Deer(
            name=f"{self._name_obj}的幼崽",
            gender=random.choice(["male", "female"]),
            environment=environment,
            birth_time=birth_time,
            genome_override=genome,
        )

    # ------------------------------------------------------------------
    # 类方法：快捷构造
    # ------------------------------------------------------------------

    @classmethod
    def create_default(cls, environment: Environment | None = None) -> Deer:
        """快捷构造一只默认忧郁鹿。"""
        return cls(environment=environment)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回完整状态。"""
        return super().status()
