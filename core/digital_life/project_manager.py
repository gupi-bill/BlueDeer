"""commit 39：长期目标管理（项目管理 + 里程碑 + 站会 + 风险 + 归档）。

零基础读者可以这样理解：
- 之前的流水线是"打零工"——一次任务一次结束
- 现在升级为"管项目"——一个项目可以跨数周，包含多个里程碑
- 每天上午 09:00 鹿自动开站会，每个员工汇报昨天/今天/阻塞
- 风险自动识别并预警监工
- 项目完成后生成总结存档，作为公司组织记忆

数据持久化：data/projects.json
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Any

# ruff: noqa: S110, S112

_PROJECTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "projects.json",
)

# 项目状态
PROJECT_PLANNING = "planning"
PROJECT_IN_PROGRESS = "in_progress"
PROJECT_BLOCKED = "blocked"
PROJECT_COMPLETED = "completed"
PROJECT_ARCHIVED = "archived"

# 里程碑状态
MILESTONE_PENDING = "pending"
MILESTONE_IN_PROGRESS = "in_progress"
MILESTONE_BLOCKED = "blocked"
MILESTONE_DONE = "done"

# 风险等级
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

# 风险类型
RISK_PROGRESS = "progress"  # 进度风险：连续 3 天未完成计划
RISK_BLOCKED = "blocked"  # 阻塞风险：关键路径被阻塞
RISK_PERSONNEL = "personnel"  # 人员风险：情感/健康持续下降


# ----------------------------------------------------------------------
# 数据结构
# ----------------------------------------------------------------------


class Milestone:
    """项目里程碑。

    零基础理解：项目的一个"中期目标"，比如"完成登录模块"。
    """

    __slots__ = (
        "completion_criteria",
        "deadline",
        "depends_on",
        "description",
        "finished_ts",
        "id",
        "name",
        "progress",
        "started_ts",
        "status",
    )

    def __init__(
        self,
        name: str,
        description: str = "",
        deadline: float | None = None,
        completion_criteria: list[str] | None = None,
        depends_on: list[str] | None = None,
    ) -> None:
        self.id: str = "m-" + uuid.uuid4().hex[:8]
        self.name: str = name
        self.description: str = description
        self.deadline: float | None = deadline
        self.completion_criteria: list[str] = completion_criteria or []
        self.depends_on: list[str] = depends_on or []  # 其他 milestone.id
        self.status: str = MILESTONE_PENDING
        self.progress: float = 0.0  # 0~100
        self.started_ts: float = 0.0
        self.finished_ts: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "deadline": self.deadline,
            "completion_criteria": self.completion_criteria,
            "depends_on": self.depends_on,
            "status": self.status,
            "progress": self.progress,
            "started_ts": self.started_ts,
            "finished_ts": self.finished_ts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Milestone:
        m = cls(
            d.get("name", ""),
            d.get("description", ""),
            d.get("deadline"),
            d.get("completion_criteria", []),
            d.get("depends_on", []),
        )
        m.id = d.get("id", m.id)
        m.status = d.get("status", MILESTONE_PENDING)
        m.progress = d.get("progress", 0.0)
        m.started_ts = d.get("started_ts", 0.0)
        m.finished_ts = d.get("finished_ts", 0.0)
        return m


class Project:
    """一个长期项目。

    零基础理解：流水线是"一次性任务"，项目是"持续数周的大事"。
    一个项目可以包含多个流水线，每个流水线推进一个里程碑。
    """

    __slots__ = (
        "archive_summary",
        "created_at",
        "daily_logs",
        "deadline",
        "description",
        "id",
        "lock",
        "milestones",
        "name",
        "owner_agent",
        "risks",
        "status",
        "team",
    )

    def __init__(
        self,
        name: str,
        description: str = "",
        owner_agent: str = "",
        team: list[str] | None = None,
        deadline: float | None = None,
    ) -> None:
        self.id: str = "p-" + uuid.uuid4().hex[:10]
        self.name: str = name
        self.description: str = description
        self.status: str = PROJECT_PLANNING
        self.milestones: list[Milestone] = []
        self.created_at: float = time.time()
        self.deadline: float | None = deadline
        self.owner_agent: str = owner_agent
        self.team: list[str] = team or []
        self.daily_logs: list[dict] = []  # 每日站会摘要
        self.risks: list[dict] = []  # 风险列表
        self.archive_summary: dict = {}  # 归档时的总结
        self.lock = threading.RLock()

    def add_milestone(self, m: Milestone) -> None:
        with self.lock:
            self.milestones.append(m)

    def overall_progress(self) -> float:
        """整体进度：所有里程碑 progress 的平均。"""
        with self.lock:
            if not self.milestones:
                return 0.0
            return sum(m.progress for m in self.milestones) / len(self.milestones)

    def to_dict(self) -> dict:
        with self.lock:
            return {
                "id": self.id,
                "name": self.name,
                "description": self.description,
                "status": self.status,
                "milestones": [m.to_dict() for m in self.milestones],
                "created_at": self.created_at,
                "deadline": self.deadline,
                "owner_agent": self.owner_agent,
                "team": list(self.team),
                "daily_logs": list(self.daily_logs[-30:]),  # 最近 30 天
                "risks": list(self.risks),
                "archive_summary": dict(self.archive_summary),
                "overall_progress": self.overall_progress(),
            }

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        p = cls(
            d.get("name", ""),
            d.get("description", ""),
            d.get("owner_agent", ""),
            d.get("team", []),
            d.get("deadline"),
        )
        p.id = d.get("id", p.id)
        p.status = d.get("status", PROJECT_PLANNING)
        p.created_at = d.get("created_at", time.time())
        p.milestones = [Milestone.from_dict(m) for m in d.get("milestones", [])]
        p.daily_logs = list(d.get("daily_logs", []))
        p.risks = list(d.get("risks", []))
        p.archive_summary = dict(d.get("archive_summary", {}))
        return p


# ----------------------------------------------------------------------
# 站会汇报模板（LLM 不可用时降级）
# ----------------------------------------------------------------------

_SPECIES_STANDUP_TEMPLATE: dict[str, str] = {
    "deer": "昨天协调了团队工作，今天继续推进项目里程碑。无阻塞。",
    "squirrel": "昨天写完了一段代码，今天准备测试和提交。无阻塞。",
    "butterfly": "昨天优化了界面布局，今天继续打磨视觉细节。无阻塞。",
    "fox": "昨天跑了测试用例，今天分析失败原因。无阻塞。",
    "hedgehog": "昨天扫描了安全漏洞，今天继续修复。无阻塞。",
    "beaver": "昨天部署了环境，今天准备扩容。无阻塞。",
    "raven": "昨天整理了记忆库，今天继续归档。无阻塞。",
    "hare": "昨天统计了性能数据，今天继续监控趋势。无阻塞。",
    "badger": "昨天排查了网络问题，今天继续监控接口。无阻塞。",
    "lark": "昨天监控了告警，今天继续观察指标。无阻塞。",
    "kite": "昨天规划了任务调度，今天继续优化排期。无阻塞。",
}


# ----------------------------------------------------------------------
# 项目管理器（单例）
# ----------------------------------------------------------------------


class ProjectManager:
    """项目管理器（单例）。

    所有项目都通过此管理器创建/查询/更新。
    独立线程每天 09:00 触发站会。
    """

    _instance: ProjectManager | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._projects: dict[str, Project] = {}
        self._biosphere_ref: Any = None
        self._standup_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_standup_date: str = ""  # YYYY-MM-DD，避免一天开多次
        self._load()

    @classmethod
    def get_instance(cls) -> ProjectManager:
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
            if os.path.exists(_PROJECTS_PATH):
                with open(_PROJECTS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for pd in data.get("projects", []):
                    p = Project.from_dict(pd)
                    self._projects[p.id] = p
        except Exception:
            pass

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_PROJECTS_PATH), exist_ok=True)
            with self._lock:
                data = {"projects": [p.to_dict() for p in self._projects.values()]}
            with open(_PROJECTS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, default=str)
        except Exception:
            pass

    # ---------------- CRUD ----------------

    def create_project(
        self,
        name: str,
        description: str = "",
        owner_agent: str = "",
        team: list[str] | None = None,
        deadline: float | None = None,
        milestones: list[dict] | None = None,
    ) -> dict:
        """创建项目。milestones 是 [{name, description, deadline, criteria, depends_on}] 列表。"""
        p = Project(name, description, owner_agent, team, deadline)
        if milestones:
            for m_def in milestones:
                m = Milestone(
                    m_def.get("name", ""),
                    m_def.get("description", ""),
                    m_def.get("deadline"),
                    m_def.get("criteria") or m_def.get("completion_criteria"),
                    m_def.get("depends_on"),
                )
                p.add_milestone(m)
        with self._lock:
            self._projects[p.id] = p
        self._save()
        return {"ok": True, "project_id": p.id}

    def list_projects(self, status: str = "", limit: int = 50) -> list[dict]:
        with self._lock:
            items = sorted(
                self._projects.values(), key=lambda p: p.created_at, reverse=True
            )
        if status:
            items = [p for p in items if p.status == status]
        return [p.to_dict() for p in items[:limit]]

    def get_project(self, pid: str) -> dict | None:
        with self._lock:
            p = self._projects.get(pid)
            return p.to_dict() if p else None

    def _get_project_obj(self, pid: str):
        """commit 39：内部使用，返回 Project 实例（不是 dict）。

        仅供 PipelineEngine / RoleEvolutionEngine 等内部模块使用，
        不暴露到前端 API。
        """
        with self._lock:
            return self._projects.get(pid)

    def update_milestone_progress(
        self, pid: str, milestone_id: str, progress: float, status: str = ""
    ) -> dict:
        """更新里程碑进度。progress 0~100。"""
        with self._lock:
            p = self._projects.get(pid)
            if p is None:
                return {"ok": False, "error": "project not found"}
            with p.lock:
                m = next((x for x in p.milestones if x.id == milestone_id), None)
                if m is None:
                    return {"ok": False, "error": "milestone not found"}
                m.progress = max(0.0, min(100.0, float(progress)))
                if status:
                    m.status = status
                if m.progress >= 100.0 and m.status != MILESTONE_DONE:
                    m.status = MILESTONE_DONE
                    m.finished_ts = time.time()
                elif m.progress > 0 and m.status == MILESTONE_PENDING:
                    m.status = MILESTONE_IN_PROGRESS
                    if not m.started_ts:
                        m.started_ts = time.time()
                # 项目状态联动
                if p.status == PROJECT_PLANNING and any(
                    x.status == MILESTONE_IN_PROGRESS for x in p.milestones
                ):
                    p.status = PROJECT_IN_PROGRESS
                if (
                    all(x.status == MILESTONE_DONE for x in p.milestones)
                    and p.milestones
                ):
                    p.status = PROJECT_COMPLETED
        self._save()
        return {"ok": True, "progress": m.progress, "status": m.status}

    def archive_project(self, pid: str) -> dict:
        """归档项目，生成总结。"""
        with self._lock:
            p = self._projects.get(pid)
            if p is None:
                return {"ok": False, "error": "project not found"}
            with p.lock:
                p.status = PROJECT_ARCHIVED
                duration = time.time() - p.created_at
                p.archive_summary = {
                    "duration_sec": round(duration, 2),
                    "duration_days": round(duration / 86400.0, 2),
                    "milestones_total": len(p.milestones),
                    "milestones_done": sum(
                        1 for m in p.milestones if m.status == MILESTONE_DONE
                    ),
                    "team_size": len(p.team),
                    "daily_logs_count": len(p.daily_logs),
                    "archived_ts": time.time(),
                }
        self._save()
        return {"ok": True, "summary": p.archive_summary}

    # ---------------- 站会 ----------------

    def start_standup_scheduler(self) -> None:
        """启动站会调度线程（每小时检查一次是否到 09:00）。"""
        if self._standup_thread is not None and self._standup_thread.is_alive():
            return
        self._stop_event.clear()
        self._standup_thread = threading.Thread(
            target=self._standup_loop, daemon=True, name="standup-scheduler"
        )
        self._standup_thread.start()

    def stop_standup_scheduler(self) -> None:
        self._stop_event.set()
        if self._standup_thread is not None and self._standup_thread.is_alive():
            self._standup_thread.join(timeout=2.0)
        self._standup_thread = None

    def _standup_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                now = time.localtime()
                today_str = time.strftime("%Y-%m-%d", now)
                # 每天 09:00 触发一次
                if now.tm_hour == 9 and self._last_standup_date != today_str:
                    self._last_standup_date = today_str
                    self.run_standup()
            except Exception:
                pass
            self._stop_event.wait(3600.0)  # 1 小时检查一次

    def run_standup(self) -> dict:
        """执行一次站会。返回所有项目的站会摘要。"""
        results: list[dict] = []
        with self._lock:
            projects = [
                p
                for p in self._projects.values()
                if p.status in (PROJECT_IN_PROGRESS, PROJECT_BLOCKED)
            ]
        for p in projects:
            summary = self._run_standup_for_project(p)
            results.append(summary)
        return {"ok": True, "standups": results, "ts": time.time()}

    def _run_standup_for_project(self, p: Project) -> dict:
        """为单个项目生成站会摘要。"""
        reports: list[dict] = []
        # 找团队中活体智能体
        agents: list = []
        if self._biosphere_ref is not None:
            for lf in getattr(self._biosphere_ref, "employees", []):
                if not getattr(lf, "_alive", False):
                    continue
                sp = getattr(lf, "species", "")
                if sp in p.team or not p.team:
                    agents.append(lf)

        for lf in agents:
            try:
                report = lf.generate_standup_report(p.to_dict())
            except Exception:
                report = {
                    "agent": getattr(lf, "_name_obj", ""),
                    "species": getattr(lf, "species", ""),
                    "yesterday": "",
                    "today": _SPECIES_STANDUP_TEMPLATE.get(
                        getattr(lf, "species", ""), "无汇报。"
                    ),
                    "blockers": "",
                }
            reports.append(report)

        # 鹿汇总
        deer_summary = ""
        progress = p.overall_progress()
        upcoming = self._upcoming_milestones(p, days=3)
        if upcoming:
            names = ", ".join(m.name for m in upcoming)
            deer_summary = (
                f"项目整体进度 {progress:.0f}%。" f"未来 3 天内到期的里程碑：{names}。"
            )

        standup = {
            "project_id": p.id,
            "project_name": p.name,
            "date": time.strftime("%Y-%m-%d %H:%M", time.localtime()),
            "ts": time.time(),
            "reports": reports,
            "deer_summary": deer_summary,
            "overall_progress": progress,
        }
        with p.lock:
            p.daily_logs.append(standup)
            if len(p.daily_logs) > 90:
                p.daily_logs = p.daily_logs[-90:]
        self._save()
        return standup

    def _upcoming_milestones(self, p: Project, days: int = 3) -> list[Milestone]:
        """未来 N 天内到期的未完成里程碑。"""
        now = time.time()
        threshold = now + days * 86400
        result = []
        with p.lock:
            for m in p.milestones:
                if m.status == MILESTONE_DONE:
                    continue
                if m.deadline and now <= m.deadline <= threshold:
                    result.append(m)
        return result

    # ---------------- 风险预警 ----------------

    def scan_risks(self) -> list[dict]:
        """扫描所有项目的风险。"""
        risks_found: list[dict] = []
        with self._lock:
            projects = list(self._projects.values())
        for p in projects:
            with p.lock:
                # 1. 里程碑即将逾期
                for m in p.milestones:
                    if m.status == MILESTONE_DONE:
                        continue
                    if m.deadline and m.progress < 70.0:
                        days_left = (m.deadline - time.time()) / 86400.0
                        if days_left < 3:
                            risk = {
                                "project_id": p.id,
                                "project_name": p.name,
                                "type": RISK_PROGRESS,
                                "level": RISK_HIGH if days_left < 1 else RISK_MEDIUM,
                                "description": (
                                    f"里程碑「{m.name}」将于 "
                                    f"{days_left:.1f} 天后到期，"
                                    f"当前进度 {m.progress:.0f}%"
                                ),
                                "ts": time.time(),
                            }
                            risks_found.append(risk)
                            self._add_risk_to_project(p, risk)
                # 2. 阻塞依赖
                done_ids = {m.id for m in p.milestones if m.status == MILESTONE_DONE}
                for m in p.milestones:
                    if m.status == MILESTONE_DONE:
                        continue
                    for dep_id in m.depends_on:
                        if dep_id not in done_ids:
                            risk = {
                                "project_id": p.id,
                                "project_name": p.name,
                                "type": RISK_BLOCKED,
                                "level": RISK_MEDIUM,
                                "description": (
                                    f"里程碑「{m.name}」依赖「{dep_id}」"
                                    f"未完成，已阻塞"
                                ),
                                "ts": time.time(),
                            }
                            risks_found.append(risk)
                            self._add_risk_to_project(p, risk)
                # 3. 人员风险：团队中智能体健康/情感持续下降
                if self._biosphere_ref is not None:
                    for lf in getattr(self._biosphere_ref, "employees", []):
                        if not getattr(lf, "_alive", False):
                            continue
                        sp = getattr(lf, "species", "")
                        if p.team and sp not in p.team:
                            continue
                        energy = float(getattr(lf, "energy", 80) or 80)
                        mood = float(getattr(lf, "mood_score", 50) or 50)
                        illness = getattr(lf, "illness", None)
                        if illness is not None or energy < 20 or mood < 20:
                            risk = {
                                "project_id": p.id,
                                "project_name": p.name,
                                "type": RISK_PERSONNEL,
                                "level": RISK_HIGH if illness else RISK_MEDIUM,
                                "description": (
                                    f"团队成员 {sp} 状态不佳："
                                    f"能量 {energy:.0f}，情绪 {mood:.0f}"
                                    + ("，生病" if illness else "")
                                ),
                                "ts": time.time(),
                            }
                            risks_found.append(risk)
                            self._add_risk_to_project(p, risk)
        if risks_found:
            self._save()
        return risks_found

    def _add_risk_to_project(self, p: Project, risk: dict) -> None:
        """去重添加风险到项目。"""
        with p.lock:
            # 同类型同描述的风险不重复添加
            for r in p.risks:
                if r.get("type") == risk.get("type") and r.get(
                    "description"
                ) == risk.get("description"):
                    return
            p.risks.append(risk)
            if len(p.risks) > 50:
                p.risks = p.risks[-50:]

    def list_risks(self, project_id: str = "") -> list[dict]:
        with self._lock:
            if project_id:
                p = self._projects.get(project_id)
                return list(p.risks) if p else []
            result = []
            for p in self._projects.values():
                result.extend(p.risks)
            return result

    # ---------------- 站会历史查询 ----------------

    def list_standups(self, project_id: str = "", limit: int = 20) -> list[dict]:
        with self._lock:
            if project_id:
                p = self._projects.get(project_id)
                return list(p.daily_logs[-limit:]) if p else []
            result = []
            for p in self._projects.values():
                result.extend(p.daily_logs)
            result.sort(key=lambda x: x.get("ts", 0), reverse=True)
            return result[:limit]


def get_project_manager() -> ProjectManager:
    return ProjectManager.get_instance()
