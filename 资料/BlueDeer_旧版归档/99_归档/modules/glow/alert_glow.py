"""告警分级光效：轻/中/重三级 + 6 类专项色。

融合项目：#19 strix、#20 fox-healer/test-glow、#22 glow-meter、#33 static-scan/glow-filter

三级告警：
- 轻度 LIGHT：黄光微脉冲（Token 小幅超限、单员工少量报错）
- 中度 MEDIUM：橙光闪烁（测试连续失败、梦境产出劣质）
- 重度 HEAVY：红光持续高亮（高危安全、流水线卡死、模型 API 中断）

6 类专项色：
- 安全 SECURTIY：红光（漏洞拦截）
- TOKEN：紫光（成本超限）
- DREAM：蓝光（梦境异常）
- TEST：青光（测试失败）
- GIT：绿光（仓库冲突）
- DEPENDENCY：粉光（依赖冲突）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.glow.color_downgrade import (
    RGB,
    ColorDowngradeRenderer,
    GlowLayer,
)

# ============== 告警等级 ==============


class AlertGlowLevel(Enum):
    """告警三级。"""

    LIGHT = "light"  # 轻度：黄光微脉冲
    MEDIUM = "medium"  # 中度：橙光闪烁
    HEAVY = "heavy"  # 重度：红光持续高亮


# ============== 告警专项类型 ==============


class AlertGlowCategory(Enum):
    """6 类告警专项色。"""

    SECURITY = "security"  # 安全：红光
    TOKEN = "token"  # Token：紫光
    DREAM = "dream"  # 梦境：蓝光
    TEST = "test"  # 测试：青光
    GIT = "git"  # Git：绿光
    DEPENDENCY = "dependency"  # 依赖：粉光


# 等级 → 颜色/层级
_LEVEL_CONFIG: dict[AlertGlowLevel, AlertGlowParams] = {}  # 在下方初始化


@dataclass
class AlertGlowParams:
    """告警发光参数。"""

    color: RGB
    layer: GlowLayer
    blink: bool = False
    pulse_frames: int = 1
    brightness: float = 1.0
    icon: str = "⚠"


# 初始化等级配置
_LEVEL_CONFIG = {
    AlertGlowLevel.LIGHT: AlertGlowParams(
        color=RGB(255, 220, 80),
        layer=GlowLayer.MIDGROUND,
        brightness=0.9,
        pulse_frames=2,
        icon="🟡",
    ),
    AlertGlowLevel.MEDIUM: AlertGlowParams(
        color=RGB(255, 140, 40),
        layer=GlowLayer.FOREGROUND,
        brightness=1.2,
        blink=True,
        pulse_frames=3,
        icon="🟠",
    ),
    AlertGlowLevel.HEAVY: AlertGlowParams(
        color=RGB(255, 60, 60),
        layer=GlowLayer.FOREGROUND,
        brightness=1.5,
        blink=True,
        pulse_frames=4,
        icon="🔴",
    ),
}


# 专项类型 → 颜色
_CATEGORY_COLOR: dict[AlertGlowCategory, RGB] = {
    AlertGlowCategory.SECURITY: RGB(255, 60, 60),  # 红
    AlertGlowCategory.TOKEN: RGB(180, 80, 220),  # 紫
    AlertGlowCategory.DREAM: RGB(80, 140, 240),  # 蓝
    AlertGlowCategory.TEST: RGB(80, 220, 200),  # 青
    AlertGlowCategory.GIT: RGB(80, 200, 100),  # 绿
    AlertGlowCategory.DEPENDENCY: RGB(240, 120, 180),  # 粉
}


# ============== 告警光效渲染器 ==============


class AlertGlowRenderer:
    """告警分级光效渲染器。

    职责：
    1. 按等级渲染告警文本（三级差异化光效）
    2. 按专项类型染色（6 类专属色）
    3. 渲染告警脉冲动画帧
    4. 渲染告警面板（多告警汇总）
    """

    def __init__(self, renderer: ColorDowngradeRenderer | None = None) -> None:
        self._renderer = renderer or ColorDowngradeRenderer()

    def render_alert(
        self,
        message: str,
        level: AlertGlowLevel = AlertGlowLevel.LIGHT,
        category: AlertGlowCategory | None = None,
    ) -> str:
        """渲染单条告警。

        Args:
            message: 告警文本。
            level: 告警等级。
            category: 专项类型（None 用等级默认色）。

        Returns:
            带 ANSI 发光的告警字符串。
        """
        params = _LEVEL_CONFIG[level]
        # 专项色优先（覆盖等级默认色）
        color = _CATEGORY_COLOR[category] if category else params.color
        adjusted = color.adjust_brightness(params.brightness)
        icon = params.icon
        return f"{icon} {self._renderer.render_glow(message, adjusted, params.layer, params.blink)}"

    def render_pulse_frames(
        self,
        message: str,
        level: AlertGlowLevel = AlertGlowLevel.HEAVY,
        category: AlertGlowCategory | None = None,
    ) -> list[str]:
        """渲染告警脉冲动画帧序列。"""
        params = _LEVEL_CONFIG[level]
        color = _CATEGORY_COLOR[category] if category else params.color
        frames_count = max(1, params.pulse_frames)
        result = []
        for i in range(frames_count):
            factor = 0.5 + 0.5 * (i / max(1, frames_count - 1))
            adjusted = color.adjust_brightness(factor * params.brightness)
            result.append(
                self._renderer.render_glow(
                    f"{params.icon} {message}",
                    adjusted,
                    params.layer,
                    blink=(i == 0 and params.blink),
                )
            )
        return result

    def render_alert_panel(
        self,
        alerts: list[tuple[str, AlertGlowLevel, AlertGlowCategory | None]],
    ) -> list[str]:
        """渲染告警面板（多行）。

        Args:
            alerts: [(message, level, category), ...]

        Returns:
            多行字符串列表。
        """
        if not alerts:
            return [
                self._renderer.render_glow(
                    "✅ 无活跃告警",
                    RGB(100, 200, 100),
                    GlowLayer.MIDGROUND,
                )
            ]
        lines = [
            self._renderer.render_glow(
                "🚨 告警面板",
                RGB(255, 100, 100),
                GlowLayer.FOREGROUND,
            )
        ]
        # 按等级排序：重度 > 中度 > 轻度
        level_order = {
            AlertGlowLevel.HEAVY: 0,
            AlertGlowLevel.MEDIUM: 1,
            AlertGlowLevel.LIGHT: 2,
        }
        sorted_alerts = sorted(alerts, key=lambda x: level_order.get(x[1], 99))
        for msg, level, cat in sorted_alerts:
            lines.append(self.render_alert(msg, level, cat))
        return lines

    def get_level_color(self, level: AlertGlowLevel) -> RGB:
        """获取等级对应的颜色。"""
        return _LEVEL_CONFIG[level].color

    def get_category_color(self, category: AlertGlowCategory) -> RGB:
        """获取专项类型对应的颜色。"""
        return _CATEGORY_COLOR[category]

    def list_categories(self) -> list[AlertGlowCategory]:
        """列出 6 类专项。"""
        return list(AlertGlowCategory)

    def list_levels(self) -> list[AlertGlowLevel]:
        """列出 3 个等级。"""
        return list(AlertGlowLevel)


# ============== 告警光效规则映射 ==============

# 预警类型 → (等级, 专项) 映射，对接 StatusCenter 的 AlertSummary
_ALERT_RULES: dict[str, tuple[AlertGlowLevel, AlertGlowCategory]] = {
    "token_overrun": (AlertGlowLevel.LIGHT, AlertGlowCategory.TOKEN),
    "memory_high": (AlertGlowLevel.LIGHT, AlertGlowCategory.TOKEN),
    "agent_stuck": (AlertGlowLevel.LIGHT, AlertGlowCategory.TEST),
    "nightmare_dream": (AlertGlowLevel.MEDIUM, AlertGlowCategory.DREAM),
    "secret_plaintext_risk": (AlertGlowLevel.HEAVY, AlertGlowCategory.SECURITY),
    "dependency_conflict": (AlertGlowLevel.HEAVY, AlertGlowCategory.DEPENDENCY),
}


def get_alert_rule(alert_key: str) -> tuple[AlertGlowLevel, AlertGlowCategory] | None:
    """根据预警键获取发光规则。

    Args:
        alert_key: 预警类型键（token_overrun / memory_high / ...）

    Returns:
        (等级, 专项) 元组，未知键返回 None。
    """
    return _ALERT_RULES.get(alert_key)


def list_alert_rules() -> dict[str, tuple[AlertGlowLevel, AlertGlowCategory]]:
    """列出所有告警规则。"""
    return dict(_ALERT_RULES)


_current_alert_level: AlertGlowLevel = AlertGlowLevel.LIGHT


def set_alert_level(level: AlertGlowLevel) -> None:
    """全局设置当前告警等级，影响后续告警渲染默认值。"""
    global _current_alert_level
    _current_alert_level = level


def get_alert_level() -> AlertGlowLevel:
    return _current_alert_level


def render_alert_by_current_level(
    renderer: AlertGlowRenderer,
    message: str,
    category: AlertGlowCategory | None = None,
) -> str:
    """按当前全局告警等级渲染告警。"""
    return renderer.render_alert(message, _current_alert_level, category)
