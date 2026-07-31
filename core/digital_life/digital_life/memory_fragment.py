"""commit 33：记忆碎片实体化系统。

零基础读者可以这样理解：
- 当发生重要事件（情感峰值、首次挚友、入职周年、死亡）时，
  在事件发生地凝结出一个发光的像素碎片。
- 碎片缓慢上下浮动，监工走到旁边（距离 < 2 格）它会变亮靠近。
- 点击碎片，弹出回忆面板，显示 2-3 句话的记忆文本 + 时间戳 + 相关智能体。
- 普通碎片存活 7 天，遗物碎片永久存在，收藏的碎片永久保存到回忆录。

设计要点：
1. 单例 MemoryFragmentSystem，全局管理所有碎片。
2. 碎片数据结构含：id, type, x, y, color, text, agent_name, agent_species, time, expire_ts, collected。
3. 同一区域最多 5 个碎片，超过则最旧的提前消散。
4. 碎片文本可由 LLM 生成（可选），降级为预置模板。
5. 资料库联动：遗物碎片缓慢飘向 raven zone（资料库）。
"""
from __future__ import annotations

import random
import threading
import time

# ====================================================================
# 碎片类型 → 颜色
# ====================================================================
# type: emotion_peak / friendship / milestone / death_relic / supervisor_chat
FRAGMENT_COLORS: dict[str, str] = {
    "emotion_peak_joy":    "rgba(255,196,87,0.9)",   # 金色
    "emotion_peak_sadness": "rgba(130,170,230,0.9)",  # 淡蓝
    "emotion_peak_anxiety": "rgba(180,180,200,0.9)",  # 灰蓝
    "friendship":          "rgba(255,150,180,0.9)",   # 粉色（友情/爱情）
    "milestone":           "rgba(140,210,150,0.9)",   # 绿色（成就）
    "death_relic":         "rgba(255,255,255,0.95)",  # 白色带彩虹边
    "supervisor_chat":     "rgba(200,150,220,0.9)",   # 紫色
    "social_dialogue":     "rgba(255,200,150,0.85)",  # 橙色（自发社交）
}

# 默认存活时间（秒）
NORMAL_LIFETIME = 7 * 86400  # 7 天
RELIC_LIFETIME = -1  # 永久

# 单区域上限
MAX_PER_ZONE = 5


# ====================================================================
# 预置记忆文本模板
# ====================================================================
FRAGMENT_TEXT_TEMPLATES: dict[str, list[str]] = {
    "emotion_peak_joy": [
        "{name} 在这里感受到了纯粹的快乐。{detail}",
        "某个瞬间，{name} 心中满是欢喜。{detail}",
        "快乐的情绪在 {name} 心中绽放，久久不散。{detail}",
    ],
    "emotion_peak_sadness": [
        "{name} 在这里留下了悲伤的痕迹。{detail}",
        "空气中似乎还残留着 {name} 的低落。{detail}",
        "{name} 一度非常难过。{detail}",
    ],
    "emotion_peak_anxiety": [
        "{name} 在这里感到不安与紧张。{detail}",
        "焦虑曾笼罩着 {name}。{detail}",
    ],
    "friendship": [
        "{name} 与 {detail} 在这里成为了挚友。",
        "一段新的友谊在 {name} 与 {detail} 之间萌芽。",
        "{name} 与 {detail} 的关系在这里迈上新台阶。",
    ],
    "milestone": [
        "{name} 达成了一个里程碑：{detail}",
        "值得纪念的时刻——{name} {detail}",
    ],
    "death_relic": [
        "{name}（{detail}）在这里走完了最后一程。愿它的灵魂安息。",
        "{name} 在此长眠。{detail}",
        "这里留下了 {name} 最后的气息。{detail}",
    ],
    "supervisor_chat": [
        "监工与 {name} 在这里有一次难忘的对话。{detail}",
        "{name} 与监工的交流让它印象深刻。{detail}",
    ],
    "social_dialogue": [
        "{name} 与 {detail} 在这里有过一段精彩的对话。",
        "这里曾回荡着 {name} 与 {detail} 的笑声与拌嘴。",
    ],
}


def pick_fragment_text(frag_type: str, name: str, detail: str = "") -> str:
    """从模板库随机选一条文本。"""
    templates = FRAGMENT_TEXT_TEMPLATES.get(frag_type, ["{name} 留下了一段记忆。"])
    tpl = random.choice(templates)
    try:
        return tpl.format(name=name, detail=detail)
    except Exception:
        return tpl


# ====================================================================
# 碎片对象
# ====================================================================
class MemoryFragment:
    __slots__ = (
        "agent_name",
        "agent_species",
        "collected",
        "color",
        "expire_ts",
        "float_phase",
        "id",
        "is_relic",
        "related_agent_name",
        "text",
        "time",
        "type",
        "x",
        "y",
        "zone_id",
    )

    def __init__(self, frag_id: int, frag_type: str, x: float, y: float,
                 zone_id: str, color: str, text: str,
                 agent_name: str, agent_species: str,
                 is_relic: bool = False,
                 related_agent_name: str = ""):
        self.id = frag_id
        self.type = frag_type
        self.x = x
        self.y = y
        self.zone_id = zone_id
        self.color = color
        self.text = text
        self.agent_name = agent_name
        self.agent_species = agent_species
        self.time = time.time()
        self.expire_ts = self.time + (RELIC_LIFETIME if is_relic else NORMAL_LIFETIME)
        self.collected = False
        self.float_phase = random.random() * math.pi * 2  # 浮动相位
        self.is_relic = is_relic
        self.related_agent_name = related_agent_name

    def is_expired(self, now: float) -> bool:
        """是否已过期。"""
        if self.is_relic:
            return False
        return now > self.expire_ts

    def to_dict(self) -> dict:
        """转为前端可序列化 dict。"""
        return {
            "id": self.id,
            "type": self.type,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "zone_id": self.zone_id,
            "color": self.color,
            "text": self.text,
            "agent_name": self.agent_name,
            "agent_species": self.agent_species,
            "time": self.time,
            "expire_ts": self.expire_ts,
            "collected": self.collected,
            "is_relic": self.is_relic,
            "related_agent_name": self.related_agent_name,
        }


# 延迟 import math
import math

# ====================================================================
# MemoryFragmentSystem 单例
# ====================================================================

class MemoryFragmentSystem:
    """记忆碎片系统（单例）。"""

    _instance: MemoryFragmentSystem | None = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> MemoryFragmentSystem:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._init_once()
                    cls._instance = obj
        return cls._instance

    def _init_once(self) -> None:
        self._lock = threading.RLock()
        self._fragments: list[MemoryFragment] = []
        self._next_id: int = 1
        # 监工回忆录（收藏的碎片）
        self._memoir: list[dict] = []
        # 设置
        self._settings: dict = {
            "density": "medium",  # low/medium/high
        }
        # 密度上限
        self._density_max = {"low": 30, "medium": 80, "high": 150}

    # ---------------- 设置 ----------------

    def update_settings(self, settings: dict) -> None:
        with self._lock:
            for k, v in settings.items():
                if k in self._settings:
                    self._settings[k] = v

    def get_settings(self) -> dict:
        return dict(self._settings)

    # ---------------- 生成碎片 ----------------

    def spawn(self, frag_type: str, x: float, y: float, zone_id: str,
              agent_name: str, agent_species: str,
              text: str | None = None,
              detail: str = "",
              related_agent_name: str = "",
              is_relic: bool = False) -> int | None:
        """生成一个记忆碎片。

        Args:
            frag_type: 碎片类型（见 FRAGMENT_COLORS）
            x, y: 世界坐标
            zone_id: 区域 id
            agent_name: 相关智能体名
            agent_species: 相关智能体物种
            text: 自定义文本（None 则从模板选）
            detail: 细节描述（用于模板填充）
            related_agent_name: 关联的另一个智能体名（如挚友事件）
            is_relic: 是否遗物碎片（永久存在）

        Returns:
            碎片 id（生成失败返回 None）
        """
        # 密度限制
        max_total = self._density_max.get(self._settings["density"], 80)
        with self._lock:
            if len(self._fragments) >= max_total:
                # 移除最旧的非遗物碎片
                non_relic = [f for f in self._fragments if not f.is_relic]
                if non_relic:
                    non_relic.sort(key=lambda f: f.time)
                    self._fragments.remove(non_relic[0])
                else:
                    return None  # 全是遗物，无法腾位

            # 单区域上限 5 个
            zone_count = sum(1 for f in self._fragments if f.zone_id == zone_id and not f.is_relic)
            if zone_count >= MAX_PER_ZONE and not is_relic:
                # 移除该区域最旧的非遗物
                zone_frags = [f for f in self._fragments if f.zone_id == zone_id and not f.is_relic]
                if zone_frags:
                    zone_frags.sort(key=lambda f: f.time)
                    self._fragments.remove(zone_frags[0])

            color = FRAGMENT_COLORS.get(frag_type, "rgba(200,200,200,0.8)")
            if text is None:
                text = pick_fragment_text(frag_type, agent_name, detail)

            frag = MemoryFragment(
                frag_id=self._next_id,
                frag_type=frag_type,
                x=x, y=y, zone_id=zone_id,
                color=color, text=text,
                agent_name=agent_name, agent_species=agent_species,
                is_relic=is_relic,
                related_agent_name=related_agent_name,
            )
            self._next_id += 1
            self._fragments.append(frag)
            return frag.id

    # ---------------- 碎片交互 ----------------

    def get_nearby(self, x: float, y: float, radius: float = 2.0) -> list[dict]:
        """获取距离 (x, y) < radius 的所有碎片（供监工拾取）。"""
        with self._lock:
            result = []
            for f in self._fragments:
                dist = ((f.x - x) ** 2 + (f.y - y) ** 2) ** 0.5
                if dist < radius:
                    result.append(f.to_dict())
            return result

    def get_fragment(self, frag_id: int) -> dict | None:
        """获取单个碎片详情（点击回放时调用）。"""
        with self._lock:
            for f in self._fragments:
                if f.id == frag_id:
                    return f.to_dict()
            # 也查回忆录
            for m in self._memoir:
                if m.get("id") == frag_id:
                    return m
            return None

    def collect(self, frag_id: int) -> bool:
        """收藏碎片到监工回忆录。"""
        with self._lock:
            for f in self._fragments:
                if f.id == frag_id and not f.collected:
                    f.collected = True
                    self._memoir.append(f.to_dict())
                    # commit 34 联动 3：翻阅遗物/悲伤碎片 → 触发附近智能体的心碎
                    self._trigger_memory_heartbreak_if_applicable(f)
                    return True
            return False

    def _trigger_memory_heartbreak_if_applicable(self, frag) -> None:
        """翻阅旧记忆触发短暂心碎（联动：记忆 → 生病）。

        触发条件：
        - 碎片类型是 death_relic 或 emotion_peak_sadness
        - 找到该碎片相关智能体（如果还活着）
        - 2% 概率触发 2 小时短暂心碎
        """
        try:
            if frag.type not in ("death_relic", "emotion_peak_sadness", "friendship"):
                return
            # 找到 environment 中的相关智能体
            from core.digital_life.environment import Environment
            env = Environment()
            # 找到该 agent_name 对应的存活智能体
            target = None
            for lf in env.population:
                if (getattr(lf, "_alive", True)
                        and getattr(lf, "_name_obj", "") == frag.agent_name):
                    target = lf
                    break
            if target is None:
                return
            # 调用 illness_system 的 memory heartbreak
            from core.digital_life.illness_system import get_illness_system
            get_illness_system().trigger_memory_heartbreak(target)
        except Exception:
            pass

    def get_memoir(self) -> list[dict]:
        """返回监工回忆录（收藏的碎片列表）。"""
        with self._lock:
            return list(self._memoir)

    # ---------------- 生命周期更新 ----------------

    def update(self, dt: float = 1.0) -> None:
        """每秒调用：清理过期碎片 + 遗物飘移到资料库。"""
        now = time.time()
        with self._lock:
            # 清理过期
            self._fragments = [f for f in self._fragments if not f.is_expired(now)]
            # 遗物缓慢飘向资料库（raven zone）
            # 简化处理：遗物每秒向 (60, 5)（资料库位置）移动 0.02 格
            for f in self._fragments:
                if f.is_relic and f.zone_id != "raven":
                    target_x, target_y = 60.0, 5.0
                    dx = target_x - f.x
                    dy = target_y - f.y
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist > 0.5:
                        f.x += (dx / dist) * 0.02
                        f.y += (dy / dist) * 0.02
                    else:
                        f.zone_id = "raven"

    # ---------------- 渲染数据 ----------------

    def snapshot(self) -> dict:
        """生成前端渲染数据。"""
        with self._lock:
            return {
                "fragments": [f.to_dict() for f in self._fragments],
                "memoir_count": len(self._memoir),
                "settings": dict(self._settings),
            }


# ====================================================================
# 模块级便捷函数
# ====================================================================

_singleton: MemoryFragmentSystem | None = None


def get_fragments() -> MemoryFragmentSystem:
    global _singleton
    if _singleton is None:
        _singleton = MemoryFragmentSystem()
    return _singleton


def spawn_fragment(frag_type: str, x: float, y: float, zone_id: str,
                   agent_name: str, agent_species: str,
                   text: str | None = None, detail: str = "",
                   related_agent_name: str = "",
                   is_relic: bool = False) -> int | None:
    """便捷接口：生成碎片。"""
    try:
        return get_fragments().spawn(
            frag_type, x, y, zone_id, agent_name, agent_species,
            text, detail, related_agent_name, is_relic,
        )
    except Exception:
        return None


def update_fragments(dt: float = 1.0) -> None:
    try:
        get_fragments().update(dt)
    except Exception:
        pass


def snapshot_fragments() -> dict:
    try:
        return get_fragments().snapshot()
    except Exception:
        return {"fragments": [], "memoir_count": 0, "settings": {}}
