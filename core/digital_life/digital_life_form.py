"""数字生命基类 DigitalLifeForm。

设计要点（零基础读者可以这样理解）：
- 一只动物 = 一个独立线程，按真实时间活着。
- tick() 是 1 秒一步：年龄→作息→代谢→睡眠→健康→情绪→决策→行为→死亡。
- 跨夜作息判定：bedtime > wakeup（如 23:00→06:00）按 [bed,24:00)∪[0,wake) 判定。
- 4 级睡眠深度：LIGHT/NORMAL/DEEP/HIBERNATION，影响恢复速度和紧急响应。
- 繁殖：基因重组 crossover，每个基因随机取父母一方，加 ±5% 变异。
- 生命周期：BABY(0-10%)/JUVENILE(10-30%)/ADULT(30-60%)/MIDDLE(60-80%)/ELDERLY(80-100%)。

子类只需：
1. 定义 SPECIES_TEMPLATE（物种默认基因）
2. 实现 _build_genome / _create_child / job_skill
3. 调用 super().__init__(...)
"""

from __future__ import annotations

import datetime
import enum
import json
import os
import random
import threading
import time
from collections import deque
from typing import ClassVar

# ----------------------------------------------------------------------
# 枚举
# ----------------------------------------------------------------------


class LifeStage(enum.Enum):
    """生命周期阶段。"""

    BABY = "BABY"  # 婴幼 0-10%
    JUVENILE = "JUVENILE"  # 少年 10-30%
    ADULT = "ADULT"  # 成年 30-60%
    MIDDLE = "MIDDLE"  # 中年 60-80%
    ELDERLY = "ELDERLY"  # 老年 80-100%


class ActionState(enum.Enum):
    """当前行为。"""

    REST = "REST"  # 休息
    SLEEP = "SLEEP"  # 睡觉
    WORK = "WORK"  # 工作
    EAT = "EAT"  # 进食
    SOCIALIZE = "SOCIALIZE"  # 社交
    REPRODUCE = "REPRODUCE"  # 繁殖
    EXPLORE = "EXPLORE"  # 探索


class SleepDepth(enum.Enum):
    """睡眠深度。"""

    LIGHT = "LIGHT"  # 浅睡：恢复慢，紧急情况能醒
    NORMAL = "NORMAL"  # 正常：中速恢复
    DEEP = "DEEP"  # 深睡：快速恢复，难以唤醒
    HIBERNATION = "HIBERNATION"  # 冬眠：极慢代谢


# ----------------------------------------------------------------------
# 模块级辅助
# ----------------------------------------------------------------------

_SLEEP_CONFIG_CACHE: dict | None = None
_SLEEP_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "sleep_config.json")


def _load_sleep_config() -> dict:
    """加载 sleep_config.json（带缓存）。"""
    global _SLEEP_CONFIG_CACHE
    if _SLEEP_CONFIG_CACHE is None:
        try:
            with open(_SLEEP_CONFIG_PATH, "r", encoding="utf-8") as f:
                _SLEEP_CONFIG_CACHE = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _SLEEP_CONFIG_CACHE = {}
    return _SLEEP_CONFIG_CACHE


def _parse_hhmm(s: str) -> tuple[int, int]:
    """把 'HH:MM' 解析为 (hour, minute)。失败返回 (0, 0)。"""
    try:
        h, m = s.split(":")
        return int(h), int(m)
    except (ValueError, AttributeError):
        return 0, 0


# ----------------------------------------------------------------------
# 基类
# ----------------------------------------------------------------------


class DigitalLifeForm(threading.Thread):
    """数字生命基类。

    注意：因为继承 threading.Thread，而 Thread.name 是 property，
    不能用 __slots__ 限制 name 字段，所以用 _name_obj 避开。
    """

    # 默认 genome（子类 SPECIES_TEMPLATE 会覆盖这些键）
    _DEFAULT_GENOME: ClassVar[ClassVar[ClassVar[dict]]] = {
        "species": "unknown",
        "default_name": "未命名",
        "metabolic_rate": 0.5,  # 每小时能量消耗
        "hunger_rate": 0.5,  # 每小时饥饿增长
        "max_age_days": 365 * 20,  # 默认寿命 20 年
        "reproduction_age_min_days": 365 * 2,
        "reproduction_age_max_days": 365 * 15,
        "litter_size_min": 1,
        "litter_size_max": 2,
        "temperament": {"active": 0.5, "social": 0.5, "curious": 0.5},
        "color_variation": 0.1,
    }

    # commit 19 P0-2：技能成长树（年龄天数, 技能名）。
    # 子类可覆盖此列表实现物种专属技能。
    SKILL_TREE: ClassVar[list[tuple[float, str]]] = [
        (365 * 2, "初阶岗位"),  # 2 岁解锁
        (365 * 5, "中阶岗位"),  # 5 岁解锁
        (365 * 10, "高阶岗位"),  # 10 岁解锁
    ]

    # commit 28：物种特有行为池（子类覆盖）。
    # 每条行为配置示例：
    #   {
    #     "name": "cache_food",          # 行为唯一名
    #     "label": "藏坚果",              # 中文显示名（前端标签）
    #     "trigger": {                   # 触发条件（全部满足才候选）
    #       "time_range": [22, 2],       # 时间范围 [起始小时, 结束小时)，可跨夜
    #       "energy_min": 70,            # 能量下限
    #       "energy_max": 100,
    #       "season": "winter",          # 季节 spring/summer/autumn/winter
    #       "min_age_days": 365,         # 最小年龄（天）
    #       "life_stages": ["ADULT"],    # 生命阶段白名单
    #       "probability": 0.02,         # 每次检查触发概率
    #     },
    #     "duration_sec": 180,           # 持续时间（秒）
    #     "cooldown_sec": 600,           # 冷却时间（秒）
    #     "animation": "work",           # 使用的动画帧 idle/walk/work/react
    #     "particles": "nut_bury",       # 粒子效果名（前端解析）
    #   }
    BEHAVIOR_POOL: ClassVar[ClassVar[list[dict]]] = []

    __slots__ = [
        # commit 31：主动消息系统
        #   _active_msg_cooldowns: {category: ts} 每个类别的上次发送时间戳
        #   _last_supervisor_interact_ts: 上次与监工互动的 ts（用于"想念监工"触发）
        #   _last_active_msg_check_tick: 上次执行 detect_and_trigger 的 tick 数
        "_active_msg_cooldowns",
        # 运行时
        "_alive",
        "_artifact_ref",
        # commit 28：行为池运行时状态
        #   _behavior_state: {行为名: {"last_run": ts, "in_progress": bool}}
        #   current_behavior: 当前正在执行的行为名（None 表示无）
        #   current_behavior_cfg: 当前行为配置 dict
        #   current_behavior_end: 当前行为结束时间戳
        "_behavior_state",
        "_cold_war_until",
        "_crisis_resolved_count",
        "_diary_discovered",
        "_emotion_memory_cooldown",
        "_environment",
        "_help_count",
        "_immunity",
        "_last_active_msg_check_tick",
        "_last_anniversary_check",
        "_last_memory_sync_ts",
        "_last_monologue_ts",
        "_last_self_cognition_sync_ts",
        "_last_social_ts",
        "_last_supervisor_interact_ts",
        "_lock",
        # 身份
        "_name_obj",
        "_pipeline_task_inbox",
        "_propagation_partners",
        "_social_count",
        "_stop_event",
        "_supervisor_interact_count",
        "_teach_count",
        "_tick_count",
        "_tool_call_meta",
        "_tool_call_status",
        "_witnessed_deaths",
        "_work_continuous_start_ts",
        "_work_output",
        "appearance_modifiers",
        "birth_time",
        # commit 37：Agent 工具链 + 流水线任务接收
        #   bound_tools: 本智能体绑定的工具名列表（由物种自动配置）
        #   _pipeline_task_inbox: 待执行的流水线任务队列（list[dict]）
        #   _tool_call_status: 当前工具调用状态（用于前端可视化）
        #     "" / "running" / "waiting" / "done" / "error"
        #   _tool_call_meta: 工具调用元数据（tool_name / started_ts / 上次完成 ts）
        "bound_tools",
        "childhood_done",
        "childhood_imprint",
        "children",
        "contradiction",
        # commit 11：核心记忆 + 生平摘要 + 遗言（死亡时生成）
        "core_memory",
        "current_action",
        "current_behavior",
        "current_behavior_cfg",
        "current_behavior_end",
        # commit 11：当前所在 zone_id（用于遗物标记 + 觅食）
        "current_zone_id",
        # Thread 兼容（不能放 name，用 _name_obj）
        # commit 30：情感系统
        #   emotional_state: 6 维情感向量 dict {joy/sadness/anxiety/
        #     contentment/loneliness/curiosity: float 0~1}
        #   _last_social_ts: 上次社交时间戳（用于 loneliness 累积）
        #   _last_monologue_ts: 上次内心独白时间戳（每小时 10% 概率）
        #   _propagation_partners: {other_id: 接触开始 ts}（持续 2 分钟触发传播）
        #   _emotion_memory_cooldown: 情感记忆冷却（避免刷屏）
        "emotional_state",
        # 状态
        "energy",
        # commit 11：对监工的好感度（0-100，初始 50）
        "fondness",
        "gender",
        # 基因
        "genome",
        "health",
        "hire_anniversary",
        "hunger",
        # commit 34：生病急救 + 持久记忆 + 桌面宠物
        #   illness: None 或 Illness 实例（来自 illness_system.py）
        #   _work_continuous_start_ts: 连续工作起始 ts（用于过劳判定）
        #   _immunity: {kind: 免疫力 0~1} 已得过且康复的疾病免疫力
        #   persistent_memory_ref: 持久记忆实例引用（首次访问时懒加载）
        #   _last_memory_sync_ts: 上次同步持久记忆的 ts
        "illness",
        # commit 39：长期目标管理 + 团队角色演化
        #   informal_roles: list[str]，自发形成的非正式角色 key
        #     （tech_leader / social_coordinator / supervisor_deputy /
        #      mentor / crisis_handler / hermit）
        #   project_contributions: dict {project_id: {"commits": int, "tasks": int,
        #     "last_active_ts": float, "role": str}}
        #   _help_count: 累计被同事求助次数
        #   _social_count: 累计自发社交次数（茶话会/调解/串门）
        #   _supervisor_interact_count: 与监工互动次数
        #   _teach_count: 成功教学次数（带新人/答疑）
        #   _crisis_resolved_count: 成功处理紧急事件次数
        #   _work_output: 工作产出量化（任务数 × 完成质量，用于隐士判定）
        "informal_roles",
        "last_words",
        "life_goal",
        "life_stage",
        "life_summary",
        "memory_long_term",
        # 记忆
        "memory_recent",
        "mood",
        # commit 19 P0-1：情绪数值（0-100，初始 50，受邻居传染）
        "mood_score",
        # commit 40：进化突变系统
        "mutations",
        # 关系
        "parents",
        "persistent_memory_ref",
        "project_contributions",
        "relationship_tags",
        # commit 30：关系网络深化
        #   relationships: {other_id: {affection/trust/respect/familiarity: float 0~1}}
        #   relationship_tags: {other_id: [tag, ...]}（挚友/导师/搭档/单恋/世交）
        #   _cold_war_until: {other_id: 冷战结束 ts}（trust 骤降时进入）
        "relationships",
        # commit 11：觅食/休息状态结束时间戳（None 表示非觅食中）
        "resting_until",
        # commit 30：人生阶段叙事
        #   retirement_wish: str（老年时设置的退休愿望，"" 表示未到老年）
        #   wish_fulfilled: bool（退休愿望是否实现）
        #   hire_anniversary: float（入职周年 ts，初始 = birth_time）
        #   _last_anniversary_check: int（上次检查周年年份，避免重复触发）
        "retirement_wish",
        # commit 35：日记 + 自传体记忆 + 工作产物
        #   self_description / values / life_goal / contradiction:
        #     自我认知的四个维度（缓存自 autobiographical_memory）
        #   _last_self_cognition_sync_ts: 上次同步自我认知到本实例的 ts
        #   _diary_discovered: 是否已被监工通过彩蛋发现日记本
        #   _artifact_ref: 工作产物集引用（懒加载）
        "self_description",
        # commit 19 P0-2：已解锁技能列表
        "skills",
        "sleep_start_time",
        "sleeping",
        "species",
        "trauma_events",
        "values",
        # commit 30：长期记忆影响
        #   wisdom: 智慧值（0~100，随年龄增长）
        #   childhood_imprint: bool（前 3 天适应期标记）
        #   childhood_done: bool（适应期是否已结束）
        #   trauma_events: list[str]（创伤事件标签，如 "witness_death"）
        #   _witnessed_deaths: list[name]（目击死亡记录，避免重复）
        "wisdom",
        "wish_fulfilled",
    ]

    def _init_base_attributes(
        self, name: str, species: str, gender: str, genome: dict, birth_time: float | None
    ) -> None:
        self._name_obj = name
        self.species = species
        self.gender = gender
        self.birth_time = float(birth_time) if birth_time is not None else time.time()
        self.life_stage = LifeStage.BABY
        self.genome = dict(self._DEFAULT_GENOME, **genome) if genome else dict(self._DEFAULT_GENOME)

    def _init_physical_state(self) -> None:
        self.energy = 80.0
        self.health = 100.0
        self.hunger = 20.0
        self.mood = "neutral"
        self.current_action = ActionState.REST
        self.sleeping = False
        self.sleep_start_time = None

    def _init_relationships(self) -> None:
        self.parents = []
        self.children = []

    def _init_memory_core(self) -> None:
        self.memory_recent = deque(maxlen=100)
        self.memory_long_term = []
        self.core_memory = []
        self.life_summary = ""
        self.last_words = ""

    def _init_fondness_and_zone(self) -> None:
        self.fondness = 50
        self.current_zone_id = ""
        self.resting_until = None

    def _init_emotion_score(self) -> None:
        self.mood_score = 50.0

    def _init_skills(self) -> None:
        self.skills = []

    def _init_behavior_state(self) -> None:
        self._behavior_state = {}
        self.current_behavior = None
        self.current_behavior_cfg = None
        self.current_behavior_end = None

    def _init_runtime(self) -> None:
        self._alive = True
        self._tick_count = 0
        self._stop_event = threading.Event()
        self._environment = None
        self._lock = threading.RLock()

    def _init_emotional_system(self) -> None:
        self.emotional_state = {
            "joy": 0.5,
            "sadness": 0.1,
            "anxiety": 0.2,
            "contentment": 0.6,
            "loneliness": 0.3,
            "curiosity": 0.7,
        }
        self._last_social_ts = time.time()
        self._last_monologue_ts = 0.0
        self._propagation_partners = {}
        self._emotion_memory_cooldown = 0.0

    def _init_relationship_network(self) -> None:
        self.relationships = {}
        self.relationship_tags = {}
        self._cold_war_until = {}

    def _init_long_term_memory(self) -> None:
        self.wisdom = 0.0
        self.childhood_imprint = True
        self.childhood_done = False
        self.trauma_events = []
        self._witnessed_deaths = []

    def _init_life_narrative(self) -> None:
        self.retirement_wish = ""
        self.wish_fulfilled = False
        self.hire_anniversary = self.birth_time
        self._last_anniversary_check = 0

    def _init_active_messaging(self) -> None:
        self._active_msg_cooldowns = {}
        self._last_supervisor_interact_ts = time.time()
        self._last_active_msg_check_tick = 0

    def _init_illness_persistence(self) -> None:
        self.illness = None
        self._work_continuous_start_ts = 0.0
        self._immunity = {}
        self.persistent_memory_ref = None
        self._last_memory_sync_ts = 0.0

    def _init_self_cognition(self) -> None:
        self.self_description = ""
        self.values = ""
        self.life_goal = ""
        self.contradiction = ""
        self._last_self_cognition_sync_ts = 0.0
        self._diary_discovered = False
        self._artifact_ref = None

    def _init_tools_and_pipeline(self) -> None:
        self.bound_tools = []
        self._pipeline_task_inbox = []
        self._tool_call_status = ""
        self._tool_call_meta = {}
        try:
            from core.digital_life.tool_registry import get_tool_registry
            self.bound_tools = get_tool_registry().list_tool_names_for_species(self.species)
        except Exception:
            self.bound_tools = []

    def _init_goals_and_evolution(self) -> None:
        self.informal_roles = []
        self.project_contributions = {}
        self._help_count = 0
        self._social_count = 0
        self._supervisor_interact_count = 0
        self._teach_count = 0
        self._crisis_resolved_count = 0
        self._work_output = 0.0
        self.mutations = []
        self.appearance_modifiers = {}

    def _init_thread_and_register(self, environment) -> None:
        super().__init__(daemon=True)
        try:
            super().__init__(name=f"life-{self.species}-{self._name_obj}", daemon=True)
        except TypeError:
            pass
        if environment is not None:
            self._environment = environment
            environment.register(self)
            environment.birth_log.append(
                {
                    "time": time.time(),
                    "species": self.species,
                    "name": self._name_obj,
                    "gender": self.gender,
                }
            )
            environment.broadcast_event(
                "birth",
                {
                    "species": self.species,
                    "name": self._name_obj,
                    "gender": self.gender,
                },
            )

    def __init__(
        self,
        name: str,
        species: str,
        gender: str,
        genome: dict,
        environment,
        birth_time: float | None = None,
    ) -> None:
        """初始化数字生命体。

        Args:
            name: 生命体名字（如"忧郁鹿"）。
            species: 物种名（如"deer"）。
            gender: 性别（"male" / "female" / 其他）。
            genome: 基因组 dict（已合并 SPECIES_TEMPLATE 与 override）。
            environment: 所属 Environment 实例（可空）。
            birth_time: 出生时间戳；None 表示现在出生。
        """
        self._init_base_attributes(name, species, gender, genome, birth_time)
        self._init_physical_state()
        self._init_relationships()
        self._init_memory_core()
        self._init_fondness_and_zone()
        self._init_emotion_score()
        self._init_skills()
        self._init_behavior_state()
        self._init_runtime()
        self._init_emotional_system()
        self._init_relationship_network()
        self._init_long_term_memory()
        self._init_life_narrative()
        self._init_active_messaging()
        self._init_illness_persistence()
        self._init_self_cognition()
        self._init_tools_and_pipeline()
        self._init_goals_and_evolution()
        self._init_thread_and_register(environment)

    # ------------------------------------------------------------------
    # 基因构造（子类可覆盖）
    # ------------------------------------------------------------------

    def _build_genome(self, override: dict | None) -> dict:
        """构造最终的 genome。

        流程：
        1. 深拷贝 SPECIES_TEMPLATE
        2. 对数值字段做 ±5% 变异
        3. 从 sleep_config.json 注入作息字段
        4. 合并 override（最高优先级）
        """
        genome = {}
        for k, v in self.SPECIES_TEMPLATE.items():
            if isinstance(v, dict):
                genome[k] = dict(v)
            else:
                genome[k] = v

        for k in (
            "metabolic_rate",
            "hunger_rate",
            "max_age_days",
            "reproduction_age_min_days",
            "reproduction_age_max_days",
            "color_variation",
        ):
            if k in genome and isinstance(genome[k], (int, float)):
                mutation = 1.0 + random.uniform(-0.05, 0.05)
                genome[k] = type(genome[k])(genome[k] * mutation)

        species_name = self.SPECIES_TEMPLATE.get("species", "unknown")
        sleep_cfg = _load_sleep_config().get(species_name, {})
        if sleep_cfg:
            for k in ("bedtime", "wakeup_time", "sleep_depth", "wake_on_emergency"):
                if k in sleep_cfg:
                    genome[k] = sleep_cfg[k]

        if override:
            for k, v in override.items():
                if isinstance(v, dict) and isinstance(genome.get(k), dict):
                    merged = dict(genome[k])
                    merged.update(v)
                    genome[k] = merged
                else:
                    genome[k] = v

        return genome

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def age(self) -> float:
        """返回年龄（天）。"""
        return (time.time() - self.birth_time) / 86400.0

    @property
    def is_sleeping(self) -> bool:
        """是否在睡觉。"""
        return self.sleeping

    # ------------------------------------------------------------------
    # 作息判定
    # ------------------------------------------------------------------

    def should_sleep_now(self, now: datetime.datetime | None = None) -> bool:
        """根据当前时间判定是否应该睡觉。

        支持跨夜作息：bedtime > wakeup（如 23:00→06:00）。
        """
        if now is None:
            now = datetime.datetime.now()
        bedtime = self.genome.get("bedtime", "23:00")
        wakeup = self.genome.get("wakeup_time", "06:00")
        bed_h, bed_m = _parse_hhmm(bedtime)
        wake_h, wake_m = _parse_hhmm(wakeup)
        bed_min = bed_h * 60 + bed_m
        wake_min = wake_h * 60 + wake_m
        now_min = now.hour * 60 + now.minute

        if bed_min == wake_min:
            return False  # 没有作息
        if bed_min < wake_min:
            # 同日：[bed, wake)
            return bed_min <= now_min < wake_min
        else:
            # 跨夜：[bed, 24:00) ∪ [0, wake)
            return now_min >= bed_min or now_min < wake_min

    # ------------------------------------------------------------------
    # tick 生命周期
    # ------------------------------------------------------------------

    def run(self) -> None:
        """线程主循环：每秒 tick 一次直到死亡或被停止。"""
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                pass
            if not self._alive:
                break
            # 用 wait 替代 sleep，便于被 stop_event 立即唤醒
            self._stop_event.wait(1.0)

    def tick(self) -> None:
        """单步推进 1 秒。

        顺序：年龄→阶段→作息→代谢→睡眠恢复→健康惩罚→
              情绪→决策→行为→死亡判定。

        commit 29：增加环境感知（微气候调整代谢 + 天气影响户外行动 +
        生态事件影响工作 + 记录区域停留 + 触发灵感）
        """
        with self._lock:
            if not self._alive:
                return

            self._tick_count += 1
            now_dt = datetime.datetime.now()
            now_ts = now_dt.timestamp()

            # commit 29：环境感知（在代谢之前应用微气候/天气修正）
            env_modifier = self._compute_env_modifier(now_ts)

            # 1. 生命周期阶段
            self._update_life_stage()

            # 2. 作息切换
            self._update_sleep_state(now_dt)

            # 3. 代谢（每小时速率，1 秒 = 1/3600 小时）
            # commit 29：天气影响能量消耗（晴 -10%，极温 +15%~25%）
            hour_frac = 1.0 / 3600.0
            metabolic = self.genome["metabolic_rate"] * env_modifier["energy_cost_mult"]
            # commit 29：雪原/寒冷 zone 长时间停留额外消耗
            if env_modifier["cold_drain"] > 0 and not self.sleeping:
                metabolic += env_modifier["cold_drain"]
            self.energy = max(0.0, self.energy - metabolic * hour_frac)
            self.hunger = min(
                100.0, self.hunger + self.genome["hunger_rate"] * hour_frac
            )

            # 4. 睡眠恢复
            if self.sleeping:
                depth = self.genome.get("sleep_depth", "NORMAL")
                recover_rate = {
                    "LIGHT": 0.5,
                    "NORMAL": 1.0,
                    "DEEP": 1.5,
                    "HIBERNATION": 0.3,
                }.get(depth, 1.0)
                # commit 30：anxiety > 0.7 → 睡眠质量下降（恢复减半）
                if self.emotional_state.get("anxiety", 0) > 0.7:
                    recover_rate *= 0.5
                self.energy = min(100.0, self.energy + recover_rate * hour_frac * 60)
                # 睡眠时缓慢恢复健康
                self.health = min(100.0, self.health + recover_rate * hour_frac * 10)

            # commit 29：微气候 zone 修正（非睡眠时）
            if not self.sleeping and env_modifier["zone_recover_mult"] != 1.0:
                # 在偏好 zone 中能量恢复加成
                bonus = (env_modifier["zone_recover_mult"] - 1.0) * hour_frac * 30
                self.energy = min(100.0, self.energy + max(0.0, bonus))

            # 5. 健康惩罚（饥饿/能量过低）
            if self.hunger > 80:
                self.health = max(0.0, self.health - 0.5 * hour_frac * 60)
            if self.energy < 10:
                self.health = max(0.0, self.health - 0.3 * hour_frac * 60)

            # 6. 情绪
            self._update_mood()

            # commit 29：大扫除日 → 全员情绪 +0.05/秒
            if (
                self._environment is not None
                and self._environment.has_event_effect("cleaning")
                and not self.sleeping
            ):
                self.mood_score = min(100.0, self.mood_score + 0.05)

            # 7. 决策与行为（非睡眠时）
            if not self.sleeping:
                self._tick_behavior_decision(env_modifier, now_dt)

                # commit 29：通用社交行为（每 5 tick 检查一次近距离同事）
                if self._tick_count % 5 == 0:
                    self._tick_social_behaviors()

                # commit 29：灵感事件（每小时检查一次）
                if self._tick_count % 3600 == 0 and self._environment is not None and self.current_action == ActionState.WORK:
                        self._environment.trigger_inspiration(self)

                # commit 34：连续工作起始时间追踪（用于过劳判定）
                if self.current_action == ActionState.WORK:
                    if self._work_continuous_start_ts == 0.0:
                        self._work_continuous_start_ts = time.time()
                else:
                    self._work_continuous_start_ts = 0.0

                # commit 35：定期同步自我认知到本实例字段
                self.sync_self_cognition()

            # 8. 死亡判定
            self._check_death()

            # 9. commit 11：好感度衰减 + 觅食状态推进
            if self._alive:
                self.tick_fondness_decay()
                self._tick_foraging()
                self._tick_periodic_tasks(env_modifier)

    def _resolve_behavior_action(self) -> None:
        """将当前 behavior 动画映射为 ActionState 并执行。"""
        anim = (self.current_behavior_cfg or {}).get("animation", "idle")
        self.current_action = {
            "idle": ActionState.REST,
            "walk": ActionState.EXPLORE,
            "work": ActionState.WORK,
            "react": ActionState.SOCIALIZE,
        }.get(anim, ActionState.REST)
        self._perform_action()

    def _tick_behavior_decision(self, env_modifier: dict, now_dt: datetime.datetime) -> None:
        """处理 tick 中的行为决策分支（降低 tick() 圈复杂度）。"""
        if env_modifier["force_indoor"]:
            indoor_zones = ("deer", "butterfly", "beaver")
            if self.current_zone_id not in indoor_zones:
                self.current_action = ActionState.REST
                self._perform_action()
                return
        self._tick_behavior(now_dt)
        if self.current_behavior is None:
            self.current_action = self._decide_action()
            self._perform_action()
        else:
            self._resolve_behavior_action()

    def _tick_periodic_tasks(self, env_modifier: dict) -> None:
        """处理 tick 中的周期性任务（社交/灵感/情感/觅食等）。"""
        # commit 19 P0-1：每 10 tick 做一次情绪传染
        if self._tick_count % 10 == 0:
            self._tick_mood_contagion()
        # commit 19 P0-2：每 30 tick 检查一次技能解锁
        if self._tick_count % 30 == 0:
            self._tick_skill_unlock()
        # commit 29：每 30 秒记录一次区域停留时间
        if self._tick_count % 30 == 0 and self._environment is not None:
            self._record_zone_stay(env_modifier)
        # commit 30：情感系统调度
        if self._tick_count % 5 == 0:
            self._tick_emotion_propagation()
            self._maybe_trigger_dialogue()
        if self._tick_count % 30 == 0:
            self._tick_emotional_memory()
            self._tick_relationship_decay()
            self._tick_wisdom()
            self._check_retirement_wish()
            self._check_anniversary()
        if self._tick_count % 3600 == 0:
            self._maybe_inner_monologue()
        # commit 31：每 60 秒扫描主动消息触发条件
        if self._tick_count % 60 == 0:
            self._tick_active_messaging()

    def _compute_env_modifier(self, now_ts: float) -> dict:
        """计算当前环境对自身的修正系数。

        Returns:
            {
                "energy_cost_mult": float,    # 能量消耗倍率
                "zone_recover_mult": float,   # 当前 zone 恢复倍率
                "cold_drain": float,          # 寒冷额外消耗（雪原非 hare 物种）
                "force_indoor": bool,         # 是否强制室内（大雨/极低温）
            }
        """
        m = {
            "energy_cost_mult": 1.0,
            "zone_recover_mult": 1.0,
            "cold_drain": 0.0,
            "force_indoor": False,
        }
        if self._environment is None:
            return m
        # 天气影响
        weather_info = self._environment.weather_info()
        m["energy_cost_mult"] = weather_info.get("energy_cost_mult", 1.0)
        # 强制室内：大雨/雷暴 或 极低温
        if self._environment.current_weather in ("heavy_rain", "cold"):
            m["force_indoor"] = True
        # 微气候 zone 修正
        zone_mult = self._environment.species_zone_modifier(
            self.species, self.current_zone_id
        )
        m["zone_recover_mult"] = zone_mult
        # 雪原寒冷消耗：非 hare 物种在 hare zone 停留会掉能量
        if self.current_zone_id == "hare" and self.species != "hare":
            m["cold_drain"] = 0.5  # 每秒额外消耗 0.5（每小时 1800）
        return m

    def _record_zone_stay(self, env_modifier: dict) -> None:
        """记录区域停留时间（30 秒一次，所以 +30）。"""
        if self._environment is None:
            return
        # 判断当前 zone 是室内还是室外
        indoor_zones = ("deer", "butterfly", "beaver")
        is_outdoor = self.current_zone_id not in indoor_zones
        try:
            self._environment.record_zone_stay(
                self.current_zone_id, 30.0, is_outdoor, self.species
            )
        except Exception:
            pass

    # ----- commit 29：通用社交行为 -----

    def _tick_social_behaviors(self) -> None:
        """通用社交行为：打招呼 / 共餐 / 互助。

        每 5 秒检查一次：
        - 打招呼：与同 zone 同事距离 < 2 格，1% 概率触发 1 秒招呼
        - 共餐：与同 zone 同事都处于 EAT 状态，自动共餐 +mood
        - 互助：自己或同事在找东西时（behavior=forget_cache 或类似），
                旁边的同事 5% 概率帮忙
        """
        if self._environment is None:
            return
        if not self._alive or self.sleeping:
            return
        # 找同 zone 的同事
        with self._environment._lock:
            others = [
                lf
                for lf in self._environment.population
                if lf is not self
                and getattr(lf, "_alive", False)
                and not getattr(lf, "sleeping", False)
                and getattr(lf, "current_zone_id", "") == self.current_zone_id
            ]
        if not others:
            return
        # 1. 打招呼（1% 概率，与随机一位同事）
        if random.random() < 0.01:
            target = random.choice(others)
            try:
                with target._lock:
                    target.mood_score = min(100.0, target.mood_score + 0.5)
                self.mood_score = min(100.0, self.mood_score + 0.3)
                # commit 29：亲近对额外加成
                is_affinity = self._environment.species_affinity(
                    self.species, target.species
                )
                if is_affinity:
                    self.mood_score = min(100.0, self.mood_score + 0.5)
                    with target._lock:
                        target.mood_score = min(100.0, target.mood_score + 0.5)
                # 记录互动
                self._environment.record_interaction(self.species, target.species)
                # 不同物种打招呼方式不同
                greet_map = {
                    "deer": "点头",
                    "squirrel": "摇尾",
                    "raven": "鸣叫",
                    "fox": "招手",
                    "butterfly": "振翅",
                    "hedgehog": "竖刺",
                    "beaver": "拍水",
                    "hare": "蹬腿",
                    "badger": "嗅鼻",
                    "lark": "啁啾",
                    "kite": "盘旋",
                }
                greet = greet_map.get(self.species, "点头")
                self._environment.broadcast_event(
                    "social_greet",
                    {
                        "from": self._name_obj,
                        "to": target._name_obj,
                        "from_species": self.species,
                        "to_species": target.species,
                        "greet": greet,
                        "affinity": is_affinity,
                    },
                )
            except Exception:
                pass
        # 2. 共餐（自己正在吃 + 同事正在吃 → 共餐）
        if self.current_action == ActionState.EAT:
            for target in others:
                if target.current_action == ActionState.EAT:
                    try:
                        with target._lock:
                            target.mood_score = min(100.0, target.mood_score + 0.3)
                        self.mood_score = min(100.0, self.mood_score + 0.3)
                        self._environment.record_interaction(
                            self.species, target.species
                        )
                    except Exception:
                        pass
                    break  # 一次只与一位共餐
        # 3. 互助（同事在 forget_cache 等寻找类行为 → 5% 概率帮忙）
        for target in others:
            tb = getattr(target, "current_behavior", None)
            if tb in ("forget_cache", "dig_new_tunnel", "patrol_safety"):
                if random.random() < 0.005:  # 0.5% 概率（每 5 秒）
                    try:
                        with target._lock:
                            target.mood_score = min(100.0, target.mood_score + 1.0)
                        # 帮忙者也 +mood（互助的快乐）
                        self.mood_score = min(100.0, self.mood_score + 0.5)
                        self._environment.record_interaction(
                            self.species, target.species
                        )
                        self._environment.broadcast_event(
                            "social_help",
                            {
                                "helper": self._name_obj,
                                "target": target._name_obj,
                                "helper_species": self.species,
                                "target_species": target.species,
                                "behavior": tb,
                            },
                        )
                    except Exception:
                        pass
                break

    def _update_life_stage(self) -> None:
        """根据年龄百分比更新生命周期阶段。"""
        max_age = self.genome.get("max_age_days", 365 * 20)
        pct = self.age / max_age if max_age > 0 else 0
        if pct < 0.1:
            self.life_stage = LifeStage.BABY
        elif pct < 0.3:
            self.life_stage = LifeStage.JUVENILE
        elif pct < 0.6:
            self.life_stage = LifeStage.ADULT
        elif pct < 0.8:
            self.life_stage = LifeStage.MIDDLE
        else:
            self.life_stage = LifeStage.ELDERLY

    def _update_sleep_state(self, now: datetime.datetime) -> None:
        """根据作息切换睡眠/苏醒。"""
        should_sleep = self.should_sleep_now(now)
        if should_sleep and not self.sleeping:
            # 入睡
            self.sleeping = True
            self.sleep_start_time = time.time()
            self.current_action = ActionState.SLEEP
            self._remember(f"入睡（{self.genome.get('sleep_depth', 'NORMAL')}）")
        elif not should_sleep and self.sleeping:
            # 醒来
            self.sleeping = False
            self.sleep_start_time = None
            self.current_action = ActionState.REST
            self._remember("自然醒来")

    def _update_mood(self) -> None:
        """根据状态更新情绪字符串 + mood_score。

        commit 19 P0-1：mood_score 与 mood 字符串保持同步，
        作为情绪传染的基础数值（0-100，越高越开心）。

        commit 30：mood_score 不再硬重置，改为根据 emotional_state 派生 +
        状态微调（如能量低时 joy 下降），保留长期情感积累。
        mood 字符串仍按状态切换，供前端 idle 动画用。
        """
        # commit 30：先更新 emotional_state（每秒一次）
        self._update_emotional_state()

        # mood 字符串仍按状态切（前端动画用）
        if self.energy < 20:
            self.mood = "exhausted"
        elif self.hunger > 70:
            self.mood = "hungry"
        elif self.health < 40:
            self.mood = "sick"
        elif self.sleeping:
            self.mood = "sleeping"
        elif self.current_action == ActionState.WORK:
            self.mood = "focused"
        elif self.current_action == ActionState.SOCIALIZE:
            self.mood = "happy"
        else:
            self.mood = "neutral"

        # commit 30：mood_score 由 emotional_state 派生
        # = (joy + contentment - sadness - anxiety - loneliness + curiosity*0.5) 归一化到 0-100
        emo = self.emotional_state
        raw = (
            emo.get("joy", 0.5)
            + emo.get("contentment", 0.5)
            - emo.get("sadness", 0.1)
            - emo.get("anxiety", 0.2) * 0.7
            - emo.get("loneliness", 0.3) * 0.5
            + emo.get("curiosity", 0.5) * 0.3
        )
        # raw 大约在 -0.6 ~ 2.3 之间，线性映射到 0-100
        mood_score = max(0.0, min(100.0, (raw + 0.6) / 2.9 * 100.0))
        self.mood_score = mood_score

    def _update_emotional_state(self) -> None:
        """commit 30：根据当前状态微调 6 维情感向量。

        每秒调用一次：
        - joy: 工作中 +0.001，社交 +0.002，能量 < 20 时 -0.001
        - sadness: 同事死亡后未恢复时 +0.0005，能量充足时 -0.0005
        - anxiety: hunger > 70 +0.002，健康 < 40 +0.001，否则 -0.0005
        - contentment: 睡觉 +0.002，吃饱 (hunger<30) +0.001，否则 -0.0005
        - loneliness: 距上次社交 > 60 秒 +0.0005，社交后归零衰减
        - curiosity: 监工互动后 +0.002，长时间同 zone -0.0005

        所有变化 ±0.001~0.002 量级，1 小时累计约 3.6~7.2，足以形成情感趋势。
        """
        emo = self.emotional_state
        # joy
        if self.current_action == ActionState.WORK:
            emo["joy"] = min(1.0, emo["joy"] + 0.001)
        elif self.current_action == ActionState.SOCIALIZE:
            emo["joy"] = min(1.0, emo["joy"] + 0.002)
            self._last_social_ts = time.time()
        if self.energy < 20:
            emo["joy"] = max(0.0, emo["joy"] - 0.001)
        # sadness
        if self.energy > 60 and self.hunger < 40 and self.health > 60:
            emo["sadness"] = max(0.0, emo["sadness"] - 0.0005)
        # anxiety
        if self.hunger > 70:
            emo["anxiety"] = min(1.0, emo["anxiety"] + 0.002)
        elif self.health < 40:
            emo["anxiety"] = min(1.0, emo["anxiety"] + 0.001)
        else:
            emo["anxiety"] = max(0.0, emo["anxiety"] - 0.0005)
        # contentment
        if self.sleeping:
            emo["contentment"] = min(1.0, emo["contentment"] + 0.002)
        elif self.hunger < 30 and self.energy > 60:
            emo["contentment"] = min(1.0, emo["contentment"] + 0.001)
        else:
            emo["contentment"] = max(0.0, emo["contentment"] - 0.0005)
        # loneliness（距上次社交时间）
        since_social = time.time() - self._last_social_ts
        if since_social > 60:
            emo["loneliness"] = min(1.0, emo["loneliness"] + 0.0005)
        else:
            emo["loneliness"] = max(0.0, emo["loneliness"] - 0.001)
        # curiosity（无明确触发时缓慢衰减）
        emo["curiosity"] = max(0.0, emo["curiosity"] - 0.0002)

        # commit 30：童年烙印基线加成（前 3 天）
        if self.childhood_imprint and not self.childhood_done:
            if self.age >= 3.0:
                # 适应期结束，根据情感快照决定基线
                self.childhood_done = True
                self.childhood_imprint = False
                if emo.get("anxiety", 0) > 0.5:
                    # 前 3 天焦虑高 → 终身 anxiety 基线 +0.1
                    emo["anxiety"] = min(1.0, emo["anxiety"] + 0.1)
                    self._remember(
                        "童年烙印：适应期焦虑，终身基线 +0.1", importance="high"
                    )
                elif emo.get("contentment", 0) > 0.6:
                    # 前 3 天满足高 → 终身 contentment 基线 +0.1
                    emo["contentment"] = min(1.0, emo["contentment"] + 0.1)
                    self._remember(
                        "童年烙印：适应期温暖，终身基线 +0.1", importance="high"
                    )

    def _tick_emotion_propagation(self) -> None:
        """commit 30：情感传播（每 5 秒调一次）。

        - 当两个智能体同 zone 且持续 > 2 分钟，情感向量缓慢趋近（各向对方 5%）
        - 高 joy(>0.8) 个体主动安慰 sadness > 0.5 的邻居（降对方 sadness 0.02）
        - 渡鸦讲古时同 zone 所有听众 contentment +0.01, anxiety -0.01
        """
        if self._environment is None or not self._alive or self.sleeping:
            return
        now = time.time()
        # 找同 zone 邻居
        with self._environment._lock:
            neighbors = [
                lf
                for lf in self._environment.population
                if lf is not self
                and getattr(lf, "_alive", False)
                and not getattr(lf, "sleeping", False)
                and getattr(lf, "current_zone_id", "") == self.current_zone_id
            ]
        if not neighbors:
            # 清空传播记录
            self._propagation_partners.clear()
            return
        my_emo = self.emotional_state
        # 1. 持续接触 2 分钟 → 情感趋近 5%
        for other in neighbors:
            oid = id(other)
            last_seen = self._propagation_partners.get(oid, 0)
            if last_seen == 0:
                self._propagation_partners[oid] = now
                continue
            if now - last_seen >= 120:  # 2 分钟
                try:
                    with other._lock:
                        other_emo = other.emotional_state
                        for k in my_emo:
                            if k in other_emo:
                                avg = (my_emo[k] + other_emo[k]) / 2
                                my_emo[k] += (avg - my_emo[k]) * 0.05
                                other_emo[k] += (avg - other_emo[k]) * 0.05
                                # 夹紧
                                my_emo[k] = max(0.0, min(1.0, my_emo[k]))
                                other_emo[k] = max(0.0, min(1.0, other_emo[k]))
                except Exception:
                    pass
        # 2. 高 joy 主动安慰
        if my_emo.get("joy", 0) > 0.8:
            for other in neighbors:
                try:
                    with other._lock:
                        if other.emotional_state.get("sadness", 0) > 0.5:
                            other.emotional_state["sadness"] = max(
                                0.0, other.emotional_state["sadness"] - 0.02
                            )
                            # 被安慰者 joy 略升
                            other.emotional_state["joy"] = min(
                                1.0, other.emotional_state.get("joy", 0) + 0.01
                            )
                except Exception:
                    pass
        # 3. 渡鸦讲古（raven + 当前行为是 narrate_old_tales）→ 听众 contentment↑ anxiety↓
        if self.species == "raven" and self.current_behavior == "narrate_old_tales":
            for other in neighbors:
                try:
                    with other._lock:
                        other.emotional_state["contentment"] = min(
                            1.0, other.emotional_state.get("contentment", 0) + 0.01
                        )
                        other.emotional_state["anxiety"] = max(
                            0.0, other.emotional_state.get("anxiety", 0) - 0.01
                        )
                except Exception:
                    pass
        # 清理已离开的邻居记录
        alive_ids = {id(o) for o in neighbors}
        for k in list(self._propagation_partners.keys()):
            if k not in alive_ids:
                del self._propagation_partners[k]

    def _tick_emotional_memory(self) -> None:
        """commit 30：情感峰值记忆（每 30 秒检查一次）。

        当某个情感值 > 0.9 或 < 0.1，且不在冷却期，记录一条情感记忆到 core_memory。
        冷却 5 分钟，避免刷屏。
        """
        now = time.time()
        if now < self._emotion_memory_cooldown:
            return
        emo = self.emotional_state
        triggered = None
        for k, v in emo.items():
            if v > 0.9:
                triggered = (k, "high")
                break
            if v < 0.1:
                triggered = (k, "low")
                break
        if not triggered:
            return
        emo_key, level = triggered
        event_text = ""
        if emo_key == "joy" and level == "high":
            event_text = "感到无比喜悦"
        elif emo_key == "sadness" and level == "high":
            event_text = "陷入深深的悲伤"
        elif emo_key == "anxiety" and level == "high":
            event_text = "极度焦虑不安"
        elif emo_key == "contentment" and level == "high":
            event_text = "感到非常满足"
        elif emo_key == "loneliness" and level == "high":
            event_text = "孤独感几乎压倒一切"
        elif emo_key == "curiosity" and level == "high":
            event_text = "好奇心爆棚"
        elif emo_key == "joy" and level == "low":
            event_text = "快乐几乎消失"
        elif emo_key == "contentment" and level == "low":
            event_text = "完全无法满足"
        if event_text:
            snapshot = {k: round(v, 2) for k, v in emo.items()}
            self._remember(f"{event_text}（情感快照：{snapshot}）", importance="high")
            self._emotion_memory_cooldown = now + 300  # 5 分钟冷却
            # commit 33：情感峰值 → 生成记忆碎片（仅 high 级别）
            if level == "high":
                try:
                    from core.digital_life.memory_fragment import spawn_fragment

                    frag_type = f"emotion_peak_{emo_key}"
                    # 用 zone 哈希生成伪坐标（前端按 zone 中心+随机偏移渲染）
                    import hashlib

                    zone_id = self.current_zone_id or "outdoor"
                    hv = int(hashlib.md5(zone_id.encode()).hexdigest()[:8], 16)
                    spawn_fragment(
                        frag_type=frag_type,
                        x=(hv % 100) * 0.5,
                        y=((hv >> 8) % 100) * 0.5,
                        zone_id=zone_id,
                        agent_name=self._name_obj,
                        agent_species=self.species,
                        detail=event_text,
                    )
                except Exception:
                    pass

    def _maybe_inner_monologue(self) -> None:
        """commit 30：内心独白（每小时检查一次，10% 概率触发）。

        独处时（无同 zone 邻居）触发概率更高（20%）。
        独白文本写入短期记忆 + 推送气泡。
        """
        if self._environment is None or not self._alive or self.sleeping:
            return
        now = time.time()
        if now - self._last_monologue_ts < 3600:  # 1 小时检查一次
            return
        self._last_monologue_ts = now
        # 独处判定（同 zone 无其他活体）
        with self._environment._lock:
            has_company = any(
                lf is not self
                and getattr(lf, "_alive", False)
                and not getattr(lf, "sleeping", False)
                and getattr(lf, "current_zone_id", "") == self.current_zone_id
                for lf in self._environment.population
            )
        prob = 0.10 if has_company else 0.20
        if random.random() > prob:
            return
        # 生成独白
        try:
            from core.digital_life.dialogue_system import pick_monologue

            text = pick_monologue(self.species, self.emotional_state)
        except Exception:
            text = "……"
        self._remember(f"（内心独白）{text}")
        # 推送气泡（无 target，表示独白）
        if self._environment is not None:
            self._environment.push_dialogue_bubble(
                self._name_obj, text, target="", duration=4.0
            )

    # ------------------------------------------------------------------
    # commit 31：主动消息系统
    # ------------------------------------------------------------------

    def _get_router(self):
        """获取 LLM router（如果可用）。

        从 Biosphere 单例中拿 router。生命体本身不持有 router，
        通过 environment 的 _biosphere_ref 反向引用。
        如果拿不到则返回 None，触发器会降级到模板。
        """
        env = self._environment
        if env is None:
            return None
        # 通过 environment 反向拿 biosphere（如果存在）
        biosphere = getattr(env, "_biosphere_ref", None)
        if biosphere is None:
            return None
        return getattr(biosphere, "_router", None)

    def _tick_active_messaging(self) -> None:
        """commit 31：每 60 秒扫描一次主动消息触发条件。

        调用 detect_and_trigger 检测健康危机/情绪波动/想念监工/早安问候。
        """
        if self._environment is None or not self._alive or self.sleeping:
            return
        try:
            from core.digital_life.active_messaging import detect_and_trigger

            detect_and_trigger(self, router=self._get_router())
        except Exception:
            pass

    def _on_work_done(self, task_detail: str = "") -> None:
        """commit 31：工作完成时由子类调用，触发 work_done 消息。

        Args:
            task_detail: 工作详情（如"3 个任务"）
        """
        try:
            from core.digital_life.active_messaging import trigger_active_message

            trigger_active_message(
                self,
                "work_done",
                detail=task_detail,
                context=f"完成工作：{task_detail}",
                router=self._get_router(),
            )
        except Exception:
            pass

    def _on_share_discovery(self, discovery: str = "") -> None:
        """commit 31：发现新事物时触发 share_discovery 消息。

        Args:
            discovery: 发现的描述
        """
        try:
            from core.digital_life.active_messaging import trigger_active_message

            trigger_active_message(
                self,
                "share_discovery",
                detail=discovery,
                context=f"分享发现：{discovery}",
                router=self._get_router(),
            )
        except Exception:
            pass

    def _on_crisis_alert(self, alert: str = "") -> None:
        """commit 31：危机警报（high 优先级）。

        Args:
            alert: 警报内容
        """
        try:
            from core.digital_life.active_messaging import trigger_active_message

            trigger_active_message(
                self,
                "crisis_alert",
                detail=alert,
                context=f"危机警报：{alert}",
                router=self._get_router(),
            )
        except Exception:
            pass

    def _on_retirement_wish_set(self, wish: str = "") -> None:
        """commit 31：老年设置退休愿望时主动告知监工。"""
        try:
            from core.digital_life.active_messaging import trigger_active_message

            trigger_active_message(
                self,
                "retirement_wish",
                detail=wish,
                context=f"设置了退休愿望：{wish}",
                router=self._get_router(),
            )
        except Exception:
            pass

    def _maybe_trigger_dialogue(self) -> None:
        """commit 30：触发对话（每 5 秒检查，5% 概率）。

        优先选同 zone 同事；同 zone 无同事时，按物种亲和对（SPECIES_AFFINITY）
        跨 zone 找说话对象（模拟"路过打招呼"）。
        """
        if self._environment is None or not self._alive or self.sleeping:
            return
        if self.current_action == ActionState.WORK:
            return  # 工作时不说闲话
        if random.random() > 0.10:  # commit 30：10% 概率（让挚友/搭档更易达成）
            return
        with self._environment._lock:
            same_zone = [
                lf
                for lf in self._environment.population
                if lf is not self
                and getattr(lf, "_alive", False)
                and not getattr(lf, "sleeping", False)
                and getattr(lf, "current_zone_id", "") == self.current_zone_id
            ]
            # commit 30：同 zone 没人时，按亲和对跨 zone 找（让 fox↔squirrel 等能对话）
            if not same_zone:
                from core.digital_life.environment import SPECIES_AFFINITY

                aff_species = SPECIES_AFFINITY.get(self.species, [])
                same_zone = [
                    lf
                    for lf in self._environment.population
                    if lf is not self
                    and getattr(lf, "_alive", False)
                    and not getattr(lf, "sleeping", False)
                    and lf.species in aff_species
                ]
        if not same_zone:
            return
        target = random.choice(same_zone)
        try:
            from core.digital_life.dialogue_system import pick_dialogue

            result = pick_dialogue(
                self.species,
                target.species,
                self.emotional_state,
                self.relationships.get(target._name_obj),
            )
            if not result:
                return
            speaker_sp, text = result
            # 如果说话者是对方，由对方说
            if speaker_sp == target.species and speaker_sp != self.species:
                speaker_name = target._name_obj
                listener_name = self._name_obj
            else:
                speaker_name = self._name_obj
                listener_name = target._name_obj
            self._environment.push_dialogue_bubble(
                speaker_name, text, target=listener_name, duration=3.5
            )
            # 对话也算一次轻社交：双方 affection 微增 + loneliness 衰减
            self._last_social_ts = time.time()
            try:
                with target._lock:
                    target._last_social_ts = time.time()
            except Exception:
                pass
            # commit 30：社交闲聊按 spec 加 affection+0.03 / familiarity+0.05
            # 额外 trust +0.02（频繁接触建立信任，让挚友/搭档可达成）
            self._bump_relationship(
                target._name_obj, affection=0.03, familiarity=0.05, trust=0.02
            )
            try:
                with target._lock:
                    target._bump_relationship(
                        self._name_obj, affection=0.03, familiarity=0.05, trust=0.02
                    )
            except Exception:
                pass
            self.emotional_state["loneliness"] = max(
                0.0, self.emotional_state.get("loneliness", 0) - 0.05
            )
        except Exception:
            pass

    def _tick_mood_contagion(self) -> None:
        """commit 19 P0-1：情绪传染。

        每 10 tick 调用一次：从环境里找同 zone 的活体邻居，
        让自己的 mood_score 向邻居均值靠拢 ±1。
        简化：随机选一个同 zone 邻居，向其 mood_score 靠拢 1 点。
        """
        if self._environment is None:
            return
        # 找同 zone 邻居（活体、非自己、同 zone_id）
        neighbors = []
        for lf in self._environment.population:
            if lf is self:
                continue
            if not getattr(lf, "_alive", False):
                continue
            if getattr(lf, "current_zone_id", "") != self.current_zone_id:
                continue
            neighbors.append(lf)
        if not neighbors:
            return
        other = random.choice(neighbors)
        try:
            with other._lock:
                diff = other.mood_score - self.mood_score
                if abs(diff) >= 1:
                    step = 1.0 if diff > 0 else -1.0
                    self.mood_score = max(0.0, min(100.0, self.mood_score + step))
        except Exception:
            pass

    def _tick_skill_unlock(self) -> None:
        """commit 19 P0-2：技能成长树。

        检查 SKILL_TREE，若年龄达到某技能要求且未解锁，
        则加入 self.skills 并写入核心记忆。
        """
        age_days = self.age
        for req_age, skill_name in self.SKILL_TREE:
            if age_days >= req_age and skill_name not in self.skills:
                self.skills.append(skill_name)
                self._remember(f"解锁技能：{skill_name}", importance="high")

    # ------------------------------------------------------------------
    # commit 30：关系网络深化
    # ------------------------------------------------------------------

    def _bump_relationship(self, other_id: str, **deltas) -> None:
        """更新与某个体的关系值（多维）。

        Args:
            other_id: 对方名字
            **deltas: affection=0.05 / trust=0.1 / respect=0.08 / familiarity=0.05
        """
        if not other_id:
            return
        rel = self.relationships.setdefault(
            other_id,
            {
                "affection": 0.5,
                "trust": 0.4,
                "respect": 0.6,
                "familiarity": 0.3,
            },
        )
        for k, v in deltas.items():
            if k in rel:
                rel[k] = max(0.0, min(1.0, rel[k] + v))
        # 检查是否产生新标签
        self._check_relationship_tags(other_id)

    def _check_relationship_tags(self, other_id: str) -> None:
        """检测关系标签变化（挚友/搭档/导师/单恋），首次触发时广播事件。"""
        try:
            from core.digital_life.dialogue_system import check_relationship_tags
        except Exception:
            return
        rel = self.relationships.get(other_id)
        if not rel:
            return
        new_tags = set(check_relationship_tags(rel))
        old_tags = set(self.relationship_tags.get(other_id, []))
        # 新增的标签
        added = new_tags - old_tags
        if added:
            self.relationship_tags[other_id] = list(new_tags)
            for tag in added:
                # 单恋/挚友/搭档/导师首次达成 → 广播事件
                event_type = {
                    "挚友": "became_friend",
                    "搭档": "became_partner",
                    "导师": "mentor_set",
                    "单恋": "crush_formed",
                }.get(tag, "relationship_change")
                if self._environment is not None:
                    self._environment.record_relationship_event(
                        event_type, self._name_obj, other_id, extra={"tag": tag}
                    )
                self._remember(
                    f"与 {other_id} 的关系新增标签：{tag}", importance="high"
                )
                # commit 31：关系里程碑 → 主动告知监工
                if tag in ("挚友", "搭档"):
                    try:
                        from core.digital_life.active_messaging import (
                            trigger_active_message,
                        )

                        trigger_active_message(
                            self,
                            "relationship_milestone",
                            detail=f"{other_id}（{tag}）",
                            context=f"与 {other_id} 达成 {tag} 关系",
                            router=self._get_router(),
                        )
                    except Exception:
                        pass
                # commit 33：首次达成关系标签 → 生成 friendship 碎片
                try:
                    import hashlib

                    from core.digital_life.memory_fragment import spawn_fragment

                    zone_id = self.current_zone_id or "outdoor"
                    hv = int(
                        hashlib.md5((zone_id + self._name_obj).encode()).hexdigest()[
                            :8
                        ],
                        16,
                    )
                    spawn_fragment(
                        frag_type="friendship",
                        x=(hv % 100) * 0.5,
                        y=((hv >> 8) % 100) * 0.5,
                        zone_id=zone_id,
                        agent_name=self._name_obj,
                        agent_species=self.species,
                        detail=f"{other_id}（{tag}）",
                        related_agent_name=other_id,
                    )
                except Exception:
                    pass
        elif new_tags != old_tags:
            # 标签集合变化（如失去挚友）— 这里只更新，不广播
            self.relationship_tags[other_id] = list(new_tags)

    def _tick_relationship_decay(self) -> None:
        """commit 30：关系值自然衰减（每 60 秒调一次）。

        所有关系值缓慢回归 0.5 中性线（每 60 秒 -0.005），
        防止初期互动累积后无法变化。
        """
        if not self.relationships:
            return
        for rel in self.relationships.values():
            for k in rel:
                if rel[k] > 0.5:
                    rel[k] = max(0.5, rel[k] - 0.005)
                elif rel[k] < 0.5:
                    rel[k] = min(0.5, rel[k] + 0.005)

    def _tick_wisdom(self) -> None:
        """commit 30：智慧增长（每 60 秒调一次）。

        - 渡鸦每分钟 +0.08（5%/年 ≈ 0.08/分钟 ≈ 5%/年）
        - 其他物种每分钟 +0.03（2%/年）
        - 老年期翻倍
        上限 100。
        """
        rate = 0.08 if self.species == "raven" else 0.03
        if self.life_stage == LifeStage.ELDERLY:
            rate *= 1.5
        self.wisdom = min(100.0, self.wisdom + rate)

    def _check_retirement_wish(self) -> None:
        """commit 30：老年时设置退休愿望（每 60 秒检查一次）。

        进入 ELDERLY 阶段且未设置愿望时，从语料库挑选一句。
        愿望实现的简化判定：
        - 老年 + contentment > 0.9 + 在自己 zone 内 + 连续 10 分钟 → 标记实现
        """
        if self.life_stage != LifeStage.ELDERLY:
            return
        if not self.retirement_wish:
            try:
                from core.digital_life.dialogue_system import get_retirement_wish

                self.retirement_wish = get_retirement_wish(self.species)
                self._remember(
                    f"产生了退休愿望：{self.retirement_wish}", importance="high"
                )
                if self._environment is not None:
                    self._environment.broadcast_event(
                        "retirement_wish_set",
                        {
                            "name": self._name_obj,
                            "species": self.species,
                            "wish": self.retirement_wish,
                        },
                    )
                # commit 31：主动告知监工自己的退休愿望
                self._on_retirement_wish_set(self.retirement_wish)
            except Exception:
                pass
        # 简化实现判定：老年 + contentment > 0.9 + 在自己 zone
        if (
            not self.wish_fulfilled
            and self.retirement_wish
            and self.emotional_state.get("contentment", 0) > 0.9
            and self.current_zone_id == self.species
        ):
            self.wish_fulfilled = True
            self.emotional_state["contentment"] = 1.0
            self._remember(f"退休愿望实现：{self.retirement_wish}", importance="high")
            if self._environment is not None:
                self._environment.broadcast_event(
                    "wish_fulfilled",
                    {
                        "name": self._name_obj,
                        "species": self.species,
                        "wish": self.retirement_wish,
                    },
                )

    def _check_anniversary(self) -> None:
        """commit 30：入职周年检查（每 60 秒调一次）。

        若当天是入职周年日（且年份变化），触发庆祝事件：
        - joy 锁定 0.8（持续当天）
        - 广播 anniversary 事件
        """
        if self._environment is None:
            return
        now = datetime.datetime.now()
        if now.year == self._last_anniversary_check:
            return
        # 检查是否是周年日（月日匹配）
        try:
            hire_dt = datetime.datetime.fromtimestamp(self.hire_anniversary)
            if now.month == hire_dt.month and now.day == hire_dt.day:
                self._last_anniversary_check = now.year
                # joy 锁定 0.8（强制提升）
                self.emotional_state["joy"] = max(0.8, self.emotional_state["joy"])
                self.emotional_state["contentment"] = min(
                    1.0, self.emotional_state["contentment"] + 0.1
                )
                self._remember(
                    f"入职 {now.year - hire_dt.year} 周年纪念日", importance="high"
                )
                self._environment.broadcast_event(
                    "anniversary",
                    {
                        "name": self._name_obj,
                        "species": self.species,
                        "years": now.year - hire_dt.year,
                    },
                )
                # commit 33：周年里程碑 → 生成 milestone 碎片
                try:
                    import hashlib

                    from core.digital_life.memory_fragment import spawn_fragment

                    zone_id = self.current_zone_id or "outdoor"
                    hv = int(
                        hashlib.md5(
                            (zone_id + self._name_obj + "anniv").encode()
                        ).hexdigest()[:8],
                        16,
                    )
                    spawn_fragment(
                        frag_type="milestone",
                        x=(hv % 100) * 0.5,
                        y=((hv >> 8) % 100) * 0.5,
                        zone_id=zone_id,
                        agent_name=self._name_obj,
                        agent_species=self.species,
                        detail=f"入职 {now.year - hire_dt.year} 周年",
                    )
                except Exception:
                    pass
                # 周年当天周围同事 affection +0.05
                with self._environment._lock:
                    peers = [
                        lf
                        for lf in self._environment.population
                        if lf is not self and getattr(lf, "_alive", False)
                    ]
                for p in peers:
                    try:
                        with p._lock:
                            p._bump_relationship(self._name_obj, affection=0.05)
                    except Exception:
                        pass
        except Exception:
            pass

    def _witness_death(self, deceased_name: str) -> None:
        """commit 30：目击同事死亡（在 _die 流程中被其他活体调用）。

        - anxiety 永久 +0.15
        - 记录创伤事件
        - 在死亡地附近会绕行（简化：current_zone_id 切换概率降低）
        """
        if deceased_name in self._witnessed_deaths:
            return
        self._witnessed_deaths.append(deceased_name)
        if "witness_death" not in self.trauma_events:
            self.trauma_events.append("witness_death")
        self.emotional_state["anxiety"] = min(
            1.0, self.emotional_state["anxiety"] + 0.15
        )
        self.emotional_state["sadness"] = min(
            1.0, self.emotional_state["sadness"] + 0.2
        )
        self._remember(f"目击 {deceased_name} 的死亡，留下心理创伤", importance="high")

    # ------------------------------------------------------------------
    # commit 28：行为池系统
    # ------------------------------------------------------------------

    def _tick_behavior(self, now: datetime.datetime) -> None:
        """行为池调度：管理特有行为的启动、持续、结束。

        优先级：
        1. 紧急需求（hunger > 80 或 energy < 10）→ 立即中断当前行为
        2. 当前行为时间到 → 结束
        3. 同 zone 渡鸦讲古 → 当前生命体切到 listening
        4. 当前空闲（REST/EXPLORE）→ 从行为池随机挑一个可触发的
        """
        # 1. 正在执行行为 → 先检查中断/结束
        if self.current_behavior is not None:
            # 紧急需求中断
            if self.hunger > 80 or self.energy < 10:
                self._end_behavior("interrupted")
            elif (
                self.current_behavior_end is not None
                and time.time() >= self.current_behavior_end
            ):
                self._end_behavior("finished")
            else:
                # 持续中：调用子类钩子
                self._on_behavior_tick(self.current_behavior_cfg)
            return

        # 2. 没有行为 → 仅在 REST/EXPLORE/SOCIALIZE 时考虑（不打断 WORK/EAT/SLEEP）
        if self.current_action not in (
            ActionState.REST,
            ActionState.EXPLORE,
            ActionState.SOCIALIZE,
        ):
            return

        # 3. 检查是否被同 zone 渡鸦讲古吸引（渡鸦自己跳过）
        if self.species != "raven" and self._check_listening_to_raven():
            self.current_behavior = "listening"
            self.current_behavior_cfg = {
                "name": "listening",
                "label": "聆听渡鸦讲古",
                "animation": "idle",
                "particles": "listen_bubble",
            }
            self.current_behavior_end = time.time() + 30
            return

        # 4. 从行为池挑一个可触发的
        cfg = self._pick_behavior(now)
        if cfg is not None:
            self._start_behavior(cfg)

    def _pick_behavior(self, now: datetime.datetime) -> dict | None:
        """从 BEHAVIOR_POOL 中随机挑一个满足触发条件且不在冷却的行为。"""
        pool = self.BEHAVIOR_POOL
        if not pool:
            return None
        now_ts = time.time()
        candidates: ClassVar[ClassVar[list[dict]]] = []
        for cfg in pool:
            # 冷却检查
            st = self._behavior_state.get(cfg["name"], {})
            last_run = st.get("last_run", 0)
            cooldown = cfg.get("cooldown_sec", 300)
            if now_ts - last_run < cooldown:
                continue
            # 触发条件检查
            if not self._check_trigger(cfg.get("trigger", {}), now):
                continue
            candidates.append(cfg)
        if not candidates:
            return None
        return random.choice(candidates)

    def _check_trigger(self, cond: dict, now: datetime.datetime) -> bool:
        """检查触发条件（全部满足才返回 True）。"""
        # 时间范围 [start_h, end_h)，支持跨夜（start > end）
        if "time_range" in cond:
            start_h, end_h = cond["time_range"]
            h = now.hour
            if start_h <= end_h:
                if not (start_h <= h < end_h):
                    return False
            else:
                # 跨夜：[start, 24) ∪ [0, end)
                if not (h >= start_h or h < end_h):
                    return False
        # 能量范围
        if "energy_min" in cond and self.energy < cond["energy_min"]:
            return False
        if "energy_max" in cond and self.energy > cond["energy_max"]:
            return False
        # 饥饿度上限（饿狠了不会做无关行为）
        if "hunger_max" in cond and self.hunger > cond["hunger_max"]:
            return False
        # 季节
        if "season" in cond and (
            self._environment is None
            or self._environment.current_season() != cond["season"]
        ):
            return False
        # 最小年龄
        if "min_age_days" in cond and self.age < cond["min_age_days"]:
            return False
        # 生命阶段白名单
        if "life_stages" in cond:
            if self.life_stage.value not in cond["life_stages"]:
                return False
        # 概率（每次检查独立掷骰）
        return not ("probability" in cond and random.random() > cond["probability"])

    def _start_behavior(self, cfg: dict) -> None:
        """开始一个行为：设置状态、广播事件、写入记忆。"""
        self.current_behavior = cfg["name"]
        self.current_behavior_cfg = cfg
        self.current_behavior_end = time.time() + cfg.get("duration_sec", 60)
        self._behavior_state.setdefault(cfg["name"], {})
        self._behavior_state[cfg["name"]]["last_run"] = time.time()
        self._behavior_state[cfg["name"]]["in_progress"] = True
        # 子类钩子
        try:
            self._on_behavior_start(cfg)
        except Exception:
            pass
        # 广播事件给前端
        if self._environment is not None:
            self._environment.broadcast_event(
                "behavior_start",
                {
                    "name": self._name_obj,
                    "species": self.species,
                    "behavior": cfg["name"],
                    "label": cfg.get("label", cfg["name"]),
                    "animation": cfg.get("animation", "idle"),
                    "particles": cfg.get("particles", ""),
                    "zone_id": self.current_zone_id,
                    "duration_sec": cfg.get("duration_sec", 60),
                },
            )
        self._remember(
            f"开始行为：{cfg.get('label', cfg['name'])}", importance="normal"
        )

    def _end_behavior(self, reason: str = "finished") -> None:
        """结束当前行为：清状态、广播事件、调子类钩子。"""
        if self.current_behavior is None:
            return
        cfg = self.current_behavior_cfg or {}
        bname = self.current_behavior
        self._behavior_state.setdefault(bname, {})
        self._behavior_state[bname]["in_progress"] = False
        # 子类钩子
        try:
            self._on_behavior_end(cfg, reason)
        except Exception:
            pass
        if self._environment is not None:
            self._environment.broadcast_event(
                "behavior_end",
                {
                    "name": self._name_obj,
                    "species": self.species,
                    "behavior": bname,
                    "reason": reason,
                    "zone_id": self.current_zone_id,
                },
            )
        self._remember(
            f"结束行为：{cfg.get('label', bname)}（{reason}）", importance="normal"
        )
        self.current_behavior = None
        self.current_behavior_cfg = None
        self.current_behavior_end = None

    # 子类可覆盖的钩子
    def _on_behavior_start(self, cfg: dict) -> None:
        """行为开始时调用（子类可覆盖实现具体效果）。"""

    def _on_behavior_tick(self, cfg: dict) -> None:
        """行为持续时每秒调用（子类可覆盖实现具体效果）。"""

    def _on_behavior_end(self, cfg: dict, reason: str) -> None:
        """行为结束时调用（子类可覆盖）。"""

    def _check_listening_to_raven(self) -> bool:
        """检查同 zone 是否有渡鸦正在讲古。"""
        if self._environment is None:
            return False
        for lf in self._environment.population:
            if lf is self:
                continue
            if not getattr(lf, "_alive", False):
                continue
            if getattr(lf, "species", "") != "raven":
                continue
            if getattr(lf, "current_zone_id", "") != self.current_zone_id:
                continue
            if getattr(lf, "current_behavior", None) == "tell_story":
                return True
        return False

    def _decide_action(self) -> ActionState:
        """决策本秒做什么（非睡眠时）。"""
        # 优先级：吃 > 工作 > 社交 > 探索 > 休息
        if self.hunger > 60 and self._environment is not None:
            return ActionState.EAT
        # 成年且有能量才工作
        if (
            self.life_stage in (LifeStage.ADULT, LifeStage.MIDDLE)
            and self.energy > 30
            and random.random() < 0.7
        ):
            return ActionState.WORK
        if random.random() < 0.1:
            return ActionState.SOCIALIZE
        if random.random() < 0.1:
            return ActionState.EXPLORE
        return ActionState.REST

    def _perform_action(self) -> None:
        """执行当前行为。"""
        action = self.current_action
        if action == ActionState.EAT:
            self._eat()
        elif action == ActionState.WORK:
            self._work()
        elif action == ActionState.SOCIALIZE:
            self._socialize()
        elif action == ActionState.EXPLORE:
            self._explore()
        # REST/SLEEP 不做事

    def _eat(self) -> None:
        """进食：从环境索取食物。"""
        if self._environment is None:
            return
        need = min(50.0, 100.0 - self.hunger)
        got = self._environment.consume_resource(need * 0.1)
        if got > 0:
            self.hunger = max(0.0, self.hunger - got * 10)
            self.energy = min(100.0, self.energy + got * 5)
            self._remember(f"进食 {got:.1f} 单位")

    def _work(self) -> None:
        """工作：消耗能量，调用 job_skill。

        commit 30：情感影响工作效率
        - joy > 0.7 → 工作效率 +15%（多调一次 job_skill，约 +15%）
        - sadness > 0.6 → 工作效率 -20%（跳过 20% 的调用）
        - anxiety > 0.7 → 工作效率 -10%（跳过 10% 的调用）

        commit 37：优先执行流水线任务（receive_pipeline_task 收到的），
        没有任务时才走原有的模拟工作（job_skill）。
        """
        self.energy = max(0.0, self.energy - 0.5)
        emo = self.emotional_state
        # 概率跳过判定（模拟效率折扣）
        skip_prob = 0.0
        if emo.get("sadness", 0) > 0.6:
            skip_prob += 0.20
        if emo.get("anxiety", 0) > 0.7:
            skip_prob += 0.10
        if random.random() < skip_prob:
            # 这一秒被情绪拖累，没产出
            self._remember("工作 1 秒（情绪不佳，效率低）")
            return

        # commit 37：优先处理流水线任务（真正干活）
        if self._pipeline_task_inbox:
            try:
                results = self.run_pending_pipeline_tasks(max_count=1)
                for r in results:
                    status = "完成" if r.get("ok") else "失败"
                    self._remember(
                        f"执行流水线任务 step{r.get('step_id')} {status}："
                        f"{r.get('task', '')[:60]}"
                    )
                    # 工作完成触发器
                    try:
                        self._on_work_done(
                            f"流水线 step{r.get('step_id')}：{r.get('task', '')[:40]}"
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            return

        # 没有流水线任务时，走原有模拟工作
        try:
            self.job_skill()
            # commit 30：joy > 0.7 → 工作效率 +15%（多调一次，相当于 1.15x）
            if emo.get("joy", 0) > 0.7 and random.random() < 0.15:
                self.job_skill()
        except Exception:
            pass
        self._remember("工作 1 秒")

    def _socialize(self) -> None:
        """社交：找到同环境的其他个体，互相 mood+。"""
        if self._environment is None:
            return
        # 简化：随机找一个邻居提升 mood
        self.energy = max(0.0, self.energy - 0.1)
        self._remember("社交互动")

    def _explore(self) -> None:
        """探索：消耗能量，可能发现资源。"""
        self.energy = max(0.0, self.energy - 0.2)
        self._remember("探索周围")

    def job_skill(self) -> None:
        """岗位技能（子类覆盖）。"""

    # ------------------------------------------------------------------
    # 繁殖
    # ------------------------------------------------------------------

    def reproduce(self, partner: DigitalLifeForm) -> DigitalLifeForm | None:
        """与 partner 繁殖，返回子代（失败返回 None）。

        条件：
        - 双方都活着
        - 双方都在繁殖年龄段
        - 双方能量 ≥ 30
        """
        with self._lock, partner._lock:
            if not (self._alive and partner._alive):
                return None
            if self.species != partner.species:
                return None
            # 用实时年龄判定（基类 self.age 仅在 tick 里更新）
            my_age = (time.time() - self.birth_time) / 86400.0
            pt_age = (time.time() - partner.birth_time) / 86400.0
            age_min = float(self.genome.get("reproduction_age_min_days", 365 * 2))
            age_max = float(self.genome.get("reproduction_age_max_days", 365 * 15))
            if not (age_min <= my_age <= age_max):
                return None
            if not (age_min <= pt_age <= age_max):
                return None
            if self.energy < 30 or partner.energy < 30:
                return None

            # 基因重组
            child_genome = self._crossover(partner)
            # 子代
            child = self._create_child(child_genome, self._environment, time.time())
            child.parents = [self, partner]
            self.children.append(child)
            partner.children.append(child)
            self.energy -= 20
            partner.energy -= 20

            if self._environment is not None:
                self._environment.broadcast_event(
                    "reproduction",
                    {
                        "species": self.species,
                        "parents": [self._name_obj, partner._name_obj],
                        "child": child._name_obj,
                    },
                )
            self._remember(f"与 {partner._name_obj} 繁殖出 {child._name_obj}")
            return child

    def _crossover(self, partner: DigitalLifeForm) -> dict:
        """基因重组：每个基因随机取父母一方，加 ±5% 变异。"""
        child_genome: ClassVar[ClassVar[dict]] = {}
        keys = set(self.genome.keys()) | set(partner.genome.keys())
        for k in keys:
            if k == "temperament":
                # 字典字段合并
                a = self.genome.get(k, {})
                b = partner.genome.get(k, {})
                merged = {}
                for mk in set(a.keys()) | set(b.keys()):
                    merged[mk] = random.choice([a.get(mk, 0.5), b.get(mk, 0.5)])
                child_genome[k] = merged
                continue
            val = random.choice([self.genome.get(k), partner.genome.get(k)])
            if val is None:
                continue
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                mutation = 1.0 + random.uniform(-0.05, 0.05)
                val = type(val)(val * mutation)
            child_genome[k] = val
        return child_genome

    def _create_child(
        self, genome: dict, environment, birth_time: float
    ) -> DigitalLifeForm:
        """繁殖时构造子代（子类必须覆盖）。"""
        raise NotImplementedError(f"{self.species} 未实现 _create_child")

    # ------------------------------------------------------------------
    # commit 34：持久记忆 + 照顾生病同事
    # ------------------------------------------------------------------

    def get_agent_id(self) -> str:
        """构造稳定的 agent_id（用于持久记忆）。"""
        return f"{self.species}-{self._name_obj}"

    # ------------------------------------------------------------------
    # commit 37：Agent 工具链 + 流水线任务接收
    # ------------------------------------------------------------------

    def execute_tool(
        self,
        tool_name: str,
        params: dict,
        need_approval: bool | None = None,
        timeout: float = 30.0,
    ) -> dict:
        """执行一个工具调用（沙箱内）。

        零基础理解：智能体想"真正干一件事"（比如写代码、扫描漏洞），
        就通过这个方法调用对应工具，工具会被独立线程安全地执行。

        Args:
            tool_name: 工具名（必须在 bound_tools 内）
            params: 调用参数 dict
            need_approval: 是否需要监工审批（None 时按 DANGEROUS_TOOLS 判断）
            timeout: 超时秒数

        Returns:
            {"ok", "output", "error", "duration_ms", "stdout", "stderr"}
        """
        try:
            from core.digital_life.tool_executor import get_tool_executor

            self._tool_call_status = "running"
            self._tool_call_meta = {
                "tool_name": tool_name,
                "started_ts": time.time(),
            }
            executor = get_tool_executor()
            result = executor.execute(
                self,
                tool_name,
                params,
                need_approval=need_approval,
                timeout=timeout,
            )
            self._tool_call_status = "done" if result.ok else "error"
            self._tool_call_meta["last_done_ts"] = time.time()
            return result.to_dict()
        except Exception as e:
            self._tool_call_status = "error"
            self._tool_call_meta["last_done_ts"] = time.time()
            return {
                "ok": False,
                "error": f"execute_tool 异常: {e}",
                "output": None,
                "duration_ms": 0,
                "stdout": "",
                "stderr": "",
                "tool_name": tool_name,
                "agent_id": self.get_agent_id(),
            }

    def receive_pipeline_task(self, task: dict) -> None:
        """接收一个流水线任务（来自 PipelineEngine）。

        task 格式：{"step_id", "agent_species", "task", "tools", "depends_on"}

        零基础理解：鹿把工作分配表里的一行任务"派"给对应智能体，
        智能体把它放到自己的待办队列里，等到工作时间再处理。
        """
        with self._lock:
            self._pipeline_task_inbox.append(task)

    def run_pending_pipeline_tasks(self, max_count: int = 1) -> list[dict]:
        """处理待办的流水线任务（每次最多处理 max_count 个）。

        在 _work() 中被调用。每个任务会通过 agent_function_calling
        派给 LLM 决策（或走降级路径），返回结果列表。

        Returns:
            list[dict]：每个任务的结果 {"task", "ok", "answer", "tool_calls"}
        """
        results: ClassVar[ClassVar[list[dict]]] = []
        with self._lock:
            todo = self._pipeline_task_inbox[:max_count]
            self._pipeline_task_inbox = self._pipeline_task_inbox[max_count:]

        for task in todo:
            task_text = task.get("task", "")
            if not task_text:
                continue
            try:
                from core.digital_life.agent_function_calling import (
                    dispatch_task_to_agent,
                )

                self._tool_call_status = "running"
                r = dispatch_task_to_agent(self, task_text)
                results.append(
                    {
                        "step_id": task.get("step_id"),
                        "task": task_text,
                        "ok": r.get("ok", False),
                        "answer": r.get("answer", ""),
                        "tool_calls": r.get("tool_calls", []),
                    }
                )
                self._tool_call_status = "done" if r.get("ok") else "error"
            except Exception as e:
                results.append(
                    {
                        "step_id": task.get("step_id"),
                        "task": task_text,
                        "ok": False,
                        "answer": f"执行异常: {e}",
                        "tool_calls": [],
                    }
                )
                self._tool_call_status = "error"
        return results

    def get_tool_call_status(self) -> dict:
        """获取当前工具调用状态（前端可视化用）。"""
        return {
            "status": self._tool_call_status,
            "tool_name": self._tool_call_meta.get("tool_name", ""),
            "started_ts": self._tool_call_meta.get("started_ts", 0),
            "last_done_ts": self._tool_call_meta.get("last_done_ts", 0),
            "bound_tools": list(self.bound_tools),
            "pending_tasks": len(self._pipeline_task_inbox),
        }

    # ------------------------------------------------------------------
    # commit 38：主动感知 + 协商 + 反思
    # ------------------------------------------------------------------

    def bid_for_task(self, task: str) -> dict:
        """评估自身状态，对任务给出竞标信息。

        零基础理解：鹿/青鸢广播一个任务后，相关智能体按自身状态
        "竞标"——是否可接、信心度多少、能量够不够、当前忙不忙。
        鹿收到所有竞标后挑最合适的派活。

        Returns:
            {
                "agent": str,             # 显示名（如"鼠·栗壳"）
                "species": str,           # 物种代号
                "agent_name": str,
                "available": bool,        # 是否可接
                "estimated_min": int,     # 预估耗时（分钟）
                "confidence": float,      # 信心度 0~1
                "current_state": {
                    "energy": float, "emotion": str,
                    "current_workload": str, "mood_score": float,
                    "pending_count": int,
                },
                "relevant_experience_count": int,  # 经验库中相关经验数
                "special_notes": str,              # 备注（如"今天有点累"）
            }
        """
        energy = float(getattr(self, "energy", 50) or 50)
        mood_score = float(getattr(self, "mood_score", 50) or 50)
        pending_count = len(getattr(self, "_pipeline_task_inbox", []) or [])
        illness = getattr(self, "illness", None)

        # 可用性判定：能量过低 / 生病 / 任务队列满 都不可接
        available = True
        special_notes_parts: ClassVar[ClassVar[list[str]]] = []
        if energy < 20:
            available = False
            special_notes_parts.append(f"能量过低({energy:.0f})")
        if illness is not None:
            available = False
            special_notes_parts.append(f"生病({getattr(illness, 'kind', 'unknown')})")
        if pending_count >= 3:
            available = False
            special_notes_parts.append(f"任务队列已满({pending_count})")

        # 工作量描述
        if pending_count == 0:
            workload = "无"
        elif pending_count == 1:
            workload = "轻"
        elif pending_count == 2:
            workload = "中"
        else:
            workload = "重"

        # 信心度：能量 + 情绪 + 基础分
        confidence = 0.3 + (energy / 100.0) * 0.4 + (mood_score / 100.0) * 0.2
        if not available:
            confidence *= 0.3
        confidence = max(0.0, min(1.0, confidence))

        # 预估耗时：能量低耗时长，工作量重耗时长
        base_min = 15
        if energy < 40:
            base_min += 10
        if workload == "中":
            base_min += 5
        if workload == "重":
            base_min += 15

        # 情绪描述
        mood_str = getattr(self, "mood", "neutral")
        if mood_score < 30:
            mood_str = "low"
            special_notes_parts.append("情绪低落")
        elif mood_score > 75:
            mood_str = "happy"

        # 经验库相关经验数
        exp_count = 0
        try:
            from core.digital_life.experience_library import get_experience_library

            exps = get_experience_library().search_by_task(
                task, agent_species=self.species, limit=10
            )
            exp_count = len(exps)
            if exp_count > 0:
                special_notes_parts.append(f"有 {exp_count} 条相关经验")
        except Exception:
            pass

        return {
            "agent": self._name_obj,
            "species": self.species,
            "agent_name": self._name_obj,
            "available": available,
            "estimated_min": base_min,
            "confidence": round(confidence, 3),
            "current_state": {
                "energy": round(energy, 1),
                "emotion": mood_str,
                "current_workload": workload,
                "mood_score": round(mood_score, 1),
                "pending_count": pending_count,
            },
            "relevant_experience_count": exp_count,
            "special_notes": (
                "；".join(special_notes_parts) if special_notes_parts else ""
            ),
        }

    def retrospect(
        self,
        task: str,
        tool_calls: list,
        ok: bool,
        duration_sec: float,
        experience_adopted: list,
    ) -> dict:
        """任务完成后触发复盘。

        零基础理解：智能体做完一件事后，回头想想——做得怎么样？
        哪里顺利、哪里卡壳、下次怎么做得更好。复盘出来的"经验"
        会存进经验库，下次同类任务会自动注入到 prompt 里参考。

        Returns:
            {"id", "agent_species", "agent_name", "task", "lesson",
             "summary", "improvement", "ok", "duration_sec", "ts"}
        """
        try:
            from core.digital_life import retrospect as retro_mod

            router = None
            try:
                env = getattr(self, "_environment", None)
                if env is not None:
                    router = env.router if hasattr(env, "router") else None
            except Exception:
                router = None
            return retro_mod.generate_retrospect(
                agent_species=self.species,
                agent_name=self._name_obj,
                task=task,
                tool_calls=tool_calls or [],
                result_ok=ok,
                duration_sec=duration_sec,
                experience_adopted=experience_adopted or [],
                router=router,
            )
        except Exception as e:
            return {
                "ok": False,
                "error": f"retrospect 异常: {e}",
                "lesson": "",
                "summary": "",
                "improvement": "",
                "agent_species": self.species,
                "agent_name": self._name_obj,
                "task": task,
                "duration_sec": duration_sec,
            }

    # ------------------------------------------------------------------
    # commit 39：长期目标管理 - 站会汇报
    # ------------------------------------------------------------------

    def generate_standup_report(self, project_dict: dict) -> dict:
        """生成每日站会汇报（昨天做了什么 / 今天计划 / 阻塞）。

        零基础理解：每天上午 09:00，鹿发起虚拟站会，把项目信息
        推给每个参与项目的智能体，让 ta 用 LLM（不可用时降级模板）
        生成一段站会汇报。鹿最后汇总所有汇报推送给监工。

        Args:
            project_dict: Project.to_dict() 的结果

        Returns:
            {
                "agent": str,             # 显示名
                "species": str,
                "project_id": str,
                "project_name": str,
                "yesterday": str,         # 昨天做了什么
                "today": str,             # 今天计划
                "blockers": str,          # 阻塞（"" 表示无）
                "raw": str,               # 原始 LLM 文本（调试用）
                "ts": float,
            }
        """
        pid = project_dict.get("id", "")
        pname = project_dict.get("name", "")
        # 从该项目中提取自己的贡献记录
        contrib = (self.project_contributions or {}).get(pid, {})
        pending = len(getattr(self, "_pipeline_task_inbox", []) or [])
        energy = float(getattr(self, "energy", 50) or 50)
        mood_score = float(getattr(self, "mood_score", 50) or 50)
        roles = list(getattr(self, "informal_roles", []) or [])

        # 默认模板（无 LLM 时用）
        yesterday_default = (
            f"在项目「{pname}」中推进了 {contrib.get('tasks', 0)} 个任务，"
            f"提交 {contrib.get('commits', 0)} 次。"
        )
        today_default = (
            f"继续推进项目「{pname}」相关任务，当前待办 {pending} 项，"
            f"能量 {energy:.0f}、情绪 {mood_score:.0f}。"
        )
        blockers_parts: ClassVar[ClassVar[list[str]]] = []
        if energy < 30:
            blockers_parts.append(f"能量偏低({energy:.0f})")
        if mood_score < 30:
            blockers_parts.append("情绪低落")
        if pending >= 3:
            blockers_parts.append(f"任务积压({pending})")
        illness = getattr(self, "illness", None)
        if illness is not None:
            blockers_parts.append(f"生病({getattr(illness, 'kind', 'unknown')})")
        blockers_default = "；".join(blockers_parts) if blockers_parts else ""

        # 尝试调 LLM
        raw_text = ""
        yesterday = yesterday_default
        today = today_default
        blockers = blockers_default
        router = None
        try:
            env = getattr(self, "_environment", None)
            if env is not None and hasattr(env, "router"):
                router = env.router
        except Exception:
            router = None

        if router is not None:
            try:
                import asyncio

                prompt = (
                    f"你是 BlueDeer 森林公司的员工「{self._name_obj}」"
                    f"（物种：{self.species}，非正式角色：{roles or '无'}）。\n"
                    f"项目「{pname}」当前进度 {project_dict.get('overall_progress', 0):.0f}%，"
                    f"状态 {project_dict.get('status', '')}。\n"
                    f"你的待办任务数：{pending}，能量 {energy:.0f}，情绪 {mood_score:.0f}。\n\n"
                    "请用 50 字以内分别输出三行：\n"
                    "YESTERDAY: 昨天做了什么\n"
                    "TODAY: 今天计划做什么\n"
                    "BLOCKERS: 有什么阻塞（无则写「无」）\n"
                )
                loop = asyncio.new_event_loop()
                try:
                    resp = loop.run_until_complete(router.complete(prompt))
                finally:
                    loop.close()
                raw_text = str(resp) if resp else ""
                for line in raw_text.split("\n"):
                    s = line.strip()
                    if s.startswith("YESTERDAY:"):
                        v = s[len("YESTERDAY:") :].strip()
                        if v:
                            yesterday = v
                    elif s.startswith("TODAY:"):
                        v = s[len("TODAY:") :].strip()
                        if v:
                            today = v
                    elif s.startswith("BLOCKERS:"):
                        v = s[len("BLOCKERS:") :].strip()
                        if v and v not in ("无", "无。", "None"):
                            blockers = v
            except Exception:
                pass

        # 累加社交/监工互动统计（站会本身就是一次与鹿的协作互动）
        try:
            self._supervisor_interact_count = int(self._supervisor_interact_count) + 1
        except Exception:
            pass

        return {
            "agent": self._name_obj,
            "species": self.species,
            "project_id": pid,
            "project_name": pname,
            "yesterday": yesterday,
            "today": today,
            "blockers": blockers,
            "raw": raw_text,
            "ts": time.time(),
        }

    def get_persistent_memory(self):
        """懒加载并返回自己的持久记忆实例。"""
        if self.persistent_memory_ref is None:
            try:
                from core.digital_life.persistent_memory import get_memory_manager

                self.persistent_memory_ref = get_memory_manager().get_or_create(
                    self.get_agent_id(),
                    agent_name=self._name_obj,
                    species=self.species,
                )
            except Exception:
                return None
        return self.persistent_memory_ref

    def care_for(self, patient) -> dict:
        """照顾生病的同事（监工可调用）。

        Args:
            patient: 被照顾的生病生命体
        Returns:
            操作结果 dict
        """
        try:
            from core.digital_life.illness_system import get_illness_system

            return get_illness_system().assign_caregiver(patient, self)
        except Exception as e:
            return {"ok": False, "reason": str(e)}

    def record_chat(self, role: str, text: str) -> None:
        """记录一轮对话到自己的短期记忆（持久记忆系统）。"""
        try:
            mem = self.get_persistent_memory()
            if mem is not None:
                mem.add_short_message(role, text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # commit 35：自传体记忆 + 日记 + 工作产物 懒加载接口
    # ------------------------------------------------------------------

    def get_autobiography(self):
        """懒加载并返回自己的自传体记忆实例。"""
        try:
            from core.digital_life.autobiographical_memory import (
                get_autobiography_manager,
            )

            return get_autobiography_manager().get_or_create(
                self.get_agent_id(),
                agent_name=self._name_obj,
                species=self.species,
            )
        except Exception:
            return None

    def sync_self_cognition(self) -> None:
        """从自传体记忆同步自我认知到本实例字段（每 60 秒一次）。"""
        now = time.time()
        if now - self._last_self_cognition_sync_ts < 60:
            return
        self._last_self_cognition_sync_ts = now
        try:
            bio = self.get_autobiography()
            if bio is not None:
                cog = bio.self_cognition
                self.self_description = cog.get("self_description", "")
                self.values = cog.get("values", "")
                self.life_goal = cog.get("life_goal", "")
                self.contradiction = cog.get("contradiction", "")
        except Exception:
            pass

    def get_artifacts(self):
        """懒加载并返回自己的工作产物集。"""
        if self._artifact_ref is None:
            try:
                from core.digital_life.work_artifacts import get_artifacts_manager

                self._artifact_ref = get_artifacts_manager().get_or_create(
                    self.get_agent_id(),
                    agent_name=self._name_obj,
                    species=self.species,
                )
            except Exception:
                pass
        return self._artifact_ref

    # ------------------------------------------------------------------
    # 死亡
    # ------------------------------------------------------------------

    def _check_death(self) -> None:
        """判定是否死亡。"""
        max_age = self.genome.get("max_age_days", 365 * 20)
        if self.age >= max_age:
            self._die("old_age")
        elif self.health <= 0:
            self._die("health_zero")
        elif self.energy <= 0 and self.hunger >= 100:
            self._die("starvation")

    def _prepare_death(self) -> bool:
        with self._lock:
            if not self._alive:
                return False
            self._alive = False
            self._stop_event.set()
        return True

    def _record_death_memory(self, reason: str) -> None:
        self._remember(f"生命终结（{reason}）", importance="high")
        if self.wish_fulfilled:
            self.emotional_state["sadness"] = 0.0
            self._remember("退休愿望已实现，安详离世", importance="high")
        else:
            self._remember(
                f"离世时仍有未竟之愿：{self.retirement_wish or '（无）'}",
                importance="high",
            )

    def _unregister_and_log(self, reason: str) -> None:
        if self._environment is None:
            return
        self._environment.unregister(self)
        self._environment.death_log.append(
            {
                "time": time.time(),
                "species": self.species,
                "name": self._name_obj,
                "reason": reason,
                "age_days": self.age,
                "zone_id": self.current_zone_id,
                "gender": self.gender,
            }
        )
        self._environment.broadcast_event(
            "death",
            {
                "species": self.species,
                "name": self._name_obj,
                "reason": reason,
                "zone_id": self.current_zone_id,
                "wish_fulfilled": self.wish_fulfilled,
            },
        )

    def _record_relic(self) -> None:
        if self._environment is None:
            return
        try:
            from core.digital_life.dialogue_system import get_relic_def
            relic_def = get_relic_def(self.species)
            self._environment.record_relic(self, relic_def)
        except Exception:
            pass

    def _notify_witnesses(self) -> None:
        if self._environment is None:
            return
        try:
            with self._environment._lock:
                witnesses = [
                    lf
                    for lf in self._environment.population
                    if lf is not self
                    and getattr(lf, "_alive", False)
                    and getattr(lf, "current_zone_id", "") == self.current_zone_id
                ]
            for w in witnesses:
                try:
                    with w._lock:
                        w._witness_death(self._name_obj)
                except Exception:
                    pass
        except Exception:
            pass

    def _notify_supervisor(self, reason: str) -> None:
        if self._environment is None:
            return
        try:
            notifier = None
            with self._environment._lock:
                for lf in self._environment.population:
                    if lf is not self and getattr(lf, "_alive", False):
                        if lf.species == "raven":
                            notifier = lf
                            break
                if notifier is None:
                    for lf in self._environment.population:
                        if lf is not self and getattr(lf, "_alive", False):
                            if lf.species == "deer":
                                notifier = lf
                                break
            if notifier is not None:
                from core.digital_life.active_messaging import (
                    trigger_active_message,
                )
                trigger_active_message(
                    notifier,
                    "death_notice",
                    detail=self._name_obj,
                    context=f"同事 {self._name_obj}（{self.species}）因 {reason} 离世",
                    router=self._get_router(),
                )
        except Exception:
            pass

    def _spawn_death_relic(self, reason: str) -> None:
        try:
            import hashlib

            from core.digital_life.memory_fragment import spawn_fragment
            zone_id = self.current_zone_id or "outdoor"
            hv = int(
                hashlib.md5(
                    (zone_id + self._name_obj + "death").encode()
                ).hexdigest()[:8],
                16,
            )
            spawn_fragment(
                frag_type="death_relic",
                x=(hv % 100) * 0.5,
                y=((hv >> 8) % 100) * 0.5,
                zone_id=zone_id,
                agent_name=self._name_obj,
                agent_species=self.species,
                detail=f"{self.species}，因{reason}离世",
                is_relic=True,
            )
        except Exception:
            pass

    def _die(self, reason: str) -> None:
        """死亡流程。

        commit 11 扩展：
        - death_log 加 zone_id（遗物标记用）
        - 死亡本身作为 high 重要性事件入 core_memory
        - life_summary / last_words 留空，由 Biosphere 监听 death 事件后调 LLM 填充

        commit 30 扩展：
        - 通知同 zone 邻居目击死亡（_witness_death）→ 邻居 anxiety +0.15
        - 如果退休愿望已实现，sadness 归零（安详离世）；否则记录遗憾
        - 调用 environment.record_relic 记录物理遗物
        """
        if not self._prepare_death():
            return
        self._record_death_memory(reason)
        self._unregister_and_log(reason)
        self._record_relic()
        self._notify_witnesses()
        self._notify_supervisor(reason)
        self._spawn_death_relic(reason)

    def stop(self) -> None:
        """外部停止生命体线程（非死亡，仅停）。"""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # 记忆
    # ------------------------------------------------------------------

    def _remember(self, text: str, importance: str = "normal") -> None:
        """写入短期记忆。

        Args:
            text: 记忆文本。
            importance: 重要性等级。
                - "normal": 仅入 memory_recent / memory_long_term
                - "high": 同时入 core_memory（死亡时归档）
        """
        entry = {"time": time.time(), "text": text, "importance": importance}
        self.memory_recent.append(entry)
        # 所有事件入长期记忆
        if len(self.memory_long_term) < 1000:
            self.memory_long_term.append(entry)
        # 重要事件入核心记忆（死亡时归档到资料库）
        if importance == "high" and len(self.core_memory) < 100:
            self.core_memory.append(entry)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回完整状态字典。"""
        with self._lock:
            return {
                "name": self._name_obj,
                "species": self.species,
                "gender": self.gender,
                "alive": self._alive,
                "age_days": round(self.age, 4),
                "life_stage": self.life_stage.value,
                "energy": round(self.energy, 3),
                "health": round(self.health, 3),
                "hunger": round(self.hunger, 3),
                "mood": self.mood,
                "current_action": self.current_action.value,
                "sleeping": self.sleeping,
                "sleep_depth": self.genome.get("sleep_depth", "NORMAL"),
                "tick_count": self._tick_count,
                "children": [getattr(c, "_name_obj", None) for c in self.children],
                "memory_recent": list(self.memory_recent)[-10:],
                # commit 11 新增字段
                "fondness": self.fondness,
                "current_zone_id": self.current_zone_id,
                "resting_until": self.resting_until,
                "core_memory_count": len(self.core_memory),
                "life_summary": self.life_summary,
                "last_words": self.last_words,
                # commit 19 P0-1/P0-2 新增字段
                "mood_score": round(self.mood_score, 1),
                "skills": list(self.skills),
                # commit 28：当前特有行为
                "current_behavior": self.current_behavior,
                "current_behavior_label": (
                    (self.current_behavior_cfg or {}).get("label", "")
                    if self.current_behavior
                    else ""
                ),
                "behavior_particles": (
                    (self.current_behavior_cfg or {}).get("particles", "")
                    if self.current_behavior
                    else ""
                ),
                # commit 30：情感与记忆系统
                "emotional_state": {
                    k: round(v, 2) for k, v in self.emotional_state.items()
                },
                "top_emotion": (
                    max(self.emotional_state.items(), key=lambda x: x[1])[0]
                    if self.emotional_state
                    else "neutral"
                ),
                "wisdom": round(self.wisdom, 1),
                "trauma_events": list(self.trauma_events),
                "retirement_wish": self.retirement_wish,
                "wish_fulfilled": self.wish_fulfilled,
                # 关系标签（仅返回有标签的关系，避免数据膨胀）
                "relationship_tags": {
                    tid: list(ts) for tid, ts in self.relationship_tags.items() if ts
                },
                # 关系值汇总（仅返回有显著关系的，避免数据膨胀）
                "relationships_summary": {
                    tid: {k: round(v, 2) for k, v in rel.items()}
                    for tid, rel in self.relationships.items()
                    if max(rel.values(), default=0) >= 0.6
                    or self.relationship_tags.get(tid)
                },
            }

    # ------------------------------------------------------------------
    # commit 11：监工互动
    # ------------------------------------------------------------------

    def interact_feed(self, amount: float = 20.0) -> dict:
        """监工投喂：能量+，好感+，扣环境食物。

        Args:
            amount: 投喂的能量值（默认 20）。

        Returns:
            操作结果 dict。
        """
        if not self._lock.acquire(timeout=3):
            return {"ok": False, "reason": "员工忙碌中，请稍后再试"}
        try:
            if not self._alive:
                return {"ok": False, "reason": "已故"}
            # 扣环境食物（amount 的 0.5 倍）
            cost = amount * 0.5
            if self._environment is not None:
                got = self._environment.consume_resource(cost)
                if got < cost:
                    return {"ok": False, "reason": "环境食物不足"}
            # 能量提升
            self.energy = min(100.0, self.energy + amount)
            # 好感度 +5（上限 100）
            self.fondness = min(100, self.fondness + 5)
            self._remember(f"监工投喂（能量+{amount:.0f}）", importance="high")
            # commit 31：更新与监工互动时间戳（避免误触发"想念监工"）
            self._last_supervisor_interact_ts = time.time()
            return {
                "ok": True,
                "energy": round(self.energy, 1),
                "fondness": self.fondness,
                "food_cost": cost,
            }
        finally:
            self._lock.release()

    def interact_greet(self) -> dict:
        """监工打招呼：好感+2，记忆入档。

        Returns:
            操作结果 dict。
        """
        with self._lock:
            if not self._alive:
                return {"ok": False, "reason": "已故"}
            self.fondness = min(100, self.fondness + 2)
            self._remember("监工打招呼", importance="normal")
            # commit 31：更新与监工互动时间戳
            self._last_supervisor_interact_ts = time.time()
            return {"ok": True, "fondness": self.fondness}

    def interact_set_schedule(self, bedtime: str, wakeup: str) -> dict:
        """监工调整作息时间。

        Args:
            bedtime: 睡觉时间 "HH:MM"。
            wakeup: 起床时间 "HH:MM"。

        Returns:
            操作结果 dict。
        """
        with self._lock:
            if not self._alive:
                return {"ok": False, "reason": "已故"}
            self.genome["bedtime"] = bedtime
            self.genome["wakeup_time"] = wakeup
            self._remember(f"监工调整作息：{bedtime}→{wakeup}", importance="high")
            # commit 31：更新与监工互动时间戳
            self._last_supervisor_interact_ts = time.time()
            return {"ok": True, "bedtime": bedtime, "wakeup": wakeup}

    def interact_mark_focus(self) -> dict:
        """监工标记关注（仅记录，不改变状态）。

        Returns:
            操作结果 dict。
        """
        with self._lock:
            self._remember("被监工标记关注", importance="high")
            # commit 31：更新与监工互动时间戳
            self._last_supervisor_interact_ts = time.time()
            return {"ok": True, "marked": True}

    def interact_wake(self) -> dict:
        """监工唤醒：从睡眠中醒来。

        Returns:
            操作结果 dict。
        """
        if not self._lock.acquire(timeout=3):
            return {"ok": False, "reason": "员工忙碌中，请稍后再试"}
        try:
            if not self._alive:
                return {"ok": False, "reason": "已故"}
            if not self.sleeping:
                return {"ok": False, "reason": "未在睡眠"}
            self.sleeping = False
            self.sleep_start_time = None
            self.current_action = ActionState.REST
            self._remember("被监工唤醒", importance="high")
            # commit 31：更新与监工互动时间戳
            self._last_supervisor_interact_ts = time.time()
            return {"ok": True, "awake": True}
        finally:
            self._lock.release()

    def set_zone(self, zone_id: str) -> None:
        """更新当前所在 zone（用于遗物标记 + 觅食）。"""
        with self._lock:
            self.current_zone_id = zone_id

    def start_foraging(self, duration_sec: float = 30.0) -> dict:
        """派去觅食：设 resting_until，期间在 canteen/lounge 恢复能量。

        Args:
            duration_sec: 觅食持续时间（秒）。

        Returns:
            操作结果 dict。
        """
        with self._lock:
            if not self._alive:
                return {"ok": False, "reason": "已故"}
            if self.sleeping:
                return {"ok": False, "reason": "睡眠中"}
            self.resting_until = time.time() + duration_sec
            self._remember(f"被派去觅食（{duration_sec:.0f}秒）", importance="normal")
            return {"ok": True, "resting_until": self.resting_until}

    def tick_fondness_decay(self) -> None:
        """好感度衰减：每 tick 检查，10 秒不互动衰减 1。

        简化实现：每次调用有 1/10 概率衰减 1（平均 10 秒衰减 1）。
        """
        with self._lock:
            if self.fondness > 50 and random.random() < 0.1:
                self.fondness = max(50, self.fondness - 1)

    def _tick_foraging(self) -> None:
        """觅食状态推进：resting_until 未到则每秒能量 +5，到时则结束。

        简化实现：在 canteen/lounge 期间每秒能量 +5，扣 env.food_available。
        """
        if self.resting_until is None:
            return
        if time.time() >= self.resting_until:
            self.resting_until = None
            self._remember("觅食结束", importance="normal")
            return
        # 每秒能量 +5，扣环境食物 5
        if self._environment is not None:
            got = self._environment.consume_resource(5.0)
            if got > 0:
                self.energy = min(100.0, self.energy + got)
                self.hunger = max(0.0, self.hunger - got * 0.5)
