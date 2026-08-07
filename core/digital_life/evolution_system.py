"""commit 40：智能体进化突变系统。

零基础读者可以这样理解：
- 智能体长期运行后会变得"可预测"，缺乏新鲜感
- 极低概率发生"进化突变"——外观/行为/技能的随机变化
- 突变有 40% 概率遗传给下一代，连续 3 代遗传后变成物种固定特征
- 1% 概率触发"传说级突变"（金鹿角、白化松鼠、凤凰蝶等）

持久化：data/evolution_system.json
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from typing import Any
# ruff: noqa: S110, S112

_EVOLUTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "evolution_system.json",
)

# 突变触发条件
MIN_AGE_DAYS = 180  # 至少存活 6 个月（现实时间）
MUTATION_PROB = 0.05  # 满足条件时 5% 概率触发
CHECK_INTERVAL = 30 * 86400  # 每现实月检查一次

# 突变维度
DIM_APPEARANCE = "appearance"  # 外观突变（30%）
DIM_BEHAVIOR = "behavior"  # 行为突变（40%）
DIM_SKILL = "skill"  # 技能突变（30%）

# 传说级突变（1% 概率）
LEGENDARY_MUTATIONS = [
    {
        "key": "golden_antler",
        "name_zh": "金鹿角",
        "species": "deer",
        "description": "鹿角完全变为金色，全公司工作效率永久 +5%",
        "effect": {"work_efficiency_bonus": 0.05, "global": True},
    },
    {
        "key": "albino_squirrel",
        "name_zh": "白化松鼠",
        "species": "squirrel",
        "description": "松鼠全身变为纯白（极稀有外观）",
        "effect": {"appearance_override": "#ffffff"},
    },
    {
        "key": "phoenix_butterfly",
        "name_zh": "凤凰蝶",
        "species": "butterfly",
        "description": "翅膀变为火焰色，死后有 50% 概率自动复活一次",
        "effect": {"revive_chance": 0.5, "appearance_override": "#ff6600"},
    },
    {
        "key": "ten_tail_fox",
        "name_zh": "十尾狐狸",
        "species": "fox",
        "description": "长出第十条尾巴的虚影，测试效率翻倍",
        "effect": {"skill_bonus": {"testing": 5.0}},
    },
    {
        "key": "immortal_raven",
        "name_zh": "永生渡鸦",
        "species": "raven",
        "description": "max_age 翻倍，几乎永生",
        "effect": {"max_age_multiplier": 2.0},
    },
]

# 普通外观突变池
APPEARANCE_MUTATIONS = [
    {"key": "fur_shift", "name_zh": "毛色微变", "description": "主色偏移 5-10 个色值"},
    {"key": "eye_color", "name_zh": "眼睛变色", "description": "虹膜变为稀有颜色"},
    {"key": "decoration", "name_zh": "装饰出现", "description": "出现独特外观标记"},
    {
        "key": "size_change",
        "name_zh": "体型微调",
        "description": "稍微变大或变小 1-2px",
    },
]

# 普通行为突变池
BEHAVIOR_MUTATIONS = [
    {
        "key": "quirk_left_foot",
        "name_zh": "新怪癖·先迈左脚",
        "description": "获得终身行为习惯",
    },
    {
        "key": "quirk_pause_door",
        "name_zh": "新怪癖·进门停 3 秒",
        "description": "获得终身行为习惯",
    },
    {
        "key": "quirk_tea_time",
        "name_zh": "新怪癖·下午 3 点茶水间",
        "description": "获得终身行为习惯",
    },
    {
        "key": "social_clingy",
        "name_zh": "社交偏好·更粘人",
        "description": "社交意愿 +50%",
    },
    {
        "key": "social_solitary",
        "name_zh": "社交偏好·更独居",
        "description": "社交意愿 -50%",
    },
    {
        "key": "work_hard_first",
        "name_zh": "工作风格·先做最难的",
        "description": "工作优先级调整",
    },
    {
        "key": "work_easy_first",
        "name_zh": "工作风格·先做简单的",
        "description": "工作优先级调整",
    },
    {
        "key": "food_preference",
        "name_zh": "食物偏好变化",
        "description": "最喜欢的食物类型改变",
    },
]

# 普通技能突变池
SKILL_MUTATIONS = [
    {
        "key": "talent_unlock",
        "name_zh": "天赋解锁",
        "description": "获得一个新技能天赋",
    },
    {
        "key": "learning_boost",
        "name_zh": "学习加速",
        "description": "学习特定技能的速度翻倍",
    },
    {
        "key": "inspiration_burst",
        "name_zh": "灵感爆发",
        "description": "未来 7 天工作效率 +10%",
    },
    {
        "key": "cross_species_skill",
        "name_zh": "跨物种技能",
        "description": "学到通常不属于本物种的技能",
    },
]


class EvolutionSystem:
    """进化突变系统（单例）。"""

    _instance: EvolutionSystem | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._biosphere_ref: Any = None
        self._mutation_log: list[dict] = []  # 所有突变历史
        self._genetic_traits: dict[str, dict] = (
            {}
        )  # 遗传特征 {species: {trait_key: generation_count}}
        self._last_check_ts: float = 0.0
        self._check_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._load()

    @classmethod
    def get_instance(cls) -> EvolutionSystem:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def set_biosphere(self, bio: Any) -> None:
        self._biosphere_ref = bio

    # ---------------- 持久化 ----------------

    def _load(self) -> None:
        try:
            if os.path.exists(_EVOLUTION_PATH):
                with open(_EVOLUTION_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._mutation_log = list(data.get("mutation_log", []))
                self._genetic_traits = dict(data.get("genetic_traits", {}))
                self._last_check_ts = float(data.get("last_check_ts", 0.0))
        except Exception:
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_EVOLUTION_PATH), exist_ok=True)
            with self._lock:
                data = {
                    "mutation_log": list(self._mutation_log),
                    "genetic_traits": dict(self._genetic_traits),
                    "last_check_ts": self._last_check_ts,
                }
            with open(_EVOLUTION_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- 调度 ----------------

    def start(self) -> None:
        """启动定期检查线程。"""
        if self._check_thread and self._check_thread.is_alive():
            return
        self._stop_event.clear()
        self._check_thread = threading.Thread(
            target=self._check_loop, daemon=True, name="evolution-check"
        )
        self._check_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._check_thread and self._check_thread.is_alive():
            try:
                self._check_thread.join(timeout=2.0)
            except Exception:
                pass

    def _check_loop(self) -> None:
        """每现实月检查一次（开发期用 60 秒便于测试）。"""
        while not self._stop_event.is_set():
            try:
                self.run_check()
            except Exception:
                pass
            interval = 60.0 if os.environ.get("BLUEDEER_DEV", "1") == "1" else 86400.0
            self._stop_event.wait(interval)

    # ---------------- 突变检查 ----------------

    def run_check(self) -> list[dict]:
        """对所有智能体执行一次突变检查，返回本次发生的突变列表。"""
        if self._biosphere_ref is None:
            return []
        new_mutations = []
        employees = getattr(self._biosphere_ref, "employees", [])
        for lf in employees:
            if not getattr(lf, "_alive", False):
                continue
            try:
                m = self._try_mutate(lf)
                if m:
                    new_mutations.append(m)
            except Exception:
                pass
        self._last_check_ts = time.time()
        self._save()
        return new_mutations

    def _try_mutate(self, lf: Any) -> dict | None:
        """检查单个智能体是否触发突变。"""
        # 条件 1：存活超过 6 个月
        age_days = float(getattr(lf, "age", 0))
        if age_days < MIN_AGE_DAYS:
            return None
        # 条件 2：成年期且健康 > 70
        health = float(getattr(lf, "health", 0))
        if health < 70:
            return None
        # 条件 3：5% 概率
        if random.random() > MUTATION_PROB:
            return None

        # 触发突变
        return self._generate_mutation(lf)

    def _generate_mutation(self, lf: Any) -> dict:
        """生成一次突变。"""
        # 1% 概率传说级
        is_legendary = random.random() < 0.01
        if is_legendary:
            # 找该物种的传说突变
            species = getattr(lf, "species", "")
            candidates = [m for m in LEGENDARY_MUTATIONS if m["species"] == species]
            if candidates:
                chosen = random.choice(candidates)
                return self._apply_mutation(lf, chosen, legendary=True)

        # 普通突变：随机选维度
        dim = random.choices(
            [DIM_APPEARANCE, DIM_BEHAVIOR, DIM_SKILL], weights=[30, 40, 30]
        )[0]
        if dim == DIM_APPEARANCE:
            pool = APPEARANCE_MUTATIONS
        elif dim == DIM_BEHAVIOR:
            pool = BEHAVIOR_MUTATIONS
        else:
            pool = SKILL_MUTATIONS
        chosen = random.choice(pool)
        return self._apply_mutation(lf, chosen, legendary=False, dimension=dim)

    def _apply_mutation(
        self, lf: Any, mutation: dict, legendary: bool = False, dimension: str = ""
    ) -> dict:
        """应用一次突变到智能体，返回记录 dict。"""
        # 写入智能体的 mutations 列表
        if not hasattr(lf, "mutations"):
            lf.mutations = []
        record = {
            "key": mutation["key"],
            "name_zh": mutation["name_zh"],
            "description": mutation["description"],
            "dimension": dimension or ("legendary" if legendary else ""),
            "legendary": legendary,
            "ts": time.time(),
            "agent_name": getattr(lf, "_name_obj", ""),
            "agent_species": getattr(lf, "species", ""),
            "inherited": False,
        }
        lf.mutations.append(record)

        # 应用效果
        effect = mutation.get("effect", {})
        if "appearance_override" in effect:
            if not hasattr(lf, "appearance_modifiers"):
                lf.appearance_modifiers = {}
            lf.appearance_modifiers["color_override"] = effect["appearance_override"]
        if "max_age_multiplier" in effect:
            try:
                lf.max_age = (
                    float(getattr(lf, "max_age", 100)) * effect["max_age_multiplier"]
                )
            except Exception:
                pass
        if "skill_bonus" in effect:
            try:
                sk = getattr(lf, "skills", {})
                if isinstance(sk, dict):
                    for k, v in effect["skill_bonus"].items():
                        sk[k] = float(sk.get(k, 0)) + float(v)
            except Exception:
                pass

        # 记录到日志
        with self._lock:
            self._mutation_log.append(record)
        return record

    # ---------------- 遗传 ----------------

    def on_agent_death(self, lf: Any) -> None:
        """智能体死亡时调用，记录可遗传的突变。"""
        mutations = getattr(lf, "mutations", [])
        if not mutations:
            return
        species = getattr(lf, "species", "")
        with self._lock:
            if species not in self._genetic_traits:
                self._genetic_traits[species] = {}
            for m in mutations:
                key = m.get("key", "")
                if not key:
                    continue
                # 40% 概率遗传
                if random.random() < 0.4:
                    cur = self._genetic_traits[species].get(key, 0)
                    self._genetic_traits[species][key] = cur + 1
                    # 连续 3 代遗传 → 固定特征
                    if self._genetic_traits[species][key] >= 3:
                        self._genetic_traits[species][key] = -1  # -1 表示已固化
        self._save()

    def get_inherited_traits(self, species: str) -> list[dict]:
        """获取某物种的遗传特征，用于新招募的个体。"""
        with self._lock:
            traits = self._genetic_traits.get(species, {})
        result = []
        for key, gen in traits.items():
            if gen == -1:
                # 固定特征，100% 遗传
                result.append({"key": key, "fixed": True})
            elif gen > 0:
                # 非固定，40% 概率遗传
                if random.random() < 0.4:
                    result.append({"key": key, "fixed": False})
        return result

    def apply_inherited_traits(self, lf: Any) -> None:
        """新招募的个体应用遗传特征。"""
        species = getattr(lf, "species", "")
        traits = self.get_inherited_traits(species)
        if not traits:
            return
        if not hasattr(lf, "mutations"):
            lf.mutations = []
        for t in traits:
            # 找到对应的突变定义
            all_mutations = (
                APPEARANCE_MUTATIONS
                + BEHAVIOR_MUTATIONS
                + SKILL_MUTATIONS
                + LEGENDARY_MUTATIONS
            )
            for m in all_mutations:
                if m["key"] == t["key"]:
                    record = {
                        "key": m["key"],
                        "name_zh": m["name_zh"],
                        "description": m["description"],
                        "dimension": "inherited",
                        "legendary": m in LEGENDARY_MUTATIONS,
                        "ts": time.time(),
                        "agent_name": getattr(lf, "_name_obj", ""),
                        "agent_species": species,
                        "inherited": True,
                    }
                    lf.mutations.append(record)
                    break

    # ---------------- 查询 ----------------

    _MUTATION_LOG_MAX = 5000

    def list_mutations(self, limit: int = 50) -> list[dict]:
        """返回最近的突变历史。"""
        with self._lock:
            if len(self._mutation_log) > self._MUTATION_LOG_MAX:
                self._mutation_log = self._mutation_log[-self._MUTATION_LOG_MAX :]
            return list(self._mutation_log[-limit:])

    def get_mutation_stats(self) -> dict:
        """返回突变统计。"""
        with self._lock:
            total = len(self._mutation_log)
            legendary = sum(1 for m in self._mutation_log if m.get("legendary"))
            by_dim = {}
            for m in self._mutation_log:
                d = m.get("dimension", "unknown")
                by_dim[d] = by_dim.get(d, 0) + 1
            return {
                "total_mutations": total,
                "legendary_mutations": legendary,
                "by_dimension": by_dim,
                "genetic_species": list(self._genetic_traits.keys()),
                "last_check_ts": self._last_check_ts,
            }


def get_evolution_system() -> EvolutionSystem:
    """获取 EvolutionSystem 单例。"""
    return EvolutionSystem.get_instance()
