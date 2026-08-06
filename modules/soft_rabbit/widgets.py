"""UI 板块三（下）：跨平台像素数据可视化组件。

统一组件：进度条、条形图、KPI 星级、占比色块、趋势图。
终端用字符色块、网页用 Canvas 像素绘图、桌面用像素图表。

对标成就系统：7 大类可视化面板，每类可拆分多维度子图表。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.soft_rabbit.pixel_render import PALETTE_16, Color

# ============== 进度条 ==============


@dataclass
class ProgressBar:
    """像素进度条：[████░░░░] 50%。

    全平台统一字符块表示。
    """

    filled_char: str = "█"
    empty_char: str = "░"
    color: Color = None  # type: ignore  # 默认在 __post_init__ 设置

    def __post_init__(self) -> None:
        if self.color is None:
            self.color = PALETTE_16["success"]

    def render(self, value: float, max_val: float = 100, width: int = 20) -> str:
        """渲染进度条。

        Args:
            value: 当前值。
            max_val: 最大值。
            width: 进度条字符宽度（不含括号和百分比）。
        """
        if max_val <= 0:
            ratio = 0.0
        else:
            ratio = max(0.0, min(1.0, value / max_val))
        filled = int(ratio * width)
        bar = self.filled_char * filled + self.empty_char * (width - filled)
        pct = int(ratio * 100)
        return f"[{bar}] {pct}%"


# ============== 条形图 ==============


@dataclass
class BarChart:
    """横向字符条形图。

    数据：[(label, value), ...]，每项一行字符条。
    """

    bar_char: str = "█"
    color: Color = None  # type: ignore

    def __post_init__(self) -> None:
        if self.color is None:
            self.color = PALETTE_16["info"]

    def render(self, data: list[tuple[str, float]], width: int = 20) -> str:
        """渲染条形图。

        Args:
            data: [(标签, 数值), ...]。
            width: 最长条的字符宽度。
        """
        if not data:
            return "(无数据)"
        max_val = max(v for _, v in data) or 1
        lines: list[str] = []
        for label, value in data:
            ratio = max(0.0, value / max_val) if max_val > 0 else 0.0
            bar_len = int(ratio * width)
            bar = self.bar_char * bar_len
            lines.append(f"{label:<8} {bar} {value}")
        return "\n".join(lines)


# ============== KPI 星级 ==============


@dataclass
class KpiStars:
    """KPI 星级面板：★★★☆☆。"""

    filled_star: str = "★"
    empty_star: str = "☆"
    color: Color = None  # type: ignore

    def __post_init__(self) -> None:
        if self.color is None:
            self.color = PALETTE_16["title"]

    def render(self, score: float, max_stars: int = 5) -> str:
        """渲染星级。

        Args:
            score: 得分。三种模式：
                - 0~1：按比例（0.5 → 半星）。
                - 1~max_stars：直接当星级数（3 → 3 星）。
                - >max_stars：按 0-100 百分比处理（100 → 满星）。
            max_stars: 星星总数。
        """
        if score > max_stars:
            # 超过最大星数，按 0-100 百分比归一化
            ratio = max(0.0, min(1.0, score / 100)) if score > 1 else 1.0
            filled = round(ratio * max_stars)
        elif score > 1:
            # 1~max_stars，直接当星级数
            filled = int(score)
        else:
            # 0~1，按比例
            filled = round(max(0.0, min(1.0, score)) * max_stars)
        filled = max(0, min(max_stars, filled))
        return self.filled_star * filled + self.empty_star * (max_stars - filled)


# ============== 占比色块 ==============


@dataclass
class RatioBlock:
    """占比色块：用字符块表示比例。

    例：5:3 占比 → ████████░░░░░░（5 绿 + 3 红 + 余灰）
    """

    def render(
        self,
        segments: list[tuple[float, Color]],
        width: int = 20,
        gap_char: str = "░",
    ) -> str:
        """渲染多段占比色块。

        Args:
            segments: [(比例, 颜色), ...] 比例值直接作为字符长度，不归一化。
            width: 总宽度。
            gap_char: 空白填充字符。
        """
        result: list[str] = []
        used = 0
        for ratio, _ in segments:
            seg_len = min(int(ratio), width - used)
            if seg_len > 0:
                result.append("█" * seg_len)
                used += seg_len
        if used < width:
            result.append(gap_char * (width - used))
        return "".join(result)

    def render_segments_with_colors(
        self,
        segments: list[tuple[float, Color]],
        width: int = 20,
    ) -> list[tuple[str, Color]]:
        """渲染带颜色的分段（供渲染后端着色）。

        Returns:
            [(字符块, 颜色), ...] 不填充 gap，仅返回有效段。
        """
        result: list[tuple[str, Color]] = []
        used = 0
        for ratio, color in segments:
            seg_len = min(int(ratio), width - used)
            if seg_len > 0:
                result.append(("█" * seg_len, color))
                used += seg_len
        return result


# ============== 趋势图 ==============


class TrendChart:
    """字符趋势折线图：用 ╱╲─ 字符表示折线走势。

    终端用字符、网页用 Canvas 像素绘图。
    """

    # 高度→字符映射（从下到上）
    _HEIGHT_CHARS = ["─", "▄", "▆", "█"]

    def render(
        self,
        values: list[float],
        width: int = 20,
        height: int = 4,
    ) -> str:
        """渲染趋势图。

        Args:
            values: 数值序列。
            width: 图表字符宽度。
            height: 图表高度（行数）。
        """
        if not values:
            return "(无数据)"
        if len(values) == 1:
            values = list(values) + list(values)

        v_min = min(values)
        v_max = max(values)
        v_range = v_max - v_min or 1

        # 采样到 width 个点
        step = max(1, len(values) / width)
        sampled = [values[min(int(i * step), len(values) - 1)] for i in range(width)]

        # 归一化到 0..height-1
        normalized = [int((v - v_min) / v_range * (height - 1)) for v in sampled]

        # 从顶到底渲染
        lines: list[str] = []
        for row in range(height - 1, -1, -1):
            line_chars: list[str] = []
            for v in normalized:
                if v >= row:
                    line_chars.append("█")
                elif v >= row - 0.5 and row > 0:
                    line_chars.append("▄")
                else:
                    line_chars.append(" ")
            lines.append("".join(line_chars))
        return "\n".join(lines)


# ============== 可视化面板注册表 ==============


class ChartRegistry:
    """可视化组件注册表。

    对标成就系统：7 大类可视化面板，每类可拆分多维度子图表。
    """

    _TYPES = {
        "progress": ProgressBar,
        "bar": BarChart,
        "stars": KpiStars,
        "ratio": RatioBlock,
        "trend": TrendChart,
    }

    def available_types(self) -> list[str]:
        return list(self._TYPES.keys())

    def create(self, chart_type: str) -> Any:
        """创建指定类型图表实例。"""
        cls = self._TYPES.get(chart_type)
        if cls is None:
            raise ValueError(
                f"未知图表类型: {chart_type}（可选: {self.available_types()}）"
            )
        return cls()


class Widget:
    """组件生命周期基类：init / render / update / destroy。

    所有 UI 组件继承此类，按生命周期管理。
    """

    def __init__(self, widget_id: str) -> None:
        self.id = widget_id
        self._initialized = False
        self._destroyed = False

    def init(self) -> None:
        """初始化阶段：资源申请、子组件创建。"""
        self._initialized = True

    def render(self) -> list[str]:
        """渲染阶段：返回文本行列表。"""
        return []

    def update(self, dt: float) -> None:
        """更新阶段：每帧逻辑更新，dt 为帧间隔秒数。"""

    def destroy(self) -> None:
        """销毁阶段：资源释放、反注册。"""
        self._destroyed = True
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def is_destroyed(self) -> bool:
        return self._destroyed


class WidgetManager:
    """组件管理器：自动管理全部 Widget 生命周期。"""

    def __init__(self) -> None:
        self._widgets: dict[str, Widget] = {}

    def add(self, widget: Widget) -> None:
        self._widgets[widget.id] = widget
        widget.init()

    def remove(self, widget_id: str) -> bool:
        w = self._widgets.pop(widget_id, None)
        if w:
            w.destroy()
            return True
        return False

    def get(self, widget_id: str) -> Widget | None:
        return self._widgets.get(widget_id)

    def update_all(self, dt: float) -> None:
        for w in self._widgets.values():
            w.update(dt)

    def render_all(self) -> list[str]:
        lines: list[str] = []
        for w in self._widgets.values():
            lines.extend(w.render())
        return lines

    def clear(self) -> None:
        for w in list(self._widgets.values()):
            w.destroy()
        self._widgets.clear()

    @property
    def count(self) -> int:
        return len(self._widgets)
