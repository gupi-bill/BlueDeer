"""UI 板块二：分层景深视觉系统（全环境通用）。

三大能力（低成本拉高高级感，扩容点极多）：
1. 通用 Z 轴分层渲染调度：底层背景→中层角色/任务卡片→顶层弹窗告警/悬浮提示
2. 跨端轻量化微动效统一规范：悬停/点击/加载/报错/成就/解锁/休眠/告警 8 套基础动效
3. 跨设备自适应景深缩放：大屏多列/常规/紧凑/手机竖栏自动切换

对标成就系统逻辑：动效与分层均可批量扩展（32 套细分动画、多层浮动面板）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from modules.soft_rabbit.pixel_render import (
    PALETTE_16,
    AnsiTerminalBackend,
    Color,
    PixelRenderEngine,
    RenderRouter,
)


# ============== Z 轴分层定义 ==============

class DepthLayer(Enum):
    """Z 轴层级（值越大越靠上）。"""
    BACKGROUND = 0   # 底层：画布背景、工位区块
    MIDGROUND = 1    # 中层：角色头像、任务卡片
    FOREGROUND = 2   # 顶层：弹窗、告警
    OVERLAY = 3      # 最顶层：悬浮提示、光标


class LayeredCanvas:
    """分层画布：各层独立绘制，合成时按 Z 序叠加。

    上层非空格字符覆盖下层，实现景深叠加效果。
    各平台自动转换：终端用绘制顺序、Web 用 z-index、桌面用图层分组。
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._layers: dict[DepthLayer, list[list[tuple[Color, str]]]] = {
            layer: self._empty_buffer() for layer in DepthLayer
        }

    def _empty_buffer(self) -> list[list[tuple[Color, str]]]:
        bg = PALETTE_16["bg"]
        return [[(bg, " ") for _ in range(self.width)] for _ in range(self.height)]

    def clear_layer(self, layer: DepthLayer) -> None:
        """清空指定层。"""
        self._layers[layer] = self._empty_buffer()

    def clear_all(self) -> None:
        for layer in DepthLayer:
            self.clear_layer(layer)

    def set_pixel(
        self, layer: DepthLayer, x: int, y: int, color: Color, char: str = " ",
    ) -> None:
        """在指定层设置像素（越界忽略）。"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self._layers[layer][y][x] = (color, char if char else " ")

    def draw_rect(
        self, layer: DepthLayer, x: int, y: int, w: int, h: int,
        color: Color, char: str = " ",
    ) -> None:
        """在指定层填充矩形。"""
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set_pixel(layer, xx, yy, color, char)

    def draw_text(
        self, layer: DepthLayer, x: int, y: int, text: str, color: Color,
    ) -> None:
        """在指定层绘制文本。"""
        for i, ch in enumerate(text):
            self.set_pixel(layer, x + i, y, color, ch)

    def compose_buffer(self) -> list[list[tuple[Color, str]]]:
        """合成所有层：从底到顶，上层非空格字符覆盖下层。"""
        result = self._empty_buffer()
        for layer in sorted(DepthLayer, key=lambda l: l.value):
            buf = self._layers[layer]
            for y in range(self.height):
                for x in range(self.width):
                    color, char = buf[y][x]
                    if char.strip():  # 非空格字符覆盖
                        result[y][x] = (color, char)
        return result

    def render(
        self, env: str = "ansi", color_level: str = "256",
    ) -> str:
        """合成后用指定后端渲染。"""
        backend = RenderRouter().select(env, self.width, self.height)
        if isinstance(backend, AnsiTerminalBackend):
            backend._color_level = color_level
        backend._buffer = self.compose_buffer()
        return backend.render()


# ============== 跨端轻量化微动效 ==============

@dataclass
class MicroAnimation:
    """微动效定义：纯字符/低算力像素帧实现。

    所有平台流畅不卡顿，统一动效节奏，无平台间动画割裂。
    """
    name: str
    frames: list[str] = field(default_factory=list)
    duration: float = 0.5       # 单轮时长（秒）
    loop: bool = True

    def frame_at(self, t: float) -> str:
        """获取时刻 t（秒）应显示的帧字符。

        loop=True 循环播放；loop=False 播完停在最后一帧。
        """
        if not self.frames:
            return ""
        n = len(self.frames)
        if self.duration <= 0:
            return self.frames[0]
        idx = int(t / self.duration * n)
        if self.loop:
            return self.frames[idx % n]
        return self.frames[min(idx, n - 1)]

    @property
    def frame_count(self) -> int:
        return len(self.frames)


class AnimationRegistry:
    """动效注册表：内置 8 套基础动效，支持批量扩展。

    对标成就系统：可从 8 套扩展到 32 套细分状态动画
    （任务排队/休眠/编译/测试/Git推送/模型切换/内存告警等）。
    """

    def __init__(self) -> None:
        self._animations: dict[str, MicroAnimation] = dict(self._builtin())

    @staticmethod
    def _builtin() -> dict[str, MicroAnimation]:
        """内置 8 套基础动效。"""
        return {
            "hover": MicroAnimation("hover", ["▁", "▂", "▃", "▂"], 0.3),
            "click": MicroAnimation("click", ["█", "▓", "▒", "░"], 0.2),
            "loading": MicroAnimation(
                "loading",
                ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
                1.0,
            ),
            "error_pulse": MicroAnimation("error_pulse", ["!", " ", "!", " "], 0.4),
            "achievement": MicroAnimation(
                "achievement", ["✦", "✧", "★", "✧", "✦"], 1.0, loop=False,
            ),
            "unlock": MicroAnimation("unlock", ["▣", "▢", "▣"], 0.5),
            "sleep": MicroAnimation("sleep", ["~", "z", "Z", "z"], 1.2),
            "alert": MicroAnimation("alert", ["▲", "▴", "▲", " "], 0.6),
        }

    def get(self, name: str) -> MicroAnimation | None:
        """获取动效（不存在返回 None）。"""
        return self._animations.get(name)

    def register(self, animation: MicroAnimation) -> None:
        """注册/覆盖动效。"""
        self._animations[animation.name] = animation

    def list_names(self) -> list[str]:
        """列出全部动效名。"""
        return sorted(self._animations.keys())

    def __len__(self) -> int:
        return len(self._animations)

    def __contains__(self, name: str) -> bool:
        return name in self._animations


# 全局默认动效注册表
DEFAULT_ANIMATIONS = AnimationRegistry()


# ============== 跨设备自适应景深缩放 ==============

class LayoutMode(Enum):
    """布局模式（按窗口尺寸自适应）。"""
    WIDE = "wide"        # 大屏：多列完整面板
    NORMAL = "normal"    # 常规：标准看板
    COMPACT = "compact"  # 紧凑：折叠侧边栏
    MOBILE = "mobile"    # 手机：竖向单栏


@dataclass
class LayoutParams:
    """布局参数（由 AdaptiveScaler 按 LayoutMode 给出）。"""
    mode: LayoutMode
    columns: int = 1              # 主面板列数
    sidebar_visible: bool = True  # 侧边栏可见
    panels_compact: bool = False  # 面板压缩
    char_width: int = 80          # 字符宽度
    show_decorations: bool = True  # 装饰元素可见


class AdaptiveScaler:
    """跨设备自适应景深缩放。

    自动读取窗口尺寸，大屏展开多列完整面板，
    窄窗口自动折叠侧边栏、压缩图表、精简文字，
    手机网页端自动切换竖向单栏布局。
    """

    # 布局模式阈值（按字符宽度）
    _WIDE_THRESHOLD = 120
    _NORMAL_THRESHOLD = 80
    _COMPACT_THRESHOLD = 50

    def detect(self, width: int, height: int = 24) -> LayoutMode:
        """根据窗口尺寸检测布局模式。"""
        if width >= self._WIDE_THRESHOLD:
            return LayoutMode.WIDE
        if width >= self._NORMAL_THRESHOLD:
            return LayoutMode.NORMAL
        if width >= self._COMPACT_THRESHOLD:
            return LayoutMode.COMPACT
        return LayoutMode.MOBILE

    def layout_params(self, width: int, height: int = 24) -> LayoutParams:
        """根据窗口尺寸给出完整布局参数。"""
        mode = self.detect(width, height)
        if mode == LayoutMode.WIDE:
            return LayoutParams(
                mode=mode, columns=3, sidebar_visible=True,
                panels_compact=False, char_width=width, show_decorations=True,
            )
        if mode == LayoutMode.NORMAL:
            return LayoutParams(
                mode=mode, columns=2, sidebar_visible=True,
                panels_compact=False, char_width=width, show_decorations=True,
            )
        if mode == LayoutMode.COMPACT:
            return LayoutParams(
                mode=mode, columns=1, sidebar_visible=False,
                panels_compact=True, char_width=width, show_decorations=False,
            )
        # MOBILE
        return LayoutParams(
            mode=mode, columns=1, sidebar_visible=False,
            panels_compact=True, char_width=width, show_decorations=False,
        )


# ============== 分层场景渲染器（组合三件套） ==============

class LayeredSceneRenderer:
    """分层场景渲染器：组合 Z 轴分层 + 微动效 + 自适应缩放。

    上层只需声明各层内容，自动合成渲染。
    用法：
        renderer = LayeredSceneRenderer(width=80, height=24)
        renderer.draw_background(...)   # 底层背景
        renderer.draw_midground(...)    # 中层卡片
        renderer.draw_foreground(...)   # 顶层弹窗
        frame = renderer.render_frame(t=1.5)  # 含动效时刻
    """

    def __init__(self, width: int, height: int) -> None:
        self._canvas = LayeredCanvas(width, height)
        self._anims = AnimationRegistry()
        self._scaler = AdaptiveScaler()
        self._active_anims: list[tuple[DepthLayer, int, int, MicroAnimation, float]] = []
        # (layer, x, y, animation, start_time)

    @property
    def canvas(self) -> LayeredCanvas:
        return self._canvas

    @property
    def layout(self) -> LayoutParams:
        return self._scaler.layout_params(self._canvas.width, self._canvas.height)

    def draw_background(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        self._canvas.draw_rect(DepthLayer.BACKGROUND, x, y, w, h, color)

    def draw_midground(self, x: int, y: int, text: str, color: Color) -> None:
        self._canvas.draw_text(DepthLayer.MIDGROUND, x, y, text, color)

    def draw_foreground(self, x: int, y: int, text: str, color: Color) -> None:
        self._canvas.draw_text(DepthLayer.FOREGROUND, x, y, text, color)

    def draw_overlay(self, x: int, y: int, text: str, color: Color) -> None:
        self._canvas.draw_text(DepthLayer.OVERLAY, x, y, text, color)

    def attach_animation(
        self, layer: DepthLayer, x: int, y: int, anim_name: str, start: float = 0.0,
    ) -> bool:
        """在指定层附加动效（渲染时按时刻取帧）。"""
        anim = self._anims.get(anim_name)
        if anim is None:
            return False
        self._active_anims.append((layer, x, y, anim, start))
        return True

    def render_frame(
        self, t: float = 0.0, env: str = "ansi", color_level: str = "256",
    ) -> str:
        """渲染时刻 t 的一帧（含动效）。"""
        # 先把动效帧画到对应层
        for layer, x, y, anim, start in self._active_anims:
            frame_char = anim.frame_at(max(0.0, t - start))
            if frame_char:
                self._canvas.set_pixel(
                    layer, x, y, PALETTE_16["title"], frame_char,
                )
        return self._canvas.render(env=env, color_level=color_level)

    def clear(self) -> None:
        self._canvas.clear_all()
        self._active_anims.clear()

    def composite(self, layers: list[DepthLayer]) -> list[list[tuple[Color, str]]]:
        """合成指定子集图层，按 Z 序叠加。"""
        result = self._canvas._empty_buffer()
        for layer in sorted(layers, key=lambda l: l.value):
            buf = self._canvas._layers[layer]
            for y in range(self._canvas.height):
                for x in range(self._canvas.width):
                    color, char = buf[y][x]
                    if char.strip():
                        result[y][x] = (color, char)
        return result

    def set_opacity(self, layer: DepthLayer, alpha: float) -> None:
        """调整指定层所有像素的亮度来模拟透明度。"""
        buf = self._canvas._layers[layer]
        for y in range(self._canvas.height):
            for x in range(self._canvas.width):
                color, char = buf[y][x]
                if char.strip():
                    blended = Color(
                        r=int(color.r * alpha + PALETTE_16["bg"].r * (1 - alpha)),
                        g=int(color.g * alpha + PALETTE_16["bg"].g * (1 - alpha)),
                        b=int(color.b * alpha + PALETTE_16["bg"].b * (1 - alpha)),
                    )
                    buf[y][x] = (blended, char)
