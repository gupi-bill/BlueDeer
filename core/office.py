"""BlueDeer 员工办公室（Office）：每个 Agent 的独立办公空间。

包含：
- 工牌系统（姓名、岗位、等级、特权）
- 状态面板（在线/忙碌/休息、金币、经验、好感度）
- 技能展示墙（已注册的工具）
- 办公桌（当前任务列表）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.reward import RewardSystem, get_level_perks
from core.task import Task

logger = logging.getLogger("bluedeer.office")


class WorkStatus(Enum):
    """工作状态。"""
    ONLINE = "online"          # 在线
    BUSY = "busy"              # 忙碌
    RESTING = "resting"        # 休息
    DREAMING = "dreaming"      # 梦境中
    IDLE = "idle"              # 空闲


@dataclass
class Badge:
    """员工工牌信息。"""
    agent_id: str
    name: str
    role: str
    department: str = ""
    level: int = 1
    perks: list[str] = field(default_factory=list)
    join_date: float = field(default_factory=time.time)


@dataclass
class WorkDesk:
    """办公桌 - 当前任务列表。"""
    current_task: Task | None = None
    completed_today: int = 0
    pending_count: int = 0


class Office:
    """员工办公室。

    每个 Agent 拥有一个独立办公室，展示其状态、技能、任务。
    """

    def __init__(self, agent_id: str, name: str = "", role: str = "") -> None:
        self._badge = Badge(
            agent_id=agent_id,
            name=name or agent_id,
            role=role,
        )
        self._status: WorkStatus = WorkStatus.IDLE
        self._desk = WorkDesk()
        self._skills: list[dict[str, str]] = []
        self._activity_log: list[str] = []

    # ---- 工牌 ----

    @property
    def badge(self) -> Badge:
        return self._badge

    @property
    def status(self) -> WorkStatus:
        return self._status

    def set_status(self, status: WorkStatus) -> None:
        self._status = status
        self._log(f"状态变更为: {status.value}")

    def update_badge(self, level: int, name: str = "") -> None:
        """更新工牌等级和特权。"""
        old_level = self._badge.level
        self._badge.level = level
        self._badge.perks = get_level_perks(level)
        if name:
            self._badge.name = name
        if level > old_level:
            self._log(f"升级! Lv{old_level} → Lv{level}，解锁特权: {self._badge.perks}")

    # ---- 技能 ----

    def register_skill(self, skill_name: str, description: str = "") -> None:
        """注册展示技能。"""
        self._skills.append({"name": skill_name, "description": description})
        self._log(f"注册技能: {skill_name}")

    @property
    def skills(self) -> list[dict[str, str]]:
        return list(self._skills)

    # ---- 办公桌 ----

    def assign_task(self, task: Task) -> None:
        """分配任务到办公桌。"""
        self._desk.current_task = task
        self._desk.pending_count += 1
        self._status = WorkStatus.BUSY
        self._log(f"接到新任务: {task.id[:8]} ({task.type})")

    def complete_task(self) -> None:
        """完成任务。"""
        self._desk.completed_today += 1
        self._desk.current_task = None
        self._status = WorkStatus.IDLE

    @property
    def desk(self) -> WorkDesk:
        return self._desk

    # ---- 活动日志 ----

    def _log(self, message: str) -> None:
        self._activity_log.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        if len(self._activity_log) > 50:
            self._activity_log.pop(0)

    @property
    def activity_log(self) -> list[str]:
        return list(self._activity_log)

    # ---- 导出 ----

    def to_dict(self) -> dict[str, Any]:
        """导出办公室状态。"""
        return {
            "badge": {
                "agent_id": self._badge.agent_id,
                "name": self._badge.name,
                "role": self._badge.role,
                "department": self._badge.department,
                "level": self._badge.level,
                "perks": self._badge.perks,
            },
            "status": self._status.value,
            "desk": {
                "current_task_id": self._desk.current_task.id[:8]
                    if self._desk.current_task else None,
                "completed_today": self._desk.completed_today,
                "pending_count": self._desk.pending_count,
            },
            "skills": self._skills,
            "recent_activity": self._activity_log[-10:],
        }


class OfficeManager:
    """办公室管理器 = 管理所有员工的办公室。"""

    def __init__(self) -> None:
        self._offices: dict[str, Office] = {}
        self._rooms: dict[str, dict[str, Any]] = {}
        self._occupancy: dict[str, list[str]] = {}

    def get_or_create(self, agent_id: str, name: str = "", role: str = "") -> Office:
        """获取或创建办公室。"""
        if agent_id not in self._offices:
            self._offices[agent_id] = Office(agent_id, name, role)
            logger.info("创建办公室: %s (%s)", name or agent_id, role)
        return self._offices[agent_id]

    def get(self, agent_id: str) -> Office | None:
        return self._offices.get(agent_id)

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有办公室状态。"""
        return [office.to_dict() for office in self._offices.values()]

    def stats(self) -> dict[str, Any]:
        """办公室统计。"""
        return {
            "total_offices": len(self._offices),
            "online": sum(1 for o in self._offices.values() if o.status == WorkStatus.ONLINE),
            "busy": sum(1 for o in self._offices.values() if o.status == WorkStatus.BUSY),
            "idle": sum(1 for o in self._offices.values() if o.status == WorkStatus.IDLE),
            "resting": sum(1 for o in self._offices.values() if o.status == WorkStatus.RESTING),
        }

    # ---- 会议室管理 ----

    def add_room(self, name: str, capacity: int) -> None:
        """添加会议室。"""
        self._rooms[name] = {"name": name, "capacity": capacity}
        self._occupancy.setdefault(name, [])

    def remove_room(self, name: str) -> bool:
        """删除会议室。"""
        if name in self._rooms:
            del self._rooms[name]
            self._occupancy.pop(name, None)
            return True
        return False

    def assign_occupant(self, room: str, occupant: str) -> bool:
        """分配 occupant 到 room。"""
        if room not in self._rooms:
            return False
        occupants = self._occupancy.setdefault(room, [])
        if len(occupants) < self._rooms[room]["capacity"]:
            occupants.append(occupant)
            return True
        return False

    def occupancy_report(self) -> dict[str, dict[str, Any]]:
        """返回每间会议室占用统计。"""
        return {
            name: {
                "capacity": info["capacity"],
                "occupants": list(self._occupancy.get(name, [])),
                "available": info["capacity"] - len(self._occupancy.get(name, [])),
            }
            for name, info in self._rooms.items()
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "offices": {aid: o.to_dict() for aid, o in self._offices.items()},
            "rooms": self.occupancy_report(),
            "stats": self.stats(),
        }