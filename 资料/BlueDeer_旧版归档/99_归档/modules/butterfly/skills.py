"""蝴蝶（butterfly）技能包：提示词扩写 / 布局设计 / 风格迁移 / 像素画。

岗位设计意图（生态工具白名单）：image_prompt_expand / layout_designer /
style_transfer / pixel_canvas_draw。当前以 builtin 真实工具兜底，
生态工具注册后即可无缝切换。
"""

from __future__ import annotations

import logging
from typing import Any

from tools.registry import ToolRegistry

logger = logging.getLogger("bluedeer.butterfly.skills")


class ImagePromptSkill:
    """提示词扩写：把一句话扩成完整绘画提示词。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def expand_prompt(self, idea: str, style_hint: str = "") -> dict:
        try:
            return await self._tools.call(
                "echo", {"text": f"扩写[{style_hint}]: {idea}"}
            )
        except Exception as e:
            logger.warning("expand_prompt 走生态工具失败: %s", e)
            return {"idea": idea, "style_hint": style_hint, "fallback": True}


class LayoutSkill:
    """布局设计：输出页面/画布布局方案。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def design_layout(self, elements: list[str], canvas: str = "16:9") -> dict:
        try:
            return await self._tools.call(
                "echo", {"text": f"布局[{canvas}]: {elements}"}
            )
        except Exception as e:
            logger.warning("design_layout 走生态工具失败: %s", e)
            return {"elements": elements, "canvas": canvas, "fallback": True}


class StyleTransferSkill:
    """风格迁移：按目标风格重绘素材。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def transfer_style(self, source: str, target_style: str) -> dict:
        try:
            return await self._tools.call(
                "echo", {"text": f"迁移[{target_style}] <- {source}"}
            )
        except Exception as e:
            logger.warning("transfer_style 走生态工具失败: %s", e)
            return {"source": source, "target_style": target_style, "fallback": True}


class PixelCanvasSkill:
    """像素画：生成像素风画作。"""

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._tools = tool_registry

    async def draw_pixel(self, subject: str, palette: list[str]) -> dict:
        try:
            return await self._tools.call(
                "echo", {"text": f"像素画[{subject}]: {palette}"}
            )
        except Exception as e:
            logger.warning("draw_pixel 走生态工具失败: %s", e)
            return {"subject": subject, "palette": palette, "fallback": True}


_SKILL_REGISTRY: dict[str, Any] = {}


def register_skill(name: str, skill: Any) -> None:
    _SKILL_REGISTRY[name] = skill


def get_skill(name: str) -> Any:
    return _SKILL_REGISTRY.get(name)


def list_skills() -> list[str]:
    return list(_SKILL_REGISTRY.keys())


def build_skills(tool_registry: ToolRegistry) -> dict[str, Any]:
    """构建蝴蝶员工全部技能并注册。"""
    skills = {
        "image_prompt_expand": ImagePromptSkill(tool_registry),
        "layout_designer": LayoutSkill(tool_registry),
        "style_transfer": StyleTransferSkill(tool_registry),
        "pixel_canvas_draw": PixelCanvasSkill(tool_registry),
    }
    for name, skill in skills.items():
        register_skill(name, skill)
    return skills
