"""commit 35：智能体私密日记系统。

零基础读者可以这样理解：
- 每天 22:00（智能体就寝前）自动写一篇日记，记录今天的内心活动
- 日记是私密的，正常界面看不到
- 彩蛋：在智能体工位附近反复点击 3 次，有概率"发现"隐藏的日记本
- 偷看日记时，被偷看智能体的 trust 会缓慢下降（直觉感觉被偷看）
- 智能体死亡后，特殊日记（入职/挚友/悼念）自动转为公开的记忆碎片

文件存储路径：data/memory/{agent_id}_diary.json
"""
from __future__ import annotations

import datetime
import json
import os
import random
import threading
import time
from typing import Any

# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------

DIARY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "memory",
)

DIARY_DAILY_HOUR = 22             # 每天 22:00 写日记
DIARY_KEEP_DAYS = 90              # 保留最近 90 天日记
PEEK_TRUST_COST = 0.05            # 每次偷看扣 trust 0.05
PEEK_DISCOVERY_PROB = 0.15        # 反复点击 3 次发现日记本的概率
SPECIAL_DIARY_TYPES = (
    "first_day",          # 入职第一天
    "retirement_wish",    # 退休愿望
    "best_friend",        # 挚友达成
    "bereavement",        # 同事死亡悼念
    "special_gift",       # 收到监工特殊礼物
    "illness_recovery",   # 大病初愈
    "rescue_rebirth",     # 急救重生
)


# ----------------------------------------------------------------------
# 日记生成 prompt
# ----------------------------------------------------------------------

DIARY_PROMPT_TEMPLATE: str = """你是 BlueDeer 森林公司的智能体 {name}（物种：{species}）。
现在是晚上 22:00，你要写今天的日记。

今天发生的事：{events}
今天的情绪：主导情感 {top_emotion}，心情分数 {mood_score}/100
今天与监工互动：{interact_text}
对监工的好感度：{fondness}/100

要求：
1. 用第一人称写一段私密日记，200-400 字
2. 必须包含：今天最值得记的事 + 对监工的感受（如有互动）+ 对某位同事的感受 + 一个小期待或担忧
3. 语气真实、私密、像写给自己的，不要客套
4. 可以有小情绪、小抱怨、小确幸
5. 末尾加"晚安。"
6. 只输出日记正文，不要标题、不要署名
"""


def _build_diary_prompt(name: str, species: str, events: str,
                          top_emotion: str, mood_score: float,
                          interact_text: str, fondness: float) -> str:
    return DIARY_PROMPT_TEMPLATE.format(
        name=name, species=species, events=events or "今天过得平淡",
        top_emotion=top_emotion, mood_score=mood_score,
        interact_text=interact_text or "今天没有与监工互动",
        fondness=fondness,
    )


# ----------------------------------------------------------------------
# 降级日记模板（LLM 不可用时）
# ----------------------------------------------------------------------

FALLBACK_DIARY_TEMPLATES: dict[str, list[str]] = {
    "squirrel": [
        "今天写了不少代码。{events}。{interact}。希望明天少点 bug，多点松果。晚安。",
        "{events}。{interact}。狐狸说我代码越来越干净了，但其实只是把脏的部分藏起来了。晚安。",
    ],
    "deer": [
        "调度了一天的任务。{events}。{interact}。看着大家各司其职，我觉得森林公司运转得不错。晚安。",
        "{events}。{interact}。今天的森林很安静，希望明天也这样。晚安。",
    ],
    "raven": [
        "又一天过去。{events}。{interact}。我记录下了今天的一切，怕忘记。晚安。",
        "{events}。{interact}。年轻时我从不怕遗忘，现在却把每个名字都写两遍。晚安。",
    ],
    "butterfly": [
        "今天调了一种新颜色。{events}。{interact}。希望被谁记住。晚安。",
        "{events}。{interact}。美是需要孤独才能创造出来的。晚安。",
    ],
    "fox": [
        "今天又抓了几个 bug。{events}。{interact}。松鼠被我气得不行，但我只是为了他好。晚安。",
        "{events}。{interact}。嘴巴毒是我的保护色。晚安。",
    ],
    "hedgehog": [
        "巡视了一天的边界。{events}。{interact}。无异常就是最好的消息。晚安。",
        "{events}。{interact}。我的刺是为了保护大家。晚安。",
    ],
    "beaver": [
        "今天修了一些东西。{events}。{interact}。沉默地修，是我爱大家的方式。晚安。",
        "{events}。{interact}。水坝还在，我就还在。晚安。",
    ],
    "hare": [
        "算了一天的账。{events}。{interact}。资源还够用，但要多省着点。晚安。",
        "{events}。{interact}。未雨绸缪是我的人生信条。晚安。",
    ],
    "badger": [
        "今天挖了一段新地道。{events}。{interact}。地下比地上安静多了。晚安。",
        "{events}。{interact}。喜欢独处不是孤僻，是享受。晚安。",
    ],
    "lark": [
        "今天清晨第一个醒了。{events}。{interact}。第一个看到日出是我的特权。晚安。",
        "{events}。{interact}。希望明天也一切正常。晚安。",
    ],
    "kite": [
        "今天飞得很高。{events}。{interact}。从高空看森林公司，一切都小小的。晚安。",
        "{events}。{interact}。但再高也要回到这片森林。晚安。",
    ],
}


def _fallback_diary(name: str, species: str, events: str,
                     interact_text: str) -> str:
    templates = FALLBACK_DIARY_TEMPLATES.get(species,
        ["{events}。{interact}。今天就这样过去了。晚安。"])
    tpl = random.choice(templates)
    return tpl.format(events=events or "今天没什么特别的事",
                       interact=interact_text or "今天没见到监工")


# ----------------------------------------------------------------------
# 单个智能体的日记本
# ----------------------------------------------------------------------

class AgentDiary:
    """一个智能体的私密日记本。"""

    __slots__ = (
        "_dirty",
        "_lock",
        "agent_id",
        "agent_name",
        "entries",
        "last_diary_date",
        "peek_count",
        "special_entries",
        "species",
    )

    def __init__(self, agent_id: str, agent_name: str = "", species: str = "") -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.species = species
        self.entries: list[dict] = []            # 普通日记
        self.special_entries: list[dict] = []    # 特殊日记（入职/悼念等）
        self._lock = threading.RLock()
        self._dirty = False
        self.last_diary_date: str = ""           # YYYY-MM-DD，避免一天写两篇
        self.peek_count: int = 0                 # 被偷看次数

    # ---------------- 文件路径 ----------------

    def _path(self) -> str:
        return os.path.join(DIARY_DIR, f"{self.agent_id}_diary.json")

    # ---------------- 加载 / 保存 ----------------

    def load(self) -> None:
        os.makedirs(DIARY_DIR, exist_ok=True)
        with self._lock:
            try:
                with open(self._path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.entries = data.get("entries", [])
                self.special_entries = data.get("special_entries", [])
                if data.get("agent_name"):
                    self.agent_name = data["agent_name"]
                if data.get("species"):
                    self.species = data["species"]
                self.last_diary_date = data.get("last_diary_date", "")
                self.peek_count = int(data.get("peek_count", 0))
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            self._dirty = False

    def save(self) -> None:
        os.makedirs(DIARY_DIR, exist_ok=True)
        with self._lock:
            if not self._dirty:
                return
            try:
                payload = {
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "species": self.species,
                    "entries": self.entries,
                    "special_entries": self.special_entries,
                    "last_diary_date": self.last_diary_date,
                    "peek_count": self.peek_count,
                }
                tmp = self._path() + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._path())
                self._dirty = False
            except Exception:
                pass

    # ---------------- 写入 ----------------

    def add_entry(self, text: str, weather: str = "sunny",
                   mood_snapshot: dict | None = None) -> None:
        with self._lock:
            entry = {
                "text": text,
                "weather": weather,
                "mood": mood_snapshot or {},
                "date": datetime.date.today().isoformat(),
                "ts": time.time(),
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "peeked": False,
            }
            self.entries.append(entry)
            self.last_diary_date = entry["date"]
            # 保留最近 90 天
            cutoff = time.time() - DIARY_KEEP_DAYS * 86400
            self.entries = [e for e in self.entries if e.get("ts", 0) >= cutoff]
            self._dirty = True

    def add_special_entry(self, kind: str, text: str,
                            meta: dict | None = None) -> None:
        """特殊日记：入职/挚友/悼念/重病康复/急救重生/特殊礼物。"""
        if kind not in SPECIAL_DIARY_TYPES:
            return
        with self._lock:
            entry = {
                "kind": kind,
                "text": text,
                "meta": meta or {},
                "ts": time.time(),
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.special_entries.append(entry)
            self._dirty = True

    def mark_peeked(self) -> int:
        """记录被偷看一次。返回当前总偷看次数。"""
        with self._lock:
            self.peek_count += 1
            # 标记最近一篇日记为"被偷看"
            if self.entries:
                self.entries[-1]["peeked"] = True
            self._dirty = True
            return self.peek_count

    # ---------------- 查询 ----------------

    def get_recent(self, days: int = 7) -> list[dict]:
        with self._lock:
            cutoff = time.time() - days * 86400
            return [e for e in self.entries if e.get("ts", 0) >= cutoff]

    def get_special_entries(self) -> list[dict]:
        with self._lock:
            return list(self.special_entries)

    def to_dict(self, include_text: bool = False) -> dict:
        with self._lock:
            return {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "species": self.species,
                "total_entries": len(self.entries),
                "total_special": len(self.special_entries),
                "last_diary_date": self.last_diary_date,
                "peek_count": self.peek_count,
                "recent": ([e for e in self.entries[-7:]] if include_text
                            else [{"date": e.get("date"), "ts": e.get("ts"),
                                    "peeked": e.get("peeked", False)}
                                   for e in self.entries[-7:]]),
                "special": (list(self.special_entries) if include_text
                             else [{"kind": e.get("kind"), "ts": e.get("ts")}
                                    for e in self.special_entries]),
            }


# ----------------------------------------------------------------------
# 全局管理器（单例）
# ----------------------------------------------------------------------

class DiaryManager:
    _instance: DiaryManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._store: dict[str, AgentDiary] = {}
        self._lock = threading.RLock()
        self._last_check_hour: int = -1

    @classmethod
    def get_instance(cls) -> DiaryManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_or_create(self, agent_id: str, agent_name: str = "",
                       species: str = "") -> AgentDiary:
        with self._lock:
            if agent_id not in self._store:
                diary = AgentDiary(agent_id, agent_name, species)
                diary.load()
                self._store[agent_id] = diary
            else:
                if agent_name and self._store[agent_id].agent_name != agent_name:
                    self._store[agent_id].agent_name = agent_name
                    self._store[agent_id]._dirty = True
                if species and self._store[agent_id].species != species:
                    self._store[agent_id].species = species
                    self._store[agent_id]._dirty = True
            return self._store[agent_id]

    def save_all(self) -> int:
        count = 0
        with self._lock:
            for d in self._store.values():
                d.save()
                count += 1
        return count

    # ---------------- 日记生成触发 ----------------

    def maybe_write_daily(self, agent: Any, router: Any = None) -> str | None:
        """检查并触发每日日记。返回日记文本（None 表示未触发）。"""
        if agent is None or not getattr(agent, "_alive", False):
            return None
        now = datetime.datetime.now()
        # 只在 22 点后写入
        if now.hour < DIARY_DAILY_HOUR:
            return None
        agent_id = agent.get_agent_id()
        diary = self.get_or_create(agent_id,
                                    agent_name=getattr(agent, "_name_obj", ""),
                                    species=getattr(agent, "species", ""))
        today = now.date().isoformat()
        if diary.last_diary_date == today:
            return None  # 今天已经写过了

        # 收集今日事件
        events = _collect_today_events(agent)
        emo = getattr(agent, "emotional_state", {})
        top_e = max(emo.items(), key=lambda x: x[1])[0] if emo else "neutral"
        mood = getattr(agent, "mood_score", 50.0)
        interact_text = _collect_today_interact(agent)
        fondness = getattr(agent, "fondness", 50.0)
        weather = _get_weather(agent)

        prompt = _build_diary_prompt(
            name=getattr(agent, "_name_obj", ""),
            species=getattr(agent, "species", ""),
            events=events,
            top_emotion=top_e,
            mood_score=mood,
            interact_text=interact_text,
            fondness=fondness,
        )

        text = None
        if router is not None:
            text = _generate_via_llm(router, prompt, timeout=8.0)
        if not text:
            text = _fallback_diary(
                name=getattr(agent, "_name_obj", ""),
                species=getattr(agent, "species", ""),
                events=events,
                interact_text=interact_text,
            )

        mood_snap = {
            "top_emotion": top_e,
            "mood_score": mood,
            "fondness": fondness,
        }
        diary.add_entry(text, weather=weather, mood_snapshot=mood_snap)

        # 联动 1：日记中的情感峰值自动标记为"自传体事件"
        # 写入持久记忆长期摘要
        try:
            from core.digital_life.persistent_memory import get_memory_manager
            mem = get_memory_manager().get_or_create(agent_id,
                agent_name=getattr(agent, "_name_obj", ""),
                species=getattr(agent, "species", ""))
            mem.add_long_summary(f"今日日记：{text[:80]}...",
                                  important=False, tags=["diary"])
        except Exception:
            pass

        return text

    # ---------------- 特殊日记 ----------------

    def write_special(self, agent: Any, kind: str, text: str,
                       meta: dict | None = None) -> bool:
        """写入特殊日记。"""
        if agent is None or kind not in SPECIAL_DIARY_TYPES:
            return False
        agent_id = agent.get_agent_id()
        diary = self.get_or_create(agent_id,
                                    agent_name=getattr(agent, "_name_obj", ""),
                                    species=getattr(agent, "species", ""))
        diary.add_special_entry(kind, text, meta=meta)
        diary.save()
        return True

    # ---------------- 偷看 ----------------

    def peek(self, agent: Any) -> dict:
        """监工偷看日记。返回最近 7 天日记 + 特殊日记。

        被偷看智能体的 trust -0.05。
        """
        if agent is None:
            return {"error": "agent not found"}
        agent_id = agent.get_agent_id()
        diary = self.get_or_create(agent_id,
                                    agent_name=getattr(agent, "_name_obj", ""),
                                    species=getattr(agent, "species", ""))
        # trust 下降
        try:
            rels = getattr(agent, "relationships", {})
            # 监工的 other_id 通常是 "supervisor" 或 "监工"
            sup_id = "supervisor"
            if sup_id in rels:
                rels[sup_id]["trust"] = max(0.0,
                    rels[sup_id].get("trust", 0.5) - PEEK_TRUST_COST)
        except Exception:
            pass
        # 偷看计数
        diary.mark_peeked()
        diary.save()
        return {
            "agent_name": diary.agent_name,
            "species": diary.species,
            "peek_count": diary.peek_count,
            "recent": diary.get_recent(days=7),
            "special": diary.get_special_entries(),
        }

    def try_discover(self, agent: Any) -> bool:
        """尝试发现日记本（彩蛋：15% 概率）。"""
        if agent is None:
            return False
        return random.random() < PEEK_DISCOVERY_PROB

    # ---------------- 死亡时转为记忆碎片 ----------------

    def publish_special_on_death(self, agent: Any) -> int:
        """智能体死亡时，特殊日记转为公开记忆碎片。返回转换数量。"""
        if agent is None:
            return 0
        agent_id = agent.get_agent_id()
        diary = self._store.get(agent_id)
        if diary is None or not diary.special_entries:
            return 0
        try:
            from core.digital_life.memory_fragment import MemoryFragmentSystem
            sys = MemoryFragmentSystem()
            x = getattr(agent, "x", 0)
            y = getattr(agent, "y", 0)
            zone = getattr(agent, "current_zone_id", "center")
            for e in diary.special_entries:
                sys.spawn(
                    frag_type="supervisor_chat",
                    x=x + random.uniform(-1, 1),
                    y=y + random.uniform(-1, 1),
                    zone_id=zone,
                    agent_name=diary.agent_name,
                    agent_species=diary.species,
                    text=f"【{diary.agent_name}的私密日记】{e.get('text', '')[:80]}",
                    detail=e.get("kind", ""),
                    is_relic=True,
                )
            return len(diary.special_entries)
        except Exception:
            return 0

    # ---------------- 查询 ----------------

    def get_all_summary(self) -> list[dict]:
        with self._lock:
            return [d.to_dict(include_text=False) for d in self._store.values()]

    def get_agent_diary(self, agent_id: str) -> dict | None:
        d = self._store.get(agent_id)
        if d is None:
            return None
        return d.to_dict(include_text=True)

    def tick(self, dt: float = 1.0, population: list = None,
              router: Any = None) -> list[dict]:
        """每秒调用：检查并生成每日日记。返回生成事件列表。"""
        events: list[dict] = []
        now = datetime.datetime.now()
        # 节流：每小时检查一次
        if now.hour != self._last_check_hour:
            self._last_check_hour = now.hour
            if population and now.hour >= DIARY_DAILY_HOUR:
                for lf in population:
                    try:
                        text = self.maybe_write_daily(lf, router=router)
                        if text:
                            events.append({
                                "type": "diary_written",
                                "agent_name": getattr(lf, "_name_obj", ""),
                                "species": getattr(lf, "species", ""),
                                "preview": text[:60],
                            })
                    except Exception:
                        pass
        # 定期落盘
        if int(time.time()) % 600 == 0:
            self.save_all()
        return events


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------

def _generate_via_llm(router: Any, prompt: str, timeout: float = 8.0) -> str | None:
    import asyncio
    if router is None:
        return None
    try:
        loop = asyncio.new_event_loop()
        try:
            if hasattr(router, "complete_with_failover"):
                coro = router.complete_with_failover("voice", prompt, agent_id="diary")
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            elif hasattr(router, "complete"):
                coro = router.complete(prompt)
                resp = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            else:
                return None
            text = getattr(resp, "content", None) or str(resp)
            text = text.strip().strip('"\'“”‘’')
            if 30 <= len(text) <= 800:
                return text
            return None
        finally:
            loop.close()
    except Exception:
        return None


def _collect_today_events(agent: Any) -> str:
    """收集今天的关键事件。"""
    try:
        from core.digital_life.persistent_memory import get_memory_manager
        mem = get_memory_manager().get_or_create(agent.get_agent_id())
        cutoff = time.time() - 86400
        recent = [e for e in mem.long if e.get("ts", 0) >= cutoff]
        if not recent:
            return "今天没什么特别的事"
        return "；".join(e.get("text", "")[:40] for e in recent[-3:])
    except Exception:
        return "今天没什么特别的事"


def _collect_today_interact(agent: Any) -> str:
    """今天的监工互动描述。"""
    try:
        last = getattr(agent, "_last_supervisor_interact_ts", 0.0)
        if time.time() - last < 86400:
            fond = getattr(agent, "fondness", 50.0)
            if fond > 70:
                return "监工今天来看过我，我很开心"
            elif fond > 40:
                return "监工今天来了，但感觉匆匆忙忙"
            else:
                return "监工今天来了，但我有点拘谨"
        return "今天没见到监工"
    except Exception:
        return "今天没见到监工"


def _get_weather(agent: Any) -> str:
    env = getattr(agent, "_environment", None)
    if env:
        return getattr(env, "weather", "sunny")
    return "sunny"


# ----------------------------------------------------------------------
# 模块级便捷函数
# ----------------------------------------------------------------------

def get_diary_manager() -> DiaryManager:
    return DiaryManager.get_instance()


def tick_diary(dt: float = 1.0, population: list = None,
                router: Any = None) -> list[dict]:
    return get_diary_manager().tick(dt, population=population, router=router)


def snapshot_diary() -> dict:
    """前端查询用：返回所有智能体日记概况（不包含正文）。"""
    mgr = get_diary_manager()
    agents = mgr.get_all_summary()
    return {
        "total_agents": len(agents),
        "total_entries": sum(a.get("total_entries", 0) for a in agents),
        "total_special": sum(a.get("total_special", 0) for a in agents),
        "total_peeks": sum(a.get("peek_count", 0) for a in agents),
        "agents": agents,
    }


def get_agent_diary(agent_id: str) -> dict | None:
    return get_diary_manager().get_agent_diary(agent_id)


def peek_agent_diary(agent: Any) -> dict:
    """监工偷看智能体日记。"""
    return get_diary_manager().peek(agent)


def try_discover_diary(agent: Any) -> bool:
    """尝试发现日记本彩蛋。"""
    return get_diary_manager().try_discover(agent)


def write_special_diary(agent: Any, kind: str, text: str,
                         meta: dict | None = None) -> bool:
    return get_diary_manager().write_special(agent, kind, text, meta=meta)


def publish_diary_on_death(agent: Any) -> int:
    return get_diary_manager().publish_special_on_death(agent)


def force_write_diary(agent: Any, router: Any = None) -> str | None:
    """强制立即写一篇日记（测试用，绕过时间检查）。"""
    if agent is None:
        return None
    mgr = get_diary_manager()
    agent_id = agent.get_agent_id()
    diary = mgr.get_or_create(
        agent_id,
        agent_name=getattr(agent, "_name_obj", ""),
        species=getattr(agent, "species", ""))
    diary.last_diary_date = ""  # 重置
    # 临时把 DIARY_DAILY_HOUR 设为 0 让 maybe_write_daily 通过时间检查
    import core.digital_life.diary_system as _ds
    orig = _ds.DIARY_DAILY_HOUR
    _ds.DIARY_DAILY_HOUR = 0
    try:
        return mgr.maybe_write_daily(agent, router=router)
    finally:
        _ds.DIARY_DAILY_HOUR = orig
