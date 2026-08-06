"""角色光晕系统：11 名员工 × 4 状态发光帧。

融合项目：#11 agency-agents、#13 hermes-agent、#23 animal-glow、#49 persona-glow/mood

11 名员工（含灵音雀）：
1. squirrel（较真松鼠）- 代码生成
2. fox（狡黠狐狸）- 测试质量
3. hedgehog（戒备猬）- 安全审计
4. beaver（勤恳海狸）- GitHub 运维
5. owl（博识鸮）- 资料归档
6. soft_rabbit（软耳兔）- 像素美术
7. fox_security（安全狐狸）- 安全测试
8. fox_art（美术狐狸）- 美术规范测试
9. hedgehog_static（静态猬）- 静态扫描
10. hedgehog_runtime（运行时猬）- 运行时审计
11. hedgehog_keymgmt（密钥猬）- 密钥管理
12. sparrow（灵音雀）- 状态播报

4 状态：在岗/休眠/故障/成就
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from modules.glow.color_downgrade import (
    RGB,
    ColorDowngradeRenderer,
    GlowLayer,
    snap_to_grid,
)

# ============== 角色状态 ==============


class RoleState(Enum):
    """角色 4 状态。"""

    ONLINE = "online"  # 在岗：常亮柔和光
    SLEEPING = "sleeping"  # 休眠：低亮度微光
    ERROR = "error"  # 故障：红色脉冲闪烁
    ACHIEVEMENT = "achievement"  # 成就解锁：金色爆发闪光


# ============== 角色光晕配置 ==============


@dataclass
class RoleGlowConfig:
    """单名角色光晕配置。"""

    agent_id: str
    role: str
    # 专属主色（RGB）
    primary_color: RGB = field(default_factory=lambda: RGB(120, 180, 240))
    # 像素精灵符号
    sprite: str = "·"
    # 64px 像素画布坐标（8px 网格对齐）
    canvas_x: int = 0
    canvas_y: int = 0
    # 各状态发光参数
    state_configs: dict[RoleState, StateGlowParams] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.state_configs:
            self.state_configs = _default_state_params(self.primary_color)


@dataclass
class StateGlowParams:
    """单状态发光参数。"""

    color: RGB  # 发光颜色
    layer: GlowLayer  # Z 轴层级
    brightness: float = 1.0  # 亮度系数 0-1.5
    blink: bool = False  # 是否闪烁
    pulse_frames: int = 1  # 脉冲动画帧数


def _default_state_params(primary: RGB) -> dict[RoleState, StateGlowParams]:
    """根据主色生成 4 状态默认参数。"""
    return {
        RoleState.ONLINE: StateGlowParams(
            color=primary,
            layer=GlowLayer.MIDGROUND,
            brightness=1.0,
        ),
        RoleState.SLEEPING: StateGlowParams(
            color=primary.adjust_brightness(0.4),
            layer=GlowLayer.BACKGROUND,
            brightness=0.5,
        ),
        RoleState.ERROR: StateGlowParams(
            color=RGB(255, 60, 60),
            layer=GlowLayer.FOREGROUND,
            brightness=1.3,
            blink=True,
            pulse_frames=3,
        ),
        RoleState.ACHIEVEMENT: StateGlowParams(
            color=RGB(255, 200, 60),
            layer=GlowLayer.FOREGROUND,
            brightness=1.5,
            pulse_frames=4,
        ),
    }


# ============== 11+1 名角色预设 ==============

_ROLE_PRESETS: dict[str, RoleGlowConfig] = {
    "squirrel": RoleGlowConfig(
        agent_id="squirrel",
        role="代码生成",
        primary_color=RGB(180, 100, 60),
        sprite="🐿",
        canvas_x=8,
        canvas_y=8,
    ),
    "fox": RoleGlowConfig(
        agent_id="fox",
        role="测试质量",
        primary_color=RGB(220, 120, 50),
        sprite="🦊",
        canvas_x=24,
        canvas_y=8,
    ),
    "hedgehog": RoleGlowConfig(
        agent_id="hedgehog",
        role="安全审计",
        primary_color=RGB(140, 100, 80),
        sprite="🦔",
        canvas_x=40,
        canvas_y=8,
    ),
    "beaver": RoleGlowConfig(
        agent_id="beaver",
        role="GitHub运维",
        primary_color=RGB(150, 110, 70),
        sprite="🦫",
        canvas_x=56,
        canvas_y=8,
    ),
    "owl": RoleGlowConfig(
        agent_id="owl",
        role="资料归档",
        primary_color=RGB(180, 160, 100),
        sprite="🦉",
        canvas_x=8,
        canvas_y=24,
    ),
    "soft_rabbit": RoleGlowConfig(
        agent_id="soft_rabbit",
        role="像素美术",
        primary_color=RGB(230, 180, 200),
        sprite="🐰",
        canvas_x=24,
        canvas_y=24,
    ),
    "fox_security": RoleGlowConfig(
        agent_id="fox_security",
        role="安全测试",
        primary_color=RGB(200, 80, 80),
        sprite="🦊",
        canvas_x=40,
        canvas_y=24,
    ),
    "fox_art": RoleGlowConfig(
        agent_id="fox_art",
        role="美术规范测试",
        primary_color=RGB(220, 140, 180),
        sprite="🦊",
        canvas_x=56,
        canvas_y=24,
    ),
    "hedgehog_static": RoleGlowConfig(
        agent_id="hedgehog_static",
        role="静态扫描",
        primary_color=RGB(160, 110, 90),
        sprite="🦔",
        canvas_x=8,
        canvas_y=40,
    ),
    "hedgehog_runtime": RoleGlowConfig(
        agent_id="hedgehog_runtime",
        role="运行时审计",
        primary_color=RGB(180, 130, 110),
        sprite="🦔",
        canvas_x=24,
        canvas_y=40,
    ),
    "hedgehog_keymgmt": RoleGlowConfig(
        agent_id="hedgehog_keymgmt",
        role="密钥管理",
        primary_color=RGB(120, 90, 140),
        sprite="🦔",
        canvas_x=40,
        canvas_y=40,
    ),
    "sparrow": RoleGlowConfig(
        agent_id="sparrow",
        role="状态播报",
        primary_color=RGB(120, 200, 240),
        sprite="🐦",
        canvas_x=56,
        canvas_y=40,
    ),
}


def get_role_preset(agent_id: str) -> RoleGlowConfig | None:
    """获取角色预设。"""
    return _ROLE_PRESETS.get(agent_id)


def list_role_ids() -> list[str]:
    """列出所有角色 ID（12 个）。"""
    return list(_ROLE_PRESETS.keys())


# ============== 角色光晕渲染器 ==============


class RoleGlowRenderer:
    """角色光晕渲染器。

    职责：
    1. 渲染单角色单状态发光精灵
    2. 渲染多角色全景光晕面板
    3. 输出脉冲动画帧序列
    """

    def __init__(self, renderer: ColorDowngradeRenderer | None = None) -> None:
        self._renderer = renderer or ColorDowngradeRenderer()

    def render_role(
        self,
        agent_id: str,
        state: RoleState = RoleState.ONLINE,
        custom_text: str | None = None,
    ) -> str:
        """渲染单角色发光文本。

        Args:
            agent_id: 角色 ID。
            state: 角色状态。
            custom_text: 自定义文本（默认用 sprite 符号）。

        Returns:
            带 ANSI 发光的字符串。
        """
        config = _ROLE_PRESETS.get(agent_id)
        if config is None:
            # 未知角色用默认配置
            config = RoleGlowConfig(
                agent_id=agent_id,
                role="unknown",
                primary_color=RGB(150, 150, 150),
                sprite="?",
            )
        params = config.state_configs.get(state, config.state_configs[RoleState.ONLINE])
        text = custom_text if custom_text is not None else config.sprite
        # 应用状态亮度
        adjusted_color = params.color.adjust_brightness(params.brightness)
        return self._renderer.render_glow(
            text,
            adjusted_color,
            params.layer,
            params.blink,
        )

    def render_role_with_label(
        self,
        agent_id: str,
        state: RoleState = RoleState.ONLINE,
    ) -> str:
        """渲染角色精灵 + 标签（角色名）。"""
        config = _ROLE_PRESETS.get(agent_id) or RoleGlowConfig(
            agent_id=agent_id,
            role="unknown",
            sprite="?",
        )
        sprite_glow = self.render_role(agent_id, state)
        label = f"{config.role}"
        return f"{sprite_glow} {label}"

    def render_pulse_frames(
        self,
        agent_id: str,
        state: RoleState = RoleState.ACHIEVEMENT,
    ) -> list[str]:
        """渲染脉冲动画帧序列。"""
        config = _ROLE_PRESETS.get(agent_id)
        if config is None:
            return [self.render_role(agent_id, state)]
        params = config.state_configs.get(state, config.state_configs[RoleState.ONLINE])
        frames_count = max(1, params.pulse_frames)
        result = []
        for i in range(frames_count):
            factor = 0.6 + 0.4 * (i / max(1, frames_count - 1))
            adjusted = params.color.adjust_brightness(factor * params.brightness)
            result.append(
                self._renderer.render_glow(
                    config.sprite,
                    adjusted,
                    params.layer,
                    blink=(i == 0 and params.blink),
                )
            )
        return result

    def render_panorama(self, states: dict[str, RoleState] | None = None) -> str:
        """渲染多角色全景光晕面板（12 角色一行）。

        Args:
            states: agent_id → 状态映射；None 表示全部 ONLINE。

        Returns:
            全景发光字符串。
        """
        states = states or {}
        cells = []
        for agent_id in list_role_ids():
            state = states.get(agent_id, RoleState.ONLINE)
            cells.append(self.render_role(agent_id, state))
        return " ".join(cells)

    def render_panorama_grid(
        self,
        states: dict[str, RoleState] | None = None,
        cols: int = 4,
    ) -> list[str]:
        """渲染多角色全景网格（每行 cols 个）。

        Returns:
            多行字符串列表。
        """
        states = states or {}
        agent_ids = list_role_ids()
        lines = []
        for i in range(0, len(agent_ids), cols):
            row_agents = agent_ids[i : i + cols]
            cells = []
            for aid in row_agents:
                state = states.get(aid, RoleState.ONLINE)
                config = _ROLE_PRESETS.get(aid)
                if config is None:
                    continue
                # 网格对齐坐标
                x, y = snap_to_grid(config.canvas_x, config.canvas_y)
                cells.append(
                    f"[{x:2d},{y:2d}]{self.render_role_with_label(aid, state)}"
                )
            lines.append(" | ".join(cells))
        return lines

    def get_role_color(self, agent_id: str, state: RoleState = RoleState.ONLINE) -> RGB:
        """获取角色在某状态下的发光颜色。"""
        config = _ROLE_PRESETS.get(agent_id)
        if config is None:
            return RGB(150, 150, 150)
        params = config.state_configs.get(state, config.state_configs[RoleState.ONLINE])
        return params.color.adjust_brightness(params.brightness)

    def render_animation_sequence(
        self,
        agent_id: str,
        states: list[RoleState],
    ) -> list[str]:
        """渲染动画状态序列帧（多状态切换动画）。"""
        frames = []
        for state in states:
            frames.append(self.render_role(agent_id, state))
        return frames

    def get_role_effect(self, agent_id: str, state: RoleState) -> dict[str, Any]:
        """获取角色效果参数（颜色 / 层级 / 脉冲 / 闪烁）。"""
        config = _ROLE_PRESETS.get(agent_id)
        if config is None:
            return {
                "color": RGB(150, 150, 150),
                "layer": GlowLayer.MIDGROUND,
                "brightness": 1.0,
                "blink": False,
                "pulse_frames": 1,
            }
        params = config.state_configs.get(state, config.state_configs[RoleState.ONLINE])
        return {
            "color": params.color,
            "layer": params.layer,
            "brightness": params.brightness,
            "blink": params.blink,
            "pulse_frames": params.pulse_frames,
        }
