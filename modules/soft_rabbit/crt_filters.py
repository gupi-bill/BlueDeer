"""UI 板块六：CRT 复古硬件模拟滤镜。

两大能力（纯视觉增值，全平台兼容）：
1. 跨端复古显示滤镜管线：扫描线 / 像素颗粒 / 色彩偏移 / 暗角 / 圆角，
   12 档强度调节，6 套硬件预设（NES/GameBoy/工控终端/办公显示器/街机CRT/掌机）。
2. 低像素降噪统一处理：抹平平滑渐变，量化到调色板最近色，还原硬色块复古质感。

终端用字符间隔/替换模拟，Web 用 Canvas 着色器，桌面用图层叠加。
纯 Python 标准库，无第三方依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.soft_rabbit.pixel_render import PALETTE_16, Color

# ============== 滤镜类型 ==============

FILTER_TYPES = (
    "scanline",  # 扫描线
    "grain",  # 像素颗粒
    "chromatic_shift",  # 色彩偏移（终端用字符偏移模拟）
    "vignette",  # 暗角
    "round_corner",  # 圆角
)

# 强度档位：0-12 档（0=关闭，12=最强）
MAX_INTENSITY_LEVEL = 12


def _level_to_ratio(level: int) -> float:
    """强度档位转比例（0.0-1.0）。"""
    return max(0.0, min(1.0, level / MAX_INTENSITY_LEVEL))


@dataclass
class FilterParams:
    """滤镜参数。"""

    type: str  # FILTER_TYPES 之一
    intensity: float = 0.5  # 0.0-1.0


# ============== 6 套硬件预设 ==============

HARDWARE_PRESETS = (
    "nes",  # NES 红白机
    "gameboy",  # GameBoy 掌机
    "industrial_terminal",  # 老式工控终端
    "office_90s",  # 90 年代办公显示器
    "arcade_crt",  # 街机 CRT
    "handheld",  # 便携掌机
)


@dataclass
class HardwarePreset:
    """硬件预设：滤镜组合 + 色调偏移。"""

    name: str
    label: str
    filters: list[FilterParams] = field(default_factory=list)
    palette_tint: Color | None = None  # 色调偏移（如 GameBoy 绿屏）


# 6 套预设定义
_HARDWARE_PRESETS: dict[str, HardwarePreset] = {
    "nes": HardwarePreset(
        "nes",
        "NES 红白机",
        filters=[
            FilterParams("scanline", 0.4),
            FilterParams("grain", 0.2),
        ],
    ),
    "gameboy": HardwarePreset(
        "gameboy",
        "GameBoy 掌机",
        filters=[
            FilterParams("scanline", 0.6),
            FilterParams("vignette", 0.5),
        ],
        palette_tint=Color(120, 160, 80),  # 经典绿屏
    ),
    "industrial_terminal": HardwarePreset(
        "industrial_terminal",
        "老式工控终端",
        filters=[
            FilterParams("scanline", 0.3),
            FilterParams("vignette", 0.7),
            FilterParams("round_corner", 0.4),
        ],
    ),
    "office_90s": HardwarePreset(
        "office_90s",
        "90 年代办公显示器",
        filters=[
            FilterParams("scanline", 0.5),
            FilterParams("vignette", 0.4),
            FilterParams("chromatic_shift", 0.3),
        ],
    ),
    "arcade_crt": HardwarePreset(
        "arcade_crt",
        "街机 CRT",
        filters=[
            FilterParams("scanline", 0.7),
            FilterParams("grain", 0.4),
            FilterParams("chromatic_shift", 0.5),
            FilterParams("vignette", 0.6),
        ],
    ),
    "handheld": HardwarePreset(
        "handheld",
        "便携掌机",
        filters=[
            FilterParams("scanline", 0.5),
            FilterParams("vignette", 0.8),
            FilterParams("round_corner", 0.6),
        ],
    ),
}


class HardwarePresetRegistry:
    """硬件预设注册表。"""

    def __init__(self) -> None:
        self._presets: dict[str, HardwarePreset] = dict(_HARDWARE_PRESETS)

    def get(self, name: str) -> HardwarePreset:
        if name not in self._presets:
            raise KeyError(f"未知硬件预设: {name}（可选: {self.list_presets()}）")
        return self._presets[name]

    def list_presets(self) -> list[str]:
        return list(self._presets.keys())

    def register(self, preset: HardwarePreset) -> None:
        self._presets[preset.name] = preset

    def count(self) -> int:
        return len(self._presets)


# ============== 单个滤镜实现 ==============
# 终端字符级模拟：通过字符替换/偏移实现视觉效果


class ScanlineFilter:
    """扫描线滤镜：每隔 N 行用半亮字符替换。

    终端模拟：每 line_spacing 行的第 2 行用 '░' 替代非空格字符。
    """

    def apply_to_lines(
        self,
        lines: list[str],
        intensity: float,
        line_spacing: int = 2,
    ) -> list[str]:
        if intensity <= 0:
            return list(lines)
        result: list[str] = []
        for i, line in enumerate(lines):
            if (i + 1) % line_spacing == 0:
                # 暗行：非空格字符降级为半亮
                dim_char = "░" if intensity > 0.5 else "·"
                new_line = "".join(dim_char if c != " " else " " for c in line)
                result.append(new_line)
            else:
                result.append(line)
        return result


class GrainFilter:
    """像素颗粒滤镜：用确定性伪随机给字符加颗粒。

    基于 (行, 列, seed) 计算伪随机，把部分字符替换为颗粒字符。
    """

    GRAIN_CHARS = (".", "·", "`", "'")

    def apply_to_lines(
        self,
        lines: list[str],
        intensity: float,
        seed: int = 0,
    ) -> list[str]:
        if intensity <= 0:
            return list(lines)
        # 颗粒密度 = intensity × 20%
        threshold = intensity * 0.2
        result: list[str] = []
        for y, line in enumerate(lines):
            new_chars: list[str] = []
            for x, c in enumerate(line):
                if c == " ":
                    new_chars.append(c)
                    continue
                # 确定性伪随机：基于坐标+种子
                r = self._pseudo_random(x, y, seed)
                if r < threshold:
                    idx = int(r * len(self.GRAIN_CHARS) * 5) % len(self.GRAIN_CHARS)
                    new_chars.append(self.GRAIN_CHARS[idx])
                else:
                    new_chars.append(c)
            result.append("".join(new_chars))
        return result

    @staticmethod
    def _pseudo_random(x: int, y: int, seed: int) -> float:
        """确定性伪随机（0.0-1.0）。"""
        h = (x * 374761393 + y * 668265263 + seed * 2147483647) & 0xFFFFFFFF
        return (h % 10000) / 10000.0


class ChromaticShiftFilter:
    """色彩偏移滤镜：模拟 RGB 通道错位。

    终端模拟：把每行内容水平偏移 1 字符（高强度时偏移更多）。
    """

    def apply_to_lines(self, lines: list[str], intensity: float) -> list[str]:
        if intensity <= 0:
            return list(lines)
        shift = 1 if intensity > 0.4 else 0
        if shift == 0:
            return list(lines)
        result: list[str] = []
        for line in lines:
            # 右移 shift 位，左侧补空格
            shifted = (
                " " * shift + line[:-shift] if len(line) > shift else " " * shift + line
            )
            result.append(shifted)
        return result


class VignetteFilter:
    """暗角滤镜：四角字符淡化。

    终端模拟：把四角的字符替换为暗字符（空格或低亮度符号）。
    """

    def apply_to_lines(
        self,
        lines: list[str],
        intensity: float,
        corner_size: int = 2,
    ) -> list[str]:
        if intensity <= 0 or not lines:
            return list(lines)
        result = list(lines)
        h = len(lines)
        dim_char = " " if intensity > 0.6 else "·"
        for y in range(h):
            line = result[y]
            if not line:
                continue
            chars = list(line)
            w = len(chars)
            # 四角区域淡化
            for x in range(w):
                in_corner = (x < corner_size or x >= w - corner_size) and (
                    y < corner_size or y >= h - corner_size
                )
                if in_corner and chars[x] != " ":
                    chars[x] = dim_char
            result[y] = "".join(chars)
        return result


class RoundCornerFilter:
    """圆角滤镜：四角用圆角字符。

    终端模拟：四角字符替换为 ╭╮╰╯。
    """

    CORNER_CHARS = {
        "tl": "╭",
        "tr": "╮",
        "bl": "╰",
        "br": "╯",
    }

    def apply_to_lines(self, lines: list[str], intensity: float) -> list[str]:
        if intensity <= 0 or len(lines) < 2:
            return list(lines)
        result = [list(line) for line in lines]
        len(result)
        # 左上 / 右上 / 左下 / 右下
        if result[0]:
            result[0][0] = self.CORNER_CHARS["tl"]
            result[0][-1] = self.CORNER_CHARS["tr"]
        if result[-1]:
            result[-1][0] = self.CORNER_CHARS["bl"]
            result[-1][-1] = self.CORNER_CHARS["br"]
        return ["".join(row) for row in result]


# ============== 滤镜管线 ==============

# 滤镜类型 → 实现类映射
_FILTER_IMPLEMENTATIONS: dict[str, Any] = {
    "scanline": ScanlineFilter,
    "grain": GrainFilter,
    "chromatic_shift": ChromaticShiftFilter,
    "vignette": VignetteFilter,
    "round_corner": RoundCornerFilter,
}


class CRTFilterPipeline:
    """CRT 滤镜管线：按顺序应用多个滤镜。

    用法：
        pipeline = CRTFilterPipeline([FilterParams("scanline", 0.5)])
        out_lines = pipeline.apply_to_lines(input_lines, width=40)
    """

    def __init__(self, filters: list[FilterParams] | None = None) -> None:
        self._filters: list[FilterParams] = list(filters) if filters else []

    def add_filter(self, params: FilterParams) -> None:
        """追加滤镜。"""
        self._filters.append(params)

    def clear(self) -> None:
        self._filters.clear()

    @property
    def filters(self) -> list[FilterParams]:
        return list(self._filters)

    def apply_to_lines(self, lines: list[str], width: int = 80) -> list[str]:
        """按顺序应用所有滤镜到行列表。"""
        result = list(lines)
        for fp in self._filters:
            impl_cls = _FILTER_IMPLEMENTATIONS.get(fp.type)
            if impl_cls is None:
                continue
            impl = impl_cls()
            result = impl.apply_to_lines(result, fp.intensity)
        return result

    def apply_to_plain(self, text: str, width: int = 80) -> str:
        """应用滤镜到多行文本。"""
        lines = text.split("\n")
        result = self.apply_to_lines(lines, width)
        return "\n".join(result)


_FILTER_PARAM_CACHE: dict[str, FilterParams] = {}


def register_filter_param(name: str, params: FilterParams) -> None:
    """注册自定义滤镜参数供后续复用。"""
    _FILTER_PARAM_CACHE[name] = params


def get_filter_param(name: str) -> FilterParams | None:
    return _FILTER_PARAM_CACHE.get(name)


def apply_preset(
    name: str,
    intensity_level: int = 6,
    registry: HardwarePresetRegistry | None = None,
) -> CRTFilterPipeline:
    """按预设名快速构建滤镜管线。"""
    return build_preset_pipeline(name, intensity_level, registry)


def custom_filter(params: list[FilterParams]) -> CRTFilterPipeline:
    """从自定义参数列表创建滤镜管线。"""
    return CRTFilterPipeline(params)


def build_preset_pipeline(
    preset_name: str,
    intensity_level: int = 6,
    registry: HardwarePresetRegistry | None = None,
) -> CRTFilterPipeline:
    """按硬件预设 + 强度档位构建滤镜管线。

    Args:
        preset_name: 硬件预设名（HARDWARE_PRESETS 之一）。
        intensity_level: 强度档位 0-12（整体缩放各滤镜强度）。
        registry: 预设注册表（None 用默认）。
    """
    reg = registry or HardwarePresetRegistry()
    preset = reg.get(preset_name)
    scale = _level_to_ratio(intensity_level)
    filters = [
        FilterParams(fp.type, min(1.0, fp.intensity * scale)) for fp in preset.filters
    ]
    return CRTFilterPipeline(filters)


# ============== 低像素降噪 ==============


class PixelDenoiser:
    """低像素降噪：量化到调色板最近色，抹平平滑渐变。

    还原硬色块复古像素质感，全平台输出画风统一。
    """

    def __init__(self, palette: list[Color] | None = None) -> None:
        # 默认用 PALETTE_16 的 16 色
        if palette is None:
            palette = list(PALETTE_16.values())
        self._palette: list[Color] = list(palette)

    @property
    def palette(self) -> list[Color]:
        return list(self._palette)

    def quantize_to_palette(self, color: Color) -> Color:
        """量化到调色板最近色（欧氏距离最近邻）。"""
        if not self._palette:
            return color
        best = self._palette[0]
        best_dist = self._distance(color, best)
        for c in self._palette[1:]:
            d = self._distance(color, c)
            if d < best_dist:
                best_dist = d
                best = c
        return best

    @staticmethod
    def _distance(a: Color, b: Color) -> float:
        """RGB 欧氏距离。"""
        return ((a.r - b.r) ** 2 + (a.g - b.g) ** 2 + (a.b - b.b) ** 2) ** 0.5

    def denoise_color(self, color: Color) -> Color:
        """单色降噪（量化到调色板）。"""
        return self.quantize_to_palette(color)

    def denoise_colors(self, colors: list[Color]) -> list[Color]:
        """批量降噪。"""
        return [self.quantize_to_palette(c) for c in colors]

    def denoise_gradient(self, colors: list[Color]) -> list[Color]:
        """降噪渐变：量化后合并相邻相同色，还原硬色块。

        相邻不同色但量化后相同的，保留为一个色块（已是相同色）。
        此方法主要确保输出都是调色板色。
        """
        return self.denoise_colors(colors)

    def count_unique_after_denoise(self, colors: list[Color]) -> int:
        """降噪后剩余的唯一色数（衡量渐变被抹平的程度）。"""
        denoised = self.denoise_colors(colors)
        unique = {(c.r, c.g, c.b) for c in denoised}
        return len(unique)
