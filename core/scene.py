"""BlueDeer 总经理办公室（CEO Office）：全局调度中心。

整合所有办公空间到统一的场景管理：
- 资料库（Library）：知识中心
- 茶水间（BreakRoom）：员工交流区
- 办公室（OfficeManager）：员工个人空间
- 休息区（RestArea）：放松回顾区
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from core.breakroom import BreakRoom
from core.library import Library
from core.office import OfficeManager
from core.restarea import RestArea


class TransitionEffect(Enum):
    FADE = "fade"
    SLIDE = "slide"


logger = logging.getLogger("bluedeer.scene")


class CEOOffice:
    """总经理办公室 = 全局调度中心。

    忧郁鹿（Harness）的办公场所，整合所有办公空间：
    - 资料库：知识管理
    - 茶水间：员工交流
    - 办公室管理：员工个人空间
    - 休息区：放松回顾
    """

    def __init__(
        self,
        library: Library | None = None,
        breakroom: BreakRoom | None = None,
        office_manager: OfficeManager | None = None,
        rest_area: RestArea | None = None,
    ) -> None:
        self.library = library or Library()
        self.breakroom = breakroom or BreakRoom()
        self.office_manager = office_manager or OfficeManager()
        self.rest_area = rest_area or RestArea()
        self._current_scene = "office"
        self._scene_stack: list[str] = ["office"]

    # ---- 全场景状态 ----

    def status(self) -> dict[str, Any]:
        """获取全场景状态。"""
        return {
            "library": self.library.stats(),
            "breakroom": self.breakroom.stats(),
            "offices": self.office_manager.stats(),
            "rest_area": self.rest_area.stats(),
        }

    def to_dict(self) -> dict[str, Any]:
        """导出全场景数据。"""
        return {
            "library": self.library.to_dict(),
            "breakroom": self.breakroom.to_dict(),
            "offices": self.office_manager.to_dict(),
            "rest_area": self.rest_area.to_dict(),
        }

    # ---- 会议 ----

    # ---- 场景切换 ----

    def transition_to(self, next_scene: str, effect: str = "fade") -> dict[str, Any]:
        """切换到下一个场景。"""
        self._scene_stack.append(self._current_scene)
        self._current_scene = next_scene
        return {
            "from": self._scene_stack[-2] if len(self._scene_stack) > 1 else None,
            "to": next_scene,
            "effect": effect,
        }

    def get_current_scene(self) -> str:
        """获取当前场景名。"""
        return self._current_scene

    def push_scene(self, scene: str) -> None:
        """将场景压入栈。"""
        self._scene_stack.append(scene)
        self._current_scene = scene

    def pop_scene(self) -> str | None:
        """弹出栈顶场景并返回。"""
        if len(self._scene_stack) > 1:
            self._scene_stack.pop()
            self._current_scene = self._scene_stack[-1]
            return self._current_scene
        return None

    # ---- 会议 ----

    def hold_meeting(self, topic: str, participants: list[str]) -> dict[str, Any]:
        """召开会议。"""
        meeting_id = f"mtg_{int(__import__('time').time() * 1000)}"
        announcement = (
            f"📍 会议开始 [{meeting_id[:8]}]: {topic}，参会: {', '.join(participants)}"
        )
        msg_id = self.breakroom.announce(announcement)
        return {
            "meeting_id": meeting_id,
            "topic": topic,
            "participants": participants,
            "announcement_id": msg_id,
        }
