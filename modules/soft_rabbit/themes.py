"""UI 板块四：多主题皮肤系统。

四大能力（对标成就系统三阶分级扩展逻辑）：
1. 跨端主题一键同步引擎：一套配置同步色板/边框/网格/动效/字体/圆角到所有环境
2. 36 套三阶主题：6 大系列（复古主机/工业控制台/暗调森林/琥珀CRT/极简办公/赛博像素）
   × 3 阶（铜/银/金）× 2 模式（亮/暗）= 36 种组合
3. 角色专属 UI 装饰：12 个员工独立主色/气泡边框/工位底色 + 3 套换装（工作/休眠/报错）
4. 护眼动态亮度自适应：按本地时间调节亮度，深夜降饱和、白天提亮

纯 Python 标准库，无第三方依赖，无 TRAe 绑定。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from modules.soft_rabbit.pixel_render import Color


# ============== 主题数据结构 ==============

@dataclass
class ThemePalette:
    """主题色板（11 个语义色）。"""
    bg: Color = field(default_factory=lambda: Color(15, 15, 25))
    panel: Color = field(default_factory=lambda: Color(25, 25, 40))
    border: Color = field(default_factory=lambda: Color(80, 80, 110))
    text: Color = field(default_factory=lambda: Color(220, 220, 230))
    text_dim: Color = field(default_factory=lambda: Color(120, 120, 140))
    title: Color = field(default_factory=lambda: Color(255, 220, 80))
    success: Color = field(default_factory=lambda: Color(80, 220, 100))
    warning: Color = field(default_factory=lambda: Color(255, 180, 60))
    error: Color = field(default_factory=lambda: Color(240, 80, 80))
    info: Color = field(default_factory=lambda: Color(80, 180, 240))
    accent: Color = field(default_factory=lambda: Color(200, 120, 240))

    def to_dict(self) -> dict[str, Color]:
        return {
            "bg": self.bg, "panel": self.panel, "border": self.border,
            "text": self.text, "text_dim": self.text_dim, "title": self.title,
            "success": self.success, "warning": self.warning, "error": self.error,
            "info": self.info, "accent": self.accent,
        }


# 边框样式：single / double / rounded / ascii / pixel
BORDER_STYLES = ("single", "double", "rounded", "ascii", "pixel")


@dataclass
class ThemeBorder:
    """主题边框样式。"""
    style: str = "single"      # 见 BORDER_STYLES
    color_key: str = "border"  # 引用 ThemePalette 的键


# 6 大系列
THEME_SERIES = (
    "retro_console",       # 复古主机
    "industrial_console",  # 工业控制台
    "dark_forest",         # 暗调森林
    "amber_crt",           # 琥珀 CRT
    "minimal_office",      # 极简办公
    "cyber_pixel",         # 赛博像素
)

# 3 阶（铜/银/金）
THEME_TIERS = ("bronze", "silver", "gold")

# 2 模式
THEME_MODES = ("dark", "light")

# 阶级 → 网格/动效/字体/圆角 参数（高阶更精致）
_TIER_PARAMS: dict[str, dict[str, Any]] = {
    "bronze": {"grid_size": 8, "anim_intensity": 0.5, "font_size": 12, "corner_radius": 0},
    "silver": {"grid_size": 8, "anim_intensity": 0.8, "font_size": 14, "corner_radius": 2},
    "gold":   {"grid_size": 4, "anim_intensity": 1.0, "font_size": 16, "corner_radius": 4},
}


@dataclass
class Theme:
    """完整主题配置。"""
    name: str                       # 主题名（唯一）
    series: str                     # 系列（THEME_SERIES）
    tier: str                       # 阶级（THEME_TIERS）
    mode: str                       # 模式（dark/light）
    palette: ThemePalette = field(default_factory=ThemePalette)
    border: ThemeBorder = field(default_factory=ThemeBorder)
    grid_size: int = 8
    anim_intensity: float = 0.8
    font_size: int = 14
    corner_radius: int = 2
    brightness: float = 1.0         # 亮度系数（0.5-1.5）


# ============== 6 系列 × 2 模式色板预设 ==============
# 每个系列定义 dark / light 两套色板，再叠加 tier 参数生成完整主题

_SERIES_PALETTES: dict[str, dict[str, ThemePalette]] = {
    "retro_console": {
        "dark": ThemePalette(
            bg=Color(15, 15, 30), panel=Color(30, 30, 50), border=Color(100, 100, 140),
            text=Color(230, 230, 240), text_dim=Color(130, 130, 160),
            title=Color(255, 220, 80), success=Color(100, 220, 100),
            warning=Color(255, 180, 60), error=Color(240, 80, 80),
            info=Color(100, 180, 240), accent=Color(200, 120, 240),
        ),
        "light": ThemePalette(
            bg=Color(240, 240, 245), panel=Color(225, 225, 235), border=Color(100, 100, 140),
            text=Color(30, 30, 50), text_dim=Color(110, 110, 130),
            title=Color(180, 140, 30), success=Color(40, 160, 60),
            warning=Color(200, 130, 30), error=Color(200, 50, 50),
            info=Color(40, 120, 200), accent=Color(150, 80, 200),
        ),
    },
    "industrial_console": {
        "dark": ThemePalette(
            bg=Color(20, 25, 20), panel=Color(30, 38, 30), border=Color(90, 110, 90),
            text=Color(200, 220, 200), text_dim=Color(110, 130, 110),
            title=Color(180, 255, 180), success=Color(80, 200, 100),
            warning=Color(220, 200, 60), error=Color(240, 120, 80),
            info=Color(120, 200, 180), accent=Color(180, 220, 140),
        ),
        "light": ThemePalette(
            bg=Color(230, 235, 230), panel=Color(215, 225, 215), border=Color(80, 110, 80),
            text=Color(30, 45, 30), text_dim=Color(100, 120, 100),
            title=Color(60, 130, 60), success=Color(40, 150, 60),
            warning=Color(170, 150, 30), error=Color(190, 80, 40),
            info=Color(40, 130, 120), accent=Color(110, 150, 70),
        ),
    },
    "dark_forest": {
        "dark": ThemePalette(
            bg=Color(12, 20, 16), panel=Color(20, 35, 25), border=Color(60, 90, 70),
            text=Color(200, 220, 200), text_dim=Color(100, 120, 105),
            title=Color(180, 230, 140), success=Color(120, 220, 120),
            warning=Color(230, 200, 100), error=Color(240, 100, 80),
            info=Color(140, 200, 220), accent=Color(180, 200, 140),
        ),
        "light": ThemePalette(
            bg=Color(235, 245, 238), panel=Color(220, 235, 225), border=Color(70, 110, 85),
            text=Color(25, 45, 30), text_dim=Color(95, 115, 100),
            title=Color(80, 140, 50), success=Color(50, 160, 70),
            warning=Color(180, 150, 40), error=Color(190, 70, 50),
            info=Color(50, 130, 160), accent=Color(110, 140, 70),
        ),
    },
    "amber_crt": {
        "dark": ThemePalette(
            bg=Color(20, 12, 5), panel=Color(35, 22, 8), border=Color(120, 80, 30),
            text=Color(255, 200, 100), text_dim=Color(160, 120, 60),
            title=Color(255, 230, 140), success=Color(220, 180, 80),
            warning=Color(255, 200, 60), error=Color(255, 120, 60),
            info=Color(220, 160, 80), accent=Color(255, 180, 100),
        ),
        "light": ThemePalette(
            bg=Color(250, 240, 220), panel=Color(240, 225, 195), border=Color(140, 100, 50),
            text=Color(80, 50, 20), text_dim=Color(130, 100, 60),
            title=Color(150, 90, 20), success=Color(150, 110, 30),
            warning=Color(180, 130, 30), error=Color(190, 80, 30),
            info=Color(150, 100, 40), accent=Color(170, 110, 40),
        ),
    },
    "minimal_office": {
        "dark": ThemePalette(
            bg=Color(22, 22, 24), panel=Color(32, 32, 36), border=Color(70, 70, 78),
            text=Color(220, 220, 225), text_dim=Color(130, 130, 138),
            title=Color(230, 230, 240), success=Color(100, 200, 130),
            warning=Color(230, 190, 90), error=Color(230, 100, 100),
            info=Color(100, 170, 230), accent=Color(180, 180, 200),
        ),
        "light": ThemePalette(
            bg=Color(252, 252, 254), panel=Color(242, 242, 246), border=Color(180, 180, 188),
            text=Color(40, 40, 48), text_dim=Color(120, 120, 130),
            title=Color(30, 30, 40), success=Color(50, 160, 80),
            warning=Color(180, 140, 40), error=Color(190, 60, 60),
            info=Color(50, 110, 180), accent=Color(90, 90, 110),
        ),
    },
    "cyber_pixel": {
        "dark": ThemePalette(
            bg=Color(15, 8, 30), panel=Color(28, 15, 50), border=Color(120, 60, 200),
            text=Color(220, 200, 255), text_dim=Color(130, 110, 170),
            title=Color(255, 100, 220), success=Color(80, 255, 180),
            warning=Color(255, 200, 80), error=Color(255, 60, 120),
            info=Color(80, 200, 255), accent=Color(200, 80, 255),
        ),
        "light": ThemePalette(
            bg=Color(245, 235, 255), panel=Color(232, 220, 250), border=Color(130, 70, 200),
            text=Color(50, 25, 80), text_dim=Color(115, 95, 150),
            title=Color(180, 40, 150), success=Color(40, 160, 100),
            warning=Color(180, 130, 30), error=Color(190, 50, 90),
            info=Color(40, 110, 180), accent=Color(140, 50, 180),
        ),
    },
}

# 系列 → 默认边框样式
_SERIES_BORDER: dict[str, ThemeBorder] = {
    "retro_console": ThemeBorder("pixel", "border"),
    "industrial_console": ThemeBorder("double", "border"),
    "dark_forest": ThemeBorder("ascii", "border"),
    "amber_crt": ThemeBorder("single", "title"),
    "minimal_office": ThemeBorder("single", "border"),
    "cyber_pixel": ThemeBorder("double", "accent"),
}


def _build_theme(series: str, tier: str, mode: str) -> Theme:
    """根据系列/阶级/模式组装主题。"""
    palette = _SERIES_PALETTES[series][mode]
    border = _SERIES_BORDER[series]
    params = _TIER_PARAMS[tier]
    name = f"{series}.{tier}.{mode}"
    return Theme(
        name=name, series=series, tier=tier, mode=mode,
        palette=palette, border=border,
        grid_size=params["grid_size"],
        anim_intensity=params["anim_intensity"],
        font_size=params["font_size"],
        corner_radius=params["corner_radius"],
        brightness=1.0,
    )


# ============== 主题注册表 ==============

class ThemeRegistry:
    """主题注册表。

    预置 36 套主题（6 系列 × 3 阶 × 2 模式），支持自定义注册。
    对标成就系统：分梯次批量扩展。
    """

    def __init__(self) -> None:
        self._themes: dict[str, Theme] = {}
        self._build_builtin()

    def _build_builtin(self) -> None:
        """构建 36 套预置主题。"""
        for series in THEME_SERIES:
            for tier in THEME_TIERS:
                for mode in THEME_MODES:
                    t = _build_theme(series, tier, mode)
                    self._themes[t.name] = t

    def get(self, name: str) -> Theme:
        """获取主题。不存在抛 KeyError。"""
        if name not in self._themes:
            raise KeyError(f"未知主题: {name}（可选: {self.list_themes()[:5]}...）")
        return self._themes[name]

    def list_themes(self) -> list[str]:
        return sorted(self._themes.keys())

    def list_by_series(self, series: str) -> list[str]:
        return sorted(n for n, t in self._themes.items() if t.series == series)

    def list_by_tier(self, tier: str) -> list[str]:
        return sorted(n for n, t in self._themes.items() if t.tier == tier)

    def list_by_mode(self, mode: str) -> list[str]:
        return sorted(n for n, t in self._themes.items() if t.mode == mode)

    def register(self, theme: Theme) -> None:
        """注册自定义主题。"""
        self._themes[theme.name] = theme

    def count(self) -> int:
        return len(self._themes)


# ============== 跨端主题同步引擎 ==============

class ThemeSyncEngine:
    """跨端主题一键同步引擎。

    一套主题配置序列化为字典，可同步到终端 / Web / 桌面任意环境。
    """

    def __init__(self, registry: ThemeRegistry) -> None:
        self._registry = registry
        self._active: Theme | None = None

    @property
    def active(self) -> Theme | None:
        return self._active

    def apply(self, name: str) -> Theme:
        """应用主题（设置为活跃）。"""
        theme = self._registry.get(name)
        self._active = theme
        return theme

    def export_config(self, theme: Theme | None = None) -> dict[str, Any]:
        """导出主题配置为字典（跨端同步用）。"""
        t = theme or self._active
        if t is None:
            raise ValueError("未指定主题")
        p = t.palette
        return {
            "name": t.name, "series": t.series, "tier": t.tier, "mode": t.mode,
            "palette": {k: (c.r, c.g, c.b) for k, c in p.to_dict().items()},
            "border": {"style": t.border.style, "color_key": t.border.color_key},
            "grid_size": t.grid_size, "anim_intensity": t.anim_intensity,
            "font_size": t.font_size, "corner_radius": t.corner_radius,
            "brightness": t.brightness,
        }

    def import_config(self, data: dict[str, Any]) -> Theme:
        """从字典反序列化主题（不注册到 registry）。"""
        pal_data = data.get("palette", {})
        palette = ThemePalette()
        for k, rgb in pal_data.items():
            if isinstance(rgb, (tuple, list)) and len(rgb) == 3:
                setattr(palette, k, Color(int(rgb[0]), int(rgb[1]), int(rgb[2])))
        border_data = data.get("border", {})
        border = ThemeBorder(
            style=border_data.get("style", "single"),
            color_key=border_data.get("color_key", "border"),
        )
        return Theme(
            name=data.get("name", "imported"),
            series=data.get("series", "custom"),
            tier=data.get("tier", "bronze"),
            mode=data.get("mode", "dark"),
            palette=palette, border=border,
            grid_size=data.get("grid_size", 8),
            anim_intensity=data.get("anim_intensity", 0.8),
            font_size=data.get("font_size", 14),
            corner_radius=data.get("corner_radius", 2),
            brightness=data.get("brightness", 1.0),
        )


# ============== 角色专属 UI 装饰 ==============

@dataclass
class RoleSkin:
    """角色专属 UI 装饰：主色/气泡边框/工位底色 + 3 套换装帧。"""
    agent_id: str
    primary_color: Color
    bubble_border: str        # 边框样式（BORDER_STYLES）
    workstation_bg: Color
    # 3 套换装：工作/休眠/报错，每套 2 帧循环
    outfit_frames: dict[str, list[str]] = field(default_factory=dict)


# 12 个员工专属皮肤（主色基于角色个性；子岗位基于父角色做颜色变体）
_ROLE_SKINS: dict[str, RoleSkin] = {
    "squirrel": RoleSkin(
        "squirrel", Color(255, 160, 60), "single", Color(45, 30, 15),
        {"working": ["🐿⌐", "🐿┐"], "sleeping": ["🐿~", "🐿~"], "error": ["🐿✗"]},
    ),
    "fox": RoleSkin(
        "fox", Color(255, 140, 80), "single", Color(45, 25, 15),
        {"working": ["🦊▶", "🦊▶"], "sleeping": ["🦊~", "🦊~"], "error": ["🦊!"]},
    ),
    "hedgehog": RoleSkin(
        "hedgehog", Color(100, 180, 100), "pixel", Color(20, 35, 20),
        {"working": ["🦔▞", "🦔▚"], "sleeping": ["🦔z", "🦔Z"], "error": ["🦔⚠"]},
    ),
    "beaver": RoleSkin(
        "beaver", Color(160, 110, 70), "ascii", Color(35, 25, 15),
        {"working": ["🦫≈", "🦫≋"], "sleeping": ["🦫z", "🦫Z"], "error": ["🦫✗"]},
    ),
    "owl": RoleSkin(
        "owl", Color(180, 120, 220), "double", Color(35, 20, 45),
        {"working": ["🦉●", "🦉○"], "sleeping": ["🦉—", "🦉—"], "error": ["🦉!?"]},
    ),
    "soft_rabbit": RoleSkin(
        "soft_rabbit", Color(255, 180, 200), "rounded", Color(40, 25, 30),
        {"working": ["🐰▔", "🐰▁"], "sleeping": ["🐰~", "🐰~"], "error": ["🐰!"]},
    ),
    "fox_security": RoleSkin(
        "fox_security", Color(220, 80, 80), "double", Color(40, 20, 20),
        {"working": ["🦊▶", "🦊▶"], "sleeping": ["🦊~", "🦊~"], "error": ["🦊⚠"]},
    ),
    "fox_art": RoleSkin(
        "fox_art", Color(220, 140, 180), "rounded", Color(40, 25, 35),
        {"working": ["🦊▞", "🦊▚"], "sleeping": ["🦊~", "🦊~"], "error": ["🦊!"]},
    ),
    "hedgehog_static": RoleSkin(
        "hedgehog_static", Color(160, 110, 90), "pixel", Color(25, 30, 20),
        {"working": ["🦔▞", "🦔▚"], "sleeping": ["🦔z", "🦔Z"], "error": ["🦔⚠"]},
    ),
    "hedgehog_runtime": RoleSkin(
        "hedgehog_runtime", Color(180, 130, 110), "ascii", Color(30, 28, 25),
        {"working": ["🦔≈", "🦔≋"], "sleeping": ["🦔z", "🦔Z"], "error": ["🦔!"]},
    ),
    "hedgehog_keymgmt": RoleSkin(
        "hedgehog_keymgmt", Color(120, 90, 140), "double", Color(25, 20, 35),
        {"working": ["🦔▞", "🦔▚"], "sleeping": ["🦔z", "🦔Z"], "error": ["🦔⚠"]},
    ),
    "sparrow": RoleSkin(
        "sparrow", Color(180, 220, 100), "single", Color(30, 35, 20),
        {"working": ["🐦▔", "🐦▁"], "sleeping": ["🐦~", "🐦~"], "error": ["🐦!"]},
    ),
}


class RoleSkinRegistry:
    """角色皮肤注册表。"""

    def __init__(self) -> None:
        self._skins: dict[str, RoleSkin] = dict(_ROLE_SKINS)

    def get(self, agent_id: str) -> RoleSkin:
        if agent_id not in self._skins:
            raise KeyError(f"未知角色: {agent_id}")
        return self._skins[agent_id]

    def list_roles(self) -> list[str]:
        return sorted(self._skins.keys())

    def register(self, skin: RoleSkin) -> None:
        self._skins[skin.agent_id] = skin

    def get_outfit_frame(self, agent_id: str, state: str, frame_idx: int = 0) -> str:
        """取角色某状态的换装帧。"""
        skin = self.get(agent_id)
        frames = skin.outfit_frames.get(state) or skin.outfit_frames.get("working") or ["?"]
        return frames[frame_idx % len(frames)]


# ============== 护眼动态亮度自适应 ==============

class BrightnessAdapter:
    """护眼动态亮度自适应。

    按本地时间调节亮度系数：
    - 06-18 时：1.0（白天，正常亮度）
    - 18-22 时：0.85（傍晚，略降）
    - 22-06 时：0.7（深夜，护眼低饱和）
    """

    # 时段 → 亮度系数
    _TIME_BRIGHTNESS = (
        (6, 1.0),   # 06:00+ 白天
        (18, 0.85), # 18:00+ 傍晚
        (22, 0.7),  # 22:00+ 深夜
    )

    def auto_brightness(self, hour: int | None = None) -> float:
        """根据小时返回亮度系数（0.5-1.5）。"""
        if hour is None:
            hour = time.localtime().tm_hour
        # 按阈值分段：深夜 22-06 / 傍晚 18-22 / 白天 06-18
        if hour >= 22 or hour < 6:
            return 0.7
        if hour >= 18:
            return 0.85
        return 1.0

    def adjust_color(self, color: Color, brightness: float) -> Color:
        """按亮度系数调整单色（0.5-1.5）。"""
        b = max(0.3, min(1.5, brightness))
        return Color(
            r=max(0, min(255, int(color.r * b))),
            g=max(0, min(255, int(color.g * b))),
            b=max(0, min(255, int(color.b * b))),
        )

    def apply_to_palette(self, palette: ThemePalette, brightness: float) -> ThemePalette:
        """按亮度系数调整整块色板。"""
        if abs(brightness - 1.0) < 0.01:
            return palette
        return ThemePalette(
            bg=self.adjust_color(palette.bg, brightness),
            panel=self.adjust_color(palette.panel, brightness),
            border=self.adjust_color(palette.border, brightness),
            text=self.adjust_color(palette.text, brightness),
            text_dim=self.adjust_color(palette.text_dim, brightness),
            title=self.adjust_color(palette.title, brightness),
            success=self.adjust_color(palette.success, brightness),
            warning=self.adjust_color(palette.warning, brightness),
            error=self.adjust_color(palette.error, brightness),
            info=self.adjust_color(palette.info, brightness),
            accent=self.adjust_color(palette.accent, brightness),
        )


# ============== 主题管理器（整合） ==============

class ThemeManager:
    """主题管理器：整合 registry + sync + brightness + role skin。

    用法：
        mgr = ThemeManager()
        mgr.set_theme("cyber_pixel.gold.dark")
        mgr.auto_adjust_brightness()  # 按当前时间自适应
        theme = mgr.get_active_theme()
        skin = mgr.get_role_skin("squirrel")
    """

    def __init__(
        self,
        registry: ThemeRegistry | None = None,
        sync: ThemeSyncEngine | None = None,
        brightness: BrightnessAdapter | None = None,
        role_skins: RoleSkinRegistry | None = None,
    ) -> None:
        self._registry = registry or ThemeRegistry()
        self._sync = sync or ThemeSyncEngine(self._registry)
        self._brightness = brightness or BrightnessAdapter()
        self._role_skins = role_skins or RoleSkinRegistry()

    @property
    def registry(self) -> ThemeRegistry:
        return self._registry

    @property
    def sync(self) -> ThemeSyncEngine:
        return self._sync

    @property
    def role_skins(self) -> RoleSkinRegistry:
        return self._role_skins

    def set_theme(self, name: str) -> Theme:
        """设置活跃主题。"""
        return self._sync.apply(name)

    def get_active_theme(self) -> Theme:
        if self._sync.active is None:
            return self.set_theme("retro_console.bronze.dark")
        return self._sync.active

    def auto_adjust_brightness(self, hour: int | None = None) -> Theme:
        """按本地时间自适应亮度，返回调整后的主题快照（不修改原主题）。"""
        base = self.get_active_theme()
        b = self._brightness.auto_brightness(hour)
        adjusted_palette = self._brightness.apply_to_palette(base.palette, b)
        # 返回快照（不持久化，每次调用重新计算）
        return Theme(
            name=base.name + f"@b{b:.2f}", series=base.series, tier=base.tier,
            mode=base.mode, palette=adjusted_palette, border=base.border,
            grid_size=base.grid_size, anim_intensity=base.anim_intensity,
            font_size=base.font_size, corner_radius=base.corner_radius,
            brightness=b,
        )

    def get_role_skin(self, agent_id: str) -> RoleSkin:
        return self._role_skins.get(agent_id)

    def export_active_config(self) -> dict[str, Any]:
        """导出当前活跃主题配置（跨端同步）。"""
        return self._sync.export_config(self.get_active_theme())


# ============== 主题继承 ==============

def extend_theme(parent: Theme, overrides: dict[str, Any], name: str) -> Theme:
    """基于 parent 主题继承并覆盖字段生成新主题。

    overrides 支持: palette, border, grid_size, anim_intensity,
    font_size, corner_radius, brightness, mode, tier, series。
    """
    new_palette = ThemePalette(
        **{k: getattr(parent.palette, k) for k in parent.palette.to_dict()}
    )
    palette_overrides = overrides.get("palette", {})
    for k, v in palette_overrides.items():
        if hasattr(new_palette, k):
            setattr(new_palette, k, v)

    new_border = ThemeBorder(
        style=overrides.get("border_style", parent.border.style),
        color_key=overrides.get("border_color_key", parent.border.color_key),
    )

    return Theme(
        name=name,
        series=overrides.get("series", parent.series),
        tier=overrides.get("tier", parent.tier),
        mode=overrides.get("mode", parent.mode),
        palette=new_palette,
        border=new_border,
        grid_size=overrides.get("grid_size", parent.grid_size),
        anim_intensity=overrides.get("anim_intensity", parent.anim_intensity),
        font_size=overrides.get("font_size", parent.font_size),
        corner_radius=overrides.get("corner_radius", parent.corner_radius),
        brightness=overrides.get("brightness", parent.brightness),
    )


def apply_theme(name: str, registry: ThemeRegistry | None = None,
                sync: ThemeSyncEngine | None = None) -> Theme:
    """快捷函数：按名称激活主题。"""
    reg = registry or ThemeRegistry()
    sync_engine = sync or ThemeSyncEngine(reg)
    return sync_engine.apply(name)
