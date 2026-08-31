"""Glow 色板降级引擎：跨端兼容的发光渲染底层。

融合项目：#1 glow、#38 ansi-multi-theme、#42 crt-glow-filter、#43 adaptive-glow

能力：
1. TrueColor → 256 色 → 16 色 → 灰度 四级降级，自动识别终端色彩上限
2. 6 套 CRT 复古硬件预设（NES/GameBoy/工控终端/90年代办公/街机/掌机）
3. 时间自适应护眼亮度（06-18/18-22/22-06 三时段）
4. 8px 网格强制对齐消除半像素模糊
5. Z 轴 4 层分层合成（背景弱光/中层标准/顶层告警/覆盖层）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("bluedeer.glow.color")


# ============== 色彩深度等级 ==============


class ColorDepth(Enum):
    """终端色彩深度等级（降级目标）。"""

    TRUE_COLOR = "truecolor"  # 24bit 真彩
    COLOR_256 = "256"  # 256 色
    COLOR_16 = "16"  # 16 基础色
    GRAYSCALE = "grayscale"  # 灰度
    ASCII = "ascii"  # 纯 ASCII（无色）


# 自动检测终端色彩深度
def detect_color_depth() -> ColorDepth:
    """检测当前终端支持的色彩深度。"""
    colorterm = os.environ.get("COLORTERM", "").lower()
    term = os.environ.get("TERM", "").lower()
    if "truecolor" in colorterm or "24bit" in colorterm:
        return ColorDepth.TRUE_COLOR
    if "256" in term:
        return ColorDepth.COLOR_256
    if "color" in term:
        return ColorDepth.COLOR_16
    if "ansi" in term or "vt100" in term:
        return ColorDepth.COLOR_16
    return ColorDepth.GRAYSCALE


# ============== RGB 颜色 ==============


@dataclass
class RGB:
    """RGB 颜色（0-255）。"""

    r: int = 0
    g: int = 0
    b: int = 0

    def to_tuple(self) -> tuple[int, int, int]:
        return (self.r, self.g, self.b)

    def to_gray(self) -> int:
        """转灰度值（0-255）。"""
        return int(0.299 * self.r + 0.587 * self.g + 0.114 * self.b)

    def to_256(self) -> int:
        """转 256 色索引。"""
        # 6×6×6 立方体
        r6 = min(5, self.r * 6 // 256)
        g6 = min(5, self.g * 6 // 256)
        b6 = min(5, self.b * 6 // 256)
        return 16 + 36 * r6 + 6 * g6 + b6

    def to_16(self) -> int:
        """转 16 色索引。"""
        # 简化映射：基于亮度+主色调
        if self.r > 128 and self.g > 128 and self.b > 128:
            return 7  # 白
        if self.r < 64 and self.g < 64 and self.b < 64:
            return 0  # 黑
        if self.r > self.g and self.r > self.b:
            return 1 if self.r < 128 else 9  # 红/亮红
        if self.g > self.r and self.g > self.b:
            return 2 if self.g < 128 else 10  # 绿/亮绿
        if self.b > self.r and self.b > self.g:
            return 4 if self.b < 128 else 12  # 蓝/亮蓝
        return 3  # 黄

    def adjust_brightness(self, factor: float) -> RGB:
        """调整亮度（factor 0-1，1.0 原样）。"""
        return RGB(
            r=max(0, min(255, int(self.r * factor))),
            g=max(0, min(255, int(self.g * factor))),
            b=max(0, min(255, int(self.b * factor))),
        )


# ============== CRT 硬件预设 ==============


class CRTPreset(Enum):
    """6 套 CRT 复古硬件预设。"""

    NES = "nes"  # 任天堂红白机
    GAMEBOY = "gameboy"  # GameBoy 4色绿
    INDUSTRIAL = "industrial"  # 工控终端琥珀
    OFFICE_90S = "office_90s"  # 90年代办公 CGA
    ARCADE = "arcade"  # 街机 CRT
    HANDHELD = "handheld"  # 掌机


# 各预设的色板限制（4-8 色）
_CRT_PALETTES: dict[CRTPreset, list[RGB]] = {
    CRTPreset.NES: [
        RGB(0, 0, 0),
        RGB(124, 124, 124),
        RGB(248, 56, 0),
        RGB(228, 92, 16),
        RGB(136, 20, 176),
        RGB(52, 104, 86),
    ],
    CRTPreset.GAMEBOY: [
        RGB(15, 56, 15),
        RGB(48, 98, 48),
        RGB(139, 172, 15),
        RGB(155, 188, 15),
    ],
    CRTPreset.INDUSTRIAL: [
        RGB(0, 0, 0),
        RGB(255, 176, 0),
        RGB(200, 130, 0),
        RGB(100, 60, 0),
    ],
    CRTPreset.OFFICE_90S: [
        RGB(0, 0, 0),
        RGB(0, 0, 170),
        RGB(0, 170, 0),
        RGB(0, 170, 170),
        RGB(170, 0, 0),
        RGB(170, 0, 170),
        RGB(170, 85, 0),
        RGB(170, 170, 170),
    ],
    CRTPreset.ARCADE: [
        RGB(20, 20, 40),
        RGB(255, 80, 80),
        RGB(80, 255, 80),
        RGB(80, 80, 255),
        RGB(255, 255, 80),
        RGB(255, 80, 255),
        RGB(80, 255, 255),
    ],
    CRTPreset.HANDHELD: [
        RGB(30, 30, 40),
        RGB(120, 180, 240),
        RGB(240, 200, 120),
        RGB(255, 255, 255),
    ],
}


def nearest_in_palette(color: RGB, preset: CRTPreset) -> RGB:
    """把颜色量化到指定 CRT 预设调色板的最近色。"""
    palette = _CRT_PALETTES[preset]
    best = palette[0]
    best_dist = float("inf")
    for p in palette:
        dist = (color.r - p.r) ** 2 + (color.g - p.g) ** 2 + (color.b - p.b) ** 2
        if dist < best_dist:
            best_dist = dist
            best = p
    return best


# ============== 时间自适应亮度 ==============


def auto_brightness_factor(hour: int | None = None) -> float:
    """根据本地时段返回亮度因子。

    - 06-18 白天：1.0
    - 18-22 傍晚：0.85
    - 22-06 深夜：0.7
    """
    import time as _time

    if hour is None:
        hour = _time.localtime().tm_hour
    if 6 <= hour < 18:
        return 1.0
    if 18 <= hour < 22:
        return 0.85
    return 0.7


# ============== 8px 网格对齐 ==============


def snap_to_grid(x: int, y: int, grid: int = 8) -> tuple[int, int]:
    """坐标吸附到 8px 网格。"""
    return ((x // grid) * grid, (y // grid) * grid)


# ============== Z 轴分层 ==============


class GlowLayer(Enum):
    """Z 轴 4 层分层合成。"""

    BACKGROUND = 0  # 背景弱光
    MIDGROUND = 1  # 中层标准光晕
    FOREGROUND = 2  # 顶层告警强脉冲
    OVERLAY = 3  # 覆盖层（弹窗/拖拽）


# ============== 降级渲染器 ==============


class ColorDowngradeRenderer:
    """色板降级渲染器。

    职责：
    1. 按目标色彩深度降级颜色
    2. 应用 CRT 预设调色板量化
    3. 应用时间自适应亮度
    4. 输出 ANSI 转义序列
    """

    def __init__(
        self,
        target_depth: ColorDepth | None = None,
        crt_preset: CRTPreset | None = None,
        auto_brightness: bool = True,
    ) -> None:
        self._depth = target_depth or detect_color_depth()
        self._crt = crt_preset
        self._auto_brightness = auto_brightness

    @property
    def depth(self) -> ColorDepth:
        return self._depth

    def set_depth(self, depth: ColorDepth) -> None:
        self._depth = depth

    def set_crt_preset(self, preset: CRTPreset | None) -> None:
        self._crt = preset

    def downgrade(self, color: RGB) -> RGB:
        """降级颜色到目标深度（返回 RGB 表示）。"""
        # CRT 预设优先（最严格限制）
        if self._crt is not None:
            return nearest_in_palette(color, self._crt)
        # 亮度自适应
        if self._auto_brightness:
            color = color.adjust_brightness(auto_brightness_factor())
        # 按深度降级
        if self._depth == ColorDepth.TRUE_COLOR:
            return color
        if self._depth == ColorDepth.COLOR_256:
            idx = color.to_256()
            return RGB(
                (idx - 16) // 36 * 51, ((idx - 16) % 36) // 6 * 51, (idx - 16) % 6 * 51
            )
        if self._depth == ColorDepth.COLOR_16:
            idx = color.to_16()
            # 16 色粗略还原
            _16_map = [
                RGB(0, 0, 0),
                RGB(128, 0, 0),
                RGB(0, 128, 0),
                RGB(128, 128, 0),
                RGB(0, 0, 128),
                RGB(128, 0, 128),
                RGB(0, 128, 128),
                RGB(192, 192, 192),
                RGB(128, 128, 128),
                RGB(255, 0, 0),
                RGB(0, 255, 0),
                RGB(255, 255, 0),
                RGB(0, 0, 255),
                RGB(255, 0, 255),
                RGB(0, 255, 255),
                RGB(255, 255, 255),
            ]
            return _16_map[idx]
        if self._depth == ColorDepth.GRAYSCALE:
            g = color.to_gray()
            return RGB(g, g, g)
        return RGB(128, 128, 128)  # ASCII

    def render_glow(
        self,
        text: str,
        color: RGB,
        layer: GlowLayer = GlowLayer.MIDGROUND,
        blink: bool = False,
    ) -> str:
        """渲染带发光效果的文本。

        Args:
            text: 文本内容。
            color: 发光颜色。
            layer: Z 轴层级（影响亮度）。
            blink: 是否闪烁。

        Returns:
            带 ANSI 转义序列的字符串。
        """
        # 层级亮度系数
        layer_factor = {
            GlowLayer.BACKGROUND: 0.5,
            GlowLayer.MIDGROUND: 1.0,
            GlowLayer.FOREGROUND: 1.3,
            GlowLayer.OVERLAY: 1.5,
        }[layer]
        # 应用层级亮度
        adjusted = RGB(
            min(255, int(color.r * layer_factor)),
            min(255, int(color.g * layer_factor)),
            min(255, int(color.b * layer_factor)),
        )
        # 降级
        final = self.downgrade(adjusted)

        if self._depth == ColorDepth.ASCII:
            return text  # 无色直接返回

        # 构建 ANSI 序列
        if self._depth == ColorDepth.TRUE_COLOR:
            prefix = f"\033[38;2;{final.r};{final.g};{final.b}m"
        elif self._depth == ColorDepth.COLOR_256:
            prefix = f"\033[38;5;{final.to_256()}m"
        else:
            prefix = f"\033[3{final.to_16() % 8}m"
            if final.to_16() >= 8:
                prefix = f"\033[9{final.to_16() - 8}m"

        if blink:
            prefix = "\033[5m" + prefix
        return f"{prefix}{text}\033[0m"

    def render_block(
        self,
        width: int,
        height: int,
        color: RGB,
        char: str = "█",
        layer: GlowLayer = GlowLayer.MIDGROUND,
    ) -> list[str]:
        """渲染发光色块（多行）。"""
        line = char * width
        return [self.render_glow(line, color, layer) for _ in range(height)]

    def apply_palette(self, preset: CRTPreset) -> None:
        """应用 CRT 预设调色板（快捷方法）。"""
        self.set_crt_preset(preset)


class PaletteManager:
    """调色板管理器：注册 / 查询 / 应用多套调色板。"""

    def __init__(self) -> None:
        self._palettes: dict[str, list[RGB]] = {}

    def register(self, name: str, colors: list[RGB]) -> None:
        self._palettes[name] = list(colors)

    def get(self, name: str) -> list[RGB] | None:
        return self._palettes.get(name)

    def list_palettes(self) -> list[str]:
        return list(self._palettes.keys())

    def unregister(self, name: str) -> bool:
        return self._palettes.pop(name, None) is not None

    def apply_palette(self, name: str, renderer: ColorDowngradeRenderer) -> bool:
        """将命名调色板应用到渲染器作为 CRT 预设。"""
        colors = self._palettes.get(name)
        if not colors:
            return False
        renderer.set_crt_preset(CRTPreset(name))
        return True

    def render_pulse(
        self,
        text: str,
        color: RGB,
        frames: int = 3,
    ) -> list[str]:
        """渲染脉冲动画帧（亮度渐变循环）。"""
        result = []
        for i in range(frames):
            factor = 0.5 + 0.5 * (i / max(1, frames - 1))
            adjusted = color.adjust_brightness(factor)
            result.append(
                self.render_glow(text, adjusted, GlowLayer.FOREGROUND, blink=(i == 0))
            )
        return result
