"""UI 板块一：跨端统一像素渲染底层引擎。

三大核心能力（所有界面共用一套渲染标准）：
1. 多渲染后端自动适配路由：ANSI 终端 / HTML Canvas / Pyxel 像素图形库
2. 全局 8px 像素网格强制校准器：坐标吸附 8px 网格，消除半像素模糊
3. 跨端色彩自动降级兼容管线：TrueColor → 256 色 → 16 基础色 → 灰度

纯 Python 标准库实现，无第三方依赖。一套 UI 配置全平台复用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


# ============== 色彩系统 ==============

@dataclass
class Color:
    """RGB 色彩（0-255）。"""
    r: int = 255
    g: int = 255
    b: int = 255

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def to_ansi256(self) -> int:
        """降级到 256 色 ANSI 索引。"""
        # 6×6×6 色立方体（16-231）
        def cube(v: int) -> int:
            if v < 48:
                return 0
            if v < 115:
                return 1
            return min(5, (v - 35) // 40)
        return 16 + 36 * cube(self.r) + 6 * cube(self.g) + cube(self.b)

    def to_gray(self) -> int:
        """降级到灰度（0-255）。"""
        return int(0.299 * self.r + 0.587 * self.g + 0.114 * self.b)


# 16 色复古主色板（跨端统一）
PALETTE_16: dict[str, Color] = {
    "bg":         Color(15, 15, 25),     # 深夜底色
    "panel":      Color(25, 25, 40),     # 面板底
    "border":     Color(80, 80, 110),    # 边框
    "text":       Color(220, 220, 230),  # 正文
    "text_dim":   Color(120, 120, 140),  # 备注
    "title":      Color(255, 220, 80),   # 标题金
    "success":    Color(80, 220, 100),   # 成功绿
    "warning":    Color(255, 180, 60),   # 警告橙
    "error":      Color(240, 80, 80),    # 错误红
    "info":       Color(80, 180, 240),   # 信息蓝
    "accent":     Color(200, 120, 240),  # 强调紫
    "coin":       Color(255, 200, 60),   # 金币
    "dream":      Color(120, 200, 255),  # 梦境
    "security":   Color(255, 100, 100),  # 安全
    "code":       Color(100, 240, 180),  # 代码
    "shadow":     Color(8, 8, 16),       # 阴影
}


# ============== 色彩降级管线 ==============

class ColorDowngradePipeline:
    """跨端色彩自动降级兼容管线。

    根据目标环境色彩上限自动降级：
    - TrueColor：保留原色
    - 256 色：降级到 ANSI 256 色立方体
    - 16 色：降级到基础 16 色
    - gray：降级到灰度黑白
    """

    # 16 色基础色映射（ANSI 0-15）
    _ANSI16 = [
        (0, 0, 0), (128, 0, 0), (0, 128, 0), (128, 128, 0),
        (0, 0, 128), (128, 0, 128), (0, 128, 128), (192, 192, 192),
        (128, 128, 128), (255, 0, 0), (0, 255, 0), (255, 255, 0),
        (0, 0, 255), (255, 0, 255), (0, 255, 255), (255, 255, 255),
    ]

    LEVELS = ("truecolor", "256", "16", "gray")

    def downgrade(self, color: Color, level: str = "256") -> Any:
        """降级色彩到指定级别。

        Args:
            color: 原始 RGB 色。
            level: truecolor / 256 / 16 / gray。

        Returns:
            - truecolor → Color
            - 256 → int（ANSI 256 索引）
            - 16 → int（0-15）
            - gray → int（0-255）
        """
        if level == "truecolor":
            return color
        if level == "256":
            return color.to_ansi256()
        if level == "16":
            return self._nearest_ansi16(color)
        if level == "gray":
            return color.to_gray()
        raise ValueError(f"未知降级级别: {level}")

    def _nearest_ansi16(self, color: Color) -> int:
        """找最近的 16 色基础色。"""
        best_idx, best_dist = 0, float("inf")
        for idx, (r, g, b) in enumerate(self._ANSI16):
            dist = (color.r - r) ** 2 + (color.g - g) ** 2 + (color.b - b) ** 2
            if dist < best_dist:
                best_dist, best_idx = dist, idx
        return best_idx

    def auto_detect_level(self) -> str:
        """自动检测当前环境色彩上限。"""
        colorterm = os.environ.get("COLORTERM", "").lower()
        term = os.environ.get("TERM", "").lower()
        if "truecolor" in colorterm or "24bit" in colorterm:
            return "truecolor"
        if "256" in term or "256color" in term:
            return "256"
        if term in ("linux", "dumb") or not term:
            return "16"
        return "256"  # 默认按 256 色处理


# ============== 8px 像素网格强制校准器 ==============

class Grid8Aligner:
    """全局 8px 像素网格强制校准器。

    所有按钮、头像、面板、分割线强制吸附 8px 网格，
    自动修正不同平台缩放导致的半像素模糊，统一复古马赛克硬边风格。
    """

    def __init__(self, grid_size: int = 8) -> None:
        if grid_size <= 0:
            raise ValueError("grid_size 必须 > 0")
        self._grid = grid_size

    @property
    def grid_size(self) -> int:
        return self._grid

    def align(self, value: int) -> int:
        """单个坐标吸附到网格。"""
        return (value // self._grid) * self._grid

    def align_point(self, x: int, y: int) -> tuple[int, int]:
        """坐标点吸附。"""
        return self.align(x), self.align(y)

    def align_rect(self, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
        """矩形吸附：左上角对齐网格，宽高补齐到网格倍数。"""
        ax, ay = self.align(x), self.align(y)
        # 宽高向上取整到网格倍数，保证覆盖原区域
        aw = self.align(x + w + self._grid - 1) - ax
        ah = self.align(y + h + self._grid - 1) - ay
        return ax, ay, aw, ah

    def is_aligned(self, value: int) -> bool:
        """是否已对齐网格。"""
        return value % self._grid == 0


# ============== 渲染后端抽象 ==============

class RenderBackend:
    """渲染后端抽象基类。

    所有后端实现统一接口：set_pixel / draw_rect / draw_text / render。
    上层 UI 代码无需关心具体平台。
    """

    backend_name: str = "abstract"

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._buffer: list[list[tuple[Color, str]]] = [
            [(PALETTE_16["bg"], " ") for _ in range(width)]
            for _ in range(height)
        ]

    def set_pixel(self, x: int, y: int, color: Color, char: str = " ") -> None:
        """设置像素点（越界忽略）。"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self._buffer[y][x] = (color, char if char else " ")

    def draw_rect(self, x: int, y: int, w: int, h: int, color: Color, char: str = " ") -> None:
        """填充矩形。"""
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set_pixel(xx, yy, color, char)

    def draw_text(self, x: int, y: int, text: str, color: Color) -> None:
        """绘制文本（逐字符）。"""
        for i, ch in enumerate(text):
            self.set_pixel(x + i, y, color, ch)

    def clear(self) -> None:
        """清空画布。"""
        bg = PALETTE_16["bg"]
        self._buffer = [
            [(bg, " ") for _ in range(self.width)]
            for _ in range(self.height)
        ]

    def render(self) -> str:
        """渲染为字符串（子类实现）。"""
        raise NotImplementedError


class AnsiTerminalBackend(RenderBackend):
    """ANSI 终端后端：256 色 + Unicode 块字符。"""

    backend_name = "ansi"

    def __init__(self, width: int, height: int, color_level: str = "256") -> None:
        super().__init__(width, height)
        self._color_level = color_level
        self._pipeline = ColorDowngradePipeline()

    def render(self) -> str:
        lines: list[str] = []
        prev_fg: Any = None
        for row in self._buffer:
            line = []
            for color, char in row:
                fg = self._pipeline.downgrade(color, self._color_level)
                if fg != prev_fg:
                    line.append(self._ansi_fg(fg))
                    prev_fg = fg
                line.append(char)
            line.append("\x1b[0m")
            lines.append("".join(line))
            prev_fg = None
        return "\n".join(lines)

    @staticmethod
    def _ansi_fg(code: Any) -> str:
        """生成前景色转义码。"""
        if isinstance(code, int):
            if code < 16:
                return f"\x1b[{30 + code}m" if code < 8 else f"\x1b[{90 + code - 8}m"
            return f"\x1b[38;5;{code}m"
        # truecolor
        return f"\x1b[38;2;{code.r};{code.g};{code.b}m"


class HtmlCanvasBackend(RenderBackend):
    """HTML5 Canvas 后端：生成 Canvas 绘图指令字符串。"""

    backend_name = "html"

    def render(self) -> str:
        """渲染为 HTML + Canvas 脚本。"""
        cell = 8  # 每像素 8px
        cmds: list[str] = [
            f'const c=document.getElementById("bd");c.width={self.width*cell};'
            f'c.height={self.height*cell};const ctx=c.getContext("2d");'
        ]
        for y, row in enumerate(self._buffer):
            for x, (color, char) in enumerate(row):
                if char.strip():
                    cmds.append(
                        f'ctx.fillStyle="{color.to_hex()}";'
                        f'ctx.font="{cell}px monospace";'
                        f'ctx.fillText("{char}",{x*cell},{(y+1)*cell-1});'
                    )
                else:
                    cmds.append(
                        f'ctx.fillStyle="{color.to_hex()}";'
                        f'ctx.fillRect({x*cell},{y*cell},{cell},{cell});'
                    )
        return (
            '<canvas id="bd"></canvas><script>'
            + "".join(cmds)
            + '</script>'
        )


class PyxelBackend(RenderBackend):
    """Pyxel 像素图形库后端：生成 Pyxel 绘图调用序列。

    纯文本指令，不依赖 pyxel 库，可在任意环境生成。
    运行时由 pyxel runtime 解释执行。
    """

    backend_name = "pyxel"

    def render(self) -> str:
        """渲染为 Pyxel 指令列表（每行一条）。"""
        cmds: list[str] = [f"pyxel.init({self.width}, {self.height})"]
        for y, row in enumerate(self._buffer):
            for x, (color, char) in enumerate(row):
                hex_col = color.to_hex()
                if char.strip():
                    cmds.append(f'pyxel.text({x}, {y}, "{char}", "{hex_col}")')
                else:
                    cmds.append(f'pyxel.rect({x}, {y}, 1, 1, "{hex_col}")')
        return "\n".join(cmds)


# ============== 渲染后端自动路由 ==============

class RenderRouter:
    """多渲染后端自动适配路由。

    自动识别当前运行环境，切换对应渲染内核。
    一套 UI 配置全平台复用，无需分平台重写界面代码。
    """

    _BACKENDS = {
        "ansi": AnsiTerminalBackend,
        "html": HtmlCanvasBackend,
        "pyxel": PyxelBackend,
    }

    def select(self, env: str = "auto", width: int = 80, height: int = 24) -> RenderBackend:
        """选择渲染后端。

        Args:
            env: auto / ansi / html / pyxel。auto 自动检测终端环境。
            width, height: 画布尺寸。

        Returns:
            对应的 RenderBackend 实例。
        """
        if env == "auto":
            env = self._detect_env()

        cls = self._BACKENDS.get(env)
        if cls is None:
            raise ValueError(f"未知渲染后端: {env}（可选: auto/ansi/html/pyxel）")

        if cls is AnsiTerminalBackend:
            level = ColorDowngradePipeline().auto_detect_level()
            return cls(width, height, color_level=level)
        return cls(width, height)

    @staticmethod
    def _detect_env() -> str:
        """自动检测运行环境。"""
        # 非 tty（如 CI / 重定向）→ html 输出更友好
        if not os.isatty(1) and os.environ.get("BD_RENDER"):
            return os.environ["BD_RENDER"]
        if os.environ.get("BD_RENDER"):
            return os.environ["BD_RENDER"]
        # 默认终端
        return "ansi"

    @property
    def available_backends(self) -> list[str]:
        return list(self._BACKENDS.keys())


# ============== 统一渲染入口 ==============

class PixelRenderEngine:
    """跨端统一渲染引擎入口。

    封装「后端路由 + 网格校准 + 色彩降级」三件套，
    上层只需调用 draw_* / render，无需关心平台差异。

    用法：
        engine = PixelRenderEngine(env="auto", width=80, height=24)
        engine.draw_rect(0, 0, 16, 16, PALETTE_16["panel"])
        engine.draw_text(0, 0, "Hello", PALETTE_16["title"])
        print(engine.render())
    """

    def __init__(
        self,
        env: str = "auto",
        width: int = 80,
        height: int = 24,
        grid_size: int = 8,
        color_level: str | None = None,
        snap_grid: bool = True,
    ) -> None:
        self._router = RenderRouter()
        self._backend = self._router.select(env, width, height)
        self._aligner = Grid8Aligner(grid_size)
        self._pipeline = ColorDowngradePipeline()
        self._color_level = color_level or self._pipeline.auto_detect_level()
        self._snap = snap_grid

    @property
    def backend(self) -> RenderBackend:
        return self._backend

    @property
    def backend_name(self) -> str:
        return self._backend.backend_name

    @property
    def color_level(self) -> str:
        return self._color_level

    @property
    def grid_size(self) -> int:
        return self._aligner.grid_size

    def _snap_point(self, x: int, y: int) -> tuple[int, int]:
        """按需吸附网格。"""
        return self._aligner.align_point(x, y) if self._snap else (x, y)

    def _snap_rect(self, x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
        return self._aligner.align_rect(x, y, w, h) if self._snap else (x, y, w, h)

    def set_pixel(self, x: int, y: int, color: Color, char: str = " ") -> None:
        x, y = self._snap_point(x, y)
        self._backend.set_pixel(x, y, color, char)

    def draw_rect(self, x: int, y: int, w: int, h: int, color: Color, char: str = " ") -> None:
        x, y, w, h = self._snap_rect(x, y, w, h)
        self._backend.draw_rect(x, y, w, h, color, char)

    def draw_text(self, x: int, y: int, text: str, color: Color) -> None:
        x, y = self._snap_point(x, y)
        self._backend.draw_text(x, y, text, color)

    def clear(self) -> None:
        self._backend.clear()

    def render(self) -> str:
        return self._backend.render()

    def downgrade_color(self, color: Color) -> Any:
        """按当前引擎色彩级别降级颜色。"""
        return self._pipeline.downgrade(color, self._color_level)


_RENDER_CACHE: dict[str, str] = {}
_RENDER_CACHE_ENABLED = True


def clear_cache() -> None:
    """清空渲染缓存。"""
    _RENDER_CACHE.clear()


def set_cache_enabled(enabled: bool) -> None:
    global _RENDER_CACHE_ENABLED
    _RENDER_CACHE_ENABLED = enabled


def batch_render(engines: list[PixelRenderEngine]) -> list[str]:
    """批量渲染多个引擎的输出。"""
    return [eng.render() for eng in engines]


def cached_render(engine: PixelRenderEngine, cache_key: str) -> str:
    """带缓存的渲染。"""
    if _RENDER_CACHE_ENABLED and cache_key in _RENDER_CACHE:
        return _RENDER_CACHE[cache_key]
    result = engine.render()
    if _RENDER_CACHE_ENABLED:
        _RENDER_CACHE[cache_key] = result
    return result
