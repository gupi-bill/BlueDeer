"""BlueDeer 森林公司前端 HTML/CSS/JS 模板（commit 9）。

零基础读者可以这样理解：这一文件里放着浏览器看到的全部"画面"——
80×60 大地图、17 个功能区、11 只会动的像素小动物、顶部菜单。
所有 HTML/CSS/JS 都用字符串拼好后由 game_server.py 一次性吐给浏览器，
浏览器不需要从网上下载任何外部资源。

设计要点：
1. 17 个功能区：11 物种岗位 + 6 公共区，按职能配色淡色背景
2. 80×60 大地图，2.5D 等距视角，每格 64×32 px
3. 像素风 64×64 精灵，16 帧程序化生成动画（呼吸/眨眼/微动）
4. 监工位置独立：每用户视角坐标存浏览器 localStorage
5. SSE 0.5 秒推送一次状态，前端被动刷新
6. 鼠标拖拽滚动 + 滚轮缩放
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# 地图与渲染常量
MAP_W = 80
MAP_H = 60
TILE_W = 64
TILE_H = 32
FRAMES = 16


# ----------------------------------------------------------------------
# 17 个功能区布局（80×60 网格上的矩形坐标）
# ----------------------------------------------------------------------
#
# 11 物种岗位 + 6 公共区，每个区是 (x1, y1, x2, y2) 矩形。
# 留白由相邻矩形间的间隙自然形成。

ZONES: list[dict[str, Any]] = [
    # ---------- 第 1 行：4 个物种岗位 ----------
    # 夜森林调色：所有 zone 用低饱和度深底 + 微妙色相差异
    # species zone 用温暖大地色系，public zone 用清凉草本色系
    # commit 41：isIndoor 标记室内 zone，雨雪粒子在室内不渲染
    {
        "id": "squirrel",
        "name": "鼠·栗壳代码区",
        "type": "species",
        "species": "squirrel",
        "color": "#3D3528",
        "rect": (2, 2, 18, 12),
        "isIndoor": True,
    },  # 深栗褐
    {
        "id": "fox",
        "name": "狐·赤谋测试区",
        "type": "species",
        "species": "fox",
        "color": "#3A2A26",
        "rect": (22, 2, 38, 12),
        "isIndoor": True,
    },  # 暗赤陶
    {
        "id": "hedgehog",
        "name": "猬·针客安全区",
        "type": "species",
        "species": "hedgehog",
        "color": "#2E3326",
        "rect": (42, 2, 58, 12),
        "isIndoor": True,
    },  # 苔藓深绿
    {
        "id": "beaver",
        "name": "狸·大坝构建区",
        "type": "species",
        "species": "beaver",
        "color": "#2B3A40",
        "rect": (62, 2, 78, 12),
        "isIndoor": True,
    },  # 暗青蓝
    # ---------- 第 2 行：4 个物种岗位 ----------
    {
        "id": "butterfly",
        "name": "蝶·绘羽设计台",
        "type": "species",
        "species": "butterfly",
        "color": "#3A2E3C",
        "rect": (2, 16, 18, 26),
        "isIndoor": True,
    },  # 暗紫莓
    {
        "id": "raven",
        "name": "鸦·黑卷档案室",
        "type": "species",
        "species": "raven",
        "color": "#262A30",
        "rect": (22, 16, 38, 26),
        "isIndoor": True,
    },  # 深石墨
    {
        "id": "hare",
        "name": "兔·霜耳核算台",
        "type": "species",
        "species": "hare",
        "color": "#38333A",
        "rect": (42, 16, 58, 26),
        "isIndoor": True,
    },  # 暖灰玫
    {
        "id": "badger",
        "name": "獾·土工工具间",
        "type": "species",
        "species": "badger",
        "color": "#2C2A26",
        "rect": (62, 16, 78, 26),
        "isIndoor": True,
    },  # 深土褐
    # ---------- 第 3 行：3 物种岗位 + 1 公共区 ----------
    {
        "id": "lark",
        "name": "雀·清音广播台",
        "type": "species",
        "species": "lark",
        "color": "#3A3622",
        "rect": (2, 30, 18, 40),
        "isIndoor": True,
    },  # 暗麦金
    {
        "id": "kite",
        "name": "鸢·天瞰俯瞰台",
        "type": "species",
        "species": "kite",
        "color": "#26323A",
        "rect": (22, 30, 38, 40),
        "isIndoor": True,
    },  # 钢蓝
    {
        "id": "canteen",
        "name": "食堂",
        "type": "public",
        "color": "#3A3128",
        "rect": (42, 30, 58, 40),
        "isIndoor": True,
    },  # 暖琥珀
    {
        "id": "lounge",
        "name": "休息区",
        "type": "public",
        "color": "#2E3528",
        "rect": (62, 30, 78, 40),
        "isIndoor": False,
    },  # 草本绿（半户外）
    # ---------- 第 4 行：1 物种岗位（中央调度台） + 6 公共区 ----------
    {
        "id": "deer",
        "name": "鹿·忧郁调度台",
        "type": "species",
        "species": "deer",
        "color": "#322A3A",
        "rect": (28, 44, 52, 58),
        "isIndoor": True,
    },  # 暮色紫
    {
        "id": "meeting",
        "name": "会议室",
        "type": "public",
        "color": "#26332E",
        "rect": (2, 44, 24, 50),
        "isIndoor": True,
    },  # 松绿
    {
        "id": "gym",
        "name": "健身房",
        "type": "public",
        "color": "#2A2E33",
        "rect": (2, 52, 24, 58),
        "isIndoor": False,
    },  # 石青（半户外）
    {
        "id": "clinic",
        "name": "医疗室",
        "type": "public",
        "color": "#3A2D32",
        "rect": (56, 44, 78, 50),
        "isIndoor": True,
    },  # 淡玫红
    {
        "id": "storage",
        "name": "储物间",
        "type": "public",
        "color": "#2C2A26",
        "rect": (56, 52, 78, 58),
        "isIndoor": True,
    },  # 暖褐
]


# ----------------------------------------------------------------------
# 11 物种配色（用于精灵渲染）
# 夜森林版：低饱和度暖色系，搭配琥珀描边
# ----------------------------------------------------------------------
SPECIES_COLORS: dict[str, dict[str, str]] = {
    "deer": {
        "body": "#A3826E",
        "accent": "#D4A574",
        "name": "鹿·忧郁",
        "nameTag": "#0B1A33",
    },  # 深邃暗蓝
    "squirrel": {
        "body": "#9C7B5E",
        "accent": "#C9925A",
        "name": "鼠·栗壳",
        "nameTag": "#1A3B5C",
    },  # 偏灰深蓝
    "butterfly": {
        "body": "#A07AA5",
        "accent": "#D4A574",
        "name": "蝶·绘羽",
        "nameTag": "#1C2E4A",
    },  # 紫调深蓝
    "fox": {
        "body": "#B86E4E",
        "accent": "#3E2A22",
        "name": "狐·赤谋",
        "nameTag": "#132A4A",
    },  # 标准藏青
    "hedgehog": {
        "body": "#7A5D44",
        "accent": "#3E2A22",
        "name": "猬·针客",
        "nameTag": "#091626",
    },  # 极黑深蓝
    "beaver": {
        "body": "#85603F",
        "accent": "#5D4037",
        "name": "狸·大坝",
        "nameTag": "#1A3B5C",
    },  # 青调深蓝
    "raven": {
        "body": "#4A5560",
        "accent": "#90A4AE",
        "name": "鸦·黑卷",
        "nameTag": "#040B17",
    },  # 最深墨蓝
    "hare": {
        "body": "#C8BFB0",
        "accent": "#A07AA5",
        "name": "兔·霜耳",
        "nameTag": "#2B4C7E",
    },  # 浅灰蓝
    "badger": {
        "body": "#5A5550",
        "accent": "#C8BFB0",
        "name": "獾·土工",
        "nameTag": "#12304D",
    },  # 沉稳深蓝
    "lark": {
        "body": "#C9925A",
        "accent": "#B86E4E",
        "name": "雀·清音",
        "nameTag": "#1A4870",
    },  # 稍亮深蓝
    "kite": {
        "body": "#6B7A95",
        "accent": "#C8BFB0",
        "name": "鸢·天瞰",
        "nameTag": "#213A5C",
    },  # 蓝灰偏冷
}


# ----------------------------------------------------------------------
# 员工默认岗位映射（物种 → zone_id）
# ----------------------------------------------------------------------
SPECIES_TO_ZONE: dict[str, str] = {
    "deer": "deer",
    "squirrel": "squirrel",
    "butterfly": "butterfly",
    "fox": "fox",
    "hedgehog": "hedgehog",
    "beaver": "beaver",
    "raven": "raven",
    "hare": "hare",
    "badger": "badger",
    "lark": "lark",
    "kite": "kite",
}


# ----------------------------------------------------------------------
# HTML 主模板（嵌入 CSS + JS，零外部依赖）
# ----------------------------------------------------------------------

HTML_TEMPLATE = (Path(__file__).parent / "templates" / "index.html").read_text(
    encoding="utf-8"
)


# ----------------------------------------------------------------------
# 渲染入口：把后端数据注入模板
# ----------------------------------------------------------------------

import json as _json


def _escape_html(text: str) -> str:
    s = str(text)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    return s


def render_index(visit_mode: bool = False, visit_token: str = "") -> str:
    """渲染首页 HTML（注入 17 区布局与物种配色）。

    commit 40：visit_mode=True 时返回参观模式 HTML（隐藏写操作按钮）。
    """
    html = (
        HTML_TEMPLATE.replace("__ZONES_JSON__", _json.dumps(ZONES, ensure_ascii=False))
        .replace(
            "__SPECIES_COLORS_JSON__", _json.dumps(SPECIES_COLORS, ensure_ascii=False)
        )
        .replace(
            "__SPECIES_TO_ZONE_JSON__", _json.dumps(SPECIES_TO_ZONE, ensure_ascii=False)
        )
    )
    if visit_mode:
        # 参观模式：注入只读标记
        safe_token = _escape_html(visit_token)
        html = html.replace(
            "<body>", f'<body data-visit-mode="1" data-visit-token="{safe_token}">'
        )
        # 在顶部插入参观者提示横幅
        html = html.replace(
            "<nav>",
            "<div id='visit-banner' style='position:fixed;top:0;left:0;right:0;"
            "background:rgba(180,140,255,0.15);color:#b488ff;text-align:center;"
            "padding:4px;font-size:12px;z-index:9999;'>"
            "👁️ 你正在参观森林公司 · 只读模式</div><nav style='margin-top:24px'>",
            1,
        )
    return html


def status() -> dict:
    """前端模块自身状态（供 game_server.status 聚合）。"""
    return {
        "zone_count": len(ZONES),
        "species_count": len(SPECIES_COLORS),
        "map_size": [MAP_W, MAP_H],
        "tile_size": [TILE_W, TILE_H],
        "frame_count": FRAMES,
    }
