"""BlueDeer P6 像素沙盘美术素材库。

P6 扩容新增：
- 背景工位区块：11 个员工工位的静态背景装饰
- 全局装饰像素元素：树/草地/路径/灯笼
- 告警闪烁动画：高危时的红色边框闪烁 2 帧
- 任务流转连线动画：任务从看板到员工的虚线流动 2 帧

纯数据定义，由 TUIRenderer 按需取用。
"""

from __future__ import annotations

from core.pixel_canvas import Color


# ============== 背景工位区块 ==============
# 每个工位 8 宽 × 5 高，作为头像的背景框
# 字符含义：'=' 桌面，'|' 桌腿，'*' 装饰

WORKSTATION_BG: list[str] = [
    "        ",
    "========",
    "        ",
    "|    | |",
    "|____|_|",
]

# 工位主题色（按工位序号循环）
WORKSTATION_COLORS: list[int] = [
    Color.DARK_GREEN, Color.DARK_BLUE, Color.BROWN,
    Color.PURPLE, Color.TEAL,
]


# ============== 全局装饰像素元素 ==============
# 树（5×4）
TREE_SPRITE: list[str] = [
    " ### ",
    "#####",
    " ### ",
    "  #  ",
]

# 草丛（3×1）
GRASS_SPRITE: list[str] = ["'w'"]

# 路径砖（2×1）
PATH_BRICK: list[str] = ["::"]

# 灯笼（3×3）
LANTERN_SPRITE: list[str] = [
    "\\|/",
    "-o-",
    "/|\\",
]

# 装饰元素颜色
TREE_COLOR = Color.DARK_GREEN
GRASS_COLOR = Color.LIME
PATH_COLOR = Color.BROWN
LANTERN_COLOR = Color.YELLOW


# ============== 告警闪烁动画 ==============
# 高危告警时整块边框红/暗红闪烁，2 帧循环

ALERT_BLINK_FRAMES: list[list[str]] = [
    # 帧 0：亮红边框
    [
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",
        "!                                        !",
        "!                                        !",
        "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",
    ],
    # 帧 1：暗（用 '.' 表示暗淡）
    [
        "........................................",
        ".                                        .",
        ".                                        .",
        "........................................",
    ],
]

ALERT_BLINK_COLORS: list[int] = [Color.RED, Color.GRAY]


# ============== 任务流转连线动画 ==============
# 任务从看板流向员工时的虚线流动，2 帧循环
# 用 '>' 字符表示流向，'.' 表示空位

TASK_FLOW_FRAMES: list[list[str]] = [
    # 帧 0
    [".>.>.>.>.>.>."],
    # 帧 1（错位）
    [">.>.>.>.>.>.>"],
]

TASK_FLOW_COLOR = Color.CYAN


# ============== 状态指示图标 ==============
# 用于头像旁的状态小图标（2×1）

STATUS_ICONS: dict[str, list[str]] = {
    "idle":     [". "],   # 灰点
    "working":  ["><"],   # 闪烁
    "success":  ["OK"],   # 绿对勾
    "failed":   ["XX"],   # 红叉
    "sleeping": ["zz"],   # 紫z
    "error":    ["!!"],   # 红感叹
}

STATUS_ICON_COLORS: dict[str, int] = {
    "idle": Color.GRAY,
    "working": Color.LIME,
    "success": Color.GREEN,
    "failed": Color.RED,
    "sleeping": Color.PURPLE,
    "error": Color.RED,
}


# ============== 沙盘场景布局辅助 ==============

def scene_layout(width: int, height: int) -> dict[str, tuple[int, int]]:
    """返回 80×24 沙盘各装饰元素的推荐坐标。

    Returns:
        {元素名: (x, y)} 坐标字典。
    """
    # 在标题栏两侧放树
    trees = [(2, 1), (width - 7, 1)]
    # 草丛沿底部
    grasses = [(x, height - 2) for x in range(4, width - 4, 8)]
    # 灯笼放四角内侧
    lanterns = [(1, 4), (width - 4, 4)]
    return {
        "trees": trees[0] if trees else (0, 0),
        "grasses": grasses[0] if grasses else (0, 0),
        "lantern": lanterns[0] if lanterns else (0, 0),
    }


# ============== 资产懒加载 ==============

import os as _os

_ASSET_REGISTRY: dict[str, dict[str, Any]] = {
    "tree": {"sprite": TREE_SPRITE, "color": TREE_COLOR, "size": 20},
    "grass": {"sprite": GRASS_SPRITE, "color": GRASS_COLOR, "size": 3},
    "path": {"sprite": PATH_BRICK, "color": PATH_COLOR, "size": 2},
    "lantern": {"sprite": LANTERN_SPRITE, "color": LANTERN_COLOR, "size": 9},
    "workstation": {"sprite": WORKSTATION_BG, "color": None, "size": 40},
}

_LOADED_CACHE: dict[str, Any] = {}


def load_asset(name: str) -> dict[str, Any] | None:
    """按需加载素材资产，缓存结果。"""
    if name in _LOADED_CACHE:
        return _LOADED_CACHE[name]
    info = _ASSET_REGISTRY.get(name)
    if info is None:
        return None
    _LOADED_CACHE[name] = info
    return info


def preload(asset_names: list[str]) -> dict[str, bool]:
    """批量预加载素材资产。"""
    result: dict[str, bool] = {}
    for n in asset_names:
        loaded = load_asset(n)
        result[n] = loaded is not None
    return result


def asset_size(name: str) -> int | None:
    """获取素材文件大小（字节）。"""
    info = _ASSET_REGISTRY.get(name)
    if info is None:
        return None
    return info.get("size")


def register_asset(name: str, sprite: list[str], color: int | None = None,
                   size: int = 0) -> None:
    """注册新的素材资产。"""
    _ASSET_REGISTRY[name] = {"sprite": sprite, "color": color, "size": size}


def list_assets() -> list[str]:
    """列出所有可用的素材名。"""
    return list(_ASSET_REGISTRY.keys())
