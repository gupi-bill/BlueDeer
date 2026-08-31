"""BlueDeer 茶水间（BreakRoom）：森林公司员工自由交流区。

功能：
- 闲聊/经验分享墙
- 任务完成后的经验交流
- 排行榜/成就展示
- 系统公告
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.task import TaskResult, TaskStatus

logger = logging.getLogger("bluedeer.breakroom")


class MessageType(Enum):
    """茶水间消息类型。"""

    CHAT = "chat"  # 闲聊
    EXPERIENCE = "experience"  # 经验分享
    ACHIEVEMENT = "achievement"  # 成就解锁
    MILESTONE = "milestone"  # 里程碑
    SYSTEM = "system"  # 系统公告


@dataclass
class BreakRoomMessage:
    """茶水间消息。"""

    msg_id: str
    msg_type: MessageType
    content: str
    author: str = ""
    timestamp: float = field(default_factory=time.time)
    likes: int = 0
    tags: list[str] = field(default_factory=list)


@dataclass
class ScheduledActivity:
    """预定的活动。"""

    activity_id: str
    name: str
    time: float
    duration: float
    participants: list[str] = field(default_factory=list)


class BreakRoom:
    """茶水间 = 员工自由交流区。

    森林公司员工在工作之余可以来这里闲聊、分享经验、
    查看排行榜和成就。
    """

    def __init__(self) -> None:
        self._messages: list[BreakRoomMessage] = []
        self._max_messages = 200
        self._activities: dict[str, ScheduledActivity] = {}

    # ---- 发布消息 ----

    def post(
        self,
        content: str,
        msg_type: MessageType = MessageType.CHAT,
        author: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """发布一条消息到茶水间。"""
        msg_id = f"br_{int(time.time() * 1000)}_{len(self._messages)}"
        msg = BreakRoomMessage(
            msg_id=msg_id,
            msg_type=msg_type,
            content=content,
            author=author,
            tags=tags or [],
        )
        self._messages.append(msg)
        # 超出上限时删除最旧的消息
        if len(self._messages) > self._max_messages:
            self._messages.pop(0)
        logger.info("茶水间 [%s] %s: %s", msg_type.value, author, content[:50])
        return msg_id

    def share_experience(self, result: TaskResult, agent_name: str = "") -> str:
        """任务完成后自动分享经验到茶水间。"""
        status_emoji = "✅" if result.status == TaskStatus.SUCCESS else "❌"
        tokens = result.token_usage.total if result.token_usage else 0
        content = (
            f"{status_emoji} 任务 {result.task_id[:8]} "
            f"({result.task_type}) 已完成，状态: {result.status.value}，"
            f"消耗 {tokens} Token"
        )
        if result.error:
            content += f"，错误: {result.error[:100]}"
        return self.post(
            content=content,
            msg_type=MessageType.EXPERIENCE,
            author=agent_name or result.agent_id,
            tags=[result.task_type, result.status.value],
        )

    def announce(self, content: str) -> str:
        """发布系统公告。"""
        return self.post(
            content=content,
            msg_type=MessageType.SYSTEM,
            author="系统",
            tags=["announcement"],
        )

    # ---- 查询 ----

    def recent(
        self, count: int = 10, msg_type: MessageType | None = None
    ) -> list[BreakRoomMessage]:
        """获取最近的消息。"""
        filtered = self._messages
        if msg_type:
            filtered = [m for m in filtered if m.msg_type == msg_type]
        return filtered[-count:]

    def like(self, msg_id: str) -> bool:
        """给消息点赞。"""
        for msg in self._messages:
            if msg.msg_id == msg_id:
                msg.likes += 1
                return True
        return False

    # ---- 统计 ----

    def stats(self) -> dict[str, Any]:
        """茶水间统计。"""
        type_counts: dict[str, int] = {}
        authors: set[str] = set()
        for m in self._messages:
            type_counts[m.msg_type.value] = type_counts.get(m.msg_type.value, 0) + 1
            if m.author:
                authors.add(m.author)
        return {
            "total_messages": len(self._messages),
            "by_type": type_counts,
            "active_authors": len(authors),
            "most_liked": max((m.likes for m in self._messages), default=0),
        }

    # ---- 活动 ----

    def schedule_activity(self, name: str, time: float, duration: float) -> str:
        """预定一个活动。"""
        activity_id = f"act_{int(time * 1000)}_{len(self._activities)}"
        self._activities[activity_id] = ScheduledActivity(
            activity_id=activity_id,
            name=name,
            time=time,
            duration=duration,
        )
        return activity_id

    def get_current_activities(self) -> list[ScheduledActivity]:
        """获取当前已开始且未结束的活动。"""
        now = __import__("time").time()
        return [
            a for a in self._activities.values() if a.time <= now <= a.time + a.duration
        ]

    def join_activity(self, activity_id: str, character: str) -> bool:
        """加入活动。"""
        act = self._activities.get(activity_id)
        if act is None:
            return False
        if character not in act.participants:
            act.participants.append(character)
        return True

    def to_dict(self) -> dict[str, Any]:
        """导出茶水间状态。"""
        return {
            "messages": [
                {
                    "msg_id": m.msg_id,
                    "type": m.msg_type.value,
                    "content": m.content,
                    "author": m.author,
                    "timestamp": m.timestamp,
                    "likes": m.likes,
                    "tags": m.tags,
                }
                for m in self._messages[-20:]  # 只返回最近 20 条
            ],
            "stats": self.stats(),
        }
