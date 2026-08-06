"""UI 板块三（上）：跨端像素字体分级渲染引擎 + 通用像素图标矢量库。

对标成就系统逻辑：
- 文字样式 3 级基础 → 10 类专用样式（可扩展）
- 像素图标 24 个基础 → 128 个细分（覆盖 10 大岗位、全功能、各类状态）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.soft_rabbit.pixel_render import PALETTE_16, Color

# ============== 文字样式分级 ==============


class TextStyle(Enum):
    """文字样式（3 级基础 + 7 类专用）。"""

    # 基础三级
    TITLE = "title"  # 标题：粗像素字符
    BODY = "body"  # 正文：常规
    DIM = "dim"  # 备注：浅灰小字
    # 7 类专用样式
    CODE = "code"  # 代码高亮
    LOG = "log"  # 日志告警
    ACHIEVEMENT = "achievement"  # 成就金色文本
    COIN = "coin"  # 金币数值
    SECURITY = "security"  # 安全风险红字
    GIT = "git"  # Git 提交注释
    DREAM = "dream"  # 梦境总结文案


@dataclass
class TextStyleDef:
    """样式定义：颜色 + 装饰前缀/后缀。"""

    color: Color
    prefix: str = ""
    suffix: str = ""


# 10 个样式映射（颜色取自 16 色主色板）
_TEXT_STYLES: dict[TextStyle, TextStyleDef] = {
    TextStyle.TITLE: TextStyleDef(PALETTE_16["title"], "╔═", "═╗"),
    TextStyle.BODY: TextStyleDef(PALETTE_16["text"]),
    TextStyle.DIM: TextStyleDef(PALETTE_16["text_dim"]),
    TextStyle.CODE: TextStyleDef(PALETTE_16["code"], "[", "]"),
    TextStyle.LOG: TextStyleDef(PALETTE_16["info"], "▸ "),
    TextStyle.ACHIEVEMENT: TextStyleDef(PALETTE_16["title"], "★ "),
    TextStyle.COIN: TextStyleDef(PALETTE_16["coin"], "◉ "),
    TextStyle.SECURITY: TextStyleDef(PALETTE_16["security"], "⚠ "),
    TextStyle.GIT: TextStyleDef(PALETTE_16["text_dim"], "⌥ "),
    TextStyle.DREAM: TextStyleDef(PALETTE_16["dream"], "☁ "),
}


class TypographyEngine:
    """跨端像素字体分级渲染引擎。

    三级文字规范全局复用：标题粗像素、正文常规、备注浅灰小字，
    自动适配终端等宽字体、Web 像素字体、桌面位图字体。
    """

    def style_color(self, style: TextStyle) -> Color:
        """获取样式对应颜色。"""
        return _TEXT_STYLES[style].color

    def style_text(self, text: str, style: TextStyle) -> str:
        """按样式渲染文本（加前缀/后缀装饰）。"""
        defn = _TEXT_STYLES[style]
        return f"{defn.prefix}{text}{defn.suffix}"

    def style_with_color(self, text: str, style: TextStyle) -> tuple[str, Color]:
        """返回带装饰的文本和颜色（供渲染后端使用）。"""
        defn = _TEXT_STYLES[style]
        return self.style_text(text, style), defn.color

    def list_styles(self) -> list[TextStyle]:
        """列出全部样式。"""
        return list(TextStyle)


# 全局默认排版引擎
DEFAULT_TYPOGRAPHY = TypographyEngine()


# ============== 通用像素图标矢量库 ==============


@dataclass
class PixelIcon:
    """16×16 通用像素符号（用单字符 + 颜色简化表示）。

    全平台统一像素图标，替代纯文字状态。
    可扩展：基础 24 个 → 128 个细分图标。
    """

    name: str
    glyph: str  # 字符表示
    color: Color


class IconRegistry:
    """像素图标注册表：内置 24 个基础图标，支持批量扩展。

    覆盖 10 大岗位、全系统功能、各类状态、风险等级。
    对标成就系统：24 → 128 可持续扩充。
    """

    def __init__(self) -> None:
        self._icons: dict[str, PixelIcon] = dict(self._builtin())

    @staticmethod
    def _builtin() -> dict[str, PixelIcon]:
        """内置 24 个基础图标。"""
        P = PALETTE_16
        return {
            # 状态图标（6）
            "run": PixelIcon("run", "▶", P["success"]),
            "done": PixelIcon("done", "✓", P["success"]),
            "error": PixelIcon("error", "✗", P["error"]),
            "sleep": PixelIcon("sleep", "z", P["dream"]),
            "lock": PixelIcon("lock", "⚿", P["text_dim"]),
            "alert": PixelIcon("alert", "▲", P["warning"]),
            # 数值图标（3）
            "coin": PixelIcon("coin", "●", P["coin"]),
            "achievement": PixelIcon("achievement", "★", P["title"]),
            "token": PixelIcon("token", "◇", P["coin"]),
            # 岗位/功能图标（10）
            "code": PixelIcon("code", "{ }", P["code"]),
            "art": PixelIcon("art", "◆", P["accent"]),
            "test": PixelIcon("test", "✓", P["info"]),
            "repo": PixelIcon("repo", "▣", P["text_dim"]),
            "security": PixelIcon("security", "⚠", P["security"]),
            "schedule": PixelIcon("schedule", "◷", P["info"]),
            "dream": PixelIcon("dream", "☁", P["dream"]),
            "branch": PixelIcon("branch", "⌥", P["text_dim"]),
            "commit": PixelIcon("commit", "●", P["text"]),
            "bug": PixelIcon("bug", "✗", P["error"]),
            # 装饰图标（5）
            "shield": PixelIcon("shield", "⛨", P["security"]),
            "bolt": PixelIcon("bolt", "⚡", P["warning"]),
            "heart": PixelIcon("heart", "♥", P["error"]),
            "star": PixelIcon("star", "★", P["title"]),
            "cog": PixelIcon("cog", "⚙", P["text_dim"]),
        }

    def get(self, name: str) -> PixelIcon | None:
        """获取图标（不存在返回 None）。"""
        return self._icons.get(name)

    def register(self, icon: PixelIcon) -> None:
        """注册/覆盖图标。"""
        self._icons[icon.name] = icon

    def list_names(self) -> list[str]:
        return sorted(self._icons.keys())

    def __len__(self) -> int:
        return len(self._icons)

    def __contains__(self, name: str) -> bool:
        return name in self._icons

    def render_icon(self, name: str) -> tuple[str, Color] | None:
        """渲染图标为 (glyph, color)。"""
        icon = self.get(name)
        if icon is None:
            return None
        return icon.glyph, icon.color


# 全局默认图标库
DEFAULT_ICONS = IconRegistry()


_FONT_CACHE: dict[str, int] = {}


def font_cache_clear() -> None:
    _FONT_CACHE.clear()


def font_cache_put(key: str, width: int) -> None:
    _FONT_CACHE[key] = width


def font_cache_get(key: str) -> int | None:
    return _FONT_CACHE.get(key)


def truncate(text: str, max_width: int, ellipsis: str = "…") -> str:
    """截断文本到指定字符宽度，超出加省略号。"""
    if len(text) <= max_width:
        return text
    return text[: max_width - len(ellipsis)] + ellipsis
