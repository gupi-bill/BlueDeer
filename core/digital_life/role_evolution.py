"""commit 39：团队角色演化。

零基础读者可以这样理解：
- 每个智能体除了岗位角色（鹿是编排、鼠是代码），还会在协作中自发形成"非正式角色"
- 比如被求助最多的成为"技术领袖"，社交最多的成为"社交协调员"
- 每周日系统自动评估一次，角色不是永久的
- 获得角色后行为微调（教学成功率提升、响应速度提升等）

6 种角色：
- 技术领袖 🏆：技能 level ≥ 8 且被求助次数最多
- 社交协调员 🤝：自发社交次数最多，且被多人标记挚友
- 监工副手 🎖️：与监工互动最多，trust > 0.9
- 新人导师 🎓：入职 > 1年，且有过成功教学记录
- 危机处理者 ⚡：成功处理紧急事件 ≥ 3 次
- 隐士 🌙：社交次数低于平均 50%，工作产出高于平均 120%

数据持久化：data/role_history.json
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

# ruff: noqa: S110, S112

_ROLE_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "role_history.json",
)

# 6 种非正式角色定义
ROLE_DEFINITIONS: dict[str, dict] = {
    "tech_leader": {
        "name_zh": "技术领袖",
        "icon": "🏆",
        "description": "被公认为技术最强，同事遇难题时首先求助的对象",
        "behavior_modifier": {
            "teach_success_rate_boost": 0.2,  # 教学成功率 +20%
            "willing_to_help": True,
        },
    },
    "social_coordinator": {
        "name_zh": "社交协调员",
        "icon": "🤝",
        "description": "主动组织茶话会、调解冲突、活跃气氛",
        "behavior_modifier": {
            "tea_party_frequency_boost": 0.3,  # 茶话会频率 +30%
            "conflict_mediation_success_boost": 0.3,
        },
    },
    "supervisor_deputy": {
        "name_zh": "监工副手",
        "icon": "🎖️",
        "description": "监工不在时，自然接管部分监工的日常职责",
        "behavior_modifier": {
            "takes_over_when_supervisor_offline": True,
            "notify_on_offline_minutes": 60,
        },
    },
    "mentor": {
        "name_zh": "新人导师",
        "icon": "🎓",
        "description": "主动帮助新招募的智能体适应环境",
        "behavior_modifier": {
            "auto_approach_newcomer": True,
            "newcomer_adaptation_speedup": 0.3,
        },
    },
    "crisis_handler": {
        "name_zh": "危机处理者",
        "icon": "⚡",
        "description": "紧急事件中第一个响应并有效处理",
        "behavior_modifier": {
            "emergency_response_speed_boost": 0.5,
        },
    },
    "hermit": {
        "name_zh": "隐士",
        "icon": "🌙",
        "description": "喜欢独处，社交少但工作质量极高",
        "behavior_modifier": {
            "solo_work_efficiency_boost": 0.3,
            "social_willingness_drop": 0.2,
        },
    },
}


# ----------------------------------------------------------------------
# 评估函数
# ----------------------------------------------------------------------


def _safe_attr(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _evaluate_tech_leader(agent: Any, all_agents: list, stats: dict) -> bool:
    """技术领袖：技能 level ≥ 8 且被求助次数最多。"""
    skills = _safe_attr(agent, "skills", []) or []
    # skills 列表长度作为 level 近似（每个技能 = 1 level）
    level = len(skills)
    if level < 8:
        return False
    # 检查是否被求助次数最多
    help_count = stats.get("help_count", 0)
    if help_count < 3:
        return False
    # 是不是所有人里最多的
    max_help = max(
        (
            s.get("help_count", 0)
            for s in [
                {"help_count": _safe_attr(a, "_help_count", 0) or 0} for a in all_agents
            ]
        ),
        default=0,
    )
    return help_count >= max_help and help_count > 0


def _evaluate_social_coordinator(agent: Any, all_agents: list, stats: dict) -> bool:
    """社交协调员：自发社交次数最多，且被多人标记为挚友。"""
    social_count = stats.get("social_count", 0)
    if social_count < 5:
        return False
    friend_tags = 0
    rel_tags = _safe_attr(agent, "relationship_tags", {}) or {}
    for tags in rel_tags.values():
        if "挚友" in (tags or []):
            friend_tags += 1
    return friend_tags >= 2


def _evaluate_supervisor_deputy(agent: Any, all_agents: list, stats: dict) -> bool:
    """监工副手：与监工互动最多，trust > 0.9。"""
    fondness = float(_safe_attr(agent, "fondness", 50) or 50)
    if fondness < 90:
        return False
    interact_count = stats.get("supervisor_interact_count", 0)
    return interact_count >= 5


def _evaluate_mentor(agent: Any, all_agents: list, stats: dict) -> bool:
    """新人导师：入职 > 1 年，且有过成功教学记录。"""
    birth = float(_safe_attr(agent, "birth_time", time.time()) or time.time())
    age_days = (time.time() - birth) / 86400.0
    if age_days < 365:
        return False
    teach_count = stats.get("teach_count", 0)
    return teach_count >= 1


def _evaluate_crisis_handler(agent: Any, all_agents: list, stats: dict) -> bool:
    """危机处理者：成功处理紧急事件 ≥ 3 次。"""
    crisis_count = stats.get("crisis_resolved_count", 0)
    return crisis_count >= 3


def _evaluate_hermit(agent: Any, all_agents: list, stats: dict) -> bool:
    """隐士：社交次数低于平均 50%，工作产出高于平均 120%。"""
    social_count = stats.get("social_count", 0)
    work_output = stats.get("work_output", 0)
    if not all_agents:
        return False
    avg_social = sum(_safe_attr(a, "_social_count", 0) or 0 for a in all_agents) / len(
        all_agents
    )
    avg_work = sum(_safe_attr(a, "_work_output", 0) or 0 for a in all_agents) / max(
        1, len(all_agents)
    )
    if avg_social == 0 or avg_work == 0:
        return False
    return social_count < avg_social * 0.5 and work_output > avg_work * 1.2


_EVALUATORS = {
    "tech_leader": _evaluate_tech_leader,
    "social_coordinator": _evaluate_social_coordinator,
    "mentor": _evaluate_mentor,
    "crisis_handler": _evaluate_crisis_handler,
    "hermit": _evaluate_hermit,
    "supervisor_deputy": _evaluate_supervisor_deputy,
}


# ----------------------------------------------------------------------
# 角色演化引擎（单例）
# ----------------------------------------------------------------------


class RoleEvolutionEngine:
    """角色演化引擎（单例）。

    每周自动评估一次所有智能体，赋予非正式角色。
    """

    _instance: RoleEvolutionEngine | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._biosphere_ref: Any = None
        self._history: list[dict] = []  # 角色变更历史
        self._eval_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_eval_date: str = ""
        self._load()

    @classmethod
    def get_instance(cls) -> RoleEvolutionEngine:
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
            if os.path.exists(_ROLE_HISTORY_PATH):
                with open(_ROLE_HISTORY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._history = list(data.get("history", []))
        except Exception:
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_ROLE_HISTORY_PATH), exist_ok=True)
            with self._lock:
                data = {"history": list(self._history[-500:])}
            with open(_ROLE_HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except Exception:
            pass

    # ---------------- 评估 ----------------

    def evaluate_all(self) -> dict:
        """对所有活体智能体评估一次，更新角色。返回评估摘要。"""
        if self._biosphere_ref is None:
            return {"ok": False, "error": "biosphere not set"}
        all_agents = [
            lf
            for lf in getattr(self._biosphere_ref, "employees", [])
            if _safe_attr(lf, "_alive", False)
        ]
        if not all_agents:
            return {"ok": False, "error": "no living agents"}

        # 收集每个智能体的统计数据
        all_stats = {
            self._get_agent_id(a): self._collect_stats(a, all_agents)
            for a in all_agents
        }

        changes: list[dict] = []
        for agent in all_agents:
            aid = self._get_agent_id(agent)
            stats = all_stats.get(aid, {})
            old_roles = list(_safe_attr(agent, "informal_roles", []) or [])
            new_roles: list[str] = []
            for role_key, evaluator in _EVALUATORS.items():
                try:
                    if evaluator(agent, all_agents, stats):
                        new_roles.append(role_key)
                except Exception:
                    pass
            # 写回 agent
            try:
                agent.informal_roles = new_roles
            except Exception:
                pass
            # 记录变更
            added = [r for r in new_roles if r not in old_roles]
            removed = [r for r in old_roles if r not in new_roles]
            if added or removed:
                changes.append(
                    {
                        "agent_id": aid,
                        "agent_name": _safe_attr(agent, "_name_obj", ""),
                        "species": _safe_attr(agent, "species", ""),
                        "added": added,
                        "removed": removed,
                        "current_roles": new_roles,
                        "ts": time.time(),
                    }
                )

        if changes:
            with self._lock:
                self._history.extend(changes)
                if len(self._history) > 500:
                    self._history = self._history[-500:]
            self._save()

        return {
            "ok": True,
            "evaluated_count": len(all_agents),
            "changes_count": len(changes),
            "changes": changes,
            "ts": time.time(),
        }

    def _get_agent_id(self, agent: Any) -> str:
        try:
            return agent.get_agent_id()
        except Exception:
            return f"{_safe_attr(agent, 'species', '?')}-{_safe_attr(agent, '_name_obj', '')}"

    def _collect_stats(self, agent: Any, all_agents: list) -> dict:
        """收集单个智能体的统计指标。"""
        return {
            "help_count": int(_safe_attr(agent, "_help_count", 0) or 0),
            "social_count": int(_safe_attr(agent, "_social_count", 0) or 0),
            "supervisor_interact_count": int(
                _safe_attr(agent, "_supervisor_interact_count", 0) or 0
            ),
            "teach_count": int(_safe_attr(agent, "_teach_count", 0) or 0),
            "crisis_resolved_count": int(
                _safe_attr(agent, "_crisis_resolved_count", 0) or 0
            ),
            "work_output": int(_safe_attr(agent, "_work_output", 0) or 0),
        }

    # ---------------- 查询 ----------------

    def list_roles(self) -> list[dict]:
        """列出所有活体智能体的当前角色。"""
        if self._biosphere_ref is None:
            return []
        result = []
        for lf in getattr(self._biosphere_ref, "employees", []):
            if not _safe_attr(lf, "_alive", False):
                continue
            roles = _safe_attr(lf, "informal_roles", []) or []
            if not roles:
                continue
            result.append(
                {
                    "agent_id": self._get_agent_id(lf),
                    "agent_name": _safe_attr(lf, "_name_obj", ""),
                    "species": _safe_attr(lf, "species", ""),
                    "roles": [
                        {
                            "key": r,
                            "name_zh": ROLE_DEFINITIONS.get(r, {}).get("name_zh", r),
                            "icon": ROLE_DEFINITIONS.get(r, {}).get("icon", ""),
                            "description": ROLE_DEFINITIONS.get(r, {}).get(
                                "description", ""
                            ),
                        }
                        for r in roles
                    ],
                }
            )
        return result

    def list_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._history[-limit:])

    def get_role_definitions(self) -> dict:
        return {
            k: {
                "key": k,
                "name_zh": v["name_zh"],
                "icon": v["icon"],
                "description": v["description"],
                "behavior_modifier": v["behavior_modifier"],
            }
            for k, v in ROLE_DEFINITIONS.items()
        }

    # ---------------- 调度 ----------------

    def start_scheduler(self) -> None:
        """启动每周评估调度（每 24 小时检查一次）。"""
        if self._eval_thread is not None and self._eval_thread.is_alive():
            return
        self._stop_event.clear()
        self._eval_thread = threading.Thread(
            target=self._eval_loop, daemon=True, name="role-evaluator"
        )
        self._eval_thread.start()

    def stop_scheduler(self) -> None:
        self._stop_event.set()
        if self._eval_thread is not None and self._eval_thread.is_alive():
            self._eval_thread.join(timeout=2.0)
        self._eval_thread = None

    def _eval_loop(self) -> None:
        """每周一评估一次。"""
        while not self._stop_event.is_set():
            try:
                now = time.localtime()
                today_str = time.strftime("%Y-%W", now)  # 年-周
                # 每周一评估
                if now.tm_wday == 0 and self._last_eval_date != today_str:
                    self._last_eval_date = today_str
                    self.evaluate_all()
            except Exception:
                pass
            self._stop_event.wait(3600.0)

    # ---------------- 角色冲突：技术对决 ----------------

    def trigger_tech_duel(
        self, agent_a: str, agent_b: str, task: str = "完成一个高难度算法题"
    ) -> dict:
        """触发技术对决。

        简化版：用能量 + 技能数 + 经验数 + 随机 因子决定胜者。
        真实场景应该用 LLM 给双方各跑一次任务，由监工投票。
        """
        if self._biosphere_ref is None:
            return {"ok": False, "error": "biosphere not set"}
        a = self._find_agent(agent_a)
        b = self._find_agent(agent_b)
        if a is None or b is None:
            return {"ok": False, "error": "agent not found"}

        import random

        def _score(x):
            energy = float(_safe_attr(x, "energy", 50) or 50)
            skills = len(_safe_attr(x, "skills", []) or [])
            exp = int(_safe_attr(x, "_work_output", 0) or 0)
            luck = random.random() * 20
            return energy * 0.3 + skills * 5 + exp * 0.5 + luck

        sa, sb = _score(a), _score(b)
        winner = agent_a if sa >= sb else agent_b
        loser = agent_b if sa >= sb else agent_a

        # 胜者获得 tech_leader，败者获得 tech_backbone（暂存为 tag）
        winner_agent = a if sa >= sb else b
        loser_agent = b if sa >= sb else a
        try:
            roles = list(_safe_attr(winner_agent, "informal_roles", []) or [])
            if "tech_leader" not in roles:
                roles.append("tech_leader")
                winner_agent.informal_roles = roles
        except Exception:
            pass
        try:
            roles = list(_safe_attr(loser_agent, "informal_roles", []) or [])
            if "tech_backbone" not in roles:
                roles.append("tech_backbone")
                loser_agent.informal_roles = roles
        except Exception:
            pass

        record = {
            "type": "tech_duel",
            "agent_a": agent_a,
            "agent_b": agent_b,
            "score_a": round(sa, 2),
            "score_b": round(sb, 2),
            "winner": winner,
            "loser": loser,
            "task": task,
            "ts": time.time(),
        }
        with self._lock:
            self._history.append(record)
            if len(self._history) > 500:
                self._history = self._history[-500:]
        self._save()
        return {
            "ok": True,
            "winner": winner,
            "loser": loser,
            "scores": {"a": round(sa, 2), "b": round(sb, 2)},
        }

    def _find_agent(self, agent_id: str) -> Any:
        for lf in getattr(self._biosphere_ref, "employees", []):
            try:
                if lf.get_agent_id() == agent_id:
                    return lf
            except Exception:
                pass
        return None


def get_role_evolution_engine() -> RoleEvolutionEngine:
    return RoleEvolutionEngine.get_instance()
