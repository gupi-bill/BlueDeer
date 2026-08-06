"""数字生命共享环境 Environment。

Borg 模式（单例共享状态）：所有 Environment 实例共享同一份 __dict__，
任意一处修改，全局可见。这样鹿、松鼠、狐狸等不需要传引用也能拿到同一份世界。

环境职责：
- 食物资源（按季节自动再生）
- 种群登记（register / unregister）
- 事件日志（broadcast_event → event_log）
- 死亡日志 / 出生日志
- 种群统计（population_status）

季节（北半球，按真实月份）：
    春 3-5 月   再生 ×1.5
    夏 6-8 月   再生 ×1.2
    秋 9-11 月  再生 ×1.0
    冬 12-2 月  再生 ×0.5

commit 29：动态生态系统
- 植物资源池（食物链基础，受季节/天气影响生长）
- 微气候区域（水坝机房/雪原/花房/大厅/室外，各有温湿度修正）
- 天气系统（晴/阴/雨/大雨/雪/极温，真正影响行为）
- 随机生态事件触发器（虫子入侵/突然灵感/花开放/溪流涨水/大扫除）
- 生态数据统计（每日资源峰谷/植物总量/事件列表/活动占比/互动次数/区域热度）
"""

from __future__ import annotations

import datetime
import random
import threading
import time
from collections import deque
from typing import Any

# ==================== commit 29：微气候区域定义 ====================
# 每个区域：温度修正 / 湿度修正 / 物种偏好（在该区域的额外能量恢复倍率）
# zone_id 与 run_biosphere.EMPLOYEES 的 species 一致（用于 set_zone）
MICROCLIMATE_ZONES: dict[str, dict] = {
    "beaver": {  # 水坝机房
        "label": "水坝机房",
        "temp_delta": 0,
        "humidity_delta": 30,
        "species_bonus": {"beaver": 0.20},  # 海狸在此恢复 +20%
        "species_penalty": {"hedgehog": -0.10, "hare": -0.10},  # 干燥物种不喜欢
    },
    "hare": {  # 算盘雪原
        "label": "算盘雪原",
        "temp_delta": -10,
        "humidity_delta": 0,
        "species_bonus": {"hare": 0.30},  # 雪兔在此恢复 +30%
        "species_penalty": {},  # 其他物种停留 >10 分钟会掉能量（在 tick 中处理）
    },
    "butterfly": {  # 花房
        "label": "花房",
        "temp_delta": 5,
        "humidity_delta": 20,
        "species_bonus": {"butterfly": 0.50},  # 蝶在此恢复最快
        "plant_growth_bonus": 0.50,  # 植物生长 +50%
    },
    "deer": {  # 大厅/休息室（鹿岗=大厅）
        "label": "大厅",
        "temp_delta": 0,
        "humidity_delta": 0,
        "species_bonus": {},  # 任何物种在此休息都有 +10%（在 tick 中统一加）
        "is_comfortable": True,
    },
    # 其他 zone（squirrel/fox/raven/badger/lark/kite）默认室外，无特殊修正
}


# ==================== commit 29：天气类型 ====================
# weather_key: {label, 户外活动倍率, 能量消耗倍率, 户外能量恢复倍率}
WEATHER_TYPES: dict[str, dict] = {
    "sunny": {
        "label": "晴天",
        "outdoor_act_mult": 1.30,
        "energy_cost_mult": 0.90,
        "recover_mult": 1.00,
    },
    "cloudy": {
        "label": "阴天",
        "outdoor_act_mult": 1.00,
        "energy_cost_mult": 1.00,
        "recover_mult": 0.85,
    },
    "light_rain": {
        "label": "小雨",
        "outdoor_act_mult": 0.80,
        "energy_cost_mult": 1.00,
        "recover_mult": 0.80,
    },
    "heavy_rain": {
        "label": "大雨/雷暴",
        "outdoor_act_mult": 0.10,
        "energy_cost_mult": 1.20,
        "recover_mult": 0.60,
    },
    "snow": {
        "label": "雪",
        "outdoor_act_mult": 0.50,
        "energy_cost_mult": 1.10,
        "recover_mult": 0.80,
    },
    "hot": {
        "label": "极高温",
        "outdoor_act_mult": 0.85,
        "energy_cost_mult": 1.15,
        "recover_mult": 0.90,
    },
    "cold": {
        "label": "极低温",
        "outdoor_act_mult": 0.30,
        "energy_cost_mult": 1.25,
        "recover_mult": 0.70,
    },
}


# ==================== commit 29：生态事件池 ====================
# 每个事件：name / label / probability（每天触发概率）/ duration_sec / effect_type
ECO_EVENTS: list[dict] = [
    {
        "name": "bug_invasion",
        "label": "真·虫子入侵",
        "probability": 0.03,  # 3%/天
        "duration_sec": 600,  # 10 分钟
        "effect_type": "work_halt",  # 工作效率归 0
    },
    {
        "name": "inspiration",
        "label": "突然灵感",
        "probability": 0.05,  # 5%/天/人（在 tick 中按人触发）
        "duration_sec": 3600,  # 1 小时
        "effect_type": "work_boost",  # 工作效率翻倍
    },
    {
        "name": "flower_bloom",
        "label": "季节性花开放",
        "probability": 0.20,  # 春季 20%/天
        "season": "spring",
        "duration_sec": 86400,  # 一整天
        "effect_type": "social_boost",  # 社交行为增加
    },
    {
        "name": "flood_risk",
        "label": "溪流涨水",
        "probability": 0.50,  # 大雨后 50%
        "requires_weather": "heavy_rain",
        "duration_sec": 1800,
        "effect_type": "dam_reinforce",  # 海狸紧急加固
    },
    {
        "name": "cleaning_day",
        "label": "大扫除日",
        "probability": 1.0,  # 每月 1 日必触发
        "day_of_month": 1,
        "duration_sec": 7200,  # 2 小时
        "effect_type": "cleaning",  # 全员情绪提升
    },
]


# ==================== commit 29：物种间关系（好感网络） ====================
# 互助对（天生亲近）：相遇时 mood 加成更多
SPECIES_AFFINITY: dict[str, list[str]] = {
    "deer": ["raven"],  # 智者同盟
    "raven": ["deer"],
    "squirrel": ["fox"],  # 最佳损友
    "fox": ["squirrel"],
    "lark": ["hare"],  # 数据搭档
    "hare": ["lark"],
    "butterfly": ["badger"],  # 獾欣赏蝶
    "badger": ["butterfly"],
    "beaver": ["kite"],  # 鸢帮海狸侦察
    "kite": ["beaver"],
}


class Environment:
    """数字生命共享环境（Borg 模式单例）。"""

    # Borg：所有实例共享 __dict__
    __shared_state: dict = {
        "food_available": 1000.0,
        "population": [],  # list[DigitalLifeForm]
        "event_log": None,  # 后续在 __init__ 中初始化为 deque
        "death_log": [],
        "birth_log": [],
        "_lock": None,  # 后续在 __init__ 中初始化
        "_init_done": False,
        # commit 29：生态系统状态
        "plant_biomass": 500.0,  # 植物总量（食物链基础）
        "insect_count": 50,  # 昆虫数量（随植物增多）
        "current_weather": "sunny",  # 当前天气 key
        "weather_changed_at": 0.0,  # 天气切换时间戳
        "weather_change_interval": 3600,  # 每 1 小时切换一次天气
        "active_eco_events": [],  # 当前活跃的生态事件列表
        "_last_eco_event_check": 0.0,  # 上次生态事件检查时间
        "_last_weather_check": 0.0,  # 上次天气切换检查时间
        "eco_stats": None,  # 生态数据统计 dict
        "zone_occupancy": {},  # 区域占用统计 {zone_id: 停留总秒数}
        "interaction_count": {},  # 物种间互动次数 {"deer-raven": N, ...}
        "_last_stats_rollover": 0.0,  # 上次统计数据滚动时间
        # commit 30：情感与关系系统状态
        #   relics: 遗物列表 [{"name","species","owner","relic_name","desc","time","zone_id"}]
        #   relationship_events: 关系事件 [{"time","type","a","b","tag",...}]
        #   dialogue_bubbles: 对话气泡队列 [{"speaker","text","target","expire_ts"}]
        #     （SSE 端每秒拉取并清空过期）
        #   _dialogue_seq: 气泡自增序号（前端用此 id 去重）
        "relics": [],
        "relationship_events": [],
        "dialogue_bubbles": [],
        "_dialogue_seq": 0,
        # commit 31：主动消息系统
        #   active_messages: 待推送的主动消息队列（SSE 拉取后清空）
        #     [{"id","sender","sender_species","text","category","priority","time"}]
        #   _active_msg_seq: 消息自增序号（前端去重用）
        #   _active_msg_hour_ts: 当前小时起始 ts（用于 _active_msg_hour_count 重置）
        #   _active_msg_hour_count: 当前小时已发送消息数（速率限制用）
        #   _active_msg_pending_overflow: 每小时超出 HOURLY_LIMIT 后的累计计数
        "active_messages": [],
        "_active_msg_seq": 0,
        "_active_msg_hour_ts": 0.0,
        "_active_msg_hour_count": 0,
        "_active_msg_pending_overflow": 0,
    }

    # 让本类只暴露 __dict__ 一个 slot（共享状态都存进去）
    __slots__ = ["__dict__"]

    def __init__(self) -> None:
        self.__dict__ = self.__shared_state
        if not self._init_done:
            self.food_available = 1000.0
            self.population = []
            self.event_log = deque(maxlen=1000)
            self.death_log = []
            self.birth_log = []
            self._lock = threading.RLock()
            self.plant_biomass = 500.0
            self.insect_count = 50
            self.current_weather = "sunny"
            self.weather_changed_at = 0.0
            self.weather_change_interval = 3600
            self.active_eco_events = []
            self._last_eco_event_check = 0.0
            self._last_weather_check = 0.0
            self.eco_stats = self._init_eco_stats()
            self.zone_occupancy = {}
            self.interaction_count = {}
            self._last_stats_rollover = 0.0
            self.relics = []
            self.relationship_events = []
            self.dialogue_bubbles = []
            self._dialogue_seq = 0
            self.active_messages = []
            self._active_msg_seq = 0
            self._active_msg_hour_ts = 0.0
            self._active_msg_hour_count = 0
            self._active_msg_pending_overflow = 0
            # commit 47：节拍器计数器，减少每秒全量子系统调用
            self._tick_counter: int = 0
            self._init_done = True

    # ------------------------------------------------------------------
    # commit 42：tick() 仿真步进 + time_of_day
    # ------------------------------------------------------------------

    _WEATHER_SYSTEM = None

    @property
    def time_of_day(self) -> str:
        h = datetime.datetime.now().hour
        if 5 <= h < 8:
            return "dawn"
        if 8 <= h < 12:
            return "morning"
        if 12 <= h < 14:
            return "noon"
        if 14 <= h < 18:
            return "afternoon"
        if 18 <= h < 21:
            return "evening"
        return "night"

    def tick(self, dt: float = 1.0, router: Any = None) -> dict:
        now = time.time()
        self.regenerate()
        self.tick_weather(now)
        self.tick_eco_events(now)
        self.tick_eco_stats(now)
        self.tick_immersive_systems(dt, router)
        return {
            "time_of_day": self.time_of_day,
            "weather": self.current_weather,
            "food": round(self.food_available, 1),
            "population": len(self.population),
            "season": self.current_season(),
        }

    # ------------------------------------------------------------------
    # 种群登记
    # ------------------------------------------------------------------

    def register(self, life_form: Any) -> None:
        with self._lock:
            if life_form not in self.population:
                self.population.append(life_form)

    def unregister(self, life_form: Any) -> None:
        with self._lock:
            try:
                self.population.remove(life_form)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # 资源
    # ------------------------------------------------------------------

    def consume_resource(self, amount: float) -> float:
        if amount <= 0:
            return 0.0
        with self._lock:
            got = min(amount, self.food_available)
            self.food_available -= got
            return got

    def regenerate(self) -> None:
        """每 tick 自动再生资源（基于植物总量 × 季节 × 天气）。"""
        season = self.current_season()
        season_mult = {"spring": 1.5, "summer": 1.2, "autumn": 1.0, "winter": 0.5}[
            season
        ]
        # commit 29：植物总量影响再生速率（植物多 → 食物多）
        plant_factor = max(0.2, self.plant_biomass / 500.0)  # 500 为基准
        # 天气影响：晴天/雨天植物生长快
        weather_mult = {
            "sunny": 1.2,
            "cloudy": 0.9,
            "light_rain": 1.1,
            "heavy_rain": 0.7,
            "snow": 0.4,
            "hot": 0.6,
            "cold": 0.5,
        }.get(self.current_weather, 1.0)
        with self._lock:
            self.food_available = min(
                2000.0,
                self.food_available + 1.0 * season_mult * plant_factor * weather_mult,
            )
            # 植物缓慢生长（每 tick +0.5，受季节 × 天气影响）
            self.plant_biomass = min(
                2000.0, self.plant_biomass + 0.5 * season_mult * weather_mult
            )
            # 昆虫随植物增多
            target_insects = int(self.plant_biomass / 10)
            if self.insect_count < target_insects:
                self.insect_count += 1
            elif self.insect_count > target_insects:
                self.insect_count -= 1

    def consume_plant(self, amount: float) -> float:
        """消耗植物（用于食草动物进食）。"""
        with self._lock:
            got = min(amount, self.plant_biomass)
            self.plant_biomass -= got
            return got

    def current_season(self) -> str:
        """返回当前季节（北半球，按真实月份）。"""
        month = datetime.datetime.now().month
        if 3 <= month <= 5:
            return "spring"
        if 6 <= month <= 8:
            return "summer"
        if 9 <= month <= 11:
            return "autumn"
        return "winter"

    # ------------------------------------------------------------------
    # commit 29：天气系统
    # ------------------------------------------------------------------

    def tick_weather(self, now_ts: float) -> None:
        """每 tick 检查是否需要切换天气。

        切换规则：
        - 每 1 小时检查一次
        - 根据季节 + 随机抽取天气
        - 极高温/极低温仅在夏季正午/冬季深夜触发
        """
        if now_ts - self._last_weather_check < self.weather_change_interval:
            return
        self._last_weather_check = now_ts
        hour = datetime.datetime.now().hour
        season = self.current_season()
        # 极温检查
        if season == "summer" and 12 <= hour <= 15:
            new_weather = (
                "hot" if random.random() < 0.4 else self._pick_normal_weather(season)
            )
        elif season == "winter" and (hour < 6 or hour >= 22):
            new_weather = (
                "cold" if random.random() < 0.4 else self._pick_normal_weather(season)
            )
        else:
            new_weather = self._pick_normal_weather(season)
        if new_weather != self.current_weather:
            old = self.current_weather
            self.current_weather = new_weather
            self.weather_changed_at = now_ts
            self.broadcast_event(
                "weather_change",
                {
                    "from": old,
                    "to": new_weather,
                    "label": WEATHER_TYPES.get(new_weather, {}).get(
                        "label", new_weather
                    ),
                },
            )

    def _pick_normal_weather(self, season: str) -> str:
        """根据季节抽取普通天气。"""
        # 各季节天气权重
        weights = {
            "spring": {"sunny": 4, "cloudy": 3, "light_rain": 2, "heavy_rain": 1},
            "summer": {"sunny": 6, "cloudy": 2, "light_rain": 1, "heavy_rain": 1},
            "autumn": {"sunny": 3, "cloudy": 4, "light_rain": 2, "heavy_rain": 1},
            "winter": {"sunny": 2, "cloudy": 3, "snow": 4, "light_rain": 1},
        }.get(season, {"sunny": 3, "cloudy": 3, "light_rain": 1})
        keys = list(weights.keys())
        vals = list(weights.values())
        return random.choices(keys, weights=vals, k=1)[0]

    def weather_info(self) -> dict:
        """返回当前天气完整信息。"""
        return WEATHER_TYPES.get(self.current_weather, {"label": self.current_weather})

    # ------------------------------------------------------------------
    # commit 29：微气候
    # ------------------------------------------------------------------

    def zone_microclimate(self, zone_id: str) -> dict:
        """返回某 zone 的微气候信息。"""
        return MICROCLIMATE_ZONES.get(
            zone_id,
            {
                "label": "室外",
                "temp_delta": 0,
                "humidity_delta": 0,
                "species_bonus": {},
                "species_penalty": {},
                "is_outdoor": True,
            },
        )

    def species_zone_modifier(self, species: str, zone_id: str) -> float:
        """返回某物种在某 zone 的能量恢复倍率修正（1.0 = 中性）。"""
        mc = MICROCLIMATE_ZONES.get(zone_id)
        if mc is None:
            # 室外：基础 1.0
            return 1.0
        bonus = mc.get("species_bonus", {}).get(species, 0.0)
        penalty = mc.get("species_penalty", {}).get(species, 0.0)
        # 大厅：任何物种休息 +10%
        if mc.get("is_comfortable", False):
            bonus += 0.10
        return 1.0 + bonus + penalty

    def species_affinity(self, sp1: str, sp2: str) -> bool:
        """两个物种是否天生亲近（互助对）。"""
        return sp2 in SPECIES_AFFINITY.get(sp1, [])

    # ------------------------------------------------------------------
    # commit 29：生态事件
    # ------------------------------------------------------------------

    def tick_eco_events(self, now_ts: float) -> None:
        """每 tick 检查生态事件触发 + 清理过期事件。

        触发频率：每小时检查一次（除 inspiration 是按人的，由 tick 中处理）
        """
        # 1. 清理过期事件
        with self._lock:
            self.active_eco_events = [
                e for e in self.active_eco_events if now_ts < e.get("end_ts", 0)
            ]
        # 2. 每小时检查一次新事件
        if now_ts - self._last_eco_event_check < 3600:
            return
        self._last_eco_event_check = now_ts
        now = datetime.datetime.now()
        for ev_def in ECO_EVENTS:
            # 跳过 inspiration（在生命体 tick 中按人触发）
            if ev_def["name"] == "inspiration":
                continue
            # 季节限制
            if "season" in ev_def and ev_def["season"] != self.current_season():
                continue
            # 日期限制（大扫除日）
            if "day_of_month" in ev_def and now.day != ev_def["day_of_month"]:
                continue
            # 天气限制
            if "requires_weather" in ev_def:
                if self.current_weather != ev_def["requires_weather"]:
                    continue
            # 已经在活跃中？
            with self._lock:
                if any(e["name"] == ev_def["name"] for e in self.active_eco_events):
                    continue
            # 概率掷骰
            if random.random() < ev_def["probability"]:
                self._trigger_eco_event(ev_def, now_ts)

    def _trigger_eco_event(self, ev_def: dict, now_ts: float) -> None:
        """触发一个生态事件。"""
        ev = {
            "name": ev_def["name"],
            "label": ev_def["label"],
            "effect_type": ev_def["effect_type"],
            "start_ts": now_ts,
            "end_ts": now_ts + ev_def["duration_sec"],
        }
        with self._lock:
            self.active_eco_events.append(ev)
        self.broadcast_event(
            "eco_event",
            {
                "name": ev["name"],
                "label": ev["label"],
                "effect_type": ev["effect_type"],
                "duration_sec": ev_def["duration_sec"],
            },
        )
        # 记入今日事件统计
        self.eco_stats["events_today"].append(
            {
                "time": datetime.datetime.now().isoformat(),
                "name": ev["name"],
                "label": ev["label"],
            }
        )

    def trigger_inspiration(self, life_form) -> bool:
        """检查某个生命体是否触发"突然灵感"（5%/天/人 = 每小时 ~0.21%）。

        由生命体 tick 每小时调用一次。
        Returns:
            True 表示触发了灵感。
        """
        # 概率：5%/天/人，假设每天活跃 24 小时，每小时概率 ≈ 0.21%
        if random.random() < 0.0021:
            now_ts = datetime.datetime.now().timestamp()
            ev = {
                "name": "inspiration",
                "label": "突然灵感",
                "effect_type": "work_boost",
                "target": getattr(life_form, "_name_obj", "?"),
                "target_species": getattr(life_form, "species", "?"),
                "start_ts": now_ts,
                "end_ts": now_ts + 3600,
            }
            with self._lock:
                self.active_eco_events.append(ev)
            self.broadcast_event(
                "eco_event",
                {
                    "name": "inspiration",
                    "label": "突然灵感",
                    "effect_type": "work_boost",
                    "target": ev["target"],
                    "target_species": ev["target_species"],
                    "duration_sec": 3600,
                },
            )
            self.eco_stats["events_today"].append(
                {
                    "time": datetime.datetime.now().isoformat(),
                    "name": "inspiration",
                    "label": "突然灵感",
                    "target": ev["target"],
                }
            )
            return True
        return False

    def has_event_effect(self, effect_type: str, target: str | None = None) -> bool:
        """检查当前是否有某类效果的活跃事件。

        Args:
            effect_type: 效果类型（work_halt / work_boost / cleaning 等）
            target: 可选，指定目标个体名（仅 work_boost 这种个人事件需要）
        """
        with self._lock:
            for e in self.active_eco_events:
                if e.get("effect_type") != effect_type:
                    continue
                if target is not None and e.get("target") != target:
                    continue
                return True
        return False

    # ------------------------------------------------------------------
    # commit 29：生态数据统计
    # ------------------------------------------------------------------

    def _init_eco_stats(self) -> dict:
        """初始化生态统计数据结构。"""
        return {
            "food_peak": 0.0,  # 今日食物峰值
            "food_valley": 9999.0,  # 今日食物谷值
            "plant_total": 0.0,  # 今日植物生长总量
            "events_today": [],  # 今日触发的事件列表
            "outdoor_time": {},  # {species: 户外秒数}
            "indoor_time": {},  # {species: 室内秒数}
            "interaction_rank": [],  # 物种间互动次数排行
            "popular_zones": {},  # {zone_id: 累计停留秒数}
            "date": datetime.datetime.now().date().isoformat(),
        }

    def tick_eco_stats(self, now_ts: float) -> None:
        """每 tick 更新生态统计 + 每 24 小时滚动一次。"""
        # 每日滚动
        today = datetime.datetime.now().date().isoformat()
        if self.eco_stats.get("date") != today:
            # 跨日：重置日级统计
            self.eco_stats["food_peak"] = self.food_available
            self.eco_stats["food_valley"] = self.food_available
            self.eco_stats["plant_total"] = 0.0
            self.eco_stats["events_today"] = []
            self.eco_stats["outdoor_time"] = {}
            self.eco_stats["indoor_time"] = {}
            self.eco_stats["interaction_rank"] = []
            self.eco_stats["popular_zones"] = {}
            self.eco_stats["date"] = today
        # 更新峰谷
        with self._lock:
            self.eco_stats["food_peak"] = max(
                self.eco_stats["food_peak"], self.food_available
            )
            self.eco_stats["food_valley"] = min(
                self.eco_stats["food_valley"], self.food_available
            )
            # 累加植物生长总量
            self.eco_stats["plant_total"] += 0.5  # 估算值，与 regenerate 中 0.5 一致

    def record_zone_stay(
        self, zone_id: str, seconds: float, is_outdoor: bool, species: str
    ) -> None:
        """记录某物种在某 zone 停留的时间。"""
        with self._lock:
            self.eco_stats["popular_zones"][zone_id] = (
                self.eco_stats["popular_zones"].get(zone_id, 0) + seconds
            )
            key = species
            if is_outdoor:
                self.eco_stats["outdoor_time"][key] = (
                    self.eco_stats["outdoor_time"].get(key, 0) + seconds
                )
            else:
                self.eco_stats["indoor_time"][key] = (
                    self.eco_stats["indoor_time"].get(key, 0) + seconds
                )

    def record_interaction(self, sp1: str, sp2: str) -> None:
        """记录一次物种间互动。"""
        key = "-".join(sorted([sp1, sp2]))
        with self._lock:
            self.interaction_count[key] = self.interaction_count.get(key, 0) + 1

    # ------------------------------------------------------------------
    # commit 30：情感与关系系统支持
    # ------------------------------------------------------------------

    def record_relic(self, life_form, relic_def: dict) -> None:
        """记录一件遗物到环境（个体死亡时调用）。

        Args:
            life_form: 已故的 DigitalLifeForm 实例
            relic_def: {"name": str, "desc": str}
        """
        with self._lock:
            relic = {
                "time": time.time(),
                "owner": getattr(life_form, "_name_obj", "?"),
                "species": getattr(life_form, "species", "?"),
                "relic_name": relic_def.get("name", "遗物"),
                "desc": relic_def.get("desc", ""),
                "zone_id": getattr(life_form, "current_zone_id", ""),
                "age_days": getattr(life_form, "age", 0.0),
            }
            self.relics.append(relic)
            # 上限 50 件，超出删除最早的
            if len(self.relics) > 50:
                self.relics = self.relics[-50:]
        self.broadcast_event(
            "relic_added",
            {
                "owner": relic["owner"],
                "species": relic["species"],
                "relic_name": relic["relic_name"],
            },
        )

    def get_relics(self) -> list:
        """返回全部遗物列表（按时间倒序）。"""
        with self._lock:
            return list(reversed(self.relics))

    def record_relationship_event(
        self, event_type: str, a: str, b: str, extra: dict | None = None
    ) -> None:
        """记录一个关系事件（首次挚友/单恋被发现/关系破裂等）。

        Args:
            event_type: "became_friend" / "confession" / "cold_war" / "mentor_set" 等
            a: 当事方 A 名字
            b: 当事方 B 名字
            extra: 额外信息 dict
        """
        with self._lock:
            evt = {
                "time": time.time(),
                "type": event_type,
                "a": a,
                "b": b,
            }
            if extra:
                evt.update(extra)
            self.relationship_events.append(evt)
            if len(self.relationship_events) > 200:
                self.relationship_events = self.relationship_events[-200:]
        self.broadcast_event("relationship_event", evt)

    def get_relationship_events(self, limit: int = 20) -> list:
        """返回最近的关系事件。"""
        with self._lock:
            return list(reversed(self.relationship_events))[:limit]

    def push_dialogue_bubble(
        self, speaker: str, text: str, target: str = "", duration: float = 3.0
    ) -> int:
        """推送一条对话气泡到队列（前端 3 秒淡出）。

        Args:
            speaker: 说话者名字
            text: 气泡文本
            target: 听话者名字（空表示独白/广播）
            duration: 显示时长（秒）

        Returns:
            气泡 id（前端用此去重）
        """
        with self._lock:
            self._dialogue_seq += 1
            bid = self._dialogue_seq
            bubble = {
                "id": bid,
                "speaker": speaker,
                "text": text,
                "target": target,
                "expire_ts": time.time() + duration,
            }
            self.dialogue_bubbles.append(bubble)
            # 队列上限 30，超出删除最早的
            if len(self.dialogue_bubbles) > 30:
                self.dialogue_bubbles = self.dialogue_bubbles[-30:]
            return bid

    def pop_dialogue_bubbles(self) -> list:
        """取出当前所有未过期对话气泡，并清空队列（供 SSE 拉取）。"""
        now = time.time()
        with self._lock:
            live = [b for b in self.dialogue_bubbles if b["expire_ts"] > now]
            self.dialogue_bubbles = []
            return live

    # ------------------------------------------------------------------
    # commit 33：沉浸感三子系统调度（情感氛围 + 记忆碎片 + 自发社交）
    # ------------------------------------------------------------------

    def tick_immersive_systems(self, dt: float = 1.0, router=None) -> None:
        """每秒调用：更新三个沉浸感子系统（带节拍器分层调度）。

        节拍策略：
        - 每 tick（1s）：情感氛围、记忆碎片、自发社交、桌面宠物
        - 每 10 tick（10s）：持久记忆、疾病
        - 每 60 tick（60s）：日记、自传体记忆、工作产物
        """
        self._tick_counter += 1
        tc = self._tick_counter

        # 高频层：每 tick
        if True:
            self._call_subsystem(
                "atmosphere_system", "update_atmosphere", self.population, dt
            )
            self._call_subsystem("memory_fragment", "update_fragments", dt)
            self._call_subsystem("spontaneous_social", "update_social", dt)
            self._call_subsystem(
                "spontaneous_social",
                "scan_social",
                self.population,
                env=self,
                router=router,
            )
            self._call_subsystem("desktop_pet", "update_desktop_pet", self.population)

        # 中频层：每 10 tick
        if tc % 10 == 0:
            self._call_subsystem("persistent_memory", "tick_persistent_memory", dt)
            weather = getattr(self, "weather", "sunny")
            season = getattr(self, "season", "spring")
            ills = self._call_subsystem(
                "illness_system",
                "update_illness",
                self.population,
                dt,
                weather=weather,
                season=season,
            )
            ills = ills if isinstance(ills, list) else []
            for ev in ills:
                self.broadcast_event("illness_event", ev)
                if ev.get("type") in (
                    "rescue_needed",
                    "epidemic_start",
                    "rescue_failed",
                ):
                    self.push_active_message(
                        sender=ev.get("agent_name", "系统"),
                        sender_species=ev.get("species", ""),
                        text=self._format_illness_event_text(ev),
                        category="crisis_alert",
                        priority="high",
                    )

        # 低频层：每 60 tick
        if tc % 60 == 0:
            for mod, fn, kwargs in [
                ("autobiographical_memory", "tick_autobiography", {}),
                ("diary_system", "tick_diary", {}),
                ("work_artifacts", "tick_artifacts", {}),
            ]:
                evts = self._call_subsystem(
                    mod, fn, dt, population=self.population, router=router
                )
                for ev in evts or []:
                    self.broadcast_event(f"{mod.split('_')[0]}_event", ev)

    def _call_subsystem(self, module: str, func: str, *args, **kwargs) -> Any:
        """安全调用子系统函数，失败返回 None。"""
        try:
            mod = __import__(f"core.digital_life.{module}", fromlist=[func])
            fn = getattr(mod, func, None)
            if fn is None:
                return None
            return fn(*args, **kwargs)
        except Exception:
            # ponytail: bare except — 正式日志系统尚未接入
            # upgrade: 接入 logger.exception() 或 structured logging
            return None

    def _format_illness_event_text(self, ev: dict) -> str:
        """格式化疾病事件文本。"""
        t = ev.get("type", "")
        name = ev.get("agent_name", "")
        if t == "illness_onset":
            return f"{name} 生病了：{ev.get('label', '')}"
        if t == "illness_cured":
            return f"{name} 康复了：{ev.get('label', '')}（{ev.get('reason', '')}）"
        if t == "rescue_needed":
            return (
                f"急救警报！{name} 因 {ev.get('disease', '')} 濒危，请在 2 小时内急救！"
            )
        if t == "rescue_failed":
            return f"急救失败，{name} 已离世……"
        if t == "epidemic_start":
            return (
                f"疫情爆发：{ev.get('label', '')}，已 {ev.get('sick_count', 0)} 人感染"
            )
        if t == "epidemic_end":
            return f"疫情结束：{ev.get('label', '')} 已平息"
        if t == "memory_heartbreak":
            return f"{name} 翻阅旧记忆时触发了短暂心碎"
        return f"疾病事件：{t}"

    # ------------------------------------------------------------------
    # commit 31：主动消息系统
    # ------------------------------------------------------------------

    def push_active_message(
        self,
        sender: str,
        sender_species: str,
        text: str,
        category: str,
        priority: str = "low",
    ) -> bool:
        """推送一条智能体主动消息。

        全局速率限制：每小时最多 HOURLY_LIMIT 条。
        超出时不入队，但累加 _active_msg_pending_overflow。
        high 优先级消息（死亡/危机警报）不受速率限制。

        Args:
            sender: 发送者名字
            sender_species: 发送者物种
            text: 消息文本
            category: 消息类别（见 active_messaging.MESSAGE_CATEGORIES）
            priority: low / medium / high

        Returns:
            True 表示入队成功，False 表示被速率限制拦截
        """
        from core.digital_life.active_messaging import HOURLY_LIMIT

        now = time.time()
        with self._lock:
            # 每小时重置计数器
            if now - self._active_msg_hour_ts >= 3600:
                self._active_msg_hour_ts = now
                self._active_msg_hour_count = 0
                self._active_msg_pending_overflow = 0
            # 速率限制（high 优先级不受限）
            if priority != "high" and self._active_msg_hour_count >= HOURLY_LIMIT:
                self._active_msg_pending_overflow += 1
                return False
            self._active_msg_seq += 1
            msg = {
                "id": self._active_msg_seq,
                "sender": sender,
                "sender_species": sender_species,
                "text": text,
                "category": category,
                "priority": priority,
                "time": now,
            }
            self.active_messages.append(msg)
            # 队列上限 100，超出丢弃最早的
            if len(self.active_messages) > 100:
                self.active_messages = self.active_messages[-100:]
            self._active_msg_hour_count += 1
            return True

    def pop_active_messages(self) -> list:
        """取出所有待推送的主动消息并清空队列（供 SSE 拉取）。

        Returns:
            消息列表 [{id, sender, sender_species, text, category, priority, time}]
        """
        with self._lock:
            taken = list(self.active_messages)
            self.active_messages = []
            return taken

    def get_active_messages(self, limit: int = 50) -> list:
        """返回最近 N 条主动消息（不清空队列，供 /api/messages 查询）。"""
        with self._lock:
            return list(self.active_messages[-limit:])

    def emotional_status(self) -> dict:
        """commit 30：返回全体情感状态汇总（供 /api/emotions 端点）。

        Returns:
            {"employees": [{name, species, emotional_state, mood_score,
                            top_emotion, wisdom, tags}], "global": {...}}
        """
        with self._lock:
            pop = list(self.population)
        employees = []
        emo_sum = {
            "joy": 0,
            "sadness": 0,
            "anxiety": 0,
            "contentment": 0,
            "loneliness": 0,
            "curiosity": 0,
        }
        n = 0
        for lf in pop:
            if not getattr(lf, "_alive", False):
                continue
            try:
                emo = dict(getattr(lf, "emotional_state", {}))
                if not emo:
                    continue
                # 主导情感
                top = max(emo.items(), key=lambda x: x[1])[0] if emo else "neutral"
                employees.append(
                    {
                        "name": lf._name_obj,
                        "species": lf.species,
                        "emotional_state": {k: round(v, 2) for k, v in emo.items()},
                        "mood_score": round(getattr(lf, "mood_score", 50.0), 1),
                        "top_emotion": top,
                        "wisdom": round(getattr(lf, "wisdom", 0.0), 1),
                        "retirement_wish": getattr(lf, "retirement_wish", ""),
                        "wish_fulfilled": getattr(lf, "wish_fulfilled", False),
                        "tags": [
                            {"target": tid, "tags": list(ts)}
                            for tid, ts in (
                                getattr(lf, "relationship_tags", {}) or {}
                            ).items()
                            if ts
                        ],
                    }
                )
                for k in emo_sum:
                    emo_sum[k] += emo.get(k, 0)
                n += 1
            except Exception:
                continue
        global_emo = {k: round(v / n, 2) for k, v in emo_sum.items()} if n > 0 else {}
        return {"employees": employees, "global": global_emo, "count": n}

    def relationship_network(self) -> dict:
        """commit 30：返回关系网络简图（供前端绘制）。

        Returns:
            {"nodes": [{id, name, species}], "edges": [{a, b, tags, affection, trust}]}
        """
        with self._lock:
            pop = list(self.population)
        nodes = []
        edges = []
        seen_pairs = set()
        for lf in pop:
            if not getattr(lf, "_alive", False):
                continue
            nodes.append(
                {
                    "id": lf._name_obj,
                    "name": lf._name_obj,
                    "species": lf.species,
                }
            )
            rels = getattr(lf, "relationships", {}) or {}
            tags_map = getattr(lf, "relationship_tags", {}) or {}
            for other_id, rel in rels.items():
                pair_key = tuple(sorted([lf._name_obj, other_id]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                # 只输出有显著关系的边（任一维度 > 0.5 或有标签）
                tags = tags_map.get(other_id, [])
                if not tags and max(rel.values(), default=0) < 0.5:
                    continue
                edges.append(
                    {
                        "a": lf._name_obj,
                        "b": other_id,
                        "tags": list(tags),
                        "affection": round(rel.get("affection", 0), 2),
                        "trust": round(rel.get("trust", 0), 2),
                        "respect": round(rel.get("respect", 0), 2),
                        "familiarity": round(rel.get("familiarity", 0), 2),
                    }
                )
        return {"nodes": nodes, "edges": edges}

    def eco_status(self) -> dict:
        """返回生态数据完整状态。"""
        with self._lock:
            # 互动排行（按次数降序，前 10）
            inter_rank = sorted(self.interaction_count.items(), key=lambda x: -x[1])[
                :10
            ]
            # 区域热度排行
            zone_rank = sorted(
                self.eco_stats.get("popular_zones", {}).items(), key=lambda x: -x[1]
            )[:10]
            return {
                "plant_biomass": round(self.plant_biomass, 1),
                "insect_count": self.insect_count,
                "weather": self.current_weather,
                "weather_label": WEATHER_TYPES.get(self.current_weather, {}).get(
                    "label", ""
                ),
                "weather_info": self.weather_info(),
                "active_eco_events": [
                    {
                        "name": e["name"],
                        "label": e["label"],
                        "effect_type": e.get("effect_type"),
                        "target": e.get("target"),
                        "remaining_sec": max(
                            0,
                            int(
                                e.get("end_ts", 0) - datetime.datetime.now().timestamp()
                            ),
                        ),
                    }
                    for e in self.active_eco_events
                ],
                "eco_stats": {
                    "date": self.eco_stats.get("date"),
                    "food_peak": round(self.eco_stats.get("food_peak", 0), 1),
                    "food_valley": round(self.eco_stats.get("food_valley", 0), 1),
                    "plant_total": round(self.eco_stats.get("plant_total", 0), 1),
                    "events_today": list(self.eco_stats.get("events_today", []))[-20:],
                    "outdoor_time": dict(self.eco_stats.get("outdoor_time", {})),
                    "indoor_time": dict(self.eco_stats.get("indoor_time", {})),
                    "interaction_rank": [
                        {"pair": k, "count": v} for k, v in inter_rank
                    ],
                    "popular_zones": [{"zone": k, "seconds": v} for k, v in zone_rank],
                },
            }

    # ------------------------------------------------------------------
    # 事件日志
    # ------------------------------------------------------------------

    def broadcast_event(self, event_type: str, data: dict | None = None) -> None:
        """记录一条事件到 event_log。

        格式：{"time": ISO字符串, "type": event_type, "data": {...}}
        """
        with self._lock:
            self.event_log.append(
                {
                    "time": datetime.datetime.now().isoformat(),
                    "type": event_type,
                    "data": dict(data) if data else {},
                }
            )

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def population_status(self) -> dict:
        """按物种/性别/阶段分组统计。"""
        with self._lock:
            by_species: dict[str, int] = {}
            by_gender: dict[str, int] = {}
            by_stage: dict[str, int] = {}
            alive_count = 0
            for lf in self.population:
                sp = getattr(lf, "species", "unknown")
                gd = getattr(lf, "gender", "unknown")
                st = getattr(lf, "life_stage", None)
                stage_val = st.value if st is not None else "unknown"
                by_species[sp] = by_species.get(sp, 0) + 1
                by_gender[gd] = by_gender.get(gd, 0) + 1
                by_stage[stage_val] = by_stage.get(stage_val, 0) + 1
                if getattr(lf, "_alive", False):
                    alive_count += 1
            return {
                "total": len(self.population),
                "alive": alive_count,
                "by_species": by_species,
                "by_gender": by_gender,
                "by_stage": by_stage,
            }

    def status(self) -> dict:
        """完整环境状态。"""
        with self._lock:
            return {
                "food_available": round(self.food_available, 3),
                "population_count": len(self.population),
                "event_log_size": len(self.event_log),
                "death_log_size": len(self.death_log),
                "birth_log_size": len(self.birth_log),
                "season": self.current_season(),
                "population_status": self.population_status(),
                # commit 29：生态数据
                "plant_biomass": round(self.plant_biomass, 1),
                "insect_count": self.insect_count,
                "weather": self.current_weather,
                "weather_label": WEATHER_TYPES.get(self.current_weather, {}).get(
                    "label", ""
                ),
            }

    # ------------------------------------------------------------------
    # 调试：清空所有共享状态（仅测试使用）
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """重置环境到初始状态（仅供测试）。"""
        with self._lock:
            self.food_available = 1000.0
            self.population = []
            self.event_log = deque(maxlen=1000)
            self.death_log = []
            self.birth_log = []
            # commit 29：重置生态状态
            self.plant_biomass = 500.0
            self.insect_count = 50
            self.current_weather = "sunny"
            self.weather_changed_at = 0.0
            self._last_weather_check = 0.0
            self._last_eco_event_check = 0.0
            self.active_eco_events = []
            self.eco_stats = self._init_eco_stats()
            self.zone_occupancy = {}
            self.interaction_count = {}
            self._last_stats_rollover = 0.0
