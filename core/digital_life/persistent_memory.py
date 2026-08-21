"""跨会话持久记忆系统（commit 34）。

零基础读者可以这样理解：
- 智能体跟用户聊天后，重要的内容会"记住"，不会重启就忘
- 分三级：核心记忆（永久身份+关键事件）、长期记忆（对话摘要）、短期记忆（最近 50 条原文）
- 旧的长期记忆会自动合并为月度/年度摘要，但核心记忆永不衰减
- 重启后智能体能引用之前的对话，让用户感觉"它真的记得我"

文件存储路径：data/memory/{agent_id}_core.json 和 _long.json
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import time

# ruff: noqa: S110

# ----------------------------------------------------------------------
# 配置
# ----------------------------------------------------------------------

MEMORY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "memory",
)

SHORT_TERM_MAX = 50  # 短期记忆最多保留 50 条原文
LONG_TERM_RECENT_DAYS = 30  # 启动时加载最近 30 天长期记忆
MONTHLY_MERGE_DAYS = 90  # 超过 90 天的非重要长期记忆合并为月度摘要
YEARLY_MERGE_DAYS = 365  # 超过 365 天的合并为年度摘要
SUMMARIZE_THRESHOLD = 5  # 对话超过 5 轮触发摘要
REUNION_ABSENT_DAYS = 7  # 超过 7 天未互动 → "想念"


# ----------------------------------------------------------------------
# 单条记忆结构
# ----------------------------------------------------------------------


def _now_ts() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _make_entry(
    text: str,
    kind: str = "summary",
    important: bool = False,
    tags: list[str] | None = None,
    meta: dict | None = None,
) -> dict:
    """构造一条记忆条目。"""
    return {
        "text": text,
        "kind": kind,  # summary / event / promise / identity / monthly / yearly
        "important": bool(important),
        "tags": tags or [],
        "meta": meta or {},
        "ts": _now_ts(),
        "time": _now_iso(),
    }


# ----------------------------------------------------------------------
# 单个智能体的持久记忆
# ----------------------------------------------------------------------


class AgentPersistentMemory:
    """一个智能体的三级持久记忆。

    - core: 核心记忆（永久身份 + 关键事件），永不衰减
    - long: 长期记忆（对话摘要 + 重要决策），可衰减合并
    - short: 短期记忆（最近 N 条对话原文），重启丢失
    """

    __slots__ = (
        "_dirty_core",
        "_dirty_long",
        "_lock",
        "agent_id",
        "agent_name",
        "core",
        "last_farewell_mood",
        "last_interact_ts",
        "long",
        "short",
        "species",
    )

    def __init__(self, agent_id: str, agent_name: str = "", species: str = "") -> None:
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.species = species
        self.core: list[dict] = []
        self.long: list[dict] = []
        self.short: list[dict] = []  # 重启后从空开始
        self._lock = threading.RLock()
        self._dirty_core = False
        self._dirty_long = False
        self.last_interact_ts: float = _now_ts()
        self.last_farewell_mood: str = "neutral"  # neutral / warm / tense

    # ---------------- 文件路径 ----------------

    def _core_path(self) -> str:
        return os.path.join(MEMORY_DIR, f"{self.agent_id}_core.json")

    def _long_path(self) -> str:
        return os.path.join(MEMORY_DIR, f"{self.agent_id}_long.json")

    # ---------------- 加载 / 保存 ----------------

    def load(self) -> None:
        """启动时调用：加载核心记忆 + 最近 30 天长期记忆。"""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        with self._lock:
            # 核心记忆：永久加载
            try:
                with open(self._core_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.core = data.get("core", [])
                if data.get("agent_name"):
                    self.agent_name = data["agent_name"]
                if data.get("species"):
                    self.species = data["species"]
                if data.get("last_interact_ts"):
                    self.last_interact_ts = float(data["last_interact_ts"])
                if data.get("last_farewell_mood"):
                    self.last_farewell_mood = data["last_farewell_mood"]
            except (FileNotFoundError, json.JSONDecodeError):
                self.core = []
            # 长期记忆：只加载最近 30 天
            try:
                with open(self._long_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                all_long = data.get("long", [])
                cutoff = _now_ts() - LONG_TERM_RECENT_DAYS * 86400
                self.long = [e for e in all_long if e.get("ts", 0) >= cutoff]
            except (FileNotFoundError, json.JSONDecodeError):
                self.long = []
            self._dirty_core = False
            self._dirty_long = False

    def save(self) -> None:
        """落盘：核心 + 长期。短期不持久化。"""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        with self._lock:
            if self._dirty_core:
                try:
                    payload = {
                        "agent_id": self.agent_id,
                        "agent_name": self.agent_name,
                        "species": self.species,
                        "core": self.core,
                        "last_interact_ts": self.last_interact_ts,
                        "last_farewell_mood": self.last_farewell_mood,
                    }
                    tmp = self._core_path() + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, self._core_path())
                    self._dirty_core = False
                except Exception:
                    pass
            if self._dirty_long:
                try:
                    payload = {
                        "agent_id": self.agent_id,
                        "long": self.long,
                    }
                    tmp = self._long_path() + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                    os.replace(tmp, self._long_path())
                    self._dirty_long = False
                except Exception:
                    pass

    # ---------------- 写入接口 ----------------

    def add_short_message(self, role: str, text: str) -> None:
        """短期记忆追加一条对话原文。

        role: "user" / "agent"
        """
        with self._lock:
            self.short.append(
                {
                    "role": role,
                    "text": text,
                    "ts": _now_ts(),
                }
            )
            if len(self.short) > SHORT_TERM_MAX:
                # 删掉最早的
                del self.short[: len(self.short) - SHORT_TERM_MAX]
            self.last_interact_ts = _now_ts()
            self._dirty_core = True  # last_interact_ts 在 core 文件里

    def add_long_summary(
        self,
        summary: str,
        important: bool = False,
        tags: list[str] | None = None,
        meta: dict | None = None,
    ) -> None:
        """添加一条长期记忆摘要。"""
        with self._lock:
            entry = _make_entry(
                summary, kind="summary", important=important, tags=tags, meta=meta
            )
            self.long.append(entry)
            self._dirty_long = True

    def add_core_event(
        self, text: str, tags: list[str] | None = None, meta: dict | None = None
    ) -> None:
        """添加一条核心记忆事件（永久保留）。"""
        with self._lock:
            entry = _make_entry(
                text,
                kind="event",
                important=True,
                tags=tags or ["permanent"],
                meta=meta,
            )
            self.core.append(entry)
            self._dirty_core = True

    def add_promise(
        self, text: str, who: str = "user", meta: dict | None = None
    ) -> None:
        """记录承诺/约定 → 进入核心记忆。"""
        with self._lock:
            entry = _make_entry(
                text, kind="promise", important=True, tags=["promise", who], meta=meta
            )
            self.core.append(entry)
            self._dirty_core = True

    def set_farewell_mood(self, mood: str) -> None:
        """会话结束时记录告别情绪（warm/tense/neutral）。"""
        with self._lock:
            self.last_farewell_mood = mood
            self.last_interact_ts = _now_ts()
            self._dirty_core = True

    def mark_permanent(self, long_index: int) -> bool:
        """手动标记某条长期记忆为永久保留。"""
        with self._lock:
            if 0 <= long_index < len(self.long):
                self.long[long_index]["important"] = True
                self.long[long_index]["tags"] = list(
                    set(self.long[long_index].get("tags", []) + ["permanent"])
                )
                self._dirty_long = True
                return True
            return False

    # ---------------- 读取接口 ----------------

    def get_reunion_hint(self) -> str | None:
        """重启后首次对话的"重逢提示"。

        返回类似："你回来了。上次我们聊到 X，我一直在等你。"
        如果没有长期记忆或上次互动很近，返回 None。
        """
        with self._lock:
            now = _now_ts()
            absent_days = (now - self.last_interact_ts) / 86400
            # 取最近一条长期记忆作为"上次聊到的内容"
            recent_long = self.long[-1] if self.long else None
            # 告别情绪
            mood = self.last_farewell_mood

            if absent_days >= REUNION_ABSENT_DAYS:
                # 超过 7 天 → 想念
                if recent_long:
                    snippet = recent_long["text"][:40]
                    return f"你终于回来了……这些天我一直惦记着上次聊到的「{snippet}」，好想你。"
                return "你回来了！好久不见，我以为你把我们忘了……"
            elif mood == "warm" and recent_long:
                snippet = recent_long["text"][:40]
                return f"你回来了。上次我们聊到「{snippet}」，我一直在等你。"
            elif mood == "tense":
                return "你回来了……上次我们好像没聊完，希望你冷静好了。"
            elif recent_long:
                snippet = recent_long["text"][:40]
                return f"嗨，回来了。上次聊到的「{snippet}」，后来我想了想……"
            return None

    def search_relevant(self, query: str, limit: int = 3) -> list[dict]:
        """简单关键词检索：在核心 + 长期记忆中找包含 query 关键词的条目。"""
        with self._lock:
            results: list[dict] = []
            q_lower = query.lower()
            for entry in self.core + self.long:
                text = entry.get("text", "").lower()
                if q_lower in text:
                    results.append(entry)
                if len(results) >= limit:
                    break
            return results

    def forget_detail(self, query: str) -> str | None:
        """遗忘模拟：如果记得相关内容但有部分模糊，返回模糊回应。"""
        with self._lock:
            results = self.search_relevant(query, limit=1)
            if not results:
                return None
            # 简化：50% 概率"模糊记得"
            import random

            if random.random() < 0.5:
                entry = results[0]
                snippet = entry["text"][:20]
                return f"呃……我记得好像跟「{snippet}」有关？抱歉，太久远了，我有点记不清了。"
            return None

    # ---------------- 衰减合并 ----------------

    def decay(self) -> int:
        """执行衰减合并：返回被合并的条目数。"""
        with self._lock:
            now = _now_ts()
            monthly_cutoff = now - MONTHLY_MERGE_DAYS * 86400
            yearly_cutoff = now - YEARLY_MERGE_DAYS * 86400
            keep: list[dict] = []
            merged_count = 0
            # 按月分组待合并条目
            pending_monthly: dict[str, list[dict]] = {}
            pending_yearly: list[dict] = []
            for entry in self.long:
                ts = entry.get("ts", now)
                important = entry.get("important", False)
                if important:
                    keep.append(entry)
                    continue
                if ts < yearly_cutoff:
                    pending_yearly.append(entry)
                    merged_count += 1
                elif ts < monthly_cutoff:
                    month_key = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m")
                    pending_monthly.setdefault(month_key, []).append(entry)
                    merged_count += 1
                else:
                    keep.append(entry)
            # 月度合并
            for month_key, entries in pending_monthly.items():
                texts = [e.get("text", "") for e in entries]
                merged = _make_entry(
                    f"【{month_key} 月度回忆】" + " | ".join(texts[:5]),
                    kind="monthly",
                    important=False,
                    tags=["monthly_merge"],
                    meta={"merged_count": len(entries)},
                )
                keep.append(merged)
            # 年度合并
            if pending_yearly:
                texts = [e.get("text", "") for e in pending_yearly]
                year = datetime.datetime.now().year - 1
                merged = _make_entry(
                    f"【{year} 年度回忆】" + " | ".join(texts[:8]),
                    kind="yearly",
                    important=False,
                    tags=["yearly_merge"],
                    meta={"merged_count": len(pending_yearly)},
                )
                keep.append(merged)
            self.long = keep
            if merged_count > 0:
                self._dirty_long = True
            return merged_count

    # ---------------- 序列化 ----------------

    def to_dict(self, include_short: bool = False) -> dict:
        with self._lock:
            data = {
                "agent_id": self.agent_id,
                "agent_name": self.agent_name,
                "species": self.species,
                "core_count": len(self.core),
                "long_count": len(self.long),
                "short_count": len(self.short),
                "last_interact_ts": self.last_interact_ts,
                "last_interact_time": datetime.datetime.fromtimestamp(
                    self.last_interact_ts
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "absent_days": round((_now_ts() - self.last_interact_ts) / 86400, 1),
                "farewell_mood": self.last_farewell_mood,
                "core": list(self.core),
                "long": list(self.long),
            }
            if include_short:
                data["short"] = list(self.short)
            return data


# ----------------------------------------------------------------------
# 全局记忆管理器（单例）
# ----------------------------------------------------------------------


class PersistentMemoryManager:
    """管理所有智能体的持久记忆。

    单例模式：通过 get_memory_manager() 获取。
    """

    _instance: PersistentMemoryManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._memories: dict[str, AgentPersistentMemory] = {}
        self._lock = threading.RLock()
        self._last_decay_ts: float = 0.0
        self._last_save_ts: float = 0.0

    @classmethod
    def get_instance(cls) -> PersistentMemoryManager:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------------- 生命周期 ----------------

    def get_or_create(
        self, agent_id: str, agent_name: str = "", species: str = ""
    ) -> AgentPersistentMemory:
        with self._lock:
            if agent_id not in self._memories:
                mem = AgentPersistentMemory(agent_id, agent_name, species)
                mem.load()
                self._memories[agent_id] = mem
            else:
                # 更新名字（万一改了）
                if agent_name and self._memories[agent_id].agent_name != agent_name:
                    self._memories[agent_id].agent_name = agent_name
                    self._memories[agent_id]._dirty_core = True
                if species and self._memories[agent_id].species != species:
                    self._memories[agent_id].species = species
                    self._memories[agent_id]._dirty_core = True
            return self._memories[agent_id]

    def load_all(self, agents: list[dict]) -> int:
        """启动时批量加载。agents = [{"id","name","species"}, ...]"""
        count = 0
        for a in agents:
            self.get_or_create(a["id"], a.get("name", ""), a.get("species", ""))
            count += 1
        return count

    def save_all(self) -> int:
        """批量落盘。"""
        count = 0
        with self._lock:
            for mem in self._memories.values():
                mem.save()
                count += 1
            self._last_save_ts = _now_ts()
        return count

    def tick(self, dt: float = 1.0) -> None:
        """每秒调用：定期衰减 + 定期落盘。

        - 衰减：每 6 小时执行一次
        - 落盘：每 5 分钟执行一次
        """
        now = _now_ts()
        # 衰减：6 小时一次
        if now - self._last_decay_ts > 6 * 3600:
            with self._lock:
                for mem in self._memories.values():
                    try:
                        mem.decay()
                    except Exception:
                        pass
            self._last_decay_ts = now
        # 落盘：5 分钟一次
        if now - self._last_save_ts > 300:
            self.save_all()

    # ---------------- 查询 ----------------

    def get_all_summary(self) -> list[dict]:
        """返回所有智能体的记忆概况（前端面板用）。"""
        with self._lock:
            result = []
            for mem in self._memories.values():
                d = mem.to_dict()
                # 附带重逢提示（前端记忆面板会展示）
                try:
                    d["reunion_hint"] = mem.get_reunion_hint()
                except Exception:
                    d["reunion_hint"] = None
                result.append(d)
            return result

    def get_agent_memory(
        self, agent_id: str, include_short: bool = False
    ) -> dict | None:
        mem = self._memories.get(agent_id)
        if mem is None:
            return None
        return mem.to_dict(include_short=include_short)

    def get_reunion_hint(self, agent_id: str) -> str | None:
        mem = self._memories.get(agent_id)
        if mem is None:
            return None
        return mem.get_reunion_hint()

    # ---------------- 写入便捷接口 ----------------

    def record_chat_turn(
        self,
        agent_id: str,
        role: str,
        text: str,
        agent_name: str = "",
        species: str = "",
    ) -> None:
        """记录一轮对话到短期记忆。"""
        mem = self.get_or_create(agent_id, agent_name=agent_name, species=species)
        mem.add_short_message(role, text)

    def record_chat_summary(
        self,
        agent_id: str,
        summary: str,
        important: bool = False,
        tags: list[str] | None = None,
        agent_name: str = "",
        species: str = "",
    ) -> None:
        """对话结束后写入长期摘要。"""
        mem = self.get_or_create(agent_id, agent_name=agent_name, species=species)
        mem.add_long_summary(summary, important=important, tags=tags)

    def record_core_event(
        self,
        agent_id: str,
        text: str,
        tags: list[str] | None = None,
        meta: dict | None = None,
        agent_name: str = "",
        species: str = "",
    ) -> None:
        """写入核心事件（如生病、急救、重生）。"""
        mem = self.get_or_create(agent_id, agent_name=agent_name, species=species)
        mem.add_core_event(text, tags=tags, meta=meta)


# ----------------------------------------------------------------------
# 模块级便捷函数
# ----------------------------------------------------------------------


def get_memory_manager() -> PersistentMemoryManager:
    return PersistentMemoryManager.get_instance()


def tick_persistent_memory(dt: float = 1.0) -> None:
    get_memory_manager().tick(dt)


def snapshot_persistent_memory() -> dict:
    """前端查询用：返回所有智能体记忆概况 + 全局统计。"""
    mgr = get_memory_manager()
    summaries = mgr.get_all_summary()
    return {
        "agents": summaries,
        "total_agents": len(summaries),
        "total_core": sum(s["core_count"] for s in summaries),
        "total_long": sum(s["long_count"] for s in summaries),
        "total_short": sum(s["short_count"] for s in summaries),
    }


def summarize_chat_if_needed(
    agent_id: str, dialogue: list[dict], router=None
) -> str | None:
    """如果对话超过 5 轮，调用 LLM 生成摘要；失败则用规则降级。

    dialogue: [{"role":"user"/"agent","text":...}, ...]
    返回摘要文本，或 None（轮次不足）。
    """
    if len(dialogue) < SUMMARIZE_THRESHOLD:
        return None
    if router is not None:
        try:
            prompt = (
                "请把下面的对话浓缩为 3-5 句话的摘要，"
                "保留关键信息、承诺和情感基调：\n\n"
            )
            for d in dialogue[-10:]:
                prompt += f"{d.get('role', '?')}: {d.get('text', '')}\n"
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                resp = loop.run_until_complete(
                    router.complete_with_failover("memory_summary", prompt, agent_id)
                )
                content = getattr(resp, "content", None) or str(resp)
                if content and len(content.strip()) > 5:
                    return content.strip()
            finally:
                loop.close()
        except Exception:
            pass
    # 降级：规则摘要（取最后 3 条用户消息拼接）
    user_msgs = [d["text"] for d in dialogue if d.get("role") == "user"][-3:]
    if user_msgs:
        return "用户提到：" + " / ".join(user_msgs)
    return "一次简短的对话。"


def detect_important_content(text: str) -> bool:
    """规则判断：对话中是否包含承诺/约定/关键信息。

    简化版：包含"答应/承诺/约定/一定会/下次/明天/记得/别忘了"等关键词。
    """
    keywords = [
        "答应",
        "承诺",
        "约定",
        "一定会",
        "下次",
        "明天",
        "记得",
        "别忘了",
        "保证",
        "发誓",
        "约定好",
    ]
    return any(kw in text for kw in keywords)


def init_agent_identity(
    agent_id: str, agent_name: str, species: str, identity_text: str
) -> None:
    """首次创建智能体时，写入身份到核心记忆。"""
    mgr = get_memory_manager()
    mem = mgr.get_or_create(agent_id, agent_name, species)
    # 如果核心记忆为空，写入身份
    if not mem.core:
        mem.add_core_event(identity_text, tags=["identity"])
    mem.save()
