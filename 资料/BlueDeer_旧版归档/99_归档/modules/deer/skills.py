"""鹿（deer）技能包：任务编排 / 共识投票 / 事件发布 / 流水线规划。

岗位设计意图（生态工具白名单）：task_orchestrate / consensus_vote /
event_bus_publish / pipeline_plan。当前工具注册表以 builtin 真实工具为准，
生态工具名在 digital_life 生态侧注册后即可无缝切换。
"""

from __future__ import annotations

import logging
from typing import Any

from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.deer.skills")


class TaskOrchestrateSkill:
    """任务编排：拆解任务并分派到各执行线。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def orchestrate(self, goal: str, subtasks: list[str]) -> dict:
        try:
            return await self._tools.call("echo", {"text": f"编排[{goal}]: {subtasks}"})
        except Exception as e:
            logger.warning("orchestrate 走生态工具失败: %s", e)
            return {"goal": goal, "subtasks": subtasks, "fallback": True}


class ConsensusVoteSkill:
    """共识投票：对决策项收集意见并投票。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def vote(self, topic: str, options: list[str]) -> dict:
        try:
            return await self._tools.call("echo", {"text": f"投票[{topic}]: {options}"})
        except Exception as e:
            logger.warning("vote 走生态工具失败: %s", e)
            return {"topic": topic, "options": options, "fallback": True}


class EventBusPublishSkill:
    """事件发布：向森林事件总线广播消息。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def publish(self, event_type: str, data: dict) -> dict:
        try:
            return await self._tools.call(
                "echo", {"text": f"广播[{event_type}]: {data}"}
            )
        except Exception as e:
            logger.warning("publish 走生态工具失败: %s", e)
            return {"event_type": event_type, "data": data, "fallback": True}


class PipelinePlanSkill:
    """流水线规划：制定阶段化执行计划。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def plan(self, stages: list[dict]) -> dict:
        try:
            return await self._tools.call("echo", {"text": f"流水线: {stages}"})
        except Exception as e:
            logger.warning("plan 走生态工具失败: %s", e)
            return {"stages": stages, "fallback": True}


_SKILL_REGISTRY: dict[str, Any] = {}


def register_skill(name: str, skill: Any) -> None:
    _SKILL_REGISTRY[name] = skill


def get_skill(name: str) -> Any:
    return _SKILL_REGISTRY.get(name)


def list_skills() -> list[str]:
    return list(_SKILL_REGISTRY.keys())


def build_skills(tool_registry: ToolRegistry) -> dict[str, Any]:
    """构建鹿员工全部技能并注册。"""
    skills = {
        "task_orchestrate": TaskOrchestrateSkill(tool_registry),
        "consensus_vote": ConsensusVoteSkill(tool_registry),
        "event_bus_publish": EventBusPublishSkill(tool_registry),
        "pipeline_plan": PipelinePlanSkill(tool_registry),
    }
    for name, skill in skills.items():
        register_skill(name, skill)
    return skills
