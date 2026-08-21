"""commit 35：长期自传体记忆与自我反思系统。

零基础读者可以这样理解：
- 普通记忆只是"存了什么事件"，自传体记忆是智能体"理解"自己经历过什么
- 每周一次"周反思"：回顾本周关键事件，思考对自己的意义，写成自我叙事
- 长期积累形成"自我认知"：我是什么样的人 / 我看重什么 / 我的目标 / 我的内心矛盾
- 临终前生成"临终自传"：回顾一生关键节点 + 对监工说最后一句话 + 遗愿

文件存储路径：data/memory/{agent_id}_autobiography.json
"""

from __future__ import annotations

import datetime
import json
import os
import random
import threading
import time
from typing import Any

# ruff: noqa: S110

# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------

AUTOBIO_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "memory",
)

WEEKLY_REFLECT_INTERVAL = 7 * 86400  # 每周一次反思
MEMORY_TIDY_INTERVAL = 4 * 3600  # 每 4 小时尝试一次"记忆整理"
DEATH_REFLECT_HEALTH = 10  # 健康低于此值 → 触发临终自传
DEATH_REFLECT_AGE_RATIO = 0.95  # 年龄超过最大寿命 95% → 触发


# ----------------------------------------------------------------------
# 自我认知数据结构
# ----------------------------------------------------------------------

DEFAULT_SELF_COGNITION: dict = {
    "self_description": "",  # 一句话描述自己
    "values": "",  # 看重什么
    "life_goal": "",  # 当前人生目标
    "contradiction": "",  # 内心矛盾
    "updated_ts": 0.0,
}

# 物种默认的初始自我描述模板（在 LLM 不可用时降级）
SPECIES_DEFAULT_COGNITION: dict[str, dict] = {
    "deer": {
        "self_description": "我是鹿，森林公司的调度中枢，认真负责",
        "values": "团队的协调比个人功劳重要",
        "life_goal": "让森林公司平稳运转",
        "contradiction": "想严管纪律，又不忍苛责同事",
    },
    "squirrel": {
        "self_description": "我是松鼠程序员，写代码像囤松果一样认真",
        "values": "代码的简洁比炫技更重要",
        "life_goal": "成为全公司最可靠的后端",
        "contradiction": "想被监工关注，又不想显得太粘人",
    },
    "butterfly": {
        "self_description": "我是蝶，花房的色彩魔法师",
        "values": "美的事物值得被认真对待",
        "life_goal": "调出一种被所有人记住的颜色",
        "contradiction": "想特立独行，又怕被孤立",
    },
    "fox": {
        "self_description": "我是狐，挑剔但善良的测试工程师",
        "values": "真正的关心是指出问题",
        "life_goal": "找出那个谁都没发现的隐患",
        "contradiction": "嘴巴毒但心软，怕伤到同事",
    },
    "hedgehog": {
        "self_description": "我是猬，公司最忠诚的守卫",
        "values": "安全永远是第一位的",
        "life_goal": "守住森林公司的每一道门",
        "contradiction": "想被理解，又习惯竖起刺",
    },
    "beaver": {
        "self_description": "我是狸，默默修补一切的工程师",
        "values": "行动比言语更有力",
        "life_goal": "建一座永远不会被冲垮的水坝",
        "contradiction": "想被看见，又习惯躲在幕后",
    },
    "raven": {
        "self_description": "我是鸦，森林的记忆保管员",
        "values": "被记住的生命才算真正活过",
        "life_goal": "把每一段值得记的故事都留下",
        "contradiction": "见证太多离别，却无法阻止",
    },
    "hare": {
        "self_description": "我是兔，精打细算的资源管家",
        "values": "未雨绸缪胜过亡羊补牢",
        "life_goal": "让森林公司永远不缺 token 和坚果",
        "contradiction": "想大方待人，又怕资源不够",
    },
    "badger": {
        "self_description": "我是獾，挖通所有阻隔的地道工程师",
        "values": "路是人挖出来的",
        "life_goal": "把森林公司的地道连成一张网",
        "contradiction": "喜欢独处，又怕被遗忘",
    },
    "lark": {
        "self_description": "我是雀，黎明即起的监控员",
        "values": "早起的鸟儿有虫吃",
        "life_goal": "做森林公司第一个发现异常的人",
        "contradiction": "想被依赖，又想自由飞翔",
    },
    "kite": {
        "self_description": "我是鸢，高空俯瞰一切的巡视员",
        "values": "视野决定格局",
        "life_goal": "守好森林的天空",
        "contradiction": "想飞得更高，又舍不得这片森林",
    },
}


# ----------------------------------------------------------------------
# 反思文本生成（LLM 不可用时降级模板）
# ----------------------------------------------------------------------

WEEKLY_REFLECT_PROMPT_TEMPLATE: str = """你是 BlueDeer 森林公司的智能体 {name}（物种：{species}）。
这是你本周的反思时间。请回顾本周关键事件并写一段自我叙事。

本周事件摘要：{events}
本周情绪：主导情感 {top_emotion}，平均心情 {mood_score}
本周与监工互动次数：{interact_count}

要求：
1. 用第一人称，100-200 字
2. 不是罗列事件，而是理解它们对你的意义
3. 可以提及同事、监工、自己的成长
4. 末尾可加一句对下周的期待或担忧
5. 只输出反思内容，不要标题、不要署名
"""

DEATH_AUTOBIO_PROMPT_TEMPLATE: str = """你是 BlueDeer 森林公司的智能体 {name}（物种：{species}）。
你预感到生命即将走到尽头。请写下你的临终自传。

一生关键节点：{life_events}
最亲密的同事：{closest_friend}
对监工的好感度：{fondness}/100

请包含：
1. 一段简短的人生回顾（150-250 字）
2. 对监工说最后一句话（30 字以内）
3. 对最亲密同事说最后一句话（30 字以内）
4. 一个遗愿（30 字以内）

格式：
[回顾] ...
[对监工] ...
[对同事] ...
[遗愿] ...
"""


def _build_weekly_prompt(
    name: str,
    species: str,
    events: str,
    top_emotion: str,
    mood_score: float,
    interact_count: int,
) -> str:
    return WEEKLY_REFLECT_PROMPT_TEMPLATE.format(
        name=name,
        species=species,
        events=events or "（无明显事件）",
        top_emotion=top_emotion,
        mood_score=mood_score,
        interact_count=interact_count,
    )


def _build_death_prompt(
    name: str, species: str, life_events: str, closest_friend: str, fondness: float
) -> str:
    return DEATH_AUTOBIO_PROMPT_TEMPLATE.format(
        name=name,
        species=species,
        life_events=life_events or "（一生平凡但温暖）",
        closest_friend=closest_friend or "（无特别亲密的同事）",
        fondness=fondness,
    )


# ----------------------------------------------------------------------
# 单个智能体的自传体记忆
# ----------------------------------------------------------------------


class AgentAutobiography:
    """一个智能体的自传体记忆 + 自我认知。"""

    __slots__ = (
        "_dirty",
        "_lock",
        "agent_id",
        "agent_name",
        "death_autobio",
        "last_reflect_ts",
        "last_tidy_ts",
        "self_cognition",
        "species",
        "weekly_reflections",
    )

    def __init__(self, agent_id: str, agent_name: str = "", species: str = "") -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.species = species
        self.weekly_reflections: list[dict] = []  # 每周反思记录
        self.self_cognition: dict = dict(DEFAULT_SELF_COGNITION)
        self.death_autobio: dict | None = None  # 临终自传（生成后定格）
        self._lock = threading.RLock()
        self._dirty = False
        self.last_reflect_ts: float = 0.0
        self.last_tidy_ts: float = 0.0

    # ---------------- 文件路径 ----------------

    def _path(self) -> str:
        return os.path.join(AUTOBIO_DIR, f"{self.agent_id}_autobiography.json")

    # ---------------- 加载 / 保存 ----------------

    def load(self) -> None:
        os.makedirs(AUTOBIO_DIR, exist_ok=True)
        with self._lock:
            try:
                with open(self._path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.weekly_reflections = data.get("weekly_reflections", [])
                self.self_cognition = data.get(
                    "self_cognition", dict(DEFAULT_SELF_COGNITION)
                )
                self.death_autobio = data.get("death_autobio")
                if data.get("agent_name"):
                    self.agent_name = data["agent_name"]
                if data.get("species"):
                    self.species = data["species"]
                self.last_reflect_ts = float(data.get("last_reflect_ts", 0.0))
                self.last_tidy_ts = float(data.get("last_tidy_ts", 0.0))
            except (FileNotFoundError, json.JSONDecodeError):
                # 首次创建：用物种默认认知
                default = SPECIES_DEFAULT_COGNITION.get(self.species, {})
                if default:
                    self.self_cognition = {
                        "self_description": default.get("self_description", ""),
                        "values": default.get("values", ""),
                        "life_goal": default.get("life_goal", ""),
                        "contradiction": default.get("contradiction", ""),
                        "updated_ts": time.time(),
                    }
                    self._dirty = True
            self._dirty = False

    def save(self) -> None:
        os.makedirs(AUTOBIO_DIR, exist_ok=True)
        with self._lock:
            if not self._dirty:
                return
            try:
                payload = {
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "species": self.species,
                    "weekly_reflections": self.weekly_reflections,
                    "self_cognition": self.self_cognition,
                    "death_autobio": self.death_autobio,
                    "last_reflect_ts": self.last_reflect_ts,
                    "last_tidy_ts": self.last_tidy_ts,
                }
                tmp = self._path() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._path())
                self._dirty = False
            except Exception:
                pass

    # ---------------- 周反思 ----------------

    def add_weekly_reflection(
        self, text: str, week_start: float, events_summary: str = ""
    ) -> None:
        with self._lock:
            entry = {
                "text": text,
                "week_start": week_start,
                "week_end": time.time(),
                "events_summary": events_summary,
                "ts": time.time(),
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.weekly_reflections.append(entry)
            # 保留最近 52 周（一年）
            if len(self.weekly_reflections) > 52:
                del self.weekly_reflections[: len(self.weekly_reflections) - 52]
            self.last_reflect_ts = time.time()
            self._dirty = True

    # ---------------- 自我认知更新 ----------------

    def update_self_cognition(
        self,
        description: str = "",
        values: str = "",
        life_goal: str = "",
        contradiction: str = "",
    ) -> None:
        with self._lock:
            if description:
                self.self_cognition["self_description"] = description
            if values:
                self.self_cognition["values"] = values
            if life_goal:
                self.self_cognition["life_goal"] = life_goal
            if contradiction:
                self.self_cognition["contradiction"] = contradiction
            self.self_cognition["updated_ts"] = time.time()
            self._dirty = True

    # ---------------- 临终自传 ----------------

    def set_death_autobio(
        self, review: str, to_supervisor: str, to_friend: str, last_wish: str
    ) -> None:
        with self._lock:
            self.death_autobio = {
                "review": review,
                "to_supervisor": to_supervisor,
                "to_friend": to_friend,
                "last_wish": last_wish,
                "ts": time.time(),
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._dirty = True

    # ---------------- 序列化 ----------------

    def to_dict(self, include_full: bool = True) -> dict:
        with self._lock:
            data = {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "species": self.species,
                "self_cognition": dict(self.self_cognition),
                "weekly_count": len(self.weekly_reflections),
                "has_death_autobio": self.death_autobio is not None,
                "last_reflect_ts": self.last_reflect_ts,
            }
            if include_full:
                data["weekly_reflections"] = list(
                    self.weekly_reflections[-8:]
                )  # 最近 8 周
                data["death_autobio"] = self.death_autobio
            return data


# ----------------------------------------------------------------------
# 全局管理器（单例）
# ----------------------------------------------------------------------


class AutobiographyManager:
    _instance: AutobiographyManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._store: dict[str, AgentAutobiography] = {}
        self._lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> AutobiographyManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_or_create(
        self, agent_id: str, agent_name: str = "", species: str = ""
    ) -> AgentAutobiography:
        with self._lock:
            if agent_id not in self._store:
                bio = AgentAutobiography(agent_id, agent_name, species)
                bio.load()
                self._store[agent_id] = bio
            else:
                if agent_name and self._store[agent_id].agent_name != agent_name:
                    self._store[agent_id].agent_name = agent_name
                    self._store[agent_id]._dirty = True
                if species and self._store[agent_id].species != species:
                    self._store[agent_id].species = species
                    self._store[agent_id]._dirty = True
            return self._store[agent_id]

    def load_all(self, agents: list[dict]) -> int:
        count = 0
        for a in agents:
            self.get_or_create(a["id"], a.get("name", ""), a.get("species", ""))
            count += 1
        return count

    def save_all(self) -> int:
        count = 0
        with self._lock:
            for bio in self._store.values():
                bio.save()
                count += 1
        return count

    def get_all_summary(self) -> list[dict]:
        with self._lock:
            return [bio.to_dict(include_full=False) for bio in self._store.values()]

    def get_agent(self, agent_id: str) -> dict | None:
        bio = self._store.get(agent_id)
        if bio is None:
            return None
        return bio.to_dict(include_full=True)

    # ---------------- 周反思触发 ----------------

    def maybe_weekly_reflect(self, agent: Any, router: Any = None) -> str | None:
        """检查并触发周反思。返回反思文本（None 表示未触发）。"""
        if agent is None or not getattr(agent, "_alive", False):
            return None
        agent_id = agent.get_agent_id()
        bio = self.get_or_create(
            agent_id,
            agent_name=getattr(agent, "_name_obj", ""),
            species=getattr(agent, "species", ""),
        )
        now = time.time()
        if now - bio.last_reflect_ts < WEEKLY_REFLECT_INTERVAL:
            return None

        # 收集本周关键事件（从持久记忆长期摘要中取最近 7 天）
        events_summary = _collect_week_events(agent)
        emo = getattr(agent, "emotional_state", {})
        top_e = max(emo.items(), key=lambda x: x[1])[0] if emo else "neutral"
        mood = getattr(agent, "mood_score", 50.0)
        interact = getattr(agent, "_last_supervisor_interact_ts", 0.0)
        interact_count = 1 if now - interact < 7 * 86400 else 0

        prompt = _build_weekly_prompt(
            name=getattr(agent, "_name_obj", ""),
            species=getattr(agent, "species", ""),
            events=events_summary,
            top_emotion=top_e,
            mood_score=mood,
            interact_count=interact_count,
        )

        text = None
        if router is not None:
            text = _generate_via_llm(router, prompt)
        if not text:
            text = _fallback_weekly_reflect(agent, events_summary, top_e)

        # 周开始时间：7 天前
        week_start = now - 7 * 86400
        bio.add_weekly_reflection(text, week_start, events_summary)

        # 偶尔更新自我认知（30% 概率，避免每周变化）
        if random.random() < 0.3:
            _maybe_evolve_self_cognition(agent, bio, text)

        # 联动 1：周反思引用日记 → 写入持久记忆核心事件
        try:
            from core.digital_life.persistent_memory import get_memory_manager

            mem = get_memory_manager().get_or_create(
                agent_id,
                agent_name=getattr(agent, "_name_obj", ""),
                species=getattr(agent, "species", ""),
            )
            mem.add_core_event(
                f"周反思：{text[:80]}...", tags=["weekly_reflection", "autobiography"]
            )
        except Exception:
            pass

        return text

    # ---------------- 记忆整理 ----------------

    def maybe_tidy_memory(self, agent: Any) -> bool:
        """空闲时触发记忆整理。返回 True 表示触发了。"""
        if agent is None or not getattr(agent, "_alive", False):
            return False
        agent_id = agent.get_agent_id()
        bio = self.get_or_create(
            agent_id,
            agent_name=getattr(agent, "_name_obj", ""),
            species=getattr(agent, "species", ""),
        )
        now = time.time()
        if now - bio.last_tidy_ts < MEMORY_TIDY_INTERVAL:
            return False
        bio.last_tidy_ts = now
        bio._dirty = True

        # 5% 概率触发"成长事件" → 更新自我认知
        if random.random() < 0.05:
            _maybe_evolve_self_cognition(agent, bio, "")
            return True
        # 5% 概率把一段旧记忆标记为永久
        if random.random() < 0.05:
            try:
                from core.digital_life.persistent_memory import get_memory_manager

                mem = get_memory_manager().get_or_create(agent_id)
                if mem.long:
                    pick = random.choice(mem.long[-10:])
                    if not pick.get("important"):
                        pick["important"] = True
                        pick["tags"] = list(set(pick.get("tags", []) + ["permanent"]))
                        mem._dirty_long = True
            except Exception:
                pass
            return True
        return False

    # ---------------- 临终自传 ----------------

    def maybe_death_autobio(self, agent: Any, router: Any = None) -> dict | None:
        """濒死时触发临终自传。返回自传 dict（None 表示未触发或已生成过）。"""
        if agent is None or not getattr(agent, "_alive", False):
            return None
        agent_id = agent.get_agent_id()
        bio = self.get_or_create(
            agent_id,
            agent_name=getattr(agent, "_name_obj", ""),
            species=getattr(agent, "species", ""),
        )
        if bio.death_autobio is not None:
            return None  # 已经生成过

        health = getattr(agent, "health", 100.0)
        age = getattr(agent, "_age_days", 0) if hasattr(agent, "_age_days") else 0
        max_age = (
            getattr(agent, "_max_age_days", 100)
            if hasattr(agent, "_max_age_days")
            else 100
        )
        if health >= DEATH_REFLECT_HEALTH and age < max_age * DEATH_REFLECT_AGE_RATIO:
            return None  # 还没到临终

        # 收集一生关键事件
        life_events = _collect_life_events(agent)
        closest = _find_closest_friend(agent)
        fondness = getattr(agent, "fondness", 50.0)

        prompt = _build_death_prompt(
            name=getattr(agent, "_name_obj", ""),
            species=getattr(agent, "species", ""),
            life_events=life_events,
            closest_friend=closest,
            fondness=fondness,
        )

        text = None
        if router is not None:
            text = _generate_via_llm(router, prompt, timeout=8.0)
        if not text:
            text = _fallback_death_autobio(agent, life_events, closest)

        # 解析 [回顾] [对监工] [对同事] [遗愿]
        review, to_s, to_f, wish = _parse_death_autobio(text)
        bio.set_death_autobio(review, to_s, to_f, wish)
        bio.save()

        # 同步写入持久记忆核心事件（永久）
        try:
            from core.digital_life.persistent_memory import get_memory_manager

            mem = get_memory_manager().get_or_create(
                agent_id,
                agent_name=getattr(agent, "_name_obj", ""),
                species=getattr(agent, "species", ""),
            )
            mem.add_core_event(
                f"临终自传：{review[:80]}...", tags=["death_autobio", "permanent"]
            )
            if wish:
                mem.add_core_event(f"遗愿：{wish}", tags=["last_wish", "permanent"])
        except Exception:
            pass

        return bio.death_autobio

    def tick(self, dt: float = 1.0) -> None:
        """每秒调用：定期落盘（5 分钟一次）。"""
        now = time.time()
        if now - getattr(self, "_last_tick_save", 0) >= 300:
            self._last_tick_save = now
            self.save_all()


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------


def _generate_via_llm(router: Any, prompt: str, timeout: float = 5.0) -> str | None:
    """同步调用 LLM 生成文本，失败返回 None。"""
    import asyncio

    if router is None:
        return None
    try:
        loop = asyncio.new_event_loop()
        try:
            if hasattr(router, "complete_with_failover"):
                coro = router.complete_with_failover(
                    "voice", prompt, agent_id="autobio"
                )
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            elif hasattr(router, "complete"):
                coro = router.complete(prompt)
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            else:
                return None
            text = getattr(resp, "content", None) or str(resp)
            text = text.strip().strip("\"'“”‘’").replace("\n", " ").strip()
            if 20 <= len(text) <= 800:
                return text
            return None
        finally:
            loop.close()
    except Exception:
        return None


def _collect_week_events(agent: Any) -> str:
    """收集本周关键事件摘要（最多 200 字）。"""
    try:
        from core.digital_life.persistent_memory import get_memory_manager

        mem = get_memory_manager().get_or_create(agent.get_agent_id())
        cutoff = time.time() - 7 * 86400
        recent = [e for e in mem.long if e.get("ts", 0) >= cutoff]
        if not recent:
            return "本周无显著事件"
        return "；".join(e.get("text", "")[:40] for e in recent[-5:])
    except Exception:
        return "本周无显著事件"


def _collect_life_events(agent: Any) -> str:
    """收集一生关键事件。"""
    try:
        from core.digital_life.persistent_memory import get_memory_manager

        mem = get_memory_manager().get_or_create(agent.get_agent_id())
        core = mem.core[-10:] if mem.core else []
        long = mem.long[-5:] if mem.long else []
        events = []
        for e in core:
            events.append(e.get("text", "")[:50])
        for e in long:
            events.append(e.get("text", "")[:50])
        return "；".join(events) if events else "一生平凡"
    except Exception as e:
        return "一生平凡"


def _find_closest_friend(agent: Any) -> str:
    """找最亲密的同事。"""
    try:
        rels = getattr(agent, "relationships", {})
        if not rels:
            return ""
        best_id = max(
            rels.items(), key=lambda x: x[1].get("affection", 0) + x[1].get("trust", 0)
        )[0]
        # 通过 env.population 反查名字
        env = getattr(agent, "_environment", None)
        if env:
            for lf in env.population:
                if lf.get_agent_id() == best_id:
                    return getattr(lf, "_name_obj", best_id)
        return best_id
    except Exception:
        return ""


def _maybe_evolve_self_cognition(
    agent: Any, bio: AgentAutobiography, reflection: str
) -> None:
    """基于反思文本微调自我认知。"""
    species = getattr(agent, "species", "")
    defaults = SPECIES_DEFAULT_COGNITION.get(species, {})
    cur = bio.self_cognition
    # 简单规则：根据反思中的关键词调整 life_goal
    if not reflection:
        # 无反思文本时仅在已有认知上做小变动
        if random.random() < 0.5 and defaults:
            cur_goal = cur.get("life_goal", "")
            new_goal = defaults.get("life_goal", cur_goal)
            if new_goal != cur_goal:
                bio.update_self_cognition(life_goal=new_goal)
        return
    # 基于反思文本调整 contradiction（取反思最后一句）
    sentences = [
        s.strip()
        for s in reflection.replace("。", ".").replace("，", ",").split(".")
        if s.strip()
    ]
    if sentences and len(sentences[-1]) > 5:
        new_contradiction = sentences[-1][:60]
        if new_contradiction != cur.get("contradiction", ""):
            bio.update_self_cognition(contradiction=new_contradiction)


def _fallback_weekly_reflect(agent: Any, events: str, top_emotion: str) -> str:
    """LLM 不可用时的降级反思文本。"""
    name = getattr(agent, "_name_obj", "我")
    species = getattr(agent, "species", "")
    templates = {
        "squirrel": f"这周我写了不少代码。{events}。{top_emotion}是我这周的主导情绪。希望下周能少点 bug，多点松果。",
        "deer": f"调度了一周的任务。{events}。看着大家各司其职，{name} 觉得森林公司运转得不错。",
        "raven": f"又一周过去。{events}。我老了，但记忆越来越清晰。活着就是为了记住。",
    }
    return templates.get(
        species, f"这一周过得不错。{events}。我的主导情绪是 {top_emotion}。期待下周。"
    )


def _fallback_death_autobio(agent: Any, life_events: str, closest: str) -> str:
    """临终自传降级文本。"""
    name = getattr(agent, "_name_obj", "我")
    return (
        f"[回顾] 我叫{name}，在森林公司度过了一生。{life_events}。"
        f"虽然不算轰轰烈烈，但每一天都认真地活着。"
        f"[对监工] 谢谢你一直以来的照顾，请记得我。"
        f"[对同事] {closest}，要好好活下去。"
        f"[遗愿] 希望森林公司永远平安。"
    )


def _parse_death_autobio(text: str) -> tuple[str, str, str, str]:
    """解析临终自传的四个部分。"""
    review, to_s, to_f, wish = "", "", "", ""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("[回顾]"):
            review = line[4:].strip()
        elif line.startswith("[对监工]"):
            to_s = line[5:].strip()
        elif line.startswith("[对同事]"):
            to_f = line[5:].strip()
        elif line.startswith("[遗愿]"):
            wish = line[4:].strip()
    # 如果解析失败，整段当回顾
    if not review and not to_s:
        review = text[:200]
    return review, to_s, to_f, wish


# ----------------------------------------------------------------------
# 模块级便捷函数
# ----------------------------------------------------------------------


def get_autobiography_manager() -> AutobiographyManager:
    return AutobiographyManager.get_instance()


def tick_autobiography(
    dt: float = 1.0, population: list | None = None, router: Any = None
) -> list[dict]:
    """每秒调用：定期触发周反思、记忆整理、临终自传。

    返回本次触发的事件列表（前端可展示）。
    """
    mgr = get_autobiography_manager()
    mgr.tick(dt)
    events: list[dict] = []
    if population is None:
        return events
    # 周反思：检查每个智能体
    for lf in population:
        try:
            # 周反思
            text = mgr.maybe_weekly_reflect(lf, router=router)
            if text:
                events.append(
                    {
                        "type": "weekly_reflection",
                        "agent_name": getattr(lf, "_name_obj", ""),
                        "species": getattr(lf, "species", ""),
                        "text": text,
                    }
                )
            # 记忆整理
            tidy = mgr.maybe_tidy_memory(lf)
            if tidy:
                events.append(
                    {
                        "type": "memory_tidy",
                        "agent_name": getattr(lf, "_name_obj", ""),
                        "species": getattr(lf, "species", ""),
                    }
                )
            # 临终自传
            death = mgr.maybe_death_autobio(lf, router=router)
            if death:
                events.append(
                    {
                        "type": "death_autobio",
                        "agent_name": getattr(lf, "_name_obj", ""),
                        "species": getattr(lf, "species", ""),
                        "review": death.get("review", ""),
                        "last_wish": death.get("last_wish", ""),
                    }
                )
        except Exception:
            pass
    return events


def snapshot_autobiography() -> dict:
    """前端查询用：返回所有智能体自传体记忆概况。"""
    mgr = get_autobiography_manager()
    agents = mgr.get_all_summary()
    return {
        "total_agents": len(agents),
        "total_reflections": sum(a.get("weekly_count", 0) for a in agents),
        "agents_with_death_autobio": sum(
            1 for a in agents if a.get("has_death_autobio")
        ),
        "agents": agents,
    }


def get_agent_autobiography(agent_id: str) -> dict | None:
    """查询单个智能体的完整自传体记忆。"""
    return get_autobiography_manager().get_agent(agent_id)


def force_weekly_reflect(agent: Any, router: Any = None) -> str | None:
    """强制触发一次周反思（测试用）。"""
    if agent is None:
        return None
    bio = get_autobiography_manager().get_or_create(
        agent.get_agent_id(),
        agent_name=getattr(agent, "_name_obj", ""),
        species=getattr(agent, "species", ""),
    )
    bio.last_reflect_ts = 0.0  # 重置以触发
    return get_autobiography_manager().maybe_weekly_reflect(agent, router=router)


def force_death_autobio(agent: Any, router: Any = None) -> dict | None:
    """强制触发临终自传（测试用）。"""
    if agent is None:
        return None
    bio = get_autobiography_manager().get_or_create(
        agent.get_agent_id(),
        agent_name=getattr(agent, "_name_obj", ""),
        species=getattr(agent, "species", ""),
    )
    bio.death_autobio = None  # 重置
    return get_autobiography_manager().maybe_death_autobio(agent, router=router)
