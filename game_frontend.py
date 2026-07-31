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
    {"id": "squirrel",  "name": "鼠·栗壳代码区",   "type": "species", "species": "squirrel",
     "color": "#3D3528", "rect": (2,  2,  18, 12), "isIndoor": True},   # 深栗褐
    {"id": "fox",       "name": "狐·赤谋测试区",   "type": "species", "species": "fox",
     "color": "#3A2A26", "rect": (22, 2,  38, 12), "isIndoor": True},   # 暗赤陶
    {"id": "hedgehog",  "name": "猬·针客安全区",   "type": "species", "species": "hedgehog",
     "color": "#2E3326", "rect": (42, 2,  58, 12), "isIndoor": True},   # 苔藓深绿
    {"id": "beaver",    "name": "狸·大坝构建区",   "type": "species", "species": "beaver",
     "color": "#2B3A40", "rect": (62, 2,  78, 12), "isIndoor": True},   # 暗青蓝
    # ---------- 第 2 行：4 个物种岗位 ----------
    {"id": "butterfly", "name": "蝶·绘羽设计台",   "type": "species", "species": "butterfly",
     "color": "#3A2E3C", "rect": (2,  16, 18, 26), "isIndoor": True},   # 暗紫莓
    {"id": "raven",     "name": "鸦·黑卷档案室",   "type": "species", "species": "raven",
     "color": "#262A30", "rect": (22, 16, 38, 26), "isIndoor": True},   # 深石墨
    {"id": "hare",      "name": "兔·霜耳核算台",   "type": "species", "species": "hare",
     "color": "#38333A", "rect": (42, 16, 58, 26), "isIndoor": True},   # 暖灰玫
    {"id": "badger",    "name": "獾·土工工具间",   "type": "species", "species": "badger",
     "color": "#2C2A26", "rect": (62, 16, 78, 26), "isIndoor": True},   # 深土褐
    # ---------- 第 3 行：3 物种岗位 + 1 公共区 ----------
    {"id": "lark",      "name": "雀·清音广播台",   "type": "species", "species": "lark",
     "color": "#3A3622", "rect": (2,  30, 18, 40), "isIndoor": True},   # 暗麦金
    {"id": "kite",      "name": "鸢·天瞰俯瞰台",   "type": "species", "species": "kite",
     "color": "#26323A", "rect": (22, 30, 38, 40), "isIndoor": True},   # 钢蓝
    {"id": "canteen",   "name": "食堂",            "type": "public",
     "color": "#3A3128", "rect": (42, 30, 58, 40), "isIndoor": True},   # 暖琥珀
    {"id": "lounge",    "name": "休息区",          "type": "public",
     "color": "#2E3528", "rect": (62, 30, 78, 40), "isIndoor": False},  # 草本绿（半户外）
    # ---------- 第 4 行：1 物种岗位（中央调度台） + 6 公共区 ----------
    {"id": "deer",      "name": "鹿·忧郁调度台",   "type": "species", "species": "deer",
     "color": "#322A3A", "rect": (28, 44, 52, 58), "isIndoor": True},   # 暮色紫
    {"id": "meeting",   "name": "会议室",          "type": "public",
     "color": "#26332E", "rect": (2,  44, 24, 50), "isIndoor": True},   # 松绿
    {"id": "gym",       "name": "健身房",          "type": "public",
     "color": "#2A2E33", "rect": (2,  52, 24, 58), "isIndoor": False},  # 石青（半户外）
    {"id": "clinic",    "name": "医疗室",          "type": "public",
     "color": "#3A2D32", "rect": (56, 44, 78, 50), "isIndoor": True},   # 淡玫红
    {"id": "storage",   "name": "储物间",          "type": "public",
     "color": "#2C2A26", "rect": (56, 52, 78, 58), "isIndoor": True},   # 暖褐
]


# ----------------------------------------------------------------------
# 11 物种配色（用于精灵渲染）
# 夜森林版：低饱和度暖色系，搭配琥珀描边
# ----------------------------------------------------------------------
SPECIES_COLORS: dict[str, dict[str, str]] = {
    "deer":      {"body": "#A3826E", "accent": "#D4A574", "name": "鹿·忧郁", "nameTag": "#0B1A33"},   # 深邃暗蓝
    "squirrel":  {"body": "#9C7B5E", "accent": "#C9925A", "name": "鼠·栗壳", "nameTag": "#1A3B5C"},   # 偏灰深蓝
    "butterfly": {"body": "#A07AA5", "accent": "#D4A574", "name": "蝶·绘羽", "nameTag": "#1C2E4A"},   # 紫调深蓝
    "fox":       {"body": "#B86E4E", "accent": "#3E2A22", "name": "狐·赤谋", "nameTag": "#132A4A"},   # 标准藏青
    "hedgehog":  {"body": "#7A5D44", "accent": "#3E2A22", "name": "猬·针客", "nameTag": "#091626"},   # 极黑深蓝
    "beaver":    {"body": "#85603F", "accent": "#5D4037", "name": "狸·大坝", "nameTag": "#1A3B5C"},   # 青调深蓝
    "raven":     {"body": "#4A5560", "accent": "#90A4AE", "name": "鸦·黑卷", "nameTag": "#040B17"},   # 最深墨蓝
    "hare":      {"body": "#C8BFB0", "accent": "#A07AA5", "name": "兔·霜耳", "nameTag": "#2B4C7E"},   # 浅灰蓝
    "badger":    {"body": "#5A5550", "accent": "#C8BFB0", "name": "獾·土工", "nameTag": "#12304D"},   # 沉稳深蓝
    "lark":      {"body": "#C9925A", "accent": "#B86E4E", "name": "雀·清音", "nameTag": "#1A4870"},   # 稍亮深蓝
    "kite":      {"body": "#6B7A95", "accent": "#C8BFB0", "name": "鸢·天瞰", "nameTag": "#213A5C"},   # 蓝灰偏冷
}


# ----------------------------------------------------------------------
# 员工默认岗位映射（物种 → zone_id）
# ----------------------------------------------------------------------
SPECIES_TO_ZONE: dict[str, str] = {
    "deer":      "deer",
    "squirrel":  "squirrel",
    "butterfly": "butterfly",
    "fox":       "fox",
    "hedgehog":  "hedgehog",
    "beaver":    "beaver",
    "raven":     "raven",
    "hare":      "hare",
    "badger":    "badger",
    "lark":      "lark",
    "kite":      "kite",
}


# ----------------------------------------------------------------------
# HTML 主模板（嵌入 CSS + JS，零外部依赖）
# ----------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>BlueDeer · 夜森林</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Manrope:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ============================================================
   Nocturne Forest · 夜森林视觉系统
   深森林墨绿底 + 单一琥珀金重点 + serif 标题 + mono 数字
   ============================================================ */
:root {
  /* 色板 - Nocturne 夜森林（默认深色） */
  --bg-deep: #0a0f0c;          /* 最深背景 */
  --bg-base: #0d1410;          /* 主背景 */
  --bg-card: rgba(22, 31, 26, 0.78);   /* 卡片玻璃 */
  --bg-card-solid: #161f1a;    /* 卡片实色 */
  --bg-elev: rgba(30, 41, 35, 0.88);   /* 浮层 */
  --nav-bg: rgba(10, 15, 12, 0.85);
  --border: rgba(212, 165, 116, 0.14); /* 极细琥珀边 */
  --border-strong: rgba(212, 165, 116, 0.32);
  --text-primary: #E8E4D8;     /* 暖白主文字 */
  --text-secondary: #A8A095;   /* 次级灰米 */
  --text-muted: #6B655C;       /* 弱化 */
  --accent: #D4A574;           /* 琥珀金（唯一重点色） */
  --accent-on-light: #0a0f0c;  /* 琥珀底上的字色 */
  --accent-dim: rgba(212, 165, 116, 0.5);
  --moss: #6B8F71;             /* 苔藓绿（状态良好） */
  --rust: #C97B5A;             /* 枯叶橙（警告） */
  --shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
  --canvas-bg-inner: #111813;  /* Canvas 径向渐变中心色 */
  --canvas-bg-outer: #0a0f0c;  /* Canvas 径向渐变边缘色 */
  --canvas-grid: #1A201B;      /* 瓦片无 zone 时的占位色 */
  --canvas-text-shadow: rgba(0, 0, 0, 0.85);
  --canvas-brighten: 0;        /* 浅色模式下瓦片调亮系数 */
  /* 字体 */
  --font-display: 'Fraunces', 'Source Han Serif SC', serif;
  --font-body: 'Manrope', -apple-system, 'PingFang SC', sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', monospace;
  /* 圆角 */
  --radius-sm: 4px;
  --radius: 8px;
  --radius-lg: 12px;
}

/* ============================================================
   Dawn Mist · 晨雾浅色模式
   米白底 + 同琥珀金 + 深褐字
   ============================================================ */
[data-theme="light"] {
  --bg-deep: #E8E2D2;
  --bg-base: #F5F2EB;
  --bg-card: rgba(255, 252, 245, 0.82);
  --bg-card-solid: #FFFCF5;
  --bg-elev: rgba(255, 252, 245, 0.94);
  --nav-bg: rgba(245, 242, 235, 0.88);
  --border: rgba(166, 122, 63, 0.22);
  --border-strong: rgba(166, 122, 63, 0.45);
  --text-primary: #2A2419;     /* 深褐主文字 */
  --text-secondary: #6B655C;   /* 灰米次级 */
  --text-muted: #9A9388;       /* 弱化 */
  --accent: #A67A3F;           /* 深琥珀（浅底易读） */
  --accent-on-light: #FFFCF5;
  --accent-dim: rgba(166, 122, 63, 0.5);
  --moss: #5A8567;
  --rust: #B65A3C;
  --shadow: 0 8px 24px rgba(60, 50, 30, 0.12);
  --canvas-bg-inner: #EDE7D5;
  --canvas-bg-outer: #D8D0BC;
  --canvas-grid: #C8C0AC;
  --canvas-text-shadow: rgba(255, 252, 245, 0.85);
  --canvas-brighten: 0.45;
}

/* ============================================================
   commit 35：Midnight 深夜模式
   深蓝黑底 + 琥珀色高亮
   ============================================================ */
[data-theme="midnight"] {
  --bg-deep: #060912;
  --bg-base: #0a0f1c;
  --bg-card: rgba(18, 24, 40, 0.82);
  --bg-card-solid: #121828;
  --bg-elev: rgba(22, 30, 50, 0.92);
  --nav-bg: rgba(8, 12, 22, 0.88);
  --border: rgba(255, 184, 77, 0.16);
  --border-strong: rgba(255, 184, 77, 0.36);
  --text-primary: #F2E8D4;
  --text-secondary: #B0A690;
  --text-muted: #6F6852;
  --accent: #FFB84D;
  --accent-on-light: #0a0f1c;
  --accent-dim: rgba(255, 184, 77, 0.5);
  --moss: #7AA88A;
  --rust: #D77A4A;
  --shadow: 0 8px 32px rgba(0, 0, 0, 0.6);
  --canvas-bg-inner: #0e1424;
  --canvas-bg-outer: #060912;
  --canvas-grid: #1a2238;
  --canvas-text-shadow: rgba(0, 0, 0, 0.9);
  --canvas-brighten: 0;
}

/* ============================================================
   commit 35：Sakura 樱花季（春季限定）
   粉白底 + 淡粉红 + 嫩绿
   ============================================================ */
[data-theme="sakura"] {
  --bg-deep: #F8E4E8;
  --bg-base: #FDF4F6;
  --bg-card: rgba(255, 250, 252, 0.85);
  --bg-card-solid: #FFFAFC;
  --bg-elev: rgba(255, 250, 252, 0.95);
  --nav-bg: rgba(252, 240, 244, 0.9);
  --border: rgba(214, 124, 158, 0.24);
  --border-strong: rgba(214, 124, 158, 0.48);
  --text-primary: #4A2A38;
  --text-secondary: #8A6A78;
  --text-muted: #B698A4;
  --accent: #D67C9E;
  --accent-on-light: #FFFAFC;
  --accent-dim: rgba(214, 124, 158, 0.5);
  --moss: #7BAA7E;
  --rust: #C77860;
  --shadow: 0 8px 24px rgba(180, 100, 130, 0.18);
  --canvas-bg-inner: #FCE8EE;
  --canvas-bg-outer: #F4D8E0;
  --canvas-grid: #E8C8D4;
  --canvas-text-shadow: rgba(255, 250, 252, 0.9);
  --canvas-brighten: 0.42;
}

/* ============================================================
   commit 35：UI 动效与过渡
   ============================================================ */
#diary-panel, #autobio-panel, #artifacts-panel {
  animation: panelPop 0.22s cubic-bezier(0.34, 1.36, 0.64, 1) both;
}
@keyframes panelPop {
  from { opacity: 0; transform: translate(-50%, -50%) scale(0.9); }
  to   { opacity: 1; transform: translate(-50%, -50%) scale(1); }
}
@keyframes bubblePop {
  0%   { opacity: 0; transform: translateY(8px) scale(0.96); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.02); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
.bubble-anim { animation: bubblePop 0.28s cubic-bezier(0.34, 1.36, 0.64, 1) both; }
/* commit 41：大屏 nav 改造 —— 汉堡菜单 + 折叠侧栏 */
#nav-hamburger {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid transparent;
  transition: background 0.15s ease, border-color 0.15s ease;
}
#nav-hamburger:hover {
  background: rgba(212, 165, 116, 0.12);
  border-color: var(--border);
}
#nav-hamburger .bars {
  display: inline-flex;
  flex-direction: column;
  gap: 3px;
}
#nav-hamburger .bars span {
  display: block;
  width: 16px;
  height: 2px;
  background: var(--text-primary);
  border-radius: 1px;
}
#nav-drawer {
  position: absolute;
  top: 56px;
  left: 0;
  width: 240px;
  max-height: calc(100vh - 56px);
  overflow-y: auto;
  background: var(--nav-bg);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border-right: 1px solid var(--border);
  padding: 16px 12px;
  z-index: 9;
  transform: translateX(-100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
#nav-drawer.open { transform: translateX(0); }
#nav-drawer a, #nav-drawer button {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 12px;
  border-radius: 6px;
  color: var(--text-primary);
  text-decoration: none;
  font-size: 13px;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s ease;
}
#nav-drawer a:hover, #nav-drawer button:hover {
  background: rgba(212, 165, 116, 0.10);
}
#nav-drawer .drawer-section {
  border-top: 1px solid var(--border);
  margin-top: 8px;
  padding-top: 8px;
}
#nav-drawer .drawer-title {
  font-size: 10px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 4px 12px;
  margin-bottom: 4px;
}
#nav-time-display {
  margin-left: auto;
  padding: 6px 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-secondary);
  background: rgba(212, 165, 116, 0.08);
  border-radius: 8px;
  border: 1px solid var(--border);
}
nav button, #tool-bar button, #zoom-controls button {
  transition: background-color 0.15s ease, color 0.15s ease, transform 0.1s ease;
}
nav button:hover, #tool-bar button:hover { transform: translateY(-1px); }
#diary-btn, #autobio-btn, #artifacts-btn, #theme-pick-btn, #perf-btn {
  font-size: 12px;
}
.tab-swap { animation: tabSwap 0.18s ease both; }
@keyframes tabSwap {
  from { opacity: 0; transform: translateX(8px); }
  to   { opacity: 1; transform: translateX(0); }
}

* { box-sizing: border-box; margin: 0; padding: 0; }

html, body { height: 100%; overflow: hidden; }

body {
  font-family: var(--font-body);
  background: var(--bg-base);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  /* 微妙的森林雾气渐变（浅色模式下更柔和） */
  background-image:
    radial-gradient(ellipse 80% 60% at 50% 0%, rgba(107, 143, 113, 0.06), transparent),
    radial-gradient(ellipse 60% 40% at 100% 100%, rgba(212, 165, 116, 0.04), transparent),
    linear-gradient(180deg, var(--bg-base) 0%, var(--bg-deep) 100%);
  transition: background-color 0.4s ease, color 0.4s ease;
}

/* ============================================================
   顶部导航：极简横栏，serif 品牌字
   ============================================================ */
nav {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 14px 32px;
  z-index: 100;
  /* commit 51：强化磨砂玻璃（blur 12→24，与底部 dock/侧边面板统一） */
  background: linear-gradient(180deg, rgba(20, 26, 22, 0.82) 0%, rgba(20, 26, 22, 0.55) 70%, rgba(20, 26, 22, 0.15) 100%);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border-bottom: 1px solid rgba(212, 165, 116, 0.25);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(212, 165, 116, 0.12);
  color: var(--text-primary);
  transition: background 0.4s ease, border-color 0.4s ease;
  pointer-events: auto;
}
nav .brand {
  font-family: var(--font-display);
  font-weight: 500;
  font-size: 19px;
  letter-spacing: 0.02em;
  color: var(--text-primary);
  margin-right: auto;
  display: flex;
  align-items: center;
  gap: 10px;
}
nav .brand::before {
  content: '';
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 12px var(--accent-dim);
}
nav a {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: 0.01em;
  transition: color 0.2s ease;
  position: relative;
}
nav a:hover { color: var(--accent); }
nav a::after {
  content: '';
  position: absolute;
  bottom: -4px;
  left: 0;
  width: 0;
  height: 1px;
  background: var(--accent);
  transition: width 0.25s ease;
}
nav a:hover::after { width: 100%; }

/* 主题切换按钮：圆形玻璃 + 太阳/月亮符号 */
#theme-toggle {
  width: 34px;
  height: 34px;
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  line-height: 1;
  transition: all 0.25s ease;
  padding: 0;
  margin-left: 8px;
  position: relative;
  overflow: hidden;
}
#theme-toggle:hover {
  color: var(--accent);
  border-color: var(--border-strong);
  background: rgba(212, 165, 116, 0.08);
  transform: rotate(15deg);
}
#theme-toggle .icon-sun,
#theme-toggle .icon-moon {
  position: absolute;
  transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease;
}
#theme-toggle .icon-moon { opacity: 1; transform: translateY(0); }
#theme-toggle .icon-sun  { opacity: 0; transform: translateY(100%); }
[data-theme="light"] #theme-toggle .icon-moon { opacity: 0; transform: translateY(-100%); }
[data-theme="light"] #theme-toggle .icon-sun  { opacity: 1; transform: translateY(0); }

/* ============================================================
   主舞台：等距画布
   ============================================================ */
#stage {
  position: relative;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(ellipse 70% 50% at 50% 50%, var(--canvas-bg-inner) 0%, var(--canvas-bg-outer) 100%);
  cursor: grab;
  touch-action: none;
  -webkit-user-select: none;
  user-select: none;
  -webkit-touch-callout: none;
  transition: background 0.4s ease;
}
#stage.dragging { cursor: grabbing; }
#map-canvas {
  position: absolute;
  top: 0;
  left: 0;
  image-rendering: pixelated;
}

/* ============================================================
   右侧状态面板：玻璃卡片，serif 小标题
   ============================================================ */
#status-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 300px;
  background: var(--bg-card);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  font-size: 13px;
  max-height: calc(100vh - 100px);
  overflow-y: auto;
  z-index: 5;
  box-shadow: var(--shadow);
}
/* commit 41 fix：状态面板关闭按钮 —— 醒目琥珀色圆角按钮 */
#status-panel .panel-close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(212, 165, 116, 0.18);
  border: 1px solid rgba(212, 165, 116, 0.5);
  color: #D4A574;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease, transform 0.15s ease;
}
#status-panel .panel-close-btn:hover {
  background: rgba(212, 165, 116, 0.35);
  transform: rotate(90deg);
}
/* commit 41 fix + commit 45-2：状态面板毛玻璃 + 深海蓝半透明（冷色调仪表盘） */
#status-panel {
  background: rgba(11, 26, 51, 0.88) !important;
  backdrop-filter: blur(24px) saturate(140%) !important;
  -webkit-backdrop-filter: blur(24px) saturate(140%) !important;
  border: 1px solid rgba(76, 154, 255, 0.3) !important;
  color: #E8F0FF !important;
}
#status-panel h3 {
  color: #D4A574 !important;
  border-bottom: 1px solid rgba(212, 165, 116, 0.2) !important;
}
#status-panel .stat-row,
#status-panel .emp-row {
  color: #E8DCC8 !important;
}
/* 自定义滚动条 */
#status-panel::-webkit-scrollbar { width: 4px; }
#status-panel::-webkit-scrollbar-track { background: transparent; }
#status-panel::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 2px;
}
#status-panel h3 {
  font-family: var(--font-display);
  font-weight: 500;
  font-size: 13px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
#status-panel h3:not(:first-child) { margin-top: 18px; }
.stat-row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 12px;
  color: var(--text-secondary);
}
.stat-row b {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

/* ============================================================
   员工列表：极简行，hover 微亮
   ============================================================ */
#employee-list { margin-top: 4px; }
.employee-row {
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  margin: 2px 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  transition: background 0.18s ease, color 0.18s ease;
  border: 1px solid transparent;
}
.employee-row:hover {
  background: rgba(212, 165, 116, 0.06);
  color: var(--text-primary);
  border-color: var(--border);
}
.employee-row .dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: middle;
  box-shadow: 0 0 6px currentColor;
}
.employee-row .name-part {
  font-family: var(--font-display);
  font-weight: 500;
  letter-spacing: 0.01em;
}
.employee-row .stat-part {
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}
.employee-row.dead { opacity: 0.3; }
.employee-row.busy {
  background: rgba(212, 165, 116, 0.05);
  border-color: var(--border);
}

/* ============================================================
   工具栏：底部右侧，胶囊按钮组
   commit 50-3：合并成贴底木质长条面板（左小地图 + 右工具按钮）
   ============================================================ */
#bottom-dock {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 64px;
  z-index: 6;
  background: linear-gradient(180deg, rgba(61, 46, 31, 0.92) 0%, rgba(38, 28, 18, 0.96) 100%);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border-top: 1px solid rgba(212, 165, 116, 0.35);
  box-shadow: 0 -8px 24px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(212, 165, 116, 0.15);
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 16px;
}
#bottom-dock .dock-minimap {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
}
#bottom-dock .dock-minimap canvas {
  width: 96px;
  height: 48px;
  border: 1px solid rgba(212, 165, 116, 0.3);
  border-radius: 6px;
  background: rgba(15, 26, 18, 0.6);
}
#bottom-dock .dock-divider {
  width: 1px;
  height: 40px;
  background: rgba(212, 165, 116, 0.25);
  flex: 0 0 auto;
}
#bottom-dock .dock-tools {
  flex: 1 1 auto;
  display: flex;
  gap: 4px;
  justify-content: center;
  align-items: center;
}
#bottom-dock .dock-tools button {
  width: 64px;
  height: 36px;
  background: transparent;
  color: #E8DCC8;
  border: 0;
  border-radius: 8px;
  font-family: "Fraunces", serif;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
#bottom-dock .dock-tools button:hover {
  background: rgba(212, 165, 116, 0.15);
  transform: translateY(-1px);
}
#bottom-dock .dock-tools button.active {
  background: rgba(212, 165, 116, 0.25);
  color: #FFE4B5;
}
/* commit 50-3：旧的悬浮 tool-bar 和 minimap 隐藏（已合并到 bottom-dock） */
#tool-bar, #minimap { display: none !important; }
#tool-bar button {
  width: 52px;
  height: 34px;
  background: transparent;
  color: var(--text-secondary);
  border: 0;
  cursor: pointer;
  font-size: 12px;
  font-family: var(--font-body);
  font-weight: 500;
  border-radius: 999px;
  transition: all 0.2s ease;
  letter-spacing: 0.02em;
}
#tool-bar button.active {
  background: var(--accent);
  color: var(--accent-on-light);
  font-weight: 600;
}
#tool-bar button:hover:not(.active) {
  color: var(--text-primary);
  background: rgba(212, 165, 116, 0.08);
}
#tool-bar button:disabled { opacity: 0.3; cursor: not-allowed; }

/* ============================================================
   缩放控件：竖排胶囊
   ============================================================ */
#zoom-controls {
  position: absolute;
  bottom: 20px;
  right: 240px;
  z-index: 5;
  background: var(--bg-card);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px;
  display: flex;
  flex-direction: row;
  gap: 2px;
  box-shadow: var(--shadow);
}
#zoom-controls button {
  width: 34px;
  height: 34px;
  background: transparent;
  color: var(--text-secondary);
  border: 0;
  cursor: pointer;
  font-size: 16px;
  border-radius: 999px;
  transition: all 0.2s ease;
}
#zoom-controls button:hover {
  background: rgba(212, 165, 116, 0.1);
  color: var(--accent);
}

/* ============================================================
   小地图：左下角玻璃方框
   ============================================================ */
#minimap {
  position: absolute;
  bottom: 20px;
  left: 20px;
  z-index: 5;
  background: var(--bg-card);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px;
  box-shadow: var(--shadow);
}
#minimap canvas {
  display: block;
  image-rendering: pixelated;
  cursor: pointer;
  border-radius: var(--radius-sm);
}

/* ============================================================
   帮助提示：左上角极淡文字
   ============================================================ */
#help {
  position: absolute;
  top: 76px;
  left: 20px;
  z-index: 5;
  background: var(--bg-card);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 14px;
  font-size: 11px;
  color: var(--text-muted);
  max-width: 240px;
  line-height: 1.6;
  letter-spacing: 0.02em;
}
#help kbd {
  display: inline-block;
  padding: 1px 5px;
  background: rgba(212, 165, 116, 0.1);
  border: 1px solid var(--border);
  border-radius: 3px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--accent);
  margin: 0 1px;
}

/* ============================================================
   悬浮 tooltip：深色玻璃 + 琥珀细边
   ============================================================ */
#tooltip {
  position: absolute;
  background: rgba(10, 15, 12, 0.95);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: var(--text-primary);
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 12px;
  pointer-events: none;
  z-index: 20;
  display: none;
  border: 1px solid var(--border-strong);
  box-shadow: var(--shadow);
  font-family: var(--font-body);
  max-width: 220px;
}
#tooltip b {
  font-family: var(--font-display);
  font-weight: 500;
  color: var(--accent);
  font-size: 13px;
}

/* ============================================================
   Toast：顶部居中，琥珀底深色字
   ============================================================ */
#toast {
  position: absolute;
  top: 76px;
  left: 50%;
  transform: translateX(-50%) translateY(-8px);
  background: var(--accent);
  color: var(--accent-on-light);
  padding: 10px 22px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  z-index: 30;
  opacity: 0;
  transition: opacity 0.3s ease, transform 0.3s ease;
  pointer-events: none;
  box-shadow: 0 8px 24px rgba(212, 165, 116, 0.3);
}
#toast.show {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}

/* ============================================================
   commit 26：Sprite 调试面板（F12 切换）
   ============================================================ */
#sprite-debug {
  position: absolute;
  top: 76px;
  right: 16px;
  width: 320px;
  max-height: 80vh;
  overflow-y: auto;
  background: rgba(13, 20, 16, 0.95);
  border: 1px solid var(--accent);
  border-radius: 8px;
  padding: 12px;
  z-index: 50;
  font-size: 12px;
  color: var(--text);
  display: none;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
}
#sprite-debug.open { display: block; }
#sprite-debug h3 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--accent);
  font-family: "Fraunces", serif;
}
#sprite-debug .dbg-row {
  margin-bottom: 8px;
}
#sprite-debug .dbg-label {
  display: block;
  color: var(--text-dim);
  margin-bottom: 3px;
  font-size: 11px;
}
#sprite-debug select,
#sprite-debug button {
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
#sprite-debug select { width: 100%; }
#sprite-debug button { margin: 2px; }
#sprite-debug button.active {
  background: var(--accent);
  color: var(--accent-on-light);
  border-color: var(--accent);
}
#sprite-debug canvas {
  display: block;
  margin: 8px auto;
  border: 1px solid var(--border);
  background: rgba(0,0,0,0.3);
  image-rendering: pixelated;
}
#sprite-debug .dbg-info {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.5;
}
#sprite-debug .dbg-gif-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
#sprite-debug .dbg-gif-row img {
  width: 64px;
  height: 64px;
  image-rendering: pixelated;
  border: 1px solid var(--border);
  border-radius: 3px;
  background: rgba(0,0,0,0.3);
}
#sprite-debug .dbg-swatch {
  display: flex; align-items: center; gap: 3px;
  font-size: 10px; color: var(--text-dim);
  font-family: monospace;
}
#sprite-debug .dbg-swatch i {
  display: inline-block;
  width: 12px; height: 12px;
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: 2px;
}

/* ============================================================
   全局统计：顶部琥珀微光块
   ============================================================ */
#global-stats {
  background: linear-gradient(135deg,
    rgba(212, 165, 116, 0.08),
    rgba(107, 143, 113, 0.04));
  border: 1px solid var(--border);
  padding: 10px 12px;
  border-radius: var(--radius);
  margin-bottom: 14px;
  font-size: 12px;
}
#global-stats .gs-row {
  display: flex;
  justify-content: space-between;
  padding: 2px 0;
  color: var(--text-secondary);
}
#global-stats .gs-row b {
  color: var(--accent);
  font-family: var(--font-mono);
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

/* ============================================================
   移动端：缩小面板，隐藏帮助
   ============================================================ */
@media (max-width: 720px) {
  nav { padding: 10px 16px; gap: 14px; }
  nav .brand { font-size: 16px; }
  nav a { font-size: 11px; }
  #status-panel {
    width: 240px;
    top: 12px;
    right: 12px;
    padding: 14px 16px;
    font-size: 12px;
  }
  #help { display: none; }
  #tool-bar { bottom: 14px; right: 14px; }
  #tool-bar button { width: 44px; height: 30px; font-size: 11px; }
  #zoom-controls { bottom: 14px; right: 200px; }
  #minimap { bottom: 14px; left: 14px; }
  #minimap canvas { width: 110px; height: 82px; }
}

/* ============================================================
   面板伸缩 + 折叠（commit 20）
   ============================================================ */
/* transition 让折叠/展开流畅 */
#status-panel, #minimap, #help {
  transition: transform 0.32s cubic-bezier(0.4, 0, 0.2, 1);
}
/* 水平拖拽手柄（左侧竖条，琥珀光带） */
.panel-resize {
  position: absolute;
  z-index: 8;
  background: transparent;
}
.panel-resize.x {
  top: 12px; left: -4px;
  width: 8px; height: calc(100% - 24px);
  cursor: ew-resize;
  border-radius: 999px;
  transition: background 0.2s ease;
}
.panel-resize.x:hover,
.panel-resize.x.active {
  background: rgba(212, 165, 116, 0.35);
  box-shadow: 0 0 12px rgba(212, 165, 116, 0.3);
}
/* 右下角双向手柄（小地图缩放） */
.panel-resize.xy {
  bottom: 2px; right: 2px;
  width: 14px; height: 14px;
  cursor: nwse-resize;
  background:
    linear-gradient(135deg, transparent 55%, rgba(212, 165, 116, 0.4) 55%, rgba(212, 165, 116, 0.4) 65%, transparent 65%, transparent 75%, rgba(212, 165, 116, 0.4) 75%);
  border-radius: 0 0 var(--radius-sm) 0;
  transition: background 0.2s ease;
}
.panel-resize.xy:hover,
.panel-resize.xy.active {
  background:
    linear-gradient(135deg, transparent 55%, rgba(212, 165, 116, 0.8) 55%, rgba(212, 165, 116, 0.8) 65%, transparent 65%, transparent 75%, rgba(212, 165, 116, 0.8) 75%);
}
/* 折叠按钮（面板右上角小圆按钮） */
.panel-collapse {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 22px; height: 22px;
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 14px;
  font-family: var(--font-body);
  border-radius: 50%;
  transition: all 0.2s ease;
  z-index: 9;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  padding: 0;
}
.panel-collapse:hover {
  color: var(--accent);
  background: rgba(212, 165, 116, 0.1);
  border-color: var(--border);
}
/* 折叠态：面板滑出视口外 */
#status-panel.collapsed {
  transform: translateX(calc(100% + 40px));
}
#minimap.collapsed {
  transform: translateY(calc(100% + 40px));
}
#help.collapsed {
  transform: translateX(calc(-100% - 40px));
}
/* 折叠后的还原按钮（留在屏幕边缘的小胶囊） */
.panel-restore {
  position: absolute;
  z-index: 5;
  background: var(--bg-card);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid var(--border);
  color: var(--accent);
  padding: 8px 14px;
  font-size: 11.5px;
  font-family: var(--font-display);
  font-weight: 500;
  letter-spacing: 0.06em;
  border-radius: 999px;
  cursor: pointer;
  display: none;
  box-shadow: var(--shadow);
  transition: all 0.2s ease;
}
.panel-restore:hover {
  background: rgba(212, 165, 116, 0.15);
  border-color: var(--border-strong);
  transform: scale(1.04);
}
.panel-restore.show { display: block; }
#status-restore { top: 76px; right: 20px; }
/* commit 41 fix：还原按钮也用暖木色 */
#status-restore {
  background: rgba(45, 34, 22, 0.92) !important;
  color: #D4A574 !important;
  border: 1px solid rgba(212, 165, 116, 0.4) !important;
}
#status-restore:hover {
  background: rgba(61, 46, 31, 0.95) !important;
}
#minimap-restore { bottom: 20px; left: 20px; }
#help-restore { top: 76px; left: 20px; }
/* 折叠按钮要给面板标题留出空间 */
#status-panel h3:first-of-type { padding-right: 28px; }
#help { padding-right: 32px; }

/* ============================================================
   commit 44-1：员工快捷交互菜单（毛玻璃暖木色）
   ============================================================ */
#emp-quick-menu {
  position: fixed;
  display: none;
  flex-direction: column;
  gap: 4px;
  padding: 6px;
  background: rgba(45, 34, 22, 0.82);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid rgba(212, 165, 116, 0.5);
  border-radius: 8px;
  z-index: 38;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5);
  min-width: 120px;
}
#emp-quick-menu button {
  padding: 8px 12px;
  font-size: 13px;
  color: #E8E4D8;
  background: transparent;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  text-align: left;
  font-family: var(--font-body);
  transition: background-color 0.15s ease;
}
#emp-quick-menu button:hover {
  background: rgba(212, 165, 116, 0.22);
  color: #FFF8E0;
}

/* ============================================================
   commit 44-2：下达指令模态框
   ============================================================ */
#command-modal {
  position: fixed;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 50;
}
#command-modal .modal-panel {
  width: 460px;
  max-width: 90vw;
  background: rgba(45, 34, 22, 0.88);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid rgba(212, 165, 116, 0.5);
  border-radius: 12px;
  padding: 22px;
  color: #E8E4D8;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
}
#command-modal .modal-title {
  font-family: var(--font-serif);
  font-size: 18px;
  margin-bottom: 12px;
  color: #FFF8E0;
}
#command-modal textarea {
  width: 100%;
  min-height: 90px;
  padding: 10px;
  font-size: 14px;
  font-family: var(--font-mono);
  color: #E8E4D8;
  background: rgba(20, 16, 10, 0.6);
  border: 1px solid rgba(212, 165, 116, 0.3);
  border-radius: 8px;
  resize: vertical;
}
#command-modal textarea:focus {
  outline: none;
  border-color: rgba(212, 165, 116, 0.7);
}
#command-modal .preset-row,
#command-modal .action-row {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  flex-wrap: wrap;
}
#command-modal .preset-btn {
  padding: 5px 10px;
  font-size: 12px;
  color: #D4A574;
  background: rgba(212, 165, 116, 0.08);
  border: 1px solid rgba(212, 165, 116, 0.3);
  border-radius: 6px;
  cursor: pointer;
}
#command-modal .preset-btn:hover {
  background: rgba(212, 165, 116, 0.2);
}
#command-modal .action-row { justify-content: flex-end; }
#command-modal .send-btn,
#command-modal .cancel-btn {
  padding: 8px 16px;
  font-size: 13px;
  border-radius: 6px;
  cursor: pointer;
  border: 1px solid rgba(212, 165, 116, 0.5);
}
#command-modal .send-btn {
  background: rgba(212, 165, 116, 0.35);
  color: #FFF8E0;
}
#command-modal .send-btn:hover { background: rgba(212, 165, 116, 0.55); }
#command-modal .cancel-btn {
  background: transparent;
  color: #C0B8A8;
}
#command-modal .cancel-btn:hover { background: rgba(255, 255, 255, 0.05); }

/* ============================================================
   commit 44-4：事件流侧边面板
   ============================================================ */
#event-feed-panel {
  position: fixed;
  right: 0;
  top: 60px;
  bottom: 60px;
  width: 320px;
  background: rgba(45, 34, 22, 0.82);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid rgba(212, 165, 116, 0.5);
  border-right: none;
  border-radius: 12px 0 0 12px;
  z-index: 36;
  color: #E8E4D8;
  transform: translateX(100%);
  transition: transform 0.28s ease;
  display: flex;
  flex-direction: column;
  box-shadow: -12px 0 32px rgba(0, 0, 0, 0.4);
}
#event-feed-panel.open { transform: translateX(0); }
#event-feed-panel .fp-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px 10px;
  border-bottom: 1px solid rgba(212, 165, 116, 0.18);
  font-family: var(--font-serif);
  font-size: 15px;
  color: #FFF8E0;
}
#event-feed-panel .fp-close {
  background: transparent;
  border: none;
  color: #C0B8A8;
  font-size: 18px;
  cursor: pointer;
}
#event-feed-panel .fp-close:hover { color: #FFF8E0; }
#event-feed-panel ul {
  list-style: none;
  margin: 0;
  padding: 8px 12px;
  overflow-y: auto;
  flex: 1;
  font-size: 12px;
  line-height: 1.5;
}
#event-feed-panel li {
  padding: 6px 8px;
  border-bottom: 1px dashed rgba(212, 165, 116, 0.1);
  color: #D8D2C4;
}
#event-feed-panel li:hover { background: rgba(212, 165, 116, 0.06); }
#event-feed-panel .ev-time {
  font-family: var(--font-mono);
  color: #D4A574;
  margin-right: 6px;
  font-size: 11px;
}

/* commit 44-3：日夜循环倍速按钮 */
#nav-speed-ctrl {
  display: inline-flex;
  gap: 2px;
  margin-left: 8px;
  padding: 2px;
  background: rgba(212, 165, 116, 0.08);
  border-radius: 8px;
  border: 1px solid var(--border);
}
#nav-speed-ctrl button {
  padding: 4px 8px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: 6px;
  cursor: pointer;
}
#nav-speed-ctrl button.active {
  background: rgba(212, 165, 116, 0.35);
  color: #FFF8E0;
}
</style>
</head>
<body>
<nav>
  <div id="nav-hamburger" onclick="toggleNavDrawer()">
    <div class="bars"><span></span><span></span><span></span></div>
    <span style="font-size:13px; color:var(--text-secondary);">菜单</span>
  </div>
  <span class="brand">BlueDeer</span>
  <div id="nav-time-display"></div>
  <div id="nav-speed-ctrl" title="commit 44-3：游戏时间倍速">
    <button data-speed="1" onclick="setGameSpeed(1)">1x</button>
    <button data-speed="60" class="active" onclick="setGameSpeed(60)">60x</button>
    <button data-speed="300" onclick="setGameSpeed(300)">300x</button>
  </div>
  <button id="immersive-btn" title="沉浸感设置"
          onclick="openImmersivePanel()">沉浸感</button>
  <button id="theme-toggle" title="切换深/浅色模式">
    <span class="icon-moon">☾</span>
    <span class="icon-sun">☀</span>
  </button>
  <div id="nav-drawer">
    <a href="/">📊 仪表盘</a>
    <a href="/story">📖 故事</a>
    <a href="/report">📈 进化报告</a>
    <a href="/snap">📷 快照</a>
    <a href="#" onclick="toggleEventFeed(); return false;">⚡ 事件流</a>
    <div class="drawer-section">
      <div class="drawer-title">智能体</div>
      <button onclick="toggleNavDrawer(); toggleTaskConsole()">📋 任务控制台</button>
      <button onclick="toggleNavDrawer(); toggleKanban()">📊 项目看板</button>
      <button onclick="toggleNavDrawer(); toggleSuggestions()">💡 建议中心</button>
      <button onclick="toggleNavDrawer(); toggleExternalPanel()">🔌 外部集成</button>
      <button onclick="toggleNavDrawer(); openApprovalsModal()">🔔 审批队列</button>
    </div>
    <div class="drawer-section">
      <div class="drawer-title">员工</div>
      <button onclick="toggleNavDrawer(); openDiseasePanel()">🏥 急救箱</button>
      <button onclick="toggleNavDrawer(); openMemoryPanel()">💾 持久记忆</button>
      <button onclick="toggleNavDrawer(); openDiaryPanel()">📔 日记本</button>
      <button onclick="toggleNavDrawer(); openAutobioPanel()">🧠 自传</button>
      <button onclick="toggleNavDrawer(); openArtifactsPanel()">🎨 成果墙</button>
      <button onclick="toggleNavDrawer(); startOnboarding()">🎓 新手引导</button>
      <button onclick="toggleNavDrawer(); toggleSharePanel()">🎁 分享导出</button>
      <button onclick="toggleNavDrawer(); toggleEvolutionPanel()">✨ 进化突变</button>
    </div>
    <div class="drawer-section">
      <div class="drawer-title">系统</div>
      <button onclick="toggleNavDrawer(); requestNotificationPermission()">🔔 桌面通知</button>
      <button onclick="toggleNavDrawer(); openMemoirPanel()">📚 监工回忆录</button>
      <button onclick="toggleNavDrawer(); openDesktopPet()">🐰 桌面宠物</button>
      <button onclick="toggleNavDrawer(); cycleTheme()">🎨 主题</button>
      <button onclick="toggleNavDrawer(); togglePerfPanel()">⚡ 性能</button>
      <button onclick="toggleNavDrawer(); openPolishPanel()">💎 打磨</button>
      <a href="/logout">🚪 退出</a>
    </div>
  </div>
</nav>
<div id="stage">
  <canvas id="map-canvas"></canvas>
  <div id="status-panel">
    <button class="panel-collapse panel-close-btn" data-target="status-panel" title="关闭面板（点击外部也可关闭）">✕</button>
    <div class="panel-resize x" data-target="status-panel" data-dir="x" title="左右拖拽调整宽度"></div>
    <div id="global-stats"></div>
    <h3>实时状态</h3>
    <div id="env-stats"></div>
    <h3>生态系统</h3>
    <div id="eco-stats"></div>
    <!-- commit 45-2：实时趋势 Canvas 折线图（食物/植物/昆虫/平均精力 4 条曲线） -->
    <h3>实时趋势</h3>
    <canvas id="stats-chart" width="280" height="120" style="display:block;width:100%;height:120px;"></canvas>
    <h3>员工 · 点击定位</h3>
    <div id="employee-list"></div>
  </div>
  <div id="tool-bar">
    <button id="tool-greet" title="问候（1）" data-action="greet">问候</button>
    <button id="tool-feed"  title="投喂（2）" data-action="feed">投喂</button>
    <button id="tool-train" title="训练（3）" data-action="mark_focus">训练</button>
    <button id="tool-rest"  title="休息（4）" data-action="set_schedule">休息</button>
    <button id="tool-recruit" title="招募（5）" data-action="recruit">招募</button>
  </div>
  <div id="zoom-controls">
    <button id="zoom-in" title="放大">+</button>
    <button id="zoom-out" title="缩小">−</button>
    <button id="zoom-reset" title="重置">⌂</button>
  </div>
  <div id="minimap">
    <button class="panel-collapse" data-target="minimap" title="收起小地图">×</button>
    <canvas id="minimap-canvas" width="160" height="120"></canvas>
    <div class="panel-resize xy" data-target="minimap" data-dir="xy" title="拖拽调整大小"></div>
  </div>
  <!-- commit 50-3：贴底木质长条面板（左小地图 + 分隔线 + 右工具按钮）-->
  <div id="bottom-dock">
    <div class="dock-minimap">
      <canvas id="dock-minimap-canvas" width="96" height="48"></canvas>
    </div>
    <div class="dock-divider"></div>
    <div class="dock-tools">
      <button data-action="greet" title="问候（1）">问候</button>
      <button data-action="feed" title="投喂（2）">投喂</button>
      <button data-action="mark_focus" title="训练（3）">训练</button>
      <button data-action="set_schedule" title="休息（4）">休息</button>
      <button data-action="recruit" title="招募（5）">招募</button>
    </div>
  </div>
  <div id="help">
    <button class="panel-collapse" data-target="help" title="收起说明">×</button>
    拖拽滚动 · 滚轮缩放 · 点击员工定位<br>
    <kbd>1</kbd>–<kbd>5</kbd> 切工具 · <kbd>Space</kbd> 居中监工
  </div>
  <button id="status-restore" class="panel-restore" data-target="status-panel">展开状态面板</button>
  <button id="minimap-restore" class="panel-restore" data-target="minimap">展开小地图</button>
  <button id="help-restore" class="panel-restore" data-target="help">展开操作说明</button>
  <div id="tooltip"></div>
  <div id="toast"></div>

  <!-- commit 44-1：员工快捷交互菜单 -->
  <div id="emp-quick-menu">
    <button onclick="quickMenuGreet()">💬 聊天</button>
    <button onclick="quickMenuCommand()">📋 下达指令</button>
    <button onclick="quickMenuProfile()">👤 查看档案</button>
  </div>

  <!-- commit 44-2：下达指令模态框 -->
  <div id="command-modal" onclick="if(event.target===this)closeCommandDialog()">
    <div class="modal-panel">
      <div class="modal-title" id="command-modal-title">下达指令</div>
      <textarea id="command-input" placeholder="例如：去休息 / 写一个快速排序 / 帮我读一下 config.json"></textarea>
      <div class="preset-row">
        <button class="preset-btn" onclick="document.getElementById('command-input').value='去休息'">去休息</button>
        <button class="preset-btn" onclick="document.getElementById('command-input').value='去茶水间'">去茶水间</button>
        <button class="preset-btn" onclick="document.getElementById('command-input').value='查看代码'">查看代码</button>
      </div>
      <div class="action-row">
        <button class="cancel-btn" onclick="closeCommandDialog()">取消</button>
        <button class="send-btn" onclick="sendCommand()">发送</button>
      </div>
    </div>
  </div>

  <!-- commit 44-4：事件流侧边面板 -->
  <div id="event-feed-panel" class="side-panel">
    <div class="fp-head">
      <span>⚡ 事件流</span>
      <button class="fp-close" onclick="toggleEventFeed()" title="关闭">×</button>
    </div>
    <ul id="event-feed-list"></ul>
  </div>

  <!-- commit 26：Sprite 调试面板（F12 切换） -->
  <div id="sprite-debug">
    <h3>Sprite 调试面板</h3>
    <div class="dbg-row">
      <span class="dbg-label">角色</span>
      <select id="dbg-species"></select>
    </div>
    <div class="dbg-row">
      <span class="dbg-label">帧类型</span>
      <div>
        <button data-anim="idle">idle</button>
        <button data-anim="walk">walk</button>
        <button data-anim="work">work</button>
        <button data-anim="sleep">sleep</button>
        <button data-anim="react">react</button>
      </div>
    </div>
    <div class="dbg-row">
      <span class="dbg-label">单帧索引（0-10）</span>
      <div>
        <button id="dbg-prev">◀</button>
        <span id="dbg-frame-idx" style="display:inline-block;width:40px;text-align:center;color:var(--accent)">0</span>
        <button id="dbg-next">▶</button>
        <button id="dbg-play">▶ 播放</button>
        <button id="dbg-flip">↔ 翻转</button>
      </div>
    </div>
    <canvas id="dbg-canvas" width="128" height="128"></canvas>
    <div class="dbg-info" id="dbg-info">—</div>
    <div class="dbg-row">
      <span class="dbg-label">像素坐标 / 颜色（悬停 canvas）</span>
      <div id="dbg-hover" style="font-family:monospace;font-size:11px;color:var(--accent);min-height:14px">—</div>
    </div>
    <div class="dbg-row">
      <span class="dbg-label">色板（按使用频率）</span>
      <div id="dbg-palette" style="display:flex;flex-wrap:wrap;gap:3px"></div>
    </div>
    <div class="dbg-row">
      <span class="dbg-label">GIF 预览（点击查看大图）</span>
      <div class="dbg-gif-row" id="dbg-gifs"></div>
    </div>
    <div class="dbg-row">
      <span class="dbg-label">PNG 加载状态</span>
      <div id="dbg-png-status" style="font-family:monospace;font-size:10px;line-height:1.6"></div>
    </div>
  </div>

  <!-- commit 33：沉浸感设置面板 -->
  <div id="immersive-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(20,20,30,0.96); color:#fff; padding:22px 26px; border-radius:14px; width:380px; max-width:90vw; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(255,255,255,0.12);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px;">沉浸感设置</h3>
      <button onclick="document.getElementById('immersive-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">情感光环强度：<span id="aura-val">70</span>%</label>
      <input type="range" id="aura-slider" min="0" max="100" value="70"
             oninput="document.getElementById('aura-val').textContent=this.value; saveImmersiveSetting()"
             style="width:100%;">
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">氛围粒子数量</label>
      <select id="particle-select" onchange="saveImmersiveSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="low">少</option>
        <option value="medium" selected>中</option>
        <option value="high">多</option>
      </select>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">记忆碎片密度</label>
      <select id="fragment-select" onchange="saveImmersiveSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="low">低</option>
        <option value="medium" selected>中</option>
        <option value="high">高</option>
      </select>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">自发社交频率</label>
      <select id="social-select" onchange="saveImmersiveSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="low">低</option>
        <option value="medium" selected>中</option>
        <option value="high">高</option>
      </select>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">气泡显示速度</label>
      <select id="bubble-select" onchange="saveImmersiveSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="slow">慢</option>
        <option value="medium" selected>中</option>
        <option value="fast">快</option>
      </select>
    </div>
    <div id="immersive-tip" style="font-size:11px; color:rgba(255,255,255,0.5); margin-top:8px;">
      设置保存到后端，刷新后生效。
    </div>
  </div>

  <!-- commit 33：监工回忆录面板 -->
  <div id="memoir-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(20,20,30,0.96); color:#fff; padding:22px 26px; border-radius:14px; width:500px; max-width:90vw; max-height:70vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(255,255,255,0.12);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; position:sticky; top:-22px; background:rgba(20,20,30,0.96); padding:14px 0; margin:-22px -26px 14px; padding-left:26px; padding-right:26px; border-bottom:1px solid rgba(255,255,255,0.1);">
      <h3 style="margin:0; font-size:16px;">监工回忆录</h3>
      <button onclick="document.getElementById('memoir-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="memoir-list" style="line-height:1.6;">
      <div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>
    </div>
  </div>

  <!-- commit 33：屏幕边缘情感晕影（监工靠近智能体时显示） -->
  <div id="emotion-vignette" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; pointer-events:none; z-index:500; box-shadow:inset 0 0 200px rgba(255,196,87,0.3); transition:box-shadow 1s ease;"></div>

  <!-- commit 34：急救箱面板 -->
  <div id="disease-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(20,20,30,0.96); color:#fff; padding:22px 26px; border-radius:14px; width:520px; max-width:90vw; max-height:70vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(255,80,80,0.3);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px; color:#ff8080;">急救箱 · 生病员工</h3>
      <button onclick="document.getElementById('disease-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="disease-list" style="line-height:1.6;">
      <div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>
    </div>
  </div>

  <!-- commit 34：持久记忆面板 -->
  <div id="memory-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(20,20,30,0.96); color:#fff; padding:22px 26px; border-radius:14px; width:600px; max-width:90vw; max-height:75vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(150,180,255,0.3);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px; color:#96b4ff;">跨会话持久记忆</h3>
      <button onclick="document.getElementById('memory-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="memory-stats" style="margin-bottom:12px; font-size:11px; color:rgba(255,255,255,0.6);"></div>
    <div id="memory-list" style="line-height:1.6;">
      <div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>
    </div>
  </div>

  <!-- commit 35：日记本面板（需彩蛋发现） -->
  <div id="diary-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(30,25,20,0.97); color:#fff; padding:22px 26px; border-radius:14px; width:560px; max-width:90vw; max-height:75vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(220,180,120,0.4);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px; color:#dcb478;">📓 私密日记本</h3>
      <button onclick="document.getElementById('diary-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="diary-stats" style="margin-bottom:12px; font-size:11px; color:rgba(255,255,255,0.6);"></div>
    <div id="diary-list" style="line-height:1.7;">
      <div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">提示：在智能体工位附近反复点击 3 次，有概率"发现"日记本</div>
    </div>
  </div>

  <!-- commit 35：自传体记忆面板 -->
  <div id="autobio-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(25,22,30,0.97); color:#fff; padding:22px 26px; border-radius:14px; width:620px; max-width:90vw; max-height:78vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(180,160,220,0.4);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px; color:#b4a0dc;">🪞 自传体记忆 · 自我认知</h3>
      <button onclick="document.getElementById('autobio-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="autobio-stats" style="margin-bottom:12px; font-size:11px; color:rgba(255,255,255,0.6);"></div>
    <div id="autobio-list" style="line-height:1.7;">
      <div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>
    </div>
  </div>

  <!-- commit 35：工作产物 / 成果展示墙 -->
  <div id="artifacts-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(22,28,22,0.97); color:#fff; padding:22px 26px; border-radius:14px; width:680px; max-width:92vw; max-height:80vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(140,200,140,0.4);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px; color:#8cd08c;">🏆 成果展示墙 · 工作产物</h3>
      <button onclick="document.getElementById('artifacts-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="artifacts-stats" style="margin-bottom:12px; font-size:11px; color:rgba(255,255,255,0.6);"></div>
    <div id="artifacts-list" style="line-height:1.6;">
      <div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>
    </div>
  </div>

  <!-- commit 35：性能监控面板 -->
  <div id="perf-panel" style="display:none; position:fixed; bottom:14px; right:14px; background:rgba(15,15,20,0.92); color:#9f9; padding:10px 14px; border-radius:8px; font-family:monospace; font-size:11px; line-height:1.6; box-shadow:0 4px 16px rgba(0,0,0,0.5); z-index:1000; border:1px solid rgba(120,200,120,0.3); pointer-events:none;">
    <div>FPS: <span id="perf-fps">--</span></div>
    <div>粒子: <span id="perf-particles">0</span></div>
    <div>渲染: <span id="perf-render">--</span> ms</div>
    <div>智能体: <span id="perf-agents">0</span></div>
  </div>

  <!-- commit 36：前端打磨设置面板 -->
  <div id="polish-panel" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(20,22,30,0.96); color:#fff; padding:22px 26px; border-radius:14px; width:400px; max-width:90vw; max-height:80vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1100; font-size:13px; border:1px solid rgba(180,200,255,0.25);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px; color:#b4c8ff;">🎨 前端打磨设置</h3>
      <button onclick="document.getElementById('polish-panel').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">屏幕暗角强度：<span id="vig-val">10</span>%</label>
      <input type="range" id="vig-slider" min="0" max="40" value="10"
             oninput="document.getElementById('vig-val').textContent=this.value; savePolishSetting()"
             style="width:100%;">
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">情感滤镜强度：<span id="ef-val">15</span>%</label>
      <input type="range" id="ef-slider" min="0" max="50" value="15"
             oninput="document.getElementById('ef-val').textContent=this.value; savePolishSetting()"
             style="width:100%;">
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">环境细节密度</label>
      <select id="env-detail-select" onchange="savePolishSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="off">关</option>
        <option value="low">低</option>
        <option value="medium" selected>中</option>
        <option value="high">高</option>
      </select>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">微表情</label>
      <select id="micro-expr-select" onchange="savePolishSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="1" selected>开</option>
        <option value="0">关</option>
      </select>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">员工显示模式</label>
      <select id="spirit-mode-select" onchange="savePolishSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="0" selected>动物形态（默认）</option>
        <option value="1">灵魂投影（光点+名牌）</option>
      </select>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">缩放灵敏度（1-5）：<span id="zs-val">2</span></label>
      <input type="range" id="zs-slider" min="1" max="5" value="2"
             oninput="document.getElementById('zs-val').textContent=this.value; savePolishSetting()"
             style="width:100%;">
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">粒子密度</label>
      <select id="polish-particle-select" onchange="savePolishSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="low">少</option>
        <option value="medium" selected>中</option>
        <option value="high">多</option>
      </select>
    </div>
    <div style="margin-bottom:14px;">
      <label style="display:block; margin-bottom:4px;">字体大小</label>
      <select id="font-size-select" onchange="savePolishSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="small">小</option>
        <option value="medium" selected>中</option>
        <option value="large">大</option>
      </select>
    </div>
    <div style="margin-bottom:8px;">
      <label style="display:block; margin-bottom:4px;">渲染帧率</label>
      <select id="fps-select" onchange="savePolishSetting()" style="width:100%; padding:4px; background:#222; color:#fff; border:1px solid #444; border-radius:4px;">
        <option value="30">30 FPS（省电）</option>
        <option value="60" selected>60 FPS（默认）</option>
      </select>
    </div>
    <div id="polish-tip" style="font-size:11px; color:rgba(255,255,255,0.5); margin-top:8px;">
      设置即时生效，存储到本地 localStorage。
    </div>
  </div>

  <!-- commit 37：任务控制台 -->
  <div id="task-console" style="display:none; position:fixed; top:60px; left:50%; transform:translateX(-50%); width:90vw; max-width:1100px; height:75vh; background:rgba(15,18,25,0.97); color:#cdd6e6; border-radius:12px; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1050; font-size:13px; border:1px solid rgba(100,150,255,0.3); flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(100,150,255,0.2);">
      <h3 style="margin:0; font-size:15px; color:#b4c8ff;">⚡ 任务控制台 · Agent Workbench</h3>
      <div style="display:flex; gap:8px; align-items:center;">
        <select id="task-mode" style="background:#222; color:#fff; border:1px solid #444; border-radius:4px; padding:3px 8px; font-size:12px;">
          <option value="auto">自动判断</option>
          <option value="single">单智能体</option>
          <option value="pipeline">流水线</option>
        </select>
        <select id="task-species" style="background:#222; color:#fff; border:1px solid #444; border-radius:4px; padding:3px 8px; font-size:12px;" title="指定物种（仅 single 模式生效）">
          <option value="">自动路由</option>
          <option value="squirrel">🐿 松鼠（代码）</option>
          <option value="butterfly">🦋 蝶（UI）</option>
          <option value="fox">🦊 狐（测试）</option>
          <option value="hedgehog">🦔 猬（安全）</option>
          <option value="beaver">🦫 海狸（运维）</option>
          <option value="raven">🐦‍⬛ 渡鸦（检索）</option>
          <option value="hare">🐰 兔（统计）</option>
          <option value="badger">🦡 獾（网络）</option>
          <option value="lark">🐤 雀（监控）</option>
          <option value="kite">🪁 鸢（调度）</option>
          <option value="deer">🦌 鹿（编排）</option>
        </select>
        <button onclick="clearTaskOutput()" title="清屏"
                style="background:#333; color:#fff; border:1px solid #555; border-radius:4px; padding:4px 8px; cursor:pointer; font-size:12px;">清屏</button>
        <button onclick="toggleTaskConsole()" title="关闭（T 键）"
                style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
      </div>
    </div>
    <div style="display:flex; padding:8px 16px; gap:8px; border-bottom:1px solid rgba(100,150,255,0.15);">
      <input id="task-input" type="text" placeholder="一句话指挥整支团队：写一个登录模块并测试，再扫描安全漏洞..."
             style="flex:1; background:#0a0d12; color:#cdd6e6; border:1px solid rgba(100,150,255,0.3); border-radius:6px; padding:8px 12px; font-size:13px; font-family:monospace;"
             onkeydown="if(event.key==='Enter')submitTaskCommand()">
      <button onclick="submitTaskCommand()"
              style="background:#4a7fc0; color:#fff; border:none; border-radius:6px; padding:8px 18px; cursor:pointer; font-size:13px; font-weight:bold;">▶ 执行</button>
    </div>
    <div style="display:flex; flex:1; overflow:hidden;">
      <div id="task-list-panel" style="width:280px; border-right:1px solid rgba(100,150,255,0.15); overflow-y:auto; padding:8px;">
        <div style="font-size:11px; color:#888; margin-bottom:6px;">流水线列表</div>
        <div id="task-pipeline-list"></div>
      </div>
      <div id="task-output-panel" style="flex:1; overflow-y:auto; padding:12px; background:#06080c; font-family:monospace; font-size:12px; line-height:1.6;">
        <div style="color:#5a8a5a;">[BlueDeer Agent Console v1.0] 智能体已就位。输入任务开始指挥...</div>
        <div style="color:#5a8a5a;">提示：含"并/然后/接着"的复杂任务自动走流水线；简单任务走单智能体。</div>
        <div style="color:#5a8a5a;">快捷键：T 切换控制台，Enter 提交命令。</div>
      </div>
    </div>
    <div id="task-status-bar" style="padding:4px 16px; border-top:1px solid rgba(100,150,255,0.15); font-size:11px; color:#888; display:flex; justify-content:space-between;">
      <span id="task-status-text">就绪</span>
      <span><a href="#" onclick="openApprovalsModal();return false;" style="color:#88aaff;">审批队列：<span id="task-approval-count">0</span></a> | <a href="#" onclick="refreshPipelineList();return false;" style="color:#88aaff;">刷新</a></span>
    </div>
  </div>

  <!-- commit 37：审批弹窗 -->
  <div id="approvals-modal" style="display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(20,22,30,0.98); color:#fff; padding:22px 26px; border-radius:14px; width:480px; max-width:90vw; max-height:80vh; overflow-y:auto; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1150; font-size:13px; border:1px solid rgba(255,180,80,0.4);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
      <h3 style="margin:0; font-size:16px; color:#ffd080;">🛡 工具调用审批</h3>
      <button onclick="document.getElementById('approvals-modal').style.display='none'"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="approvals-list" style="margin-bottom:14px;"></div>
    <div style="font-size:11px; color:rgba(255,255,255,0.5);">未响应的审批将在 30 分钟后自动拒绝。</div>
  </div>

  <!-- commit 38：建议中心（4 tab：建议/复盘/经验库/协商） -->
  <div id="suggestions-modal" style="display:none; position:fixed; top:60px; left:50%; transform:translateX(-50%); width:90vw; max-width:1100px; height:75vh; background:rgba(15,18,25,0.97); color:#cdd6e6; border-radius:12px; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1055; font-size:13px; border:1px solid rgba(255,200,120,0.3); flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,200,120,0.2);">
      <h3 style="margin:0; font-size:15px; color:#ffd080;">💡 建议中心 · Suggestion Hub</h3>
      <div style="display:flex; gap:8px; align-items:center;">
        <button onclick="scanNow()" title="立即扫描一次"
                style="background:#4a7fc0; color:#fff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px;">🔍 立即扫描</button>
        <button onclick="toggleSuggestions()" title="关闭（I 键）"
                style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
      </div>
    </div>
    <div style="display:flex; gap:4px; padding:6px 16px; border-bottom:1px solid rgba(255,200,120,0.15); font-size:12px;">
      <button class="sugg-tab" data-tab="suggestions" onclick="switchSuggTab('suggestions')" style="background:rgba(255,200,120,0.2); color:#ffd080; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">📋 建议</button>
      <button class="sugg-tab" data-tab="retrospects" onclick="switchSuggTab('retrospects')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">📝 复盘</button>
      <button class="sugg-tab" data-tab="experiences" onclick="switchSuggTab('experiences')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">📚 经验库</button>
      <button class="sugg-tab" data-tab="negotiations" onclick="switchSuggTab('negotiations')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">🤝 协商</button>
    </div>
    <div id="sugg-tab-suggestions" style="flex:1; overflow-y:auto; padding:12px 16px;"></div>
    <div id="sugg-tab-retrospects" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="sugg-tab-experiences" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="sugg-tab-negotiations" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="sugg-status-bar" style="padding:4px 16px; border-top:1px solid rgba(255,200,120,0.15); font-size:11px; color:#888;">
      <span id="sugg-status-text">就绪</span>
    </div>
  </div>

  <!-- commit 39：项目看板（按 P 键切换） -->
  <div id="kanban-modal" style="display:none; position:fixed; top:60px; left:50%; transform:translateX(-50%); width:90vw; max-width:1200px; height:78vh; background:rgba(15,18,25,0.97); color:#cdd6e6; border-radius:12px; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1060; font-size:13px; border:1px solid rgba(120,220,160,0.3); flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(120,220,160,0.2);">
      <h3 style="margin:0; font-size:15px; color:#80d0a0;">📊 项目看板 · Project Kanban</h3>
      <div style="display:flex; gap:8px; align-items:center;">
        <button onclick="createSampleProject()" title="创建示例项目"
                style="background:#4a8f60; color:#fff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px;">＋ 示例项目</button>
        <button onclick="loadKanban()" title="刷新"
                style="background:#333; color:#fff; border:1px solid #555; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:12px;">↻ 刷新</button>
        <button onclick="toggleKanban()" title="关闭（P 键）"
                style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
      </div>
    </div>
    <div style="display:flex; gap:4px; padding:6px 16px; border-bottom:1px solid rgba(120,220,160,0.15); font-size:12px;">
      <button class="kanban-tab" data-tab="projects" onclick="switchKanbanTab('projects')" style="background:rgba(120,220,160,0.2); color:#80d0a0; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">📁 项目</button>
      <button class="kanban-tab" data-tab="standups" onclick="switchKanbanTab('standups')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">☕ 站会</button>
      <button class="kanban-tab" data-tab="risks" onclick="switchKanbanTab('risks')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">⚠️ 风险</button>
      <button class="kanban-tab" data-tab="roles" onclick="switchKanbanTab('roles')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">🏆 角色</button>
    </div>
    <div id="kanban-tab-projects" style="flex:1; overflow-y:auto; padding:12px 16px;"></div>
    <div id="kanban-tab-standups" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="kanban-tab-risks" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="kanban-tab-roles" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="kanban-status-bar" style="padding:4px 16px; border-top:1px solid rgba(120,220,160,0.15); font-size:11px; color:#888;">
      <span id="kanban-status-text">就绪 | 快捷键 P 切换看板，I 切换建议中心，T 切换任务控制台</span>
    </div>
  </div>

  <!-- commit 39：外部集成面板 -->
  <div id="external-modal" style="display:none; position:fixed; top:60px; right:20px; width:540px; max-width:95vw; max-height:80vh; background:rgba(15,18,25,0.97); color:#cdd6e6; border-radius:12px; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1065; font-size:13px; border:1px solid rgba(180,140,255,0.3); flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(180,140,255,0.2);">
      <h3 style="margin:0; font-size:15px; color:#b488ff;">🔌 外部集成 · External Integration</h3>
      <button onclick="toggleExternalPanel()" title="关闭"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div style="display:flex; gap:4px; padding:6px 16px; border-bottom:1px solid rgba(180,140,255,0.15); font-size:12px;">
      <button class="ext-tab" data-tab="config" onclick="switchExtTab('config')" style="background:rgba(180,140,255,0.2); color:#b488ff; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">⚙️ 配置</button>
      <button class="ext-tab" data-tab="approvals" onclick="switchExtTab('approvals')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">🛡 审批<span id="ext-approval-count" style="margin-left:4px; color:#ff8080;"></span></button>
      <button class="ext-tab" data-tab="execute" onclick="switchExtTab('execute')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">⚡ 执行</button>
    </div>
    <div id="ext-tab-config" style="flex:1; overflow-y:auto; padding:12px 16px;"></div>
    <div id="ext-tab-approvals" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="ext-tab-execute" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;"></div>
    <div id="ext-status-bar" style="padding:4px 16px; border-top:1px solid rgba(180,140,255,0.15); font-size:11px; color:#888;">
      <span id="ext-status-text">风险等级：🟢低 🟡中 🔴高 | 默认全部关闭，需手动开启</span>
    </div>
  </div>

  <!-- commit 40：新手引导模态框 -->
  <div id="onboard-modal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); z-index:1080; align-items:center; justify-content:center;">
    <div style="width:520px; max-width:95vw; background:rgba(15,18,25,0.98); color:#cdd6e6; border-radius:16px; box-shadow:0 16px 64px rgba(180,140,255,0.3); border:1px solid rgba(180,140,255,0.4); overflow:hidden;">
      <div style="display:flex; justify-content:space-between; align-items:center; padding:12px 20px; background:linear-gradient(135deg, rgba(180,140,255,0.2), rgba(200,170,110,0.15));">
        <h3 style="margin:0; font-size:16px; color:#b488ff;">🎓 新手引导 · 灵音雀带你参观</h3>
        <button onclick="skipOnboarding()" title="跳过引导"
                style="background:rgba(255,100,100,0.2); border:1px solid rgba(255,100,100,0.4); color:#ff8080; padding:4px 10px; border-radius:6px; cursor:pointer; font-size:12px;">跳过</button>
      </div>
      <div id="onboard-content" style="padding:24px; min-height:200px;">
        <div style="text-align:center; font-size:48px; margin:12px 0;">🐦</div>
        <div id="onbird-bubble" style="background:rgba(180,140,255,0.15); border:1px solid rgba(180,140,255,0.3); border-radius:12px; padding:14px 18px; margin:12px 0; font-size:14px; line-height:1.6;"></div>
        <div id="onboard-progress" style="text-align:center; font-size:12px; color:#888; margin:8px 0;"></div>
        <div id="onboard-hint" style="background:rgba(255,200,80,0.1); border-left:3px solid #ffc850; padding:8px 12px; margin:8px 0; font-size:12px; color:#ffc850;"></div>
      </div>
      <div style="display:flex; gap:8px; padding:12px 20px; border-top:1px solid rgba(180,140,255,0.15); justify-content:flex-end;">
        <button id="onboard-back-btn" onclick="onboardPrev()" style="background:#333; color:#aaa; border:none; padding:6px 14px; border-radius:6px; cursor:pointer; font-size:12px;">上一步</button>
        <button id="onboard-next-btn" onclick="onboardNext()" style="background:linear-gradient(135deg, #b488ff, #c9a96e); color:#fff; border:none; padding:6px 18px; border-radius:6px; cursor:pointer; font-size:13px; font-weight:bold;">下一步 →</button>
      </div>
    </div>
  </div>

  <!-- commit 40：分享与导出模态框 -->
  <div id="share-modal" style="display:none; position:fixed; top:60px; right:20px; width:560px; max-width:95vw; max-height:85vh; background:rgba(15,18,25,0.97); color:#cdd6e6; border-radius:12px; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1070; font-size:13px; border:1px solid rgba(255,200,80,0.3); flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,200,80,0.2);">
      <h3 style="margin:0; font-size:15px; color:#ffc850;">🎁 分享与导出 · Share & Export</h3>
      <button onclick="toggleSharePanel()" title="关闭"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div style="display:flex; gap:4px; padding:6px 16px; border-bottom:1px solid rgba(255,200,80,0.15); font-size:12px;">
      <button class="share-tab" data-tab="visit" onclick="switchShareTab('visit')" style="background:rgba(255,200,80,0.2); color:#ffc850; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">👁 参观链接</button>
      <button class="share-tab" data-tab="card" onclick="switchShareTab('card')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">🎴 智能体卡片</button>
      <button class="share-tab" data-tab="snapshot" onclick="switchShareTab('snapshot')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">📄 公司快照</button>
      <button class="share-tab" data-tab="text" onclick="switchShareTab('text')" style="background:#222; color:#aaa; border:none; border-radius:4px 4px 0 0; padding:6px 14px; cursor:pointer;">✍️ 分享文案</button>
    </div>
    <div id="share-tab-visit" style="flex:1; overflow-y:auto; padding:12px 16px;">
      <div style="margin-bottom:10px;">
        <input id="share-token-name" type="text" placeholder="备注（如：朋友小王）" style="background:#222; color:#fff; border:1px solid #444; border-radius:6px; padding:6px 10px; width:60%;">
        <button onclick="createShareToken()" style="background:linear-gradient(135deg, #ffc850, #ff9040); color:#1a1a2e; border:none; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:bold; margin-left:6px;">生成链接</button>
      </div>
      <div id="share-tokens-list" style="font-size:12px;"></div>
    </div>
    <div id="share-tab-card" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;">
      <div style="margin-bottom:10px;">
        <select id="share-card-agent" style="background:#222; color:#fff; border:1px solid #444; border-radius:6px; padding:6px 10px; width:50%;"></select>
        <button onclick="generateAgentCard()" style="background:linear-gradient(135deg, #ffc850, #ff9040); color:#1a1a2e; border:none; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:bold; margin-left:6px;">生成卡片</button>
      </div>
      <div id="share-card-preview" style="text-align:center; min-height:200px;"></div>
    </div>
    <div id="share-tab-snapshot" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;">
      <p style="color:#aaa; font-size:12px; line-height:1.6;">导出公司当前状态的 Markdown 快照，包含员工列表、技能矩阵、已故员工、资源状态、本月事件、今日站会。</p>
      <button onclick="downloadSnapshot()" style="background:linear-gradient(135deg, #ffc850, #ff9040); color:#1a1a2e; border:none; padding:8px 20px; border-radius:6px; cursor:pointer; font-weight:bold; margin-top:8px;">📄 下载 Markdown 快照</button>
    </div>
    <div id="share-tab-text" style="flex:1; overflow-y:auto; padding:12px 16px; display:none;">
      <button onclick="generateShareText()" style="background:linear-gradient(135deg, #ffc850, #ff9040); color:#1a1a2e; border:none; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:bold; margin-bottom:8px;">生成分享文案</button>
      <div id="share-text-output" style="background:#222; border:1px solid #444; border-radius:6px; padding:12px; min-height:80px; font-size:13px; line-height:1.6; color:#cdd6e6;"></div>
      <button onclick="copyShareText()" style="background:#444; color:#fff; border:none; padding:4px 12px; border-radius:4px; cursor:pointer; font-size:11px; margin-top:6px;">复制到剪贴板</button>
    </div>
  </div>

  <!-- commit 40：进化突变模态框 -->
  <div id="evolution-modal" style="display:none; position:fixed; top:60px; right:20px; width:520px; max-width:95vw; max-height:80vh; background:rgba(15,18,25,0.97); color:#cdd6e6; border-radius:12px; box-shadow:0 12px 48px rgba(0,0,0,0.6); z-index:1075; font-size:13px; border:1px solid rgba(255,215,0,0.3); flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 16px; border-bottom:1px solid rgba(255,215,0,0.2);">
      <h3 style="margin:0; font-size:15px; color:#ffd700;">✨ 进化突变 · Evolution</h3>
      <button onclick="toggleEvolutionPanel()" title="关闭"
              style="background:none; border:none; color:#fff; font-size:18px; cursor:pointer;">×</button>
    </div>
    <div id="evolution-stats" style="padding:8px 16px; border-bottom:1px solid rgba(255,215,0,0.15); font-size:12px; color:#888;"></div>
    <div style="padding:6px 16px; border-bottom:1px solid rgba(255,215,0,0.15);">
      <button onclick="forceEvolution()" style="background:linear-gradient(135deg, #ffd700, #ff9040); color:#1a1a2e; border:none; padding:4px 12px; border-radius:4px; cursor:pointer; font-size:12px; font-weight:bold;">强制触发（测试）</button>
      <input id="evolution-agent-name" type="text" placeholder="智能体名字" style="background:#222; color:#fff; border:1px solid #444; border-radius:4px; padding:4px 8px; margin-left:6px; font-size:12px; width:120px;">
    </div>
    <div id="evolution-log" style="flex:1; overflow-y:auto; padding:12px 16px; font-size:12px;"></div>
  </div>

  <!-- commit 40：突变通知横幅 -->
  <div id="mutation-banner" style="display:none; position:fixed; top:60px; left:50%; transform:translateX(-50%); background:linear-gradient(135deg, rgba(255,215,0,0.95), rgba(255,140,40,0.95)); color:#1a1a2e; padding:8px 24px; border-radius:8px; box-shadow:0 8px 32px rgba(255,215,0,0.4); z-index:1090; font-size:13px; font-weight:bold;"></div>

  <!-- commit 40：小贴士气泡 -->
  <div id="tip-bubble" style="display:none; position:fixed; bottom:20px; right:20px; max-width:300px; background:rgba(15,18,25,0.97); color:#cdd6e6; padding:12px 16px; border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,0.5); z-index:1085; font-size:12px; border:1px solid rgba(200,170,110,0.3);">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
      <span style="color:#c9a96e; font-weight:bold;">💡 小贴士</span>
      <button onclick="document.getElementById('tip-bubble').style.display='none'" style="background:none; border:none; color:#888; cursor:pointer; font-size:14px;">×</button>
    </div>
    <div id="tip-text"></div>
  </div>
</div>
<script>
// ==================== 配置 ====================
const MAP_W = 80, MAP_H = 60;
const TILE_W = 64, TILE_H = 32;
const FRAMES = 16;

// 17 个功能区（后端注入）
const ZONES = __ZONES_JSON__;
const SPECIES_COLORS = __SPECIES_COLORS_JSON__;
const SPECIES_TO_ZONE = __SPECIES_TO_ZONE_JSON__;

// commit 47：员工统一色表（花名册圆点 / 小地图 / 头像 / 衣服染色 全部读这个）
// 解决"圆点和衣服颜色对不上"的根因：原来圆点读 colors.body（棕褐系），衣服读 UNIFORM（深蓝），数据源不统一
// 现在 11 物种统一一个主色（深蓝变体，呼应侧边栏 nameTag），花名册和地图衣服都从这里取色
const EMPLOYEE_COLOR_MAP = {
  'deer':      '#0B1A33',  // 鹿·忧郁 深邃暗蓝
  'squirrel':  '#1A3B5C',  // 鼠·栗壳 偏灰深蓝
  'butterfly': '#1C2E4A',  // 蝶·绘羽 紫调深蓝
  'fox':       '#132A4A',  // 狐·赤谋 标准藏青
  'hedgehog':  '#091626',  // 猬·针客 极黑深蓝
  'beaver':    '#1A3B5C',  // 狸·大坝 青调深蓝
  'raven':     '#040B17',  // 鸦·黑卷 最深墨蓝
  'hare':      '#2B4C7E',  // 兔·霜耳 浅灰蓝
  'badger':    '#12304D',  // 獾·土工 沉稳深蓝
  'lark':      '#1A4870',  // 雀·清音 稍亮深蓝
  'kite':      '#213A5C',  // 鸢·天瞰 蓝灰偏冷
};
// 兜底函数：取物种主色，找不到就回退默认深蓝
function getEmployeeColor(species) {
  return EMPLOYEE_COLOR_MAP[species] || '#1A3B5C';
}

// commit 49-1：碰撞地图 —— 大型道具/高台/木桩位置作为障碍，员工不能走进这些格子
// 解决"穿墙/盖在墙上"问题：员工移动前检测目标格是否障碍，是则拒绝移动
// 每个障碍是 {x, y, r}：圆心(x,y) 半径 r（网格单位），员工进入则回弹
const OBSTACLES = [
  // kite 瞭望台木桩（zone 22,30,38,40 中心 30,35）
  {x: 30, y: 35, r: 1.2, type: 'pillar', species: 'kite'},
  // raven 枯树枝（zone 22,16,38,26 中心 30,21）
  {x: 30, y: 22, r: 1.0, type: 'branch', species: 'raven'},
  // badger 矿灯柱（zone 62,16,78,26 中心 70,21）
  {x: 70, y: 22, r: 0.8, type: 'lamp', species: 'badger'},
  // beaver 木料堆（zone 62,2,78,12 中心 70,7）
  {x: 70, y: 8, r: 1.0, type: 'logs', species: 'beaver'},
  // deer 中央调度台（zone 28,44,52,58 中心 40,51）
  {x: 40, y: 51, r: 1.5, type: 'desk', species: 'deer'},
];
// 鸢·天瞰固定锚点（站在瞭望台木桩上，不参与随机游走）
const KITE_ANCHOR = {x: 30, y: 35};

// commit 50-5：地图装饰物 —— 在 zone 外围森林撒 32x32 静止物件（树/石/灯/箱/花盆）
// 这些物件占地 1 格，配置碰撞阻挡，员工不能走过去
// 用伪随机种子，让每次刷新位置一致
const DECORATIONS = (function() {
  const list = [];
  const types = ['tree', 'rock', 'lamp', 'box', 'pot'];
  // 在 zone 外围撒 40 个装饰物
  let seed = 12345;
  function rnd() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
  for (let i = 0; i < 40; i++) {
    let x, y, tries = 0;
    do {
      x = Math.floor(rnd() * MAP_W);
      y = Math.floor(rnd() * MAP_H);
      tries++;
    } while (tries < 20 && _isInAnyZone(x, y));
    if (tries >= 20) continue;
    list.push({
      x: x, y: y,
      type: types[Math.floor(rnd() * types.length)],
      seed: Math.floor(rnd() * 1000),
    });
  }
  return list;
})();
function _isInAnyZone(ix, iy) {
  for (const z of ZONES) {
    const [x1, y1, x2, y2] = z.rect;
    if (ix >= x1 && ix <= x2 && iy >= y1 && iy <= y2) return true;
  }
  return false;
}
// 检测坐标是否在障碍内
function isObstacle(x, y, exceptSpecies) {
  // commit 50-1：地图边界 —— 最外 2 圈作为天然围墙，员工不能走出地图
  if (x < 2 || y < 2 || x > MAP_W - 3 || y > MAP_H - 3) return true;
  for (const o of OBSTACLES) {
    if (exceptSpecies && o.species === exceptSpecies) continue;  // 该物种自己的道具可踩
    const dx = x - o.x, dy = y - o.y;
    if (dx * dx + dy * dy < o.r * o.r) return true;
  }
  // commit 50-5：装饰物碰撞
  for (const d of DECORATIONS) {
    if (exceptSpecies && d.species === exceptSpecies) continue;
    const dx = x - d.x, dy = y - d.y;
    if (dx * dx + dy * dy < 0.7 * 0.7) return true;
  }
  return false;
}

// ==================== Canvas 设置 ====================
const canvas = document.getElementById('map-canvas');
const ctx = canvas.getContext('2d');
const stage = document.getElementById('stage');
const tooltip = document.getElementById('tooltip');
const toast = document.getElementById('toast');

// commit 41：nav 抽屉切换 + 时间显示
function toggleNavDrawer() {
  const d = document.getElementById('nav-drawer');
  if (d) d.classList.toggle('open');
}
// 点击抽屉外区域自动收起
document.addEventListener('click', (e) => {
  const d = document.getElementById('nav-drawer');
  const ham = document.getElementById('nav-hamburger');
  if (d && d.classList.contains('open') && !d.contains(e.target) && !ham.contains(e.target)) {
    d.classList.remove('open');
  }
});
// commit 41 fix：点击 status-panel 外部关闭它（App 标配交互）
document.addEventListener('click', (e) => {
  const panel = document.getElementById('status-panel');
  const restore = document.getElementById('status-restore');
  if (!panel || panel.classList.contains('collapsed')) return;  // 已收起不处理
  // 如果点击的不是面板本身、不是面板内的元素、不是还原按钮
  if (!panel.contains(e.target) && !restore.contains(e.target)) {
    // 但要避免点击 nav-drawer 和 nav-hamburger 时误关
    const drawer = document.getElementById('nav-drawer');
    const ham = document.getElementById('nav-hamburger');
    if (drawer && drawer.contains(e.target)) return;
    if (ham && ham.contains(e.target)) return;
    // 避免点击其他模态框按钮时误关
    if (e.target.closest('button') && e.target.closest('button').onclick) return;
    togglePanel('status-panel', true);  // 强制收起
  }
});
// 时间显示（每分钟刷新）
// commit 44-3：游戏时间循环（默认 60 倍速：1 分钟跳 1 小时）
let gameHour = 8;       // 游戏内小时（0-23）
let gameMinute = 0;     // 游戏内分钟（0-59）
let gameSpeed = 60;     // 倍速：1 / 60 / 300
function setGameSpeed(s) {
  gameSpeed = s;
  // 同步高亮按钮
  document.querySelectorAll('#nav-speed-ctrl button').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.speed, 10) === s);
  });
}
// commit 44-3：每秒推进游戏时间
setInterval(() => {
  gameMinute += gameSpeed / 60;
  while (gameMinute >= 60) {
    gameMinute -= 60;
    gameHour = (gameHour + 1) % 24;
  }
}, 1000);
function updateNavTime() {
  const el = document.getElementById('nav-time-display');
  if (!el) return;
  // commit 44-3：使用游戏时间而非系统时间
  const h = String(Math.floor(gameHour)).padStart(2, '0');
  const m = String(Math.floor(gameMinute)).padStart(2, '0');
  el.textContent = h + ':' + m;
}
setInterval(updateNavTime, 1000);  // commit 44-3：游戏时间每秒变，所以每秒刷

// commit 41：大屏默认收起右侧状态面板（腾出地图空间）
// 用 setTimeout 让 DOM 完全加载后再触发
setTimeout(() => {
  // commit 41 fix：改用 togglePanel + collapsed class，与 − 按钮机制一致
  // 原 inline style.transform 会覆盖 collapsed class 导致关不掉
  if (window.innerWidth > 1024) {
    togglePanel('status-panel', true);  // true = 强制收起
  }
  updateNavTime();
}, 100);

function resizeCanvas() {
  canvas.width = stage.clientWidth;
  canvas.height = stage.clientHeight;
}
window.addEventListener('resize', resizeCanvas);
resizeCanvas();

// ==================== 视角状态（存 localStorage，监工位置独立） ====================
const VIEW_KEY = 'bluedeer_view_v1';
// commit 41：初始 zoom 1.6（大屏默认更近，只看 6×6 格子）
let view = { x: -200, y: -100, zoom: 1.6 };
try {
  const saved = JSON.parse(localStorage.getItem(VIEW_KEY) || '{}');
  if (typeof saved.x === 'number') view = saved;
} catch (e) {}
// commit 41：旧 localStorage 校正到 1.6（minZoom 提到 1.0）
if (view.zoom < 1.0) view.zoom = 1.6;

function saveView() {
  try { localStorage.setItem(VIEW_KEY, JSON.stringify(view)); } catch (e) {}
}

// ==================== commit 18：配置持久化（工具/天气） ====================
const SETTINGS_KEY = 'bluedeer_settings_v1';
let settings = { tool: 'greet', weather: 'sunny' };
try {
  const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
  if (typeof s.tool === 'string') settings = s;
} catch (e) {}

function saveSettings() {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch (e) {}
}

// ==================== 等距坐标转换 ====================
function isoToScreen(ix, iy) {
  // 等距投影：屏幕 x = (ix - iy) * TILE_W/2 * zoom + view.x
  //          屏幕 y = (ix + iy) * TILE_H/2 * zoom + view.y
  return {
    x: (ix - iy) * TILE_W / 2 * view.zoom + view.x,
    y: (ix + iy) * TILE_H / 2 * view.zoom + view.y,
  };
}

function screenToIso(sx, sy) {
  const dx = (sx - view.x) / view.zoom;
  const dy = (sy - view.y) / view.zoom;
  return {
    x: (dx / (TILE_W / 2) + dy / (TILE_H / 2)) / 2,
    y: (dy / (TILE_H / 2) - dx / (TILE_W / 2)) / 2,
  };
}

// commit 41：屏幕坐标→地砖坐标（用于室内外天气判断）
// 复用 screenToIso，再向下取整 + 地图边界裁剪
function screenToTile(sx, sy) {
  const iso = screenToIso(sx, sy);
  const ix = Math.floor(iso.x), iy = Math.floor(iso.y);
  if (ix < 0 || ix >= MAP_W || iy < 0 || iy >= MAP_H) return null;
  return { ix, iy };
}

// ==================== 精灵程序化生成（16 帧） ====================
// 每个物种 1 个 base sprite，16 帧通过参数化变形生成：
// 帧 0-3: 静止呼吸（身体上下 1px）
// 帧 4-7: 眨眼（眼睛高度 0→1→0）
// 帧 8-11: 走动（左右脚交替）
// 帧 12-15: 工作（手臂摆动）
const spriteCache = {};

// commit 26：像素精灵图集 PNG（11 帧：idle×2 + walk×4 + work×3 + sleep×1 + react×1）
// 每帧 32x32，1px 透明分隔，由 generate_sprites.py 程序化生成。
const SPRITE_SHEET_FRAME = 32;       // 单帧像素尺寸
const SPRITE_SHEET_GAP = 1;          // 帧间透明分隔
const SPRITE_SHEET_FRAMES = 11;      // 每张图集总帧数
// species → 图集文件名前缀（不含 _sprite.png）
const SPECIES_TO_PNG = {
  'deer':      'melancholy_deer',
  'squirrel':  'meticulous_squirrel',
  'butterfly': 'painted_butterfly',
  'fox':       'cunning_fox',
  'hedgehog':  'vigilant_hedgehog',
  'beaver':    'diligent_beaver',
  'raven':     'raven',
  'hare':      'snow_hare',
  'badger':    'little_badger',
  'lark':      'lark',
  'kite':      'green_kite',
  'overseer':  'overseer',  // commit 26：监工也用 PNG sprite
};
// 帧序列索引（0..10）：
//   0=idle0, 1=idle1, 2..5=walk0..3, 6..8=work0..2, 9=sleep0, 10=react0
// 已加载完成的图集 Image 对象，未加载时为 undefined
const pngSpriteSheets = {};
// 已加载失败的 species 集合（避免重复请求 + 回退到矢量）
const pngSpriteFailed = new Set();

// 异步预加载某物种的 PNG sprite sheet
// commit 53：优先尝试 /assets/sprites/（用户开源素材覆盖），失败回退 /sprites/（默认素材）
function loadPngSprite(species) {
  if (pngSpriteSheets[species] || pngSpriteFailed.has(species)) return;
  if (!SPECIES_TO_PNG[species]) return;  // 该物种没有 PNG（如未知物种）
  const img = new Image();
  img.onload = () => { pngSpriteSheets[species] = img; };
  img.onerror = () => {
    // /assets/ 失败 → 尝试默认 /sprites/
    const fallback = new Image();
    fallback.onload = () => { pngSpriteSheets[species] = fallback; };
    fallback.onerror = () => { pngSpriteFailed.add(species); };
    fallback.src = '/sprites/' + SPECIES_TO_PNG[species] + '_sprite.png';
  };
  img.src = '/assets/sprites/' + SPECIES_TO_PNG[species] + '_sprite.png';
}

// 启动时预加载全部 11 个物种
function preloadAllPngSprites() {
  Object.keys(SPECIES_TO_PNG).forEach(loadPngSprite);
}

// ====================================================================
// 装饰品 PNG 加载（17 个 zone × 3 个装饰品 = 51 个 PNG）
// 每个 zone 内 1-3 个 32x32 像素装饰品，与 sprite 同画风
// ====================================================================
const decoPngs = {};          // key: "zone_id_n" → Image
const decoPngFailed = new Set();
const DECO_POSITIONS_3 = [    // zone 内相对位置（dx, dy 归一化到 zone 宽高）
  {dx: -0.32, dy: 0.10}, {dx: 0.0, dy: -0.05}, {dx: 0.32, dy: 0.10}
];

function loadDecoPng(zoneId, n) {
  const key = zoneId + '_' + n;
  if (decoPngs[key] || decoPngFailed.has(key)) return;
  // commit 53：优先 /assets/ 开源素材，失败回退 /sprites/ 默认素材
  const img = new Image();
  img.onload = () => { decoPngs[key] = img; };
  img.onerror = () => {
    const fallback = new Image();
    fallback.onload = () => { decoPngs[key] = fallback; };
    fallback.onerror = () => { decoPngFailed.add(key); };
    fallback.src = '/sprites/deco/deco_' + key + '.png';
  };
  img.src = '/assets/deco/deco_' + key + '.png';
}

function preloadAllDecoPngs() {
  ZONES.forEach(z => {
    for (let i = 1; i <= 3; i++) loadDecoPng(z.id, i);
  });
}

// 判断某 zone 的全部 3 个装饰品是否已加载完毕
function zoneDecoReady(zoneId) {
  for (let i = 1; i <= 3; i++) {
    if (!decoPngs[zoneId + '_' + i]) return false;
  }
  return true;
}

// ====================================================================
// commit 26：Sprite 调试面板
// F12 切换显示；可选角色 + 帧类型 + 单帧索引；自动播放
// ====================================================================
const DBG_FRAME_MAP = {
  idle:  [0, 1],
  walk:  [2, 3, 4, 5],
  work:  [6, 7, 8],
  sleep: [9],
  react: [10],
};
let dbgState = {
  species: 'deer',
  anim: 'idle',
  frameIdx: 0,        // 在当前 anim 内的索引
  playing: false,
  playTimer: null,
  flipped: false,     // 水平翻转预览（模拟朝左走）
};

function initSpriteDebugPanel() {
  const panel = document.getElementById('sprite-debug');
  const sel = document.getElementById('dbg-species');
  const canvas = document.getElementById('dbg-canvas');
  const ctx2 = canvas.getContext('2d');
  ctx2.imageSmoothingEnabled = false;
  const idxLabel = document.getElementById('dbg-frame-idx');
  const info = document.getElementById('dbg-info');
  const gifsEl = document.getElementById('dbg-gifs');
  const hoverEl = document.getElementById('dbg-hover');
  const paletteEl = document.getElementById('dbg-palette');
  const pngStatusEl = document.getElementById('dbg-png-status');
  // 缓存当前帧的 ImageData（用于 hover 取色），key 为渲染时间戳
  let lastImageData = null;

  // 填充角色下拉
  const displayNames = {
    deer: '忧郁鹿', squirrel: '较真松鼠', butterfly: '彩纹蝶', fox: '狡黠狐狸',
    hedgehog: '戒备猬', beaver: '勤恳海狸', raven: '渡鸦', hare: '雪兔',
    badger: '小獾', lark: '灵音雀', kite: '青鸢', overseer: '监工',
  };
  Object.keys(SPECIES_TO_PNG).forEach(sp => {
    const opt = document.createElement('option');
    opt.value = sp;
    opt.textContent = displayNames[sp] + ' (' + sp + ')';
    sel.appendChild(opt);
  });

  function currentAbsoluteFrame() {
    const seq = DBG_FRAME_MAP[dbgState.anim];
    return seq[dbgState.frameIdx % seq.length];
  }

  function render() {
    const absIdx = currentAbsoluteFrame();
    idxLabel.textContent = absIdx;
    // 清画布
    ctx2.fillStyle = '#0d1410';
    ctx2.fillRect(0, 0, 128, 128);
    // 网格
    ctx2.strokeStyle = 'rgba(255,255,255,0.05)';
    for (let i = 0; i <= 128; i += 16) {
      ctx2.beginPath(); ctx2.moveTo(i, 0); ctx2.lineTo(i, 128); ctx2.stroke();
      ctx2.beginPath(); ctx2.moveTo(0, i); ctx2.lineTo(128, i); ctx2.stroke();
    }
    // 画 sprite（从 PNG 切片，4x 放大 = 128）
    const img = pngSpriteSheets[dbgState.species];
    if (!img) {
      ctx2.fillStyle = '#888';
      ctx2.font = '10px monospace';
      ctx2.fillText('PNG 未加载', 8, 64);
      info.textContent = 'PNG 未加载（可能仍在下载或加载失败）';
      return;
    }
    const sx = absIdx * (SPRITE_SHEET_FRAME + SPRITE_SHEET_GAP);
    // 朝左翻转预览
    if (dbgState.flipped) {
      ctx2.save();
      ctx2.translate(128, 0);
      ctx2.scale(-1, 1);
      ctx2.drawImage(img, sx, 0, SPRITE_SHEET_FRAME, SPRITE_SHEET_FRAME,
                     0, 0, 128, 128);
      ctx2.restore();
    } else {
      ctx2.drawImage(img, sx, 0, SPRITE_SHEET_FRAME, SPRITE_SHEET_FRAME,
                     0, 0, 128, 128);
    }
    // 信息
    const seqLen = DBG_FRAME_MAP[dbgState.anim].length;
    // 缓存 ImageData 供 hover 取色 + 质量统计
    let pixelCount = 0, colorCount = 0;
    try {
      lastImageData = ctx2.getImageData(0, 0, 128, 128);
      const data = lastImageData.data;
      const colorSet = {};
      for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] >= 200) {
          pixelCount++;
          const k = data[i] + ',' + data[i + 1] + ',' + data[i + 2];
          colorSet[k] = 1;
        }
      }
      colorCount = Object.keys(colorSet).length;
    } catch (e) { lastImageData = null; }
    // 注意：128x128 是 4x 放大，原始 32x32 像素数 = pixelCount / 16
    const origPixels = Math.round(pixelCount / 16);
    const coverage = (origPixels / (32 * 32) * 100).toFixed(1);
    info.innerHTML =
      '角色: <b>' + dbgState.species + '</b><br>' +
      '动画: <b>' + dbgState.anim + '</b>（' + seqLen + ' 帧）<br>' +
      '当前: 第 ' + (dbgState.frameIdx % seqLen + 1) + ' 帧 / 绝对索引 ' + absIdx + '<br>' +
      'PNG: ' + SPECIES_TO_PNG[dbgState.species] + '_sprite.png<br>' +
      '切片 x: ' + sx + ' ~ ' + (sx + 32) + '<br>' +
      '质量: ' + origPixels + ' 像素 / ' + colorCount + ' 色 / 覆盖率 ' + coverage + '%';
    // 计算色板（按使用频率排序，最多 8 个）
    updatePalette();
    // 刷新 PNG 加载状态（每帧调用，但只重建 DOM 一次）
    updatePngStatus();
  }

  function updatePngStatus() {
    if (updatePngStatus._lastGen && Date.now() - updatePngStatus._lastGen < 1000) return;
    updatePngStatus._lastGen = Date.now();
    let html = '';
    let okCount = 0, failCount = 0;
    Object.keys(SPECIES_TO_PNG).forEach(sp => {
      const ok = !!pngSpriteSheets[sp];
      const fail = pngSpriteFailed.has(sp);
      if (ok) okCount++;
      else if (fail) failCount++;
      const icon = ok ? '<span style="color:#6b8f71">✓</span>'
                     : fail ? '<span style="color:#c45b5a">✗</span>'
                            : '<span style="color:#d4a574">…</span>';
      html += icon + sp + ' ';
    });
    html = '<div style="margin-bottom:4px;color:var(--text-dim)">已加载 <b style="color:#6b8f71">' + okCount + '</b> / 失败 <b style="color:#c45b5a">' + failCount + '</b> / 等待 <b style="color:#d4a574">' + (12 - okCount - failCount) + '</b></div>' + html;
    pngStatusEl.innerHTML = html;
  }

  function updatePalette() {
    paletteEl.innerHTML = '';
    if (!lastImageData) return;
    const counts = {};
    const data = lastImageData.data;
    for (let i = 0; i < data.length; i += 4) {
      const a = data[i + 3];
      if (a < 200) continue;  // 跳过透明
      const key = data[i] + ',' + data[i + 1] + ',' + data[i + 2];
      counts[key] = (counts[key] || 0) + 1;
    }
    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const total = 128 * 128;
    sorted.forEach(([rgb, cnt]) => {
      const [r, g, b] = rgb.split(',').map(Number);
      const hex = '#' + [r, g, b].map(n => n.toString(16).padStart(2, '0')).join('');
      const swatch = document.createElement('div');
      swatch.className = 'dbg-swatch';
      swatch.title = hex + '  ' + cnt + ' 像素';
      swatch.innerHTML = '<i style="background:' + hex + '"></i>' +
        '<span>' + hex + '</span><span style="opacity:0.6">×' + cnt + '</span>';
      paletteEl.appendChild(swatch);
    });
  }

  function updateGifs() {
    gifsEl.innerHTML = '';
    ['idle', 'walk', 'work', 'sleep', 'react'].forEach(anim => {
      const img = document.createElement('img');
      img.src = '/sprites/gif/' + SPECIES_TO_PNG[dbgState.species] + '_' + anim + '.gif';
      img.title = anim + ' 动画';
      img.alt = anim;
      gifsEl.appendChild(img);
    });
  }

  function stopPlay() {
    if (dbgState.playTimer) {
      clearInterval(dbgState.playTimer);
      dbgState.playTimer = null;
    }
    dbgState.playing = false;
    document.getElementById('dbg-play').textContent = '▶ 播放';
  }

  function startPlay() {
    stopPlay();
    dbgState.playing = true;
    document.getElementById('dbg-play').textContent = '⏸ 暂停';
    const durations = { idle: 300, walk: 150, work: 200, sleep: 800, react: 400 };
    dbgState.playTimer = setInterval(() => {
      const seq = DBG_FRAME_MAP[dbgState.anim];
      dbgState.frameIdx = (dbgState.frameIdx + 1) % seq.length;
      render();
    }, durations[dbgState.anim] || 200);
  }

  // 事件绑定
  sel.onchange = () => {
    dbgState.species = sel.value;
    dbgState.frameIdx = 0;
    render();
    updateGifs();
  };
  document.querySelectorAll('#sprite-debug button[data-anim]').forEach(btn => {
    btn.onclick = () => {
      dbgState.anim = btn.dataset.anim;
      dbgState.frameIdx = 0;
      document.querySelectorAll('#sprite-debug button[data-anim]')
        .forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      render();
      if (dbgState.playing) startPlay();  // 切动画时重启播放
    };
  });
  document.getElementById('dbg-prev').onclick = () => {
    const seq = DBG_FRAME_MAP[dbgState.anim];
    dbgState.frameIdx = (dbgState.frameIdx - 1 + seq.length) % seq.length;
    render();
  };
  document.getElementById('dbg-next').onclick = () => {
    const seq = DBG_FRAME_MAP[dbgState.anim];
    dbgState.frameIdx = (dbgState.frameIdx + 1) % seq.length;
    render();
  };
  document.getElementById('dbg-play').onclick = () => {
    if (dbgState.playing) stopPlay();
    else startPlay();
  };
  document.getElementById('dbg-flip').onclick = (e) => {
    dbgState.flipped = !dbgState.flipped;
    e.target.classList.toggle('active', dbgState.flipped);
    render();
  };

  // F12 切换面板
  document.addEventListener('keydown', (e) => {
    if (e.key === 'F12') {
      e.preventDefault();
      panel.classList.toggle('open');
      if (panel.classList.contains('open')) {
        // 默认激活 idle 按钮
        document.querySelector('#sprite-debug button[data-anim="idle"]').click();
      }
    }
  });

  // canvas 鼠标悬停：显示像素坐标和颜色（4x 放大，每 4px 对应 1 像素）
  canvas.addEventListener('mousemove', (e) => {
    if (!lastImageData) { hoverEl.textContent = '—'; return; }
    const rect = canvas.getBoundingClientRect();
    // canvas 内坐标（0~128）
    const cx = Math.floor((e.clientX - rect.left) * canvas.width / rect.width);
    const cy = Math.floor((e.clientY - rect.top) * canvas.height / rect.height);
    if (cx < 0 || cx >= 128 || cy < 0 || cy >= 128) return;
    const idx = (cy * 128 + cx) * 4;
    const r = lastImageData.data[idx];
    const g = lastImageData.data[idx + 1];
    const b = lastImageData.data[idx + 2];
    const a = lastImageData.data[idx + 3];
    // 原始像素坐标（除以 4）
    const px = Math.floor(cx / 4);
    const py = Math.floor(cy / 4);
    if (a < 10) {
      hoverEl.textContent = '(' + px + ', ' + py + ')  透明';
    } else {
      const hex = '#' + [r, g, b].map(n => n.toString(16).padStart(2, '0')).join('');
      hoverEl.innerHTML = '(' + px + ', ' + py + ')  ' + hex +
        '  <i style="display:inline-block;width:10px;height:10px;background:' + hex +
        ';vertical-align:middle;border:1px solid rgba(255,255,255,0.3)"></i>';
    }
  });
  canvas.addEventListener('mouseleave', () => { hoverEl.textContent = '—'; });

  // PNG 加载完成后重渲染（处理首次打开时 PNG 未就绪）
  const waitPng = setInterval(() => {
    if (pngSpriteSheets[dbgState.species]) {
      render();
      updateGifs();
      clearInterval(waitPng);
    }
  }, 200);
}

// 切片：从 PNG sprite sheet 取第 idx 帧（0..10）绘制到目标 canvas
// 返回 canvas（64x64 放大 2x 显示更清晰），失败返回 null
const pngFrameCache = {};
function getPngFrame(species, frameIdx) {
  if (frameIdx < 0 || frameIdx >= SPRITE_SHEET_FRAMES) return null;
  const img = pngSpriteSheets[species];
  if (!img) return null;
  const key = species + '_' + frameIdx;
  if (pngFrameCache[key]) return pngFrameCache[key];
  const off = document.createElement('canvas');
  off.width = 64; off.height = 64;
  const c = off.getContext('2d');
  c.imageSmoothingEnabled = false;  // 像素艺术：禁用抗锯齿
  const sx = frameIdx * (SPRITE_SHEET_FRAME + SPRITE_SHEET_GAP);
  // commit 41：48×48 居中放大（原 64×64 满铺导致像素糊）
  // 从 32×32 源放大到 48×48，居中放在 64×64 画布上（偏移 8,8）
  const destSize = 48;
  const destOff = (64 - destSize) / 2;
  c.drawImage(img, sx, 0, SPRITE_SHEET_FRAME, SPRITE_SHEET_FRAME,
              destOff, destOff, destSize, destSize);
  // commit 41：强化轮廓 —— source-atop 模式下 4 方向偏移重绘制造描边
  c.globalCompositeOperation = 'source-atop';
  for (const [dx, dy] of [[1,0],[-1,0],[0,1],[0,-1]]) c.drawImage(off, dx, dy);
  c.globalCompositeOperation = 'source-over';
  // 最上层重画原图，保证主体清晰
  c.drawImage(img, sx, 0, SPRITE_SHEET_FRAME, SPRITE_SHEET_FRAME,
              destOff, destOff, destSize, destSize);
  pngFrameCache[key] = off;
  return off;
}

// 根据员工状态选择 PNG 帧索引
// 死亡 → sleep（帧 9，趴下）；情绪极低 → react（帧 10，每 2 秒闪 0.4 秒）；
// busy → work（帧 6/7/8 循环）；走动中 → walk（帧 2/3/4/5 循环）；静止 → idle（帧 0/1）
function pickPngFrameIdx(emp, frame) {
  // 死亡员工：永远显示 sleep 帧（趴下）
  if (emp.alive === false) return 9;
  // 情绪极低员工：周期性触发 react 帧（每 2 秒闪 0.4 秒警示）
  if (emp.mood_score != null && emp.mood_score < 20) {
    const cycle = (performance.now() / 1000) % 2.0;  // 2 秒周期
    if (cycle < 0.4) return 10;  // react 帧
  }
  if (emp.busy) {
    // work 帧 6/7/8 循环
    return 6 + (frame % 3);
  }
  // 检查是否在走动（_wtx/_wty 与 _wx/_wy 有距离）
  if (emp._wx != null && emp._wtx != null) {
    const dx = emp._wtx - emp._wx;
    const dy = emp._wty - emp._wy;
    if (dx * dx + dy * dy > 0.4) {
      return 2 + (frame % 4);  // walk 帧 2/3/4/5
    }
  }
  return frame % 2;  // idle 帧 0/1
}

function getSprite(species, frame) {
  const key = species + '_' + frame;
  if (spriteCache[key]) return spriteCache[key];
  const off = document.createElement('canvas');
  off.width = 64; off.height = 64;
  const c = off.getContext('2d');
  drawSprite(c, species, frame);
  spriteCache[key] = off;
  return off;
}

function drawSprite(c, species, frame) {
  const colors = SPECIES_COLORS[species] || {body: '#7A6E5C', accent: '#D4A574'};
  // commit 48：终极方案 —— 四足/自然动物原形 + 职业配件（禁直立人形）
  // 三条规则：① 动物原本姿态（鹿四脚站、松鼠蹲、鸟停枝头）② 拟人靠配件（眼镜/帽/挎包/望远镜）
  // ③ 配件主色 = EMPLOYEE_COLOR_MAP[species]（与花名册圆点同源）
  const seg = Math.floor(frame / 4);  // 0:呼吸 1:眨眼 2:走动 3:工作
  const sub = (frame % 4) / 4;

  // === 统一调色板 ===
  const BASE_COLOR = '#D8C3A5';      // 原木卡其（所有动物身体底色统一）
  const BASE_DARK  = '#B5997A';      // 卡其暗部
  const BASE_LIGHT = '#E8D8B8';      // 卡其亮部
  const GEAR_COLOR = getEmployeeColor(species);  // 配件主色（= 花名册圆点色）
  const GEAR_DARK  = shadeHex(GEAR_COLOR, -0.15);
  const GEAR_LIGHT = shadeHex(GEAR_COLOR, 0.15);
  const ACCENT     = colors.accent;  // 物种特征色（角/尾等点缀）
  const EDGE       = 'rgba(60, 40, 20, 0.7)';
  const WOOD       = '#8B6F47';      // 木色道具
  const WOOD_DK    = '#5C4022';

  c.clearRect(0, 0, 64, 64);

  // 阴影
  c.fillStyle = 'rgba(0, 0, 0, 0.3)';
  c.beginPath();
  c.ellipse(32, 58, 14, 3, 0, 0, Math.PI * 2);
  c.fill();

  // 呼吸偏移（待机动作，不做走动骨骼）
  const bobY = (seg === 0) ? Math.sin(sub * Math.PI * 2) * 0.6 : 0;
  const breath = (seg === 0) ? 1 + Math.sin(sub * Math.PI * 2) * 0.03 : 1;

  c.strokeStyle = EDGE;
  c.lineWidth = 1.5;

  // ==================== 各物种自然形态（四足/蹲/停枝） ====================
  if (species === 'deer') {
    // 鹿：四脚站立，长腿+鹿角+煤油灯挂角上
    // 身体（椭圆）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(32, 42 + bobY, 13, 8, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 四条腿（细长矩形）
    c.fillStyle = BASE_DARK;
    c.fillRect(22, 46 + bobY, 3, 10);
    c.fillRect(28, 46 + bobY, 3, 10);
    c.fillRect(36, 46 + bobY, 3, 10);
    c.fillRect(42, 46 + bobY, 3, 10);
    // 脖子（斜向上）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.moveTo(38, 38 + bobY);
    c.lineTo(44, 30 + bobY);
    c.lineTo(40, 28 + bobY);
    c.lineTo(35, 36 + bobY);
    c.closePath();
    c.fill(); c.stroke();
    // 头（椭圆）
    c.beginPath();
    c.ellipse(44, 26 + bobY, 6, 5, 0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 鹿角（深棕，分叉）
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(42, 22 + bobY); c.lineTo(39, 14 + bobY);
    c.moveTo(40, 18 + bobY); c.lineTo(36, 16 + bobY);
    c.moveTo(46, 22 + bobY); c.lineTo(49, 14 + bobY);
    c.moveTo(48, 18 + bobY); c.lineTo(52, 16 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(45, 25 + bobY, 1.5, 1.5);
    // 职业配件：木质药草项链 + 鹿角挂煤油灯（GEAR_COLOR 主色）
    c.fillStyle = GEAR_COLOR;
    c.beginPath();
    c.ellipse(40, 34 + bobY, 2, 1.5, 0, 0, Math.PI * 2);
    c.fill();
    // 煤油灯（挂在鹿角左侧）
    c.fillStyle = GEAR_COLOR;
    c.fillRect(35, 16 + bobY, 3, 4);
    c.strokeRect(35, 16 + bobY, 3, 4);
    const glow = 0.5 + Math.sin(sub * Math.PI * 2) * 0.3;
    c.fillStyle = 'rgba(255, 220, 120, ' + glow + ')';
    c.fillRect(35.5, 17 + bobY, 2, 2);
  } else if (species === 'squirrel') {
    // 松鼠：四肢蹲地，大尾巴+护目镜+代码石板
    // 大尾巴（蓬松，背后）
    c.fillStyle = ACCENT;
    c.beginPath();
    c.ellipse(44, 36 + bobY, 6, 10, 0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 身体（圆胖蹲姿）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(30, 44 + bobY, 9, 8, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 头（圆）
    c.beginPath();
    c.ellipse(26, 36 + bobY, 6, 5, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 小耳朵
    c.fillStyle = BASE_COLOR;
    c.beginPath(); c.arc(23, 31 + bobY, 2, 0, Math.PI * 2); c.fill(); c.stroke();
    c.beginPath(); c.arc(29, 31 + bobY, 2, 0, Math.PI * 2); c.fill(); c.stroke();
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(23, 35 + bobY, 1.5, 1.5);
    c.fillRect(28, 35 + bobY, 1.5, 1.5);
    // 职业配件：黑框护目镜（GEAR_COLOR 主色）戴头上
    c.strokeStyle = GEAR_COLOR;
    c.lineWidth = 2;
    c.strokeRect(21, 33 + bobY, 4, 3);
    c.strokeRect(27, 33 + bobY, 4, 3);
    c.beginPath();
    c.moveTo(25, 34 + bobY); c.lineTo(27, 34 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 代码石板（爪子抱，GEAR_COLOR 边框）
    c.fillStyle = '#E8DCC8';
    c.fillRect(32, 42 + bobY, 10, 8);
    c.strokeStyle = GEAR_COLOR;
    c.strokeRect(32, 42 + bobY, 10, 8);
    c.strokeStyle = EDGE;
    // 石板上的代码线
    c.fillStyle = GEAR_COLOR;
    for (let i = 0; i < 4; i++) {
      c.fillRect(34, 44 + bobY + i * 1.5, 6 + Math.sin(sub * Math.PI * 2 + i) * 2, 1);
    }
  } else if (species === 'butterfly') {
    // 蝶：停在画架旁，翅膀+小画板背包
    const flap = Math.abs(Math.sin(sub * Math.PI * 2)) * 0.2 + 0.8;
    // 翅膀（ACCENT 物种色）
    c.fillStyle = ACCENT;
    c.globalAlpha = 0.7;
    c.beginPath();
    c.ellipse(24, 32 + bobY, 8 * flap, 10, -0.2, 0, Math.PI * 2);
    c.fill();
    c.beginPath();
    c.ellipse(40, 32 + bobY, 8 * flap, 10, 0.2, 0, Math.PI * 2);
    c.fill();
    c.globalAlpha = 1;
    // 身体（细长椭圆）
    c.fillStyle = BASE_DARK;
    c.beginPath();
    c.ellipse(32, 36 + bobY, 2, 7, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 头（小圆）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.arc(32, 28 + bobY, 2.5, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 触角
    c.strokeStyle = BASE_DARK;
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(31, 26 + bobY); c.quadraticCurveTo(29, 22 + bobY, 28, 20 + bobY);
    c.moveTo(33, 26 + bobY); c.quadraticCurveTo(35, 22 + bobY, 36, 20 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(31, 28 + bobY, 1, 1);
    c.fillRect(33, 28 + bobY, 1, 1);
    // 职业配件：小画板背包（GEAR_COLOR 主色背带）
    c.fillStyle = WOOD;
    c.fillRect(40, 42 + bobY, 8, 6);
    c.strokeRect(40, 42 + bobY, 8, 6);
    // 背带（GEAR_COLOR）
    c.strokeStyle = GEAR_COLOR;
    c.lineWidth = 1.5;
    c.beginPath();
    c.moveTo(36, 38 + bobY); c.lineTo(42, 44 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 画板上颜料点
    c.fillStyle = GEAR_COLOR;
    c.fillRect(42, 44 + bobY, 2, 2);
  } else if (species === 'fox') {
    // 狐：趴在地上，长尾+测试日志+羽毛笔叼嘴
    // 蓬松大尾巴（ACCENT）
    c.fillStyle = ACCENT;
    c.beginPath();
    c.ellipse(46, 44 + bobY, 7, 5, 0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 白尾尖
    c.fillStyle = '#E8E4D8';
    c.beginPath();
    c.arc(51, 42 + bobY, 2, 0, Math.PI * 2);
    c.fill();
    // 身体（趴着，长椭圆）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(30, 48 + bobY, 14, 6, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 四条腿（趴着收起，只露小腿）
    c.fillStyle = BASE_DARK;
    c.fillRect(20, 50 + bobY, 3, 5);
    c.fillRect(26, 50 + bobY, 3, 5);
    c.fillRect(36, 50 + bobY, 3, 5);
    c.fillRect(42, 50 + bobY, 3, 5);
    // 头（前伸）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(16, 44 + bobY, 6, 5, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 三角尖耳（ACCENT）
    c.fillStyle = ACCENT;
    c.beginPath();
    c.moveTo(13, 40 + bobY); c.lineTo(11, 34 + bobY); c.lineTo(17, 40 + bobY);
    c.closePath(); c.fill(); c.stroke();
    c.beginPath();
    c.moveTo(19, 40 + bobY); c.lineTo(21, 34 + bobY); c.lineTo(15, 40 + bobY);
    c.closePath(); c.fill(); c.stroke();
    // 白下巴
    c.fillStyle = '#E8E4D8';
    c.beginPath();
    c.arc(14, 47 + bobY, 2, 0, Math.PI * 2);
    c.fill();
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(13, 43 + bobY, 1.5, 1.5);
    // 职业配件：摊开的测试日志（GEAR_COLOR 边框）
    c.fillStyle = '#E8DCC8';
    c.fillRect(18, 50 + bobY, 12, 5);
    c.strokeStyle = GEAR_COLOR;
    c.strokeRect(18, 50 + bobY, 12, 5);
    c.strokeStyle = EDGE;
    // 日志线
    c.fillStyle = GEAR_COLOR;
    for (let i = 0; i < 3; i++) {
      c.fillRect(20, 51 + bobY + i * 1.5, 8, 0.8);
    }
    // 羽毛笔（叼在嘴里，GEAR_COLOR 笔杆）
    c.strokeStyle = GEAR_COLOR;
    c.lineWidth = 1.5;
    c.beginPath();
    c.moveTo(14, 46 + bobY); c.lineTo(22, 50 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
  } else if (species === 'hedgehog') {
    // 猬：缩成球+背刺+安全钢盔
    // 球形身体
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.arc(32, 44 + bobY, 11, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 背刺（密密麻麻）
    c.fillStyle = BASE_DARK;
    for (let i = 0; i < 12; i++) {
      const ang = -Math.PI + i * Math.PI / 11;
      const r1 = 11, r2 = 14;
      c.beginPath();
      c.moveTo(32 + Math.cos(ang) * r1, 44 + bobY + Math.sin(ang) * r1);
      c.lineTo(32 + Math.cos(ang) * r2, 44 + bobY + Math.sin(ang) * r2);
      c.stroke();
    }
    // 脸（小球前方）
    c.fillStyle = BASE_LIGHT;
    c.beginPath();
    c.arc(22, 44 + bobY, 5, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(20, 43 + bobY, 1.5, 1.5);
    // 鼻
    c.fillStyle = '#3D2E1F';
    c.beginPath();
    c.arc(18, 45 + bobY, 1, 0, Math.PI * 2);
    c.fill();
    // 职业配件：安全钢盔（GEAR_COLOR 主色）戴头顶
    c.fillStyle = GEAR_COLOR;
    c.beginPath();
    c.arc(22, 40 + bobY, 5, Math.PI, 0);
    c.fill(); c.stroke();
    c.fillRect(17, 40 + bobY, 10, 1.5);
    // 盔顶高光
    c.fillStyle = GEAR_LIGHT;
    c.fillRect(20, 37 + bobY, 4, 1);
    // 警戒盾牌（GEAR_COLOR，背在身上）
    c.fillStyle = GEAR_DARK;
    c.beginPath();
    c.moveTo(38, 38 + bobY);
    c.lineTo(44, 40 + bobY);
    c.lineTo(44, 48 + bobY);
    c.lineTo(38, 50 + bobY);
    c.closePath();
    c.fill(); c.stroke();
    // 盾牌黄黑警戒条纹
    c.fillStyle = '#F1C40F';
    c.fillRect(39, 42 + bobY, 4, 1.5);
    c.fillRect(39, 46 + bobY, 4, 1.5);
  } else if (species === 'beaver') {
    // 海狸：坐着抱木头+工地安全帽
    // 扁平尾巴（拖地，ACCENT 卡其暗）
    c.fillStyle = BASE_DARK;
    c.beginPath();
    c.ellipse(46, 52 + bobY, 6, 3, 0.2, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 身体（坐姿，圆胖）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(30, 46 + bobY, 10, 9, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 头（圆）
    c.beginPath();
    c.ellipse(26, 36 + bobY, 7, 6, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 小圆耳
    c.fillStyle = BASE_COLOR;
    c.beginPath(); c.arc(22, 31 + bobY, 2, 0, Math.PI * 2); c.fill(); c.stroke();
    c.beginPath(); c.arc(30, 31 + bobY, 2, 0, Math.PI * 2); c.fill(); c.stroke();
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(23, 35 + bobY, 1.5, 1.5);
    c.fillRect(28, 35 + bobY, 1.5, 1.5);
    // 门牙
    c.fillStyle = '#E8E4D8';
    c.fillRect(25, 40 + bobY, 1.5, 3);
    c.fillRect(27, 40 + bobY, 1.5, 3);
    // 职业配件：工地安全帽（GEAR_COLOR 主色）
    c.fillStyle = GEAR_COLOR;
    c.beginPath();
    c.arc(26, 32 + bobY, 7, Math.PI, 0);
    c.fill(); c.stroke();
    c.fillRect(19, 32 + bobY, 14, 1.5);
    // 帽顶高光
    c.fillStyle = GEAR_LIGHT;
    c.fillRect(24, 29 + bobY, 4, 1);
    // 抱着的大木头（爪子抱）
    c.fillStyle = WOOD;
    c.fillRect(34, 42 + bobY, 14, 5);
    c.strokeRect(34, 42 + bobY, 14, 5);
    // 木头纹理
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 0.8;
    c.beginPath();
    c.moveTo(38, 42 + bobY); c.lineTo(38, 47 + bobY);
    c.moveTo(44, 42 + bobY); c.lineTo(44, 47 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
  } else if (species === 'raven') {
    // 鸦：停在枯树枝上+记忆卷轴
    // 枯树枝（横向）
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 2.5;
    c.beginPath();
    c.moveTo(14, 50 + bobY); c.lineTo(50, 50 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 身体（椭圆，蹲枝上）
    c.fillStyle = BASE_DARK;
    c.beginPath();
    c.ellipse(32, 42 + bobY, 9, 8, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 头（圆）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.arc(32, 32 + bobY, 6, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 粗喙（深色）
    c.fillStyle = WOOD_DK;
    c.beginPath();
    c.moveTo(32, 32 + bobY);
    c.lineTo(40, 34 + bobY);
    c.lineTo(32, 36 + bobY);
    c.closePath();
    c.fill(); c.stroke();
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(30, 31 + bobY, 1.5, 1.5);
    // 翅膀（收拢，深色）
    c.fillStyle = BASE_DARK;
    c.beginPath();
    c.ellipse(28, 42 + bobY, 5, 7, -0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    c.beginPath();
    c.ellipse(36, 42 + bobY, 5, 7, 0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 爪子（抓枝）
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 1.5;
    c.beginPath();
    c.moveTo(28, 48 + bobY); c.lineTo(28, 52 + bobY);
    c.moveTo(30, 48 + bobY); c.lineTo(30, 52 + bobY);
    c.moveTo(34, 48 + bobY); c.lineTo(34, 52 + bobY);
    c.moveTo(36, 48 + bobY); c.lineTo(36, 52 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 职业配件：记忆卷轴（GEAR_COLOR 主色，挂在树枝旁）
    c.fillStyle = GEAR_COLOR;
    c.fillRect(18, 52 + bobY, 8, 4);
    c.strokeRect(18, 52 + bobY, 8, 4);
    // 卷轴两端
    c.fillStyle = GEAR_DARK;
    c.fillRect(17, 51 + bobY, 1.5, 6);
    c.fillRect(25.5, 51 + bobY, 1.5, 6);
    // 卷轴绳
    c.strokeStyle = GEAR_COLOR;
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(22, 56 + bobY); c.lineTo(22, 50 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
  } else if (species === 'hare') {
    // 兔：蹲着+邮差包+快递箱
    // 身体（蹲姿圆胖）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(32, 44 + bobY, 9, 8, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 头（圆）
    c.beginPath();
    c.arc(32, 34 + bobY, 6, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 超长竖耳（卡其底，ACCENT 内）
    c.fillStyle = BASE_COLOR;
    c.beginPath(); c.ellipse(28, 22 + bobY, 2, 10, 0, 0, Math.PI * 2); c.fill(); c.stroke();
    c.beginPath(); c.ellipse(36, 22 + bobY, 2, 10, 0, 0, Math.PI * 2); c.fill(); c.stroke();
    c.fillStyle = ACCENT;
    c.globalAlpha = 0.6;
    c.beginPath(); c.ellipse(28, 23 + bobY, 0.8, 7, 0, 0, Math.PI * 2); c.fill();
    c.beginPath(); c.ellipse(36, 23 + bobY, 0.8, 7, 0, 0, Math.PI * 2); c.fill();
    c.globalAlpha = 1;
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(29, 33 + bobY, 1.5, 1.5);
    c.fillRect(34, 33 + bobY, 1.5, 1.5);
    // 鼻
    c.fillStyle = '#3D2E1F';
    c.beginPath();
    c.arc(32, 36 + bobY, 1, 0, Math.PI * 2);
    c.fill();
    // 职业配件：邮差包（GEAR_COLOR 主色，挎脖）
    c.fillStyle = GEAR_COLOR;
    c.beginPath();
    c.moveTo(26, 40 + bobY);
    c.lineTo(38, 40 + bobY);
    c.lineTo(40, 48 + bobY);
    c.lineTo(24, 48 + bobY);
    c.closePath();
    c.fill(); c.stroke();
    // 包盖
    c.fillStyle = GEAR_DARK;
    c.fillRect(26, 40 + bobY, 12, 2);
    // 背带
    c.strokeStyle = GEAR_COLOR;
    c.lineWidth = 1.5;
    c.beginPath();
    c.moveTo(28, 38 + bobY); c.lineTo(32, 34 + bobY); c.lineTo(36, 38 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 快递箱（背后，GEAR_COLOR 主色）
    c.fillStyle = GEAR_COLOR;
    c.fillRect(42, 42 + bobY, 8, 7);
    c.strokeRect(42, 42 + bobY, 8, 7);
    // 箱盖
    c.fillStyle = GEAR_DARK;
    c.fillRect(42, 42 + bobY, 8, 1.5);
  } else if (species === 'badger') {
    // 獾：四肢站立+嘴里叼铁锹+头顶矿灯
    // 身体（长椭圆）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(32, 44 + bobY, 13, 7, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 黑白条纹（背部）
    c.fillStyle = '#1A1A1A';
    c.fillRect(22, 40 + bobY, 20, 2);
    c.fillStyle = '#E8E4D8';
    c.fillRect(22, 42 + bobY, 20, 1);
    c.fillStyle = '#1A1A1A';
    c.fillRect(22, 43 + bobY, 20, 2);
    // 四条腿
    c.fillStyle = BASE_DARK;
    c.fillRect(22, 48 + bobY, 3, 8);
    c.fillRect(28, 48 + bobY, 3, 8);
    c.fillRect(36, 48 + bobY, 3, 8);
    c.fillRect(42, 48 + bobY, 3, 8);
    // 头（前伸，黑白条纹脸）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(18, 42 + bobY, 6, 5, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 脸条纹
    c.fillStyle = '#E8E4D8';
    c.fillRect(14, 40 + bobY, 2, 6);
    c.fillStyle = '#1A1A1A';
    c.fillRect(16, 40 + bobY, 2, 6);
    c.fillStyle = '#E8E4D8';
    c.fillRect(18, 40 + bobY, 2, 6);
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(17, 42 + bobY, 1.5, 1.5);
    // 职业配件：头顶矿灯（GEAR_COLOR 主色）
    c.fillStyle = GEAR_COLOR;
    c.beginPath();
    c.arc(18, 36 + bobY, 3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 灯泡（发光）
    const lampGlow = 0.5 + Math.sin(sub * Math.PI * 2) * 0.3;
    c.fillStyle = 'rgba(255, 240, 180, ' + lampGlow + ')';
    c.beginPath();
    c.arc(18, 36 + bobY, 1.5, 0, Math.PI * 2);
    c.fill();
    // 嘴里叼铁锹（GEAR_COLOR 锹柄）
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 2;
    c.beginPath();
    c.moveTo(14, 44 + bobY); c.lineTo(4, 38 + bobY);
    c.stroke();
    // 锹头（GEAR_COLOR）
    c.fillStyle = GEAR_COLOR;
    c.fillRect(2, 36 + bobY, 5, 4);
    c.strokeRect(2, 36 + bobY, 5, 4);
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
  } else if (species === 'lark') {
    // 雀：停在收音机喇叭上+音符
    // 收音机喇叭（底座）
    c.fillStyle = WOOD;
    c.fillRect(22, 46 + bobY, 20, 10);
    c.strokeRect(22, 46 + bobY, 20, 10);
    // 喇叭口（GEAR_COLOR 主色）
    c.fillStyle = GEAR_COLOR;
    c.beginPath();
    c.ellipse(32, 46 + bobY, 7, 3, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 身体（小鸟，蹲喇叭上）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(32, 38 + bobY, 6, 6, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 头
    c.beginPath();
    c.arc(32, 30 + bobY, 4.5, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 翘毛（ACCENT）
    c.fillStyle = ACCENT;
    c.beginPath();
    c.moveTo(32, 26 + bobY); c.lineTo(34, 20 + bobY); c.lineTo(36, 26 + bobY);
    c.closePath(); c.fill(); c.stroke();
    // 尖喙（ACCENT）
    c.beginPath();
    c.moveTo(32, 30 + bobY); c.lineTo(38, 31 + bobY); c.lineTo(32, 32 + bobY);
    c.closePath(); c.fill(); c.stroke();
    // 眼
    c.fillStyle = '#0a0f0c';
    c.fillRect(31, 29 + bobY, 1.2, 1.2);
    // 翅膀（ACCENT）
    c.fillStyle = ACCENT;
    c.beginPath();
    c.ellipse(28, 38 + bobY, 3, 5, -0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 爪子（抓喇叭）
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(30, 44 + bobY); c.lineTo(30, 46 + bobY);
    c.moveTo(34, 44 + bobY); c.lineTo(34, 46 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 音符（飘动，GEAR_COLOR）
    c.fillStyle = GEAR_COLOR;
    c.globalAlpha = 0.7 + Math.sin(sub * Math.PI * 2) * 0.3;
    c.font = '10px serif';
    c.fillText('\u266A', 16, 26 + bobY);
    c.fillText('\u266B', 46, 22 + bobY);
    c.globalAlpha = 1;
  } else if (species === 'kite') {
    // 鸢：站在高木桩瞭望台+脖子挂单筒望远镜
    // 高木桩（瞭望台底座）
    c.fillStyle = WOOD;
    c.fillRect(28, 44 + bobY, 8, 14);
    c.strokeRect(28, 44 + bobY, 8, 14);
    // 木桩纹理
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 0.8;
    c.beginPath();
    c.moveTo(32, 46 + bobY); c.lineTo(32, 58 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 身体（鸟形，站在桩上）
    c.fillStyle = BASE_COLOR;
    c.beginPath();
    c.ellipse(32, 36 + bobY, 8, 7, 0, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 头（圆，仰视）
    c.beginPath();
    c.arc(32, 26 + bobY, 5, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 羽冠（ACCENT）
    c.fillStyle = ACCENT;
    c.beginPath();
    c.moveTo(32, 22 + bobY); c.lineTo(30, 16 + bobY); c.lineTo(34, 20 + bobY);
    c.closePath(); c.fill(); c.stroke();
    // 弯钩喙（ACCENT）
    c.beginPath();
    c.moveTo(32, 26 + bobY); c.lineTo(40, 27 + bobY);
    c.quadraticCurveTo(42, 30 + bobY, 38, 30 + bobY);
    c.closePath(); c.fill(); c.stroke();
    // 眼（锐利）
    c.fillStyle = '#0a0f0c';
    c.fillRect(33, 25 + bobY, 1.5, 1.5);
    c.fillStyle = '#FFFFFF';
    c.fillRect(33.5, 25 + bobY, 0.5, 0.5);
    // 翅膀（收拢）
    c.fillStyle = BASE_DARK;
    c.beginPath();
    c.ellipse(27, 36 + bobY, 4, 6, -0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    c.beginPath();
    c.ellipse(37, 36 + bobY, 4, 6, 0.3, 0, Math.PI * 2);
    c.fill(); c.stroke();
    // 爪子（抓桩顶）
    c.strokeStyle = WOOD_DK;
    c.lineWidth = 1.2;
    c.beginPath();
    c.moveTo(30, 42 + bobY); c.lineTo(30, 46 + bobY);
    c.moveTo(32, 42 + bobY); c.lineTo(32, 46 + bobY);
    c.moveTo(34, 42 + bobY); c.lineTo(34, 46 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
    // 职业配件：脖子挂单筒望远镜（GEAR_COLOR 主色）
    c.fillStyle = GEAR_COLOR;
    c.fillRect(28, 32 + bobY, 8, 3);
    c.strokeRect(28, 32 + bobY, 8, 3);
    // 望远镜两端（深色）
    c.fillStyle = GEAR_DARK;
    c.fillRect(27, 32 + bobY, 2, 3);
    c.fillRect(35, 32 + bobY, 2, 3);
    // 挂绳
    c.strokeStyle = GEAR_COLOR;
    c.lineWidth = 1;
    c.beginPath();
    c.moveTo(28, 32 + bobY); c.quadraticCurveTo(26, 28 + bobY, 30, 26 + bobY);
    c.moveTo(36, 32 + bobY); c.quadraticCurveTo(38, 28 + bobY, 34, 26 + bobY);
    c.stroke();
    c.lineWidth = 1.5; c.strokeStyle = EDGE;
  }

  // ==================== 脚下物种色条（保留点缀，与花名册同源） ====================
  c.fillStyle = GEAR_COLOR;
  c.globalAlpha = 0.5;
  c.fillRect(20, 57 + bobY, 24, 1.5);
  c.globalAlpha = 1;
}

// commit 41：xOff 辅助函数（走动时左右摆动）
function xOff() {
  return 0;
}

// ==================== 员工状态（后端 SSE 推送） ====================
let employees = [];
let envStats = {};
let currentFrame = 0;

// ==================== commit 45-2：仪表盘 Canvas 折线图 ====================
// 零基础读者说明：每秒采样一次生态系统数据（食物/植物/昆虫/平均精力），
// 存到 ecoHistory 数组（最多 60 条 = 60 秒），然后每 500ms 在 canvas 上画 4 条折线。
let ecoHistory = [];  // {t, food, plants, insects, population, energy_avg}
const ECO_HISTORY_MAX = 60;

function sampleEcoHistory() {
  if (!envStats) return;
  const avgEnergy = employees.length > 0
    ? employees.reduce((s, e) => s + (e.energy || 0), 0) / employees.length
    : 0;
  ecoHistory.push({
    t: Date.now(),
    food: parseFloat(envStats.food || 0),
    plants: parseFloat(envStats.plants || 0),
    insects: parseFloat(envStats.insects || 0),
    population: parseFloat(envStats.population || 0),
    energy_avg: avgEnergy,
  });
  if (ecoHistory.length > ECO_HISTORY_MAX) ecoHistory.shift();
}

// drawStatsChart：把 ecoHistory 数据画成 4 条折线到 #stats-chart canvas（每 500ms 调用）
function drawStatsChart() {
  const canvas = document.getElementById('stats-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  // 背景（深海蓝半透明，与面板底色呼应）
  ctx.fillStyle = 'rgba(11, 26, 51, 0.5)';
  ctx.fillRect(0, 0, w, h);

  // 网格线（4 等分水平线）
  ctx.strokeStyle = 'rgba(76, 154, 255, 0.1)';
  ctx.lineWidth = 0.5;
  for (let i = 1; i < 4; i++) {
    const y = h * i / 4;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  if (ecoHistory.length < 2) {
    ctx.fillStyle = 'rgba(232, 240, 255, 0.4)';
    ctx.font = '11px "Fraunces", serif';
    ctx.textAlign = 'center';
    ctx.fillText('采集中…', w / 2, h / 2);
    return;
  }

  // 4 条曲线：食物(绿) / 植物(浅绿) / 昆虫(紫) / 平均精力(琥珀)
  const series = [
    {key: 'food',       color: '#7FD97F', label: '食物'},
    {key: 'plants',     color: '#A5D5A5', label: '植物'},
    {key: 'insects',    color: '#C8A5D5', label: '昆虫'},
    {key: 'energy_avg', color: '#D4A574', label: '精力'},
  ];

  // 计算最大值用于归一化（最小 100，避免低值时曲线贴顶）
  let maxVal = 1;
  for (const s of series) {
    for (const p of ecoHistory) {
      const v = p[s.key] || 0;
      if (v > maxVal) maxVal = v;
    }
  }
  maxVal = Math.max(maxVal, 100);

  for (const s of series) {
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ecoHistory.forEach((p, i) => {
      const x = (i / (ECO_HISTORY_MAX - 1)) * w;
      const y = h - ((p[s.key] || 0) / maxVal) * h * 0.85 - 5;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  // 图例（底部横排）
  ctx.font = '9px "Fraunces", serif';
  ctx.textAlign = 'left';
  let lx = 4;
  for (const s of series) {
    ctx.fillStyle = s.color;
    ctx.fillRect(lx, h - 10, 6, 2);
    ctx.fillStyle = 'rgba(232, 240, 255, 0.7)';
    ctx.fillText(s.label, lx + 8, h - 4);
    lx += 50;
  }
}

setInterval(sampleEcoHistory, 1000);   // 每秒采样一次
setInterval(drawStatsChart, 500);      // 每 500ms 重绘折线图

// ==================== 渲染 ====================
function render() {
  // commit 56：摄像机边界写死 —— 防止拖拽/缩放飘出地图到空白区
  // 零基础说明：算出 worldCanvas 在当前 zoom 下占多大，把 view.x/y 限制在
  // "地图比视口大 → 可移动范围 = 地图宽 - 视口宽" 之内
  if (worldCanvas) {
    const mapW = worldCanvas.width * view.zoom;
    const mapH = worldCanvas.height * view.zoom;
    // 允许一定的越界余量（地图边缘可以露出一点，但不会飘到无边空白）
    const margin = 150;
    // 当地图比视口小，居中即可；比视口大，限制在 [-(mapW-cw)-margin, margin]
    const cw = canvas.width, ch = canvas.height;
    if (mapW > cw) {
      view.x = Math.max(-(mapW - cw) - margin, Math.min(margin, view.x));
    } else {
      view.x = (cw - mapW) / 2;
    }
    if (mapH > ch) {
      view.y = Math.max(-(mapH - ch) - margin, Math.min(margin, view.y));
    } else {
      view.y = (ch - mapH) / 2;
    }
  }

  // 背景：径向渐变（颜色从 THEME_COLORS 缓存读取，跟随主题）
  const grad = ctx.createRadialGradient(
    canvas.width / 2, canvas.height / 2, 0,
    canvas.width / 2, canvas.height / 2, Math.max(canvas.width, canvas.height) / 1.2
  );
  grad.addColorStop(0, THEME_COLORS.canvasBgInner);
  grad.addColorStop(1, THEME_COLORS.canvasBgOuter);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // 1. commit 15：静态地图预渲染（worldCanvas 只画一次，drawImage 时按 zoom 缩放）
  if (!worldCanvas) {
    prerenderWorld();
  }
  // 把 worldCanvas 整张按 view.zoom 缩放后贴到主画布
  // worldCanvas 内部坐标 (wx, wy) → 主画布坐标 (wx*zoom + view.x - worldOffsetX*zoom, ...)
  const dw = worldCanvas.width * view.zoom;
  const dh = worldCanvas.height * view.zoom;
  const dx = view.x - worldOffsetX * view.zoom;
  const dy = view.y - worldOffsetY * view.zoom;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(worldCanvas, dx, dy, dw, dh);

  // commit 25 P3-4：zone 悬停高亮（在地图之上、其他对象之下）
  drawZoneHoverHighlight();

  // commit 45-1：11 工位大型动画覆盖层（每帧重画，在静态装饰之上叠加光效/粒子/状态条）
  // 零基础读者说明：在主渲染循环里调用（非离屏 prerenderWorld），保证动画每帧刷新
  for (const zone of ZONES) {
    drawZoneAnimationOverlay(ctx, zone, performance.now());
  }

  // 2. commit 13：渲染遗物标记（已故员工的 zone 中心）
  drawRelicMarkers();

  // 3. commit 13：渲染晶柜粒子（金色光点飘动）
  drawMemoryParticles();

  // 4. commit 13：渲染晶柜（在 raven 档案室）
  drawMemoryCrystals();

  // 5. commit 14：渲染招募蒙版+海报（DEAD/PENDING/RECRUITING 状态的 zone）
  drawRecruitOverlays();

  // commit 33：渲染区域氛围着色（地面微弱色调）
  drawZoneAuraOverlay();

  // commit 33：渲染氛围粒子（金色光点/蓝色碎屑/灰色抖动）
  drawAtmosphereParticles();

  // 6. 渲染员工精灵（commit 49-2：按 _wy 排序，确保前后遮挡正确）
  // 规则：Y 坐标越大（画面越靠下）的越后画，覆盖在 Y 小的（画面靠上）物体上
  const sorted = [...employees].sort((a, b) => {
    return (a._wy || 0) - (b._wy || 0);
  });
  for (const emp of sorted) {
    drawEmployee(emp);
  }

  // 7. commit 14：渲染走入岗位的新员工（最上层）
  drawWalkingIn();

  // commit 33：渲染记忆碎片（员工之上，可点击）
  drawMemoryFragments();

  // 8. commit 15：渲染通用粒子池（投喂等临时粒子）
  drawActiveParticles();

  // 9. commit 16：渲染监工光标 + 监工反应气泡 + 小地图
  drawSupervisor();
  drawSupervisorReaction();
  drawMinimap();

  // 10. commit 17：环境蝴蝶 + 光照色温叠加 + 天气标识
  drawAmbientButterflies();
  drawTimeOfDayOverlay();
  // commit 25 P3-5：鸟群飞过（最上层）
  drawBirdFlocks();
  // commit 30：对话气泡（员工头顶，3 秒淡出）
  drawDialogueBubbles();

  // commit 33：屏幕边缘情感晕影（监工靠近智能体时）
  updateEmotionVignette();

  // commit 36：环境细节层（窗帘/水波/灰尘/盆栽微动/雾气）
  if (polishSettings.envDetail !== 'off') drawEnvironmentDetails();

  // commit 36：屏幕暗角（CRT 风晕影，夜晚加深）
  drawVignette();

  // commit 36：情感滤镜（监工靠近情感强烈智能体时整屏色调偏移）
  drawEmotionFilter();

  // commit 42：浮空数字（投喂/训练反馈）
  drawFloatNumbers();

  // commit 56：环境色阶滤镜 —— 全屏深色蒙版压暗（解决"过曝/太白/廉价感"）
  // 零基础说明：在所有内容画完后，罩一层半透明深蓝灰，立刻产生"赛博森林"暗色调
  ctx.save();
  ctx.fillStyle = 'rgba(15, 23, 42, 0.35)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

function findZone(ix, iy) {
  for (const z of ZONES) {
    const [x1, y1, x2, y2] = z.rect;
    if (ix >= x1 && ix <= x2 && iy >= y1 && iy <= y2) return z;
  }
  return null;
}

// commit 25 P3-4：zone 悬停高亮
// 鼠标悬停的 zone 整片微微发亮 + 边框
function drawZoneHoverHighlight() {
  if (!hoveredZone) return;
  const [x1, y1, x2, y2] = hoveredZone.rect;
  const t = performance.now() / 1000;
  const pulse = 0.5 + Math.sin(t * 3) * 0.5;
  ctx.save();
  // 高亮覆盖（半透明琥珀）
  ctx.fillStyle = 'rgba(212, 165, 116, ' + (0.06 + pulse * 0.04) + ')';
  for (let ix = x1; ix <= x2; ix++) {
    for (let iy = y1; iy <= y2; iy++) {
      const p = isoToScreen(ix, iy);
      if (p.x < -50 || p.x > canvas.width + 50) continue;
      if (p.y < -50 || p.y > canvas.height + 50) continue;
      const w = TILE_W * view.zoom / 2;
      const h = TILE_H * view.zoom / 2;
      ctx.beginPath();
      ctx.moveTo(p.x, p.y - h);
      ctx.lineTo(p.x + w, p.y);
      ctx.lineTo(p.x, p.y + h);
      ctx.lineTo(p.x - w, p.y);
      ctx.closePath();
      ctx.fill();
    }
  }
  // 边框（zone 边缘的菱形描边）
  const corners = [
    isoToScreen(x1, y1),
    isoToScreen(x2, y1),
    isoToScreen(x2, y2),
    isoToScreen(x1, y2),
  ];
  ctx.strokeStyle = 'rgba(212, 165, 116, ' + (0.4 + pulse * 0.3) + ')';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(corners[0].x, corners[0].y);
  for (let i = 1; i < corners.length; i++) {
    ctx.lineTo(corners[i].x, corners[i].y);
  }
  ctx.closePath();
  ctx.stroke();

  // zone 名字标签（顶部居中）
  const labelP = isoToScreen((x1 + x2) / 2, y1);
  const label = hoveredZone.name || hoveredZone.id || '';
  if (label) {
    ctx.font = '500 ' + (13 * view.zoom) + 'px "Fraunces", serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = THEME_COLORS.textShadow;
    for (let dx = -1; dx <= 1; dx++) {
      for (let dy = -1; dy <= 1; dy++) {
        if (dx === 0 && dy === 0) continue;
        ctx.fillText(label, labelP.x + dx, labelP.y - 14 + dy);
      }
    }
    ctx.fillStyle = '#D4A574';
    ctx.fillText(label, labelP.x, labelP.y - 14);
  }
  ctx.restore();
}

function drawEmployee(emp) {
  // commit 33：记录当前员工物种，供 drawMoodAura 查找光环数据
  currentEmpSpecies = emp.species;
  // 默认放在所属 zone 的中心
  const zone = ZONES.find(z => z.id === SPECIES_TO_ZONE[emp.species]);
  let cx = 40, cy = 30;
  if (zone) {
    cx = (zone.rect[0] + zone.rect[2]) / 2;
    cy = (zone.rect[1] + zone.rect[3]) / 2;
  }

  // commit 24 P1-2：员工在 zone 内真实走动
  // 每个员工有自己的当前位置 (_wx, _wy) 和目标位置 (_wtx, _wty)
  // busy 时停在原地（在工作），闲时朝目标走，到达后随机选新目标
  const zw = zone ? (zone.rect[2] - zone.rect[0]) : 16;
  const zh = zone ? (zone.rect[3] - zone.rect[1]) : 10;
  // commit 50-4：限制踱步范围在工位中心 ±2 格（5x5 小范围），让动作更明显
  // 旧版用 halfW=zw/2-2，zone 太大员工走得很慢像没动；现在固定 ±2 格，小碎步更明显
  const halfW = 2;
  const halfH = 2;

  // 初始化位置（首次出现时）
  if (emp._wx == null) {
    emp._wx = cx + (Math.random() - 0.5) * halfW;
    emp._wy = cy + (Math.random() - 0.5) * halfH;
    emp._wtx = cx + (Math.random() - 0.5) * halfW;
    emp._wty = cy + (Math.random() - 0.5) * halfH;
    emp._wt = 0;  // 在目标停留计时
    emp._facing = 1;  // 朝向：1=右，-1=左
  }

  // commit 44-3：根据游戏时间决定目标 zone（午餐/休闲时段偏移到对应区）
  let targetZoneCx = cx, targetZoneCy = cy;  // 默认本 zone
  if (gameHour >= 11 && gameHour < 13) {
    // 午餐 → 茶水间/休息区
    const lounge = ZONES.find(z => z.id === 'lounge' || z.id === 'pantry');
    if (lounge) {
      targetZoneCx = (lounge.rect[0] + lounge.rect[2]) / 2;
      targetZoneCy = (lounge.rect[1] + lounge.rect[3]) / 2;
    }
  } else if (gameHour >= 18 && gameHour < 22) {
    // 休闲 → 花园/休息区（无 garden zone 时回退 lounge）
    const garden = ZONES.find(z => z.id === 'garden' || z.id === 'lounge');
    if (garden) {
      targetZoneCx = (garden.rect[0] + garden.rect[2]) / 2;
      targetZoneCy = (garden.rect[1] + garden.rect[3]) / 2;
    }
  }

  if (emp.alive === false) {
    // 死亡员工：停止 AI 移动，原地趴下
    emp._wt = 0;
  } else if (emp.busy) {
    // 工作时停在原地（轻微呼吸抖动）
    emp._wt = 0;
    emp._walking = false;  // commit 42：工作时不算走动
  } else if (gameHour >= 22 || gameHour < 7) {
    // commit 44-3：睡眠时段 → 停止走动，原地小憩（仍绘制员工）
    emp._wt = 0;
    emp._walking = false;
  } else if (emp.species === 'kite') {
    // commit 49-3：鸢·天瞰固定站在瞭望台锚点（不参与随机游走）
    // 鸢是观察员，永远站在高木桩上俯瞰，符合角色设定
    emp._wx = KITE_ANCHOR.x;
    emp._wy = KITE_ANCHOR.y;
    emp._wtx = KITE_ANCHOR.x;
    emp._wty = KITE_ANCHOR.y;
    emp._walking = false;
  } else {
    // 闲时朝目标走
    // commit 25 P3-3：清空工作进度计时，下次 busy 重新开始
    emp._workStart = null;
    // 闲时朝目标走
    const dx = emp._wtx - emp._wx;
    const dy = emp._wty - emp._wy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 0.3) {
      // 到达目标，停留一段时间再换新目标
      emp._wt += 1;
      emp._walking = false;  // commit 42：停留时不算走动
      if (emp._wt > 60 + Math.random() * 60) {  // 60-120 帧停留
        // commit 44-3：用目标 zone 中心（午餐/休闲时会偏移到对应区）
        emp._wtx = targetZoneCx + (Math.random() - 0.5) * halfW * 2;
        emp._wty = targetZoneCy + (Math.random() - 0.5) * halfH * 2;
        emp._wt = 0;
      }
    } else {
      // commit 42：走动速度提升（0.12 → 0.22，更明显）
      if (Math.abs(dx) > 0.05) emp._facing = dx > 0 ? 1 : -1;
      const speed = 0.22;
      // commit 49-1：碰撞检测 —— 移动前检测目标格是否障碍，是则拒绝移动并选新目标
      const newX = emp._wx + (dx / dist) * speed;
      const newY = emp._wy + (dy / dist) * speed;
      if (isObstacle(newX, newY, emp.species)) {
        // 撞墙：原地停留，重新选目标
        emp._wt = 80;  // 强制下次循环选新目标
        emp._walking = false;
      } else {
        emp._wx = newX;
        emp._wy = newY;
        emp._walking = true;  // 标记正在走动（供 drawSprite 用 seg===2）
      }
    }
  }

  const ix = emp._wx;
  const iy = emp._wy;
  const p = isoToScreen(ix, iy);
  if (p.x < -100 || p.x > canvas.width + 100) return;
  if (p.y < -100 || p.y > canvas.height + 100) return;

  // commit 35：软阴影（角色脚下，增强立体感）
  const _sz = 64 * view.zoom;
  if (emp.alive !== false && view.zoom > 0.5) {
    drawSoftShadow(p, _sz);
  }
  // commit 41：员工脚下暖色聚光灯（让角色从地砖中"跳出来"）
  {
    const spotR = _sz * 0.6;
    const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, spotR);
    grad.addColorStop(0, 'rgba(255, 200, 120, 0.18)');
    grad.addColorStop(0.6, 'rgba(255, 180, 100, 0.08)');
    grad.addColorStop(1, 'rgba(255, 180, 100, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(p.x, p.y, spotR, spotR * 0.5, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  // commit 35：工作产物画布展示（员工工位附近，最新 2 件）
  if (emp.alive !== false) {
    drawWorkArtifact(emp, p, _sz);
  }
  // commit 19 P0-1：情绪光环
  // commit 26：优先用 PNG 像素图集（11 帧），加载失败回退到矢量简笔画（16 帧）
  // commit 41：远景 LOD 阈值调到 1.15（配合 minZoom 1.0）
  // commit 54：spiritMode 强制走灵魂投影分支（无视 zoom）
  if (polishSettings.spiritMode || view.zoom < 1.15) {
    // commit 56：黑剪影 + 彩色发光光晕（掩盖动物画得丑，用高对比发光体吸引视觉）
    const spiritColor = getEmployeeColor(emp.species);
    const speciesColor = (SPECIES_COLORS[emp.species] && SPECIES_COLORS[emp.species].body) || '#D4A574';
    const useColor = polishSettings.spiritMode ? spiritColor : speciesColor;
    const ringR = polishSettings.spiritMode ? 22 : 14;
    const dotR = polishSettings.spiritMode ? 10 : 6;
    const pulseT = polishSettings.spiritMode ? (Math.sin(performance.now() / 600) * 0.15 + 1) : 1;
    // 1. 彩色光晕（shadowBlur 实现真实发光感）
    ctx.save();
    ctx.shadowBlur = polishSettings.spiritMode ? 30 : 12;
    ctx.shadowColor = useColor;
    const grad = ctx.createRadialGradient(p.x, p.y - 8, 0, p.x, p.y - 8, ringR * 1.8 * pulseT);
    grad.addColorStop(0, useColor + 'cc');
    grad.addColorStop(0.5, useColor + '55');
    grad.addColorStop(1, useColor + '00');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(p.x, p.y - 8, ringR * 1.8 * pulseT, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
    // 2. 黑色剪影（纯黑实心圆，高对比度，不再画丑动物）
    ctx.fillStyle = '#000000';
    ctx.beginPath();
    ctx.arc(p.x, p.y - 8, dotR, 0, Math.PI * 2);
    ctx.fill();
    // 3. 彩色描边（物种色，区分身份）
    ctx.strokeStyle = useColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(p.x, p.y - 8, dotR, 0, Math.PI * 2);
    ctx.stroke();
    // 大字名牌（岗位名简化，字号 13px）
    const shortName = (emp.name || '').split('·')[1] || (emp.name || '');
    ctx.font = '700 13px "Fraunces", serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // 名牌底板
    const textW = ctx.measureText(shortName).width;
    const bx = p.x;
    const by = p.y - 32;
    ctx.fillStyle = 'rgba(45, 34, 22, 0.92)';
    ctx.fillRect(bx - textW / 2 - 6, by - 9, textW + 12, 18);
    ctx.strokeStyle = 'rgba(212, 165, 116, 0.7)';
    ctx.lineWidth = 1;
    ctx.strokeRect(bx - textW / 2 - 6, by - 9, textW + 12, 18);
    // 文字
    ctx.fillStyle = '#FFE4B5';
    ctx.fillText(shortName, bx, by);
    return;  // 跳过后续精灵绘制
  }
  // commit 53：重新启用 PNG sprite（优先 /assets/ 开源素材，fallback /sprites/ 默认素材，再 fallback 矢量）
  // commit 42：走动时强制用走动帧（seg===2，frame 8-11），让腿部动画可见
  const walkFrame = emp._walking
    ? 8 + (Math.floor(performance.now() / 120) % 4)
    : currentFrame;
  const sprite = getSprite(emp.species, walkFrame);
  const pngFrame = getPngFrame(emp.species, pickPngFrameIdx(emp, currentFrame));
  const renderSprite = pngFrame || sprite;  // PNG 优先，未加载/失败回退矢量
  const size = 64 * view.zoom;
  if (emp.alive !== false && emp.mood_score != null) {
    drawMoodAura(p, size, emp.mood_score);
  }

  // 朝左走时水平翻转 sprite（_facing=-1）
  // 注意：矢量简笔画 fallback 是对称的，翻转无影响；PNG 像素图需要翻转
  if (emp._facing === -1) {
    ctx.save();
    ctx.translate(p.x + size / 2, p.y - size);
    ctx.scale(-1, 1);
    ctx.drawImage(renderSprite, 0, 0, size, size);
    ctx.restore();
  } else {
    ctx.drawImage(renderSprite, p.x - size / 2, p.y - size, size, size);
  }

  // commit 41：禁用 drawMoodExpression（二次元笑脸弧线与 2.5D 像素风格不兼容）
  // 情绪现在通过 drawMoodAura（头顶光环颜色）和矢量精灵本身的姿态表达
  // drawMoodExpression 函数保留但不调用，避免破坏其他依赖

  // commit 25 P3-3：工作进度条（busy 时头顶细条）
  drawWorkProgress(emp, p, size);

  // commit 17：busy 时头上画工作图标
  drawActionIcon(emp, p, size);

  // commit 19 P0-2：技能徽章
  if (emp.skills && emp.skills.length > 0) {
    drawSkillBadge(p, size, emp.skills.length);
  }

  // commit 28：行为标签 + 粒子效果
  if (emp.alive !== false) {
    drawBehaviorLabel(emp, p, size);
    emitBehaviorParticles(emp, p, size);
  }

  // commit 36：微表情层（开心/困倦/专注/害羞等短暂表情）
  if (emp.alive !== false && polishSettings.microExpr) {
    drawMicroExpression(emp, p, size);
  }

  // commit 37：Agent 工具调用状态图标（头顶齿轮/沙漏/勾/感叹号）
  if (emp.alive !== false) {
    drawAgentWorkIcon(emp, p, size);
  }

  // commit 36：悬停描边（鼠标悬停时 1px 淡色描边）
  if (emp._hover && emp.alive !== false) {
    drawHoverOutline(p, size, emp.illness ? '#ff8080' : '#d4a574');
  }

  // commit 36：点击缩放反馈（被点击的员工短暂缩放）
  if (emp._clickPulse && emp.alive !== false) {
    drawClickPulse(emp, p, size);
  }

  // commit 34：疾病图标 + 打喷嚏粒子
  if (emp.alive !== false && emp.illness) {
    drawIllnessIcon(emp, p, size);
    emitSneezeParticles(emp, p, size);
  }

  // commit 41：员工名牌 —— 常驻发光气泡 + 小尾巴指向角色
  // 白底深字，hover 时多显示能量/健康
  // commit 43：底色改为物种专属深蓝（nameTag），文字改暖白
  {
    const nameText = (emp.name || '').split('·')[1] || (emp.name || '');
    const detailText = emp._hover
      ? '  E:' + (emp.energy||0).toFixed(0) + ' H:' + (emp.health||0).toFixed(0)
      : '';
    const fullText = nameText + detailText;
    // 字号：基于 zoom 自适应，最小 11px
    const fontSize = Math.max(11, 12 * view.zoom);
    ctx.font = '600 ' + fontSize + 'px "Fraunces", serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const padX = 8;
    const padY = 4;
    const textW = ctx.measureText(fullText).width;
    const bubbleW = textW + padX * 2;
    const bubbleH = fontSize + padY * 2;
    // 气泡位置：员工头顶
    const bx = p.x;
    const by = p.y - size - 14;
    // 物种专属深蓝底色（兜底 #0B1A33）
    const colors = SPECIES_COLORS[emp.species] || {};
    const tagBg = colors.nameTag || '#0B1A33';
    const tagFill = hexToRgba(tagBg, 0.96);
    // 气泡尾巴（小三角形指向员工头顶）
    ctx.fillStyle = tagFill;
    ctx.beginPath();
    ctx.moveTo(bx - 4, by + bubbleH / 2);
    ctx.lineTo(bx + 4, by + bubbleH / 2);
    ctx.lineTo(bx, by + bubbleH / 2 + 6);
    ctx.closePath();
    ctx.fill();
    // 气泡底板（深蓝 + 琥珀描边 + 投影）
    ctx.save();
    ctx.shadowColor = 'rgba(0, 0, 0, 0.5)';
    ctx.shadowBlur = 6;
    ctx.shadowOffsetY = 2;
    ctx.fillStyle = tagFill;
    // 圆角矩形
    const rx = bx - bubbleW / 2;
    const ry = by - bubbleH / 2;
    const r = 6;
    ctx.beginPath();
    ctx.moveTo(rx + r, ry);
    ctx.lineTo(rx + bubbleW - r, ry);
    ctx.quadraticCurveTo(rx + bubbleW, ry, rx + bubbleW, ry + r);
    ctx.lineTo(rx + bubbleW, ry + bubbleH - r);
    ctx.quadraticCurveTo(rx + bubbleW, ry + bubbleH, rx + bubbleW - r, ry + bubbleH);
    ctx.lineTo(rx + r, ry + bubbleH);
    ctx.quadraticCurveTo(rx, ry + bubbleH, rx, ry + bubbleH - r);
    ctx.lineTo(rx, ry + r);
    ctx.quadraticCurveTo(rx, ry, rx + r, ry);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
    // 琥珀描边
    ctx.strokeStyle = 'rgba(212, 165, 116, 0.7)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(rx + r, ry);
    ctx.lineTo(rx + bubbleW - r, ry);
    ctx.quadraticCurveTo(rx + bubbleW, ry, rx + bubbleW, ry + r);
    ctx.lineTo(rx + bubbleW, ry + bubbleH - r);
    ctx.quadraticCurveTo(rx + bubbleW, ry + bubbleH, rx + bubbleW - r, ry + bubbleH);
    ctx.lineTo(rx + r, ry + bubbleH);
    ctx.quadraticCurveTo(rx, ry + bubbleH, rx, ry + bubbleH - r);
    ctx.lineTo(rx, ry + r);
    ctx.quadraticCurveTo(rx, ry, rx + r, ry);
    ctx.closePath();
    ctx.stroke();
    // 文字（暖白色，深蓝底对比）
    ctx.fillStyle = '#F5EDD8';
    ctx.fillText(fullText, bx, by);
  }

  // commit 42：员工路过同事时触发对话气泡（随机概率，避免刷屏）
  if (emp.alive !== false && emp._walking && Math.random() < 0.008) {
    // 找最近的同事（距离 < 3 格）
    for (const other of employees) {
      if (other === emp || other.alive === false) continue;
      if (other._wx == null || other._wy == null) continue;
      const ddx = other._wx - emp._wx;
      const ddy = other._wy - emp._wy;
      const dd = Math.sqrt(ddx * ddx + ddy * ddy);
      if (dd < 3) {
        // 触发对话气泡
        const phrases = {
          'deer': ['嗯……今天的光线很温柔。', '我在想一个老问题。', '树洞里有回声。'],
          'squirrel': ['嘿！要不要看我的橡果？', '代码写完了！嗷！', '我藏了好多坚果！'],
          'butterfly': ['这片色彩真美~', '让我画下这一刻。', '风里有花香。'],
          'fox': ['哼，又来打扰我？', '我找到了一个漏洞~', '小心点，我在测试。'],
          'hedgehog': ['……（默默点头）', '别靠近我。', '我在警戒。'],
          'beaver': ['木头！我要木头！', '大坝快好了！', '干活干活！'],
          'raven': ['……（沉默）', '我记得一切。', '档案室很安静。'],
          'hare': ['哇！你吓到我了！', '我要跑快点！', '怀表在滴答响……'],
          'badger': ['挖！继续挖！', '地下有宝藏。', '别挡我的路。'],
          'lark': ['啦啦啦~♪', '你知道吗？听说……', '今天天气真好！'],
          'kite': ['远处有动静。', '我看到了全局。', '风向我诉说。'],
        };
        const list = phrases[emp.species] || ['……'];
        const text = list[Math.floor(Math.random() * list.length)];
        activeBubbles.push({
          id: 'passby-' + Date.now() + '-' + Math.random(),
          speaker: emp.name || emp.species,
          text: text,
          target: other.name || '同事',
          expireTs: Date.now() + 3500,
        });
        if (activeBubbles.length > 10) activeBubbles.shift();
        break;  // 一次只触发一个
      }
    }
  }
}

// commit 19 P0-1：情绪光环（夜森林配色）
// ≥70 苔藓绿，50-70 琥珀，30-50 枯叶橙，<30 暗玫红
function drawMoodAura(p, size, moodScore) {
  // commit 33：升级为基于情感向量的多色光环
  // 先尝试从 atmosphereData 找到该员工的情感光环数据
  // atmosphereData.auras 是 [{name, species, emo, intensity, secondary_emo, ...}, ...]
  const auraData = (atmosphereData.auras || []).find(a =>
    a.species === currentEmpSpecies);
  if (auraData) {
    drawEmotionAura(p, size, auraData);
    return;
  }
  // 降级：用旧版 moodScore 单色光环
  const auraColor = moodScore >= 70 ? 'rgba(107,143,113,.32)'
                  : moodScore >= 50 ? 'rgba(212,165,116,.30)'
                  : moodScore >= 30 ? 'rgba(201,123,90,.32)'
                  : 'rgba(180,90,80,.40)';
  const r = Math.max(8, size * 0.55);
  ctx.save();
  const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r);
  grad.addColorStop(0, auraColor);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, r, r * 0.4, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// 当前正在绘制的员工物种（drawEmployee 入口设置，供 drawMoodAura 查找光环数据）
let currentEmpSpecies = '';

// commit 33：基于情感向量的多色光环
// 主情感 = 光环主色，次情感 = 边缘渐变色
// 焦虑（anxiety）会有脉冲效果
function drawEmotionAura(p, size, auraData) {
  const intensity = auraData.intensity || 0.5;
  const radius = Math.max(8, size * (0.55 + intensity * 0.3));
  const emo = auraData.emo || 'joy';
  const secEmo = auraData.secondary_emo;
  const secIntensity = auraData.secondary_intensity || 0;

  // 焦虑脉冲：频率随强度加快
  let pulseAlpha = 1.0;
  if (auraData.anxiety_pulse) {
    const t = performance.now() / 1000;
    const freq = 2 + intensity * 3;  // 2-5 Hz
    pulseAlpha = 0.5 + Math.sin(t * freq * Math.PI * 2) * 0.5;
  }

  ctx.save();
  const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius);
  // 主色在中心
  grad.addColorStop(0, auraData.color || 'rgba(200,200,200,0.3)');
  // 次色在 0.6 处（如果有）
  if (secEmo && secIntensity > 0) {
    const secColor = emotionToRgba(secEmo, secIntensity * 0.6);
    grad.addColorStop(0.6, secColor);
  }
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.globalAlpha = pulseAlpha;
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, radius, radius * 0.4, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

// 情感 → rgba 颜色（与后端 atmosphere_system.EMOTION_COLORS 对应）
function emotionToRgba(emo, intensity) {
  const colors = {
    joy: [255, 196, 87],
    sadness: [130, 170, 230],
    anxiety: [160, 160, 170],
    contentment: [140, 210, 150],
    loneliness: [180, 180, 200],
    curiosity: [200, 150, 220],
  };
  const c = colors[emo] || [200, 200, 200];
  const alpha = Math.max(0, Math.min(1, intensity * 0.45));
  return `rgba(${c[0]},${c[1]},${c[2]},${alpha.toFixed(3)})`;
}

// commit 25 P3-2：情绪表情
// 在精灵嘴部位置画嘴角弧线：≥70 上翘笑，50-70 平直，30-50 微下垂，<30 下垂悲伤
// 精灵嘴部在 64x64 中的 (32, 22)，换算到主画布坐标
function drawMoodExpression(p, size, moodScore) {
  // 嘴部主画布坐标
  const mx = p.x;
  const my = p.y - size + size * 22 / 64;
  const w = size * 0.10;  // 嘴宽
  ctx.save();
  ctx.strokeStyle = 'rgba(20, 15, 10, 0.85)';
  ctx.lineWidth = Math.max(0.8, size * 0.018);
  ctx.lineCap = 'round';
  ctx.beginPath();
  if (moodScore >= 70) {
    // 笑：嘴角上翘的弧
    ctx.moveTo(mx - w, my);
    ctx.quadraticCurveTo(mx, my + w * 0.7, mx + w, my);
  } else if (moodScore >= 50) {
    // 平：直线
    ctx.moveTo(mx - w, my);
    ctx.lineTo(mx + w, my);
  } else if (moodScore >= 30) {
    // 微下垂
    ctx.moveTo(mx - w, my + w * 0.2);
    ctx.quadraticCurveTo(mx, my - w * 0.1, mx + w, my + w * 0.2);
  } else {
    // 悲伤：嘴角下垂
    ctx.moveTo(mx - w, my + w * 0.3);
    ctx.quadraticCurveTo(mx, my - w * 0.6, mx + w, my + w * 0.3);
  }
  ctx.stroke();
  ctx.restore();
}

// commit 25 P3-3：工作进度条
// busy 时在精灵顶部画一个细长进度条（0-100% 循环，模拟工作进度）
function drawWorkProgress(emp, p, size) {
  if (!emp.busy) return;
  // 用 emp._workStart 记录开始时间，10 秒一循环
  if (emp._workStart == null) emp._workStart = performance.now();
  const elapsed = (performance.now() - emp._workStart) / 1000;
  // 8 秒一个工作循环，进度从 0 到 1
  const cycle = 8;
  const progress = (elapsed % cycle) / cycle;
  // 条形参数
  const barW = size * 0.5;
  const barH = Math.max(2, size * 0.05);
  const bx = p.x - barW / 2;
  const by = p.y - size - 2;
  ctx.save();
  // 背景
  ctx.fillStyle = 'rgba(10, 15, 12, 0.7)';
  ctx.fillRect(bx, by, barW, barH);
  // 进度填充（琥珀色渐变）
  const grad = ctx.createLinearGradient(bx, by, bx + barW, by);
  grad.addColorStop(0, '#D4A574');
  grad.addColorStop(1, '#FFE4B5');
  ctx.fillStyle = grad;
  ctx.fillRect(bx, by, barW * progress, barH);
  // 描边
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.5)';
  ctx.lineWidth = 0.5;
  ctx.strokeRect(bx, by, barW, barH);
  ctx.restore();
}

// commit 19 P0-2：技能徽章
// 在员工脚下画一个小金色圆 + 数字
function drawSkillBadge(p, size, count) {
  const bx = p.x + size * 0.35;
  const by = p.y - 2;
  const r = Math.max(6, size * 0.13);
  ctx.save();
  ctx.fillStyle = '#D4A574';
  ctx.beginPath();
  ctx.arc(bx, by, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = '#0a0f0c';
  ctx.font = '600 ' + Math.max(8, r * 1.2) + 'px "JetBrains Mono", monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(String(count), bx, by + 1);
  ctx.restore();
}

// commit 28：行为标签 + 粒子效果
// 在精灵头顶画一个小标签显示当前特有行为名（如"藏坚果"）
function drawBehaviorLabel(emp, p, size) {
  if (!emp.current_behavior_label) return;
  const text = emp.current_behavior_label;
  const fontSize = Math.max(10, 11 * view.zoom);
  ctx.save();
  ctx.font = '500 ' + fontSize + 'px "Fraunces", serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const tw = ctx.measureText(text).width;
  const padX = 6, padY = 3;
  const bx = p.x;
  const by = p.y - size - 10;
  // 标签背景（夜森林琥珀）
  ctx.fillStyle = 'rgba(20, 28, 22, 0.88)';
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.6)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.rect(bx - tw/2 - padX, by - fontSize/2 - padY, tw + padX*2, fontSize + padY*2);
  ctx.fill();
  ctx.stroke();
  // 文字
  ctx.fillStyle = '#E8E4D8';
  ctx.fillText(text, bx, by + 1);
  ctx.restore();
}

// 行为粒子配置表：每种粒子有颜色、大小、运动模式
const BEHAVIOR_PARTICLE_CONFIG = {
  nut_bury:       {color: '#85603F', size: 3, type: 'dot',     vy: 30,  vx: 0,   life: 0.6},
  panic_sweat:    {color: '#7AB8E5', size: 2, type: 'dot',     vy: -20, vx: 0,   life: 0.8},
  rainbow_tail:   {color: 'rainbow', size: 3, type: 'dot',     vy: 5,   vx: 0,   life: 1.0},
  smirk:          {color: '#C97B5A', size: 2, type: 'dot',     vy: -10, vx: 5,   life: 0.5},
  spy_glasses:    {color: '#2A3038', size: 2, type: 'dot',     vy: 0,   vx: 8,   life: 0.7},
  snow_puff:      {color: '#FFFFFF', size: 3, type: 'snow',    vy: -15, vx: 0,   life: 1.2},
  feather_shine:  {color: '#E8E4D8', size: 2, type: 'firefly', vy: -5,  vx: 0,   life: 1.5},
  sparkle:        {color: '#D4A574', size: 2, type: 'firefly', vy: -8,  vx: 0,   life: 1.0},
  story_bubble:   {color: '#9B88B0', size: 3, type: 'dot',     vy: -12, vx: 0,   life: 1.5},
  feather_drop:   {color: '#7A6E5C', size: 3, type: 'leaf',    vy: 10,  vx: 0,   life: 1.5},
  listen_bubble:  {color: '#9B88B0', size: 2, type: 'dot',     vy: -3,  vx: 0,   life: 1.0},
};

// 在精灵位置发射行为粒子（每帧调用，自带节流：每 ~150ms 发 1 个）
function emitBehaviorParticles(emp, p, size) {
  if (!emp.behavior_particles) return;
  const cfg = BEHAVIOR_PARTICLE_CONFIG[emp.behavior_particles];
  if (!cfg) return;
  // 节流：用 emp._behParticleTS 记录上次发射时间
  const now = performance.now();
  if (!emp._behParticleTS) emp._behParticleTS = 0;
  if (now - emp._behParticleTS < 150) return;
  emp._behParticleTS = now;
  // 在精灵头顶随机位置发射 1 个粒子
  const ox = (Math.random() - 0.5) * size * 0.6;
  const oy = -Math.random() * size * 0.4;
  // 彩虹尾巴：每次随机色
  let color = cfg.color;
  if (color === 'rainbow') {
    const palette = ['#E57373', '#FFB74D', '#FFF176', '#81C784', '#64B5F6', '#9575CD'];
    color = palette[Math.floor(Math.random() * palette.length)];
  }
  spawnParticle({
    x: p.x + ox,
    y: p.y - size + oy,
    vx: cfg.vx + (Math.random() - 0.5) * 4,
    vy: cfg.vy + (Math.random() - 0.5) * 4,
    life: cfg.life,
    color: color,
    size: cfg.size,
    type: cfg.type,
  });
}

// ==================== commit 15：性能优化 ====================
// 零基础读者可以这样理解：
// 1) 静态地图预渲染：把所有"不会动"的瓦片和 zone 标签一次性画到一张
//    离屏画布 worldCanvas，每帧只 drawImage 复制，省掉 4800 次瓦片绘制。
// 2) 粒子池化：预先建 200 个粒子对象的池子，要用时 spawnParticle 取出，
//    用完 active=false 归还。避免每次都 new 对象触发 GC。
// 3) 帧节流：精灵帧动画从 60fps 降到 12fps（每 80ms 推一帧），节省 5/6 重画。

let worldCanvas = null;          // 离屏预渲染画布
let worldOffsetX = 0;            // worldCanvas 内 isoToScreen 的 view 偏移
let worldOffsetY = 0;

const PARTICLE_POOL_SIZE = 200;  // 粒子池大小
const particlePool = [];         // 粒子对象池

function initParticlePool() {
  // 预分配 PARTICLE_POOL_SIZE 个粒子对象，初始 active=false
  // commit 24：粒子扩展字段 type/rotation/rotSpeed 用于不同渲染
  for (let i = 0; i < PARTICLE_POOL_SIZE; i++) {
    particlePool.push({
      active: false, x: 0, y: 0, vx: 0, vy: 0,
      life: 0, maxLife: 1, color: '#D4A574', size: 2,
      type: 'dot', rotation: 0, rotSpeed: 0,
    });
  }
}

// spawnParticle：从池里取一个空闲粒子并激活，池满返回 null
// 用法示例（commit 16 投喂）：
//   spawnParticle({x: 200, y: 150, vx: 0, vy: -20, life: 0.6, color: '#FFB74D', size: 3});
// commit 24 新增：type（'rain'/'snow'/'firefly'/'fog'/'sunbeam'/'leaf'/'petal'/'dot'）
//              rotation/rotSpeed（旋转动画用）
function spawnParticle(props) {
  for (let i = 0; i < particlePool.length; i++) {
    const p = particlePool[i];
    if (p.active) continue;
    p.active = true;
    p.x = props.x || 0;
    p.y = props.y || 0;
    p.vx = props.vx || 0;
    p.vy = props.vy || 0;
    p.life = props.life || 1;
    p.maxLife = p.life;
    p.color = props.color || '#D4A574';
    p.size = props.size || 2;
    p.type = props.type || 'dot';
    p.rotation = props.rotation || 0;
    p.rotSpeed = props.rotSpeed || (Math.random() - 0.5) * 4;
    return p;
  }
  return null;
}

function updateActiveParticles(dt) {
  // dt 单位秒。推进所有激活粒子的位置、生命、旋转
  // 不同粒子类型有特殊运动：
  //   萤火虫：正弦摆动 + 闪烁
  //   雪/花瓣/落叶：水平摆动 + 旋转
  //   雾：水平漂移，无垂直
  for (let i = 0; i < particlePool.length; i++) {
    const p = particlePool[i];
    if (!p.active) continue;
    p.x += p.vx * dt;
    p.y += p.vy * dt;
    // 萤火虫/落叶/雪/花瓣：加摆动
    if (p.type === 'firefly') {
      p.x += Math.sin(p.life * 3) * 0.5;
      p.y += Math.cos(p.life * 2) * 0.3;
    } else if (p.type === 'snow' || p.type === 'leaf' || p.type === 'petal') {
      p.x += Math.sin(p.life * 2 + p.rotation) * 0.8;
      p.rotation += p.rotSpeed * dt;
    }
    p.life -= dt;
    // 出屏剔除
    if (p.life <= 0 || p.y > canvas.height + 50 || p.x < -100 || p.x > canvas.width + 100) {
      p.active = false;
    }
  }
}

function drawActiveParticles() {
  // commit 24：根据 type 用不同方式绘制
  for (let i = 0; i < particlePool.length; i++) {
    const p = particlePool[i];
    if (!p.active) continue;
    const lifeRatio = Math.max(0, p.life / p.maxLife);

    if (p.type === 'rain') {
      // 雨：斜线段
      // commit 41：室内 zone 不渲染雨滴（地图外正常渲染）
      const _t = screenToTile(p.x, p.y);
      const _z = _t && findZone(_t.ix, _t.iy);
      if (_z && _z.isIndoor) continue;
      ctx.globalAlpha = 0.6 * lifeRatio;
      ctx.strokeStyle = p.color;
      ctx.lineWidth = p.size;
      ctx.beginPath();
      ctx.moveTo(p.x, p.y);
      ctx.lineTo(p.x - 3, p.y + 10);
      ctx.stroke();
    } else if (p.type === 'snow') {
      // 雪：旋转的小六角星
      // commit 41：室内 zone 不渲染雪
      const _t = screenToTile(p.x, p.y);
      const _z = _t && findZone(_t.ix, _t.iy);
      if (_z && _z.isIndoor) continue;
      ctx.globalAlpha = 0.85 * lifeRatio;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
      // 中心高光
      ctx.globalAlpha = lifeRatio;
      ctx.fillStyle = '#FFFFFF';
      ctx.beginPath();
      ctx.arc(p.x - p.size * 0.3, p.y - p.size * 0.3, p.size * 0.4, 0, Math.PI * 2);
      ctx.fill();
    } else if (p.type === 'firefly') {
      // 萤火虫：发光球 + 闪烁
      const blink = 0.5 + Math.sin(p.life * 6) * 0.5;
      ctx.globalAlpha = blink * lifeRatio;
      // 外层光晕（径向渐变）
      const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 4);
      grad.addColorStop(0, p.color);
      grad.addColorStop(0.3, 'rgba(212, 165, 116, 0.5)');
      grad.addColorStop(1, 'rgba(212, 165, 116, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * 4, 0, Math.PI * 2);
      ctx.fill();
      // 中心亮点
      ctx.globalAlpha = blink * lifeRatio;
      ctx.fillStyle = '#FFE4B5';
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    } else if (p.type === 'fog') {
      // 雾：大柔圆
      ctx.globalAlpha = 0.5 * lifeRatio;
      const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size);
      grad.addColorStop(0, p.color);
      grad.addColorStop(1, 'rgba(168, 160, 149, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    } else if (p.type === 'sunbeam') {
      // 光斑：柔光金点
      ctx.globalAlpha = 0.7 * lifeRatio;
      const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 3);
      grad.addColorStop(0, p.color);
      grad.addColorStop(1, 'rgba(212, 165, 116, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size * 3, 0, Math.PI * 2);
      ctx.fill();
    } else if (p.type === 'leaf') {
      // 落叶：旋转的椭圆叶片
      ctx.globalAlpha = 0.9 * lifeRatio;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.ellipse(0, 0, p.size * 1.5, p.size * 0.7, 0, 0, Math.PI * 2);
      ctx.fill();
      // 叶脉
      ctx.strokeStyle = 'rgba(60, 40, 20, 0.5)';
      ctx.lineWidth = 0.4;
      ctx.beginPath();
      ctx.moveTo(-p.size * 1.5, 0);
      ctx.lineTo(p.size * 1.5, 0);
      ctx.stroke();
      ctx.restore();
    } else if (p.type === 'petal') {
      // 花瓣：旋转的小圆瓣
      ctx.globalAlpha = 0.85 * lifeRatio;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rotation);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.ellipse(0, 0, p.size, p.size * 0.6, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    } else {
      // 默认：实心圆
      ctx.globalAlpha = lifeRatio;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.globalAlpha = 1;
}

function isoToWorld(ix, iy) {
  // worldCanvas 内部坐标（zoom=1，偏移 worldOffsetX/Y）
  return {
    x: (ix - iy) * TILE_W / 2 + worldOffsetX,
    y: (ix + iy) * TILE_H / 2 + worldOffsetY,
  };
}

function prerenderWorld() {
  // 计算 80×60 地图在 zoom=1 下的 isoToScreen 边界框
  // 留出墙壁高度 + zone label 空间
  const wallH = TILE_H * 12;  // 墙壁高度（再翻一倍，营造高大围合感）
  const minX = -(MAP_H - 1) * TILE_W / 2;
  const maxX = (MAP_W - 1) * TILE_W / 2;
  const minY = 0;
  const maxY = (MAP_W + MAP_H - 2) * TILE_H / 2;
  const padX = 80, padY = 80;  // 给 zone label + 墙壁留空间
  const w = Math.ceil(maxX - minX) + padX * 2;
  const h = Math.ceil(maxY - minY) + padY * 2 + wallH;  // 顶部加墙高
  worldOffsetX = -minX + padX;
  worldOffsetY = -minY + padY + wallH;  // 整体下移，给墙留空间
  if (!worldCanvas) worldCanvas = document.createElement('canvas');
  if (worldCanvas.width !== w || worldCanvas.height !== h) {
    worldCanvas.width = w;
    worldCanvas.height = h;
  }
  const wc = worldCanvas.getContext('2d');
  wc.clearRect(0, 0, w, h);
  // 画瓦片（按 sum=ix+iy 升序保证遮挡正确）
  for (let sum = 0; sum < MAP_W + MAP_H; sum++) {
    for (let ix = 0; ix <= sum; ix++) {
      const iy = sum - ix;
      if (ix >= MAP_W || iy >= MAP_H) continue;
      drawTileTo(wc, ix, iy);
    }
  }
  // commit 41：zone 外画深绿森林迷雾（砍掉无限地砖感）
  drawForestMist(wc);
  // commit 50-5：在森林里撒装饰物（树/石/灯/箱/花盆）
  drawDecorations(wc);
  // commit 41：先画地毯和栅栏作为底层，再画标签和装饰品
  for (const zone of ZONES) {
    drawZoneCarpet(wc, zone);
  }
  for (const zone of ZONES) {
    drawZoneFence(wc, zone);
  }
  for (const zone of ZONES) {
    drawZoneTrees(wc, zone);
  }
  // 画 zone label
  for (const zone of ZONES) {
    drawZoneLabelTo(wc, zone);
  }
  // 画 zone 装饰品（commit 23：每个工位的家具/工具/植物）
  for (const zone of ZONES) {
    drawZoneDecor(wc, zone);
  }
  // commit 29：画微气候色块（极淡）
  drawMicroclimateOverlays(wc);
  // 画四周白色墙壁（commit 22）
  drawWalls(wc);
}

// commit 29：微气候区域色块（极淡，可开关）
let showMicroclimate = true;  // 默认显示
function drawMicroclimateOverlays(ctx) {
  if (!showMicroclimate) return;
  // 微气候 zone 配色（极淡半透明）
  const zoneColors = {
    beaver:    'rgba(80, 140, 200, 0.06)',   // 水坝机房：蓝（湿）
    hare:      'rgba(200, 220, 255, 0.10)',  // 算盘雪原：白蓝（冷）
    butterfly: 'rgba(180, 220, 150, 0.08)',  // 花房：绿（植物）
    deer:      'rgba(220, 200, 150, 0.05)',  // 大厅：暖黄（舒适）
  };
  for (const zone of ZONES) {
    const color = zoneColors[zone.id];
    if (!color) continue;
    // 画 zone 中心瓦片（中心 ±2 格范围）
    const cx = zone.x, cy = zone.y;
    for (let dx = -2; dx <= 2; dx++) {
      for (let dy = -2; dy <= 2; dy++) {
        const ix = cx + dx, iy = cy + dy;
        if (ix < 0 || ix >= MAP_W || iy < 0 || iy >= MAP_H) continue;
        const p = isoToScreenOn(ctx.canvas, ix, iy);
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(p.x + TILE_W/2, p.y + TILE_H/2);
        ctx.lineTo(p.x, p.y + TILE_H);
        ctx.lineTo(p.x - TILE_W/2, p.y + TILE_H/2);
        ctx.closePath();
        ctx.fill();
      }
    }
  }
}
function isoToScreenOn(canvas, ix, iy) {
  // 辅助：在 prerendered canvas 坐标系下转换
  const x = (ix - iy) * TILE_W / 2 + worldOffsetX;
  const y = (ix + iy) * TILE_H / 2 + worldOffsetY;
  return { x, y };
}

// ==================== commit 23：工位装饰品 ====================
// 零基础读者可以这样理解：
// 每个 zone（功能区）不只是空地，里面会摆上对应的家具/工具/装饰物：
// 鼠·代码区放显示器+键盘，狐·测试区放服务器机柜，
// 食堂放长桌+餐盘，休息区放沙发+落地灯，等等。
// 装饰品是 2.5D 等距视角画的"小立方体组合"，用 zone 色调的稍亮版本上色，
// 让装饰物从瓦片背景中浮出但又不喧宾夺主。

// 辅助：在等距坐标 (ix, iy) 画一个 2.5D 立方体（顶面+右面+左面）
function drawIsoBox(ctx, ix, iy, w, h, height, topColor, rightColor, leftColor, edgeColor) {
  // (ix, iy) 是立方体底部中心的等距坐标
  // w, h 是底面菱形的半宽半高，height 是立方体高度
  const p = isoToWorld(ix, iy);
  const baseY = p.y;  // 底面中心 Y
  // 顶面四角
  const topL = { x: p.x - w, y: baseY - height };
  const topR = { x: p.x + w, y: baseY - height };
  const topT = { x: p.x,     y: baseY - height - h };
  const topB = { x: p.x,     y: baseY - height + h };
  // 底面四角
  const botL = { x: p.x - w, y: baseY };
  const botR = { x: p.x + w, y: baseY };

  // 左面（梯形：topL, topB, botR... 不对，应该是 topL-topB-botB-botL）
  // 修正：左面 = topT-topL-botL ？ 这里要重新想清楚等距菱形立方体面
  // 等距立方体可见三面：顶面（菱形）、右面（向右下）、左面（向左下）
  // 顶面四角：topT(上), topR(右), topB(下), topL(左)
  // 右面 = topR, topB, botR （右面是 topR-topB-botR 三角形？不对，是四边形 topR-topB-botB'-botR')
  // 简化：用立方体高度向下投影
  // 顶面菱形：topT, topR, topB, topL（在 baseY - height 高度）
  // 右面：topR → topB → (topB.x, topB.y + height) → (topR.x, topR.y + height)
  // 左面：topL → topB → (topB.x, topB.y + height) → (topL.x, topL.y + height)

  // 左面
  ctx.fillStyle = leftColor;
  ctx.beginPath();
  ctx.moveTo(topL.x, topL.y);
  ctx.lineTo(topB.x, topB.y);
  ctx.lineTo(topB.x, topB.y + height);
  ctx.lineTo(topL.x, topL.y + height);
  ctx.closePath();
  ctx.fill();
  if (edgeColor) { ctx.strokeStyle = edgeColor; ctx.lineWidth = 0.5; ctx.stroke(); }

  // 右面
  ctx.fillStyle = rightColor;
  ctx.beginPath();
  ctx.moveTo(topR.x, topR.y);
  ctx.lineTo(topB.x, topB.y);
  ctx.lineTo(topB.x, topB.y + height);
  ctx.lineTo(topR.x, topR.y + height);
  ctx.closePath();
  ctx.fill();
  if (edgeColor) { ctx.strokeStyle = edgeColor; ctx.lineWidth = 0.5; ctx.stroke(); }

  // 顶面（菱形）
  ctx.fillStyle = topColor;
  ctx.beginPath();
  ctx.moveTo(topT.x, topT.y);
  ctx.lineTo(topR.x, topR.y);
  ctx.lineTo(topB.x, topB.y);
  ctx.lineTo(topL.x, topL.y);
  ctx.closePath();
  ctx.fill();
  if (edgeColor) { ctx.strokeStyle = edgeColor; ctx.lineWidth = 0.5; ctx.stroke(); }
}

// 辅助：画一根等距圆柱（顶面椭圆 + 矩形侧面 + 底面椭圆）
function drawIsoCylinder(ctx, ix, iy, radius, height, topColor, sideColor, edgeColor) {
  const p = isoToWorld(ix, iy);
  const baseY = p.y;
  const r = radius;
  const ry = radius * 0.5;  // 椭圆压扁
  // 侧面（矩形 + 底部半椭圆）
  ctx.fillStyle = sideColor;
  ctx.beginPath();
  ctx.moveTo(p.x - r, baseY - height);
  ctx.lineTo(p.x + r, baseY - height);
  ctx.lineTo(p.x + r, baseY);
  ctx.bezierCurveTo(p.x + r, baseY + ry, p.x - r, baseY + ry, p.x - r, baseY);
  ctx.closePath();
  ctx.fill();
  if (edgeColor) { ctx.strokeStyle = edgeColor; ctx.lineWidth = 0.5; ctx.stroke(); }
  // 顶面椭圆
  ctx.fillStyle = topColor;
  ctx.beginPath();
  ctx.ellipse(p.x, baseY - height, r, ry, 0, 0, Math.PI * 2);
  ctx.fill();
  if (edgeColor) { ctx.strokeStyle = edgeColor; ctx.lineWidth = 0.5; ctx.stroke(); }
}

// 辅助：把 hex 色按 amount 调亮（正数）或调暗（负数），返回新 hex
function shadeHex(hex, amount) {
  const h = hex.replace('#', '');
  const r = Math.max(0, Math.min(255, parseInt(h.substr(0, 2), 16) + Math.round(amount * 255)));
  const g = Math.max(0, Math.min(255, parseInt(h.substr(2, 2), 16) + Math.round(amount * 255)));
  const b = Math.max(0, Math.min(255, parseInt(h.substr(4, 2), 16) + Math.round(amount * 255)));
  return '#' + r.toString(16).padStart(2, '0') + g.toString(16).padStart(2, '0') + b.toString(16).padStart(2, '0');
}

// commit 43：hex → rgba 字符串（用于名牌底色半透明化）
function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '');
  const r = parseInt(h.substr(0, 2), 16);
  const g = parseInt(h.substr(2, 2), 16);
  const b = parseInt(h.substr(4, 2), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

// 主：根据 zone id 画对应装饰品
function drawZoneDecor(ctx, zone) {
  // 优先用 PNG 装饰品（与 sprite 同画风），失败回退到矢量 isometric
  if (zoneDecoReady(zone.id)) {
    drawZoneDecorPng(ctx, zone);
    return;
  }
  drawZoneDecorVector(ctx, zone);
}

// PNG 装饰品渲染：3 个 32x32 PNG 按左中右排布在 zone 中心
// 与 sprite 同画风：1px 描边、低饱和度深色、琥珀金强调
function drawZoneDecorPng(ctx, zone) {
  const [x1, y1, x2, y2] = zone.rect;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const wTiles = x2 - x1;
  const hTiles = y2 - y1;
  // 装饰品大小：基于 zone 宽度自适应（最小 zone 也要装得下 3 个）
  const decoSize = Math.max(56, Math.min(88, wTiles * 5.5));
  // commit 41：工位布局 —— 主道具在中心偏后，两个小道具在前方左右两侧
  // 模仿真实工位：桌子在中间，左右各放配套小物件
  const offsets = [
    {dx: -wTiles * 0.22, dy: hTiles * 0.12, scale: 0.85},  // 左前小道具
    {dx: 0,              dy: -hTiles * 0.08, scale: 1.0},   // 中心主道具（最大）
    {dx: wTiles * 0.22,  dy: hTiles * 0.12, scale: 0.85},   // 右前小道具
  ];
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  for (let i = 0; i < 3; i++) {
    const img = decoPngs[zone.id + '_' + (i + 1)];
    if (!img) continue;
    const p = isoToWorld(cx + offsets[i].dx, cy + offsets[i].dy);
    const sz = decoSize * (offsets[i].scale || 1.0);
    // 锚点：底部中心（与 sprite 一致）
    ctx.drawImage(img, p.x - sz / 2, p.y - sz, sz, sz);
  }
  ctx.restore();
}

// 矢量 isometric 装饰品（PNG 加载失败时的 fallback）
function drawZoneDecorVector(ctx, zone) {
  const [x1, y1, x2, y2] = zone.rect;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const w = x2 - x1;
  const h = y2 - y1;
  // 装饰物配色：基于 zone 色调亮/调暗
  const base = zone.color;
  const top   = shadeHex(base, 0.28);   // 顶面亮
  const right = shadeHex(base, -0.05);  // 右面稍暗
  const left  = shadeHex(base, -0.18);  // 左面更暗
  const edge  = 'rgba(212, 165, 116, 0.22)';
  const accent = '#D4A574';

  // 通用：每个 zone 内画 1-3 个装饰物，位置在 zone 内偏移
  switch (zone.id) {
    // ---------- 11 物种岗位 ----------
    case 'squirrel':  // 鼠·栗壳代码区：显示器 + 键盘
      drawIsoBox(ctx, cx - 2, cy - 1, 8, 4, 5, top, right, left, edge);   // 显示器底座
      drawIsoBox(ctx, cx - 2, cy - 1, 6, 3, 10, shadeHex(base, 0.5), right, left, edge); // 显示器主体
      ctx.fillStyle = '#7CB8A8';  // 屏幕青绿
      const sp = isoToWorld(cx - 2, cy - 1);
      ctx.fillRect(sp.x - 5, sp.y - 12, 10, 7);
      drawIsoBox(ctx, cx - 2, cy + 1.5, 7, 3, 1.5, shadeHex(base, 0.15), right, left, edge); // 键盘
      break;

    case 'fox':  // 狐·赤谋测试区：服务器机柜
      for (let i = -1; i <= 1; i++) {
        drawIsoBox(ctx, cx + i * 2.5, cy, 5, 2.5, 16, top, right, left, edge);
        // 机柜上的指示灯
        const lp = isoToWorld(cx + i * 2.5, cy);
        ctx.fillStyle = i === 0 ? '#C97B5A' : '#6B8F71';
        ctx.fillRect(lp.x - 3, lp.y - 14, 1.5, 1.5);
        ctx.fillRect(lp.x, lp.y - 14, 1.5, 1.5);
        ctx.fillRect(lp.x + 3, lp.y - 14, 1.5, 1.5);
      }
      break;

    case 'hedgehog':  // 猬·针客安全区：盾牌 + 警戒灯
      // 盾牌（菱形立柱）
      drawIsoBox(ctx, cx, cy - 1, 6, 3, 9, shadeHex(base, 0.3), right, left, edge);
      // 盾面上的纹路
      const sp2 = isoToWorld(cx, cy - 1);
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.ellipse(sp2.x, sp2.y - 5, 3, 4, 0, 0, Math.PI * 2);
      ctx.fill();
      // 警戒灯（小圆柱）
      drawIsoCylinder(ctx, cx + 3, cy + 1, 3, 5, '#C97B5A', shadeHex('#C97B5A', -0.2), edge);
      break;

    case 'beaver':  // 狸·大坝构建区：木材堆 + 工具箱
      // 木材堆（三根并排圆木）
      for (let i = -1; i <= 1; i++) {
        drawIsoCylinder(ctx, cx + i * 2.2, cy, 2.5, 7,
          shadeHex('#85603F', 0.15), shadeHex('#85603F', -0.15), edge);
      }
      // 工具箱（小立方体）
      drawIsoBox(ctx, cx + 4, cy + 2, 4, 2, 4, shadeHex(base, 0.2), right, left, edge);
      break;

    case 'butterfly':  // 蝶·绘羽设计台：画架 + 调色盘
      // 画架（瘦高立方体）
      drawIsoBox(ctx, cx - 2, cy, 4, 2, 14, shadeHex(base, 0.35), right, left, edge);
      // 画板（贴在画架上的矩形）
      const ep = isoToWorld(cx - 2, cy);
      ctx.fillStyle = '#E8E4D8';
      ctx.fillRect(ep.x - 4, ep.y - 16, 8, 10);
      ctx.strokeStyle = edge;
      ctx.lineWidth = 0.5;
      ctx.strokeRect(ep.x - 4, ep.y - 16, 8, 10);
      // 调色盘（扁平椭圆）
      drawIsoCylinder(ctx, cx + 3, cy + 1, 4, 1.5, top, right, edge);
      break;

    case 'raven':  // 鸦·黑卷档案室：书架 + 卷轴
      // 书架（高瘦立方体）
      drawIsoBox(ctx, cx - 2, cy, 5, 2.5, 18, shadeHex(base, 0.2), right, left, edge);
      // 书架上的书脊（彩色细条）
      const bp = isoToWorld(cx - 2, cy);
      const bookColors = ['#A67A3F', '#7C5C8C', '#5A8567', '#C97B5A'];
      for (let i = 0; i < 4; i++) {
        ctx.fillStyle = bookColors[i];
        ctx.fillRect(bp.x - 4 + i * 2.5, bp.y - 16, 1.8, 14);
      }
      // 卷轴（横躺圆柱）
      drawIsoCylinder(ctx, cx + 3, cy + 1, 3, 3, '#E8E4D8', '#A8A095', edge);
      break;

    case 'hare':  // 兔·霜耳核算台：算盘 + 账本
      // 算盘框（立方体）
      drawIsoBox(ctx, cx - 1, cy, 7, 3, 8, shadeHex(base, 0.25), right, left, edge);
      // 算盘珠子
      const abp = isoToWorld(cx - 1, cy);
      for (let row = 0; row < 3; row++) {
        for (let col = 0; col < 5; col++) {
          ctx.fillStyle = col % 2 === 0 ? accent : '#C97B5A';
          ctx.beginPath();
          ctx.arc(abp.x - 6 + col * 3, abp.y - 6 + row * 2, 1, 0, Math.PI * 2);
          ctx.fill();
        }
      }
      // 账本（扁平小立方体）
      drawIsoBox(ctx, cx + 4, cy + 1, 3, 1.5, 1.5, '#E8E4D8', '#A8A095', '#A8A095', edge);
      break;

    case 'badger':  // 獾·土工工具间：工具架 + 铲子
      // 工具架（高瘦立方体）
      drawIsoBox(ctx, cx, cy, 4, 2, 14, shadeHex(base, 0.18), right, left, edge);
      // 挂着的铲子（细线 + 小矩形）
      const tp = isoToWorld(cx, cy);
      ctx.strokeStyle = '#A8A095';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(tp.x - 3, tp.y - 13);
      ctx.lineTo(tp.x - 3, tp.y - 4);
      ctx.stroke();
      ctx.fillStyle = '#7A6E5C';
      ctx.fillRect(tp.x - 5, tp.y - 16, 4, 3);  // 铲头
      // 水桶（圆柱）
      drawIsoCylinder(ctx, cx + 4, cy + 1, 3, 5, shadeHex(base, 0.1), right, edge);
      break;

    case 'lark':  // 雀·清音广播台：麦克风 + 音箱
      // 麦克风立柱
      drawIsoCylinder(ctx, cx - 2, cy, 1.5, 14, '#7A6E5C', shadeHex('#7A6E5C', -0.2), edge);
      // 麦克风头（球）
      const mp = isoToWorld(cx - 2, cy);
      ctx.fillStyle = '#4A5560';
      ctx.beginPath();
      ctx.arc(mp.x, mp.y - 14, 3, 0, Math.PI * 2);
      ctx.fill();
      // 音箱（立方体）
      drawIsoBox(ctx, cx + 3, cy, 5, 2.5, 12, shadeHex(base, 0.2), right, left, edge);
      // 音箱喇叭（圆）
      const lp2 = isoToWorld(cx + 3, cy);
      ctx.fillStyle = '#1A201B';
      ctx.beginPath();
      ctx.arc(lp2.x, lp2.y - 8, 2, 0, Math.PI * 2);
      ctx.fill();
      break;

    case 'kite':  // 鸢·天瞰俯瞰台：望远镜 + 地球仪
      // 望远镜支架（三脚架简化为立柱）
      drawIsoCylinder(ctx, cx - 2, cy, 1.5, 12, '#7A6E5C', shadeHex('#7A6E5C', -0.2), edge);
      // 镜筒（斜放矩形）
      const tlp = isoToWorld(cx - 2, cy);
      ctx.fillStyle = '#4A5560';
      ctx.save();
      ctx.translate(tlp.x, tlp.y - 12);
      ctx.rotate(-0.3);
      ctx.fillRect(-2, -2, 8, 4);
      ctx.restore();
      // 地球仪（球）
      drawIsoCylinder(ctx, cx + 3, cy, 4, 6, '#5A8567', shadeHex('#5A8567', -0.2), edge);
      const gp = isoToWorld(cx + 3, cy);
      ctx.fillStyle = accent;
      ctx.beginPath();
      ctx.arc(gp.x, gp.y - 6, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#5A8567';
      ctx.beginPath();
      ctx.arc(gp.x, gp.y - 6, 3, 0, Math.PI * 2);
      ctx.fill();
      break;

    case 'deer':  // 鹿·忧郁调度台：大桌子 + 调度图
      // 大办公桌
      drawIsoBox(ctx, cx, cy, 9, 4, 5, shadeHex(base, 0.3), right, left, edge);
      // 桌上的调度图（卷轴状）
      drawIsoCylinder(ctx, cx - 3, cy, 3, 2, '#E8E4D8', '#A8A095', edge);
      // 桌上的茶杯
      drawIsoCylinder(ctx, cx + 3, cy, 1.5, 2, '#E8E4D8', '#A8A095', edge);
      // 椅子（小立方体在桌后）
      drawIsoBox(ctx, cx, cy - 3, 4, 2, 6, shadeHex(base, 0.15), right, left, edge);
      break;

    // ---------- 6 公共区 ----------
    case 'canteen':  // 食堂：长桌 + 餐盘
      // 长桌
      drawIsoBox(ctx, cx, cy, 10, 4, 4, shadeHex(base, 0.3), right, left, edge);
      // 桌上的餐盘（小椭圆 x3）
      for (let i = -1; i <= 1; i++) {
        drawIsoCylinder(ctx, cx + i * 3, cy, 2, 1, '#E8E4D8', '#A8A095', edge);
      }
      break;

    case 'lounge':  // 休息区：沙发 + 落地灯
      // 沙发（宽矮立方体）
      drawIsoBox(ctx, cx - 2, cy, 8, 4, 5, shadeHex(base, 0.25), right, left, edge);
      // 沙发靠背（高一点的部分）
      drawIsoBox(ctx, cx - 2, cy - 2, 8, 1.5, 9, shadeHex(base, 0.18), right, left, edge);
      // 落地灯（细高圆柱 + 灯罩）
      drawIsoCylinder(ctx, cx + 4, cy, 1, 16, '#7A6E5C', shadeHex('#7A6E5C', -0.2), edge);
      const lmp = isoToWorld(cx + 4, cy);
      ctx.fillStyle = '#E8E4D8';
      ctx.beginPath();
      ctx.moveTo(lmp.x - 4, lmp.y - 16);
      ctx.lineTo(lmp.x + 4, lmp.y - 16);
      ctx.lineTo(lmp.x + 3, lmp.y - 20);
      ctx.lineTo(lmp.x - 3, lmp.y - 20);
      ctx.closePath();
      ctx.fill();
      // 灯光晕染
      const lgrad2 = ctx.createRadialGradient(lmp.x, lmp.y - 18, 0, lmp.x, lmp.y - 18, 14);
      lgrad2.addColorStop(0, 'rgba(212, 165, 116, 0.25)');
      lgrad2.addColorStop(1, 'rgba(212, 165, 116, 0)');
      ctx.fillStyle = lgrad2;
      ctx.beginPath();
      ctx.arc(lmp.x, lmp.y - 18, 14, 0, Math.PI * 2);
      ctx.fill();
      break;

    case 'meeting':  // 会议室：圆桌 + 椅子
      // 圆桌（圆柱）
      drawIsoCylinder(ctx, cx, cy, 6, 5, shadeHex(base, 0.3), right, edge);
      // 周围 4 把椅子（小立方体）
      const chairPos = [[cx - 4, cy], [cx + 4, cy], [cx, cy - 3], [cx, cy + 3]];
      for (const [chx, chy] of chairPos) {
        drawIsoBox(ctx, chx, chy, 2.5, 1.5, 4, shadeHex(base, 0.15), right, left, edge);
      }
      break;

    case 'gym':  // 健身房：哑铃 + 跑步机
      // 哑铃（两端球 + 中间杆）
      const dbp = isoToWorld(cx - 2, cy);
      ctx.fillStyle = '#4A5560';
      ctx.beginPath(); ctx.arc(dbp.x - 5, dbp.y - 4, 3, 0, Math.PI * 2); ctx.fill();
      ctx.beginPath(); ctx.arc(dbp.x + 5, dbp.y - 4, 3, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = '#7A6E5C';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(dbp.x - 5, dbp.y - 4); ctx.lineTo(dbp.x + 5, dbp.y - 4); ctx.stroke();
      // 跑步机（立方体 + 履带）
      drawIsoBox(ctx, cx + 3, cy, 5, 3, 4, shadeHex(base, 0.2), right, left, edge);
      const rp = isoToWorld(cx + 3, cy);
      ctx.fillStyle = '#1A201B';
      ctx.fillRect(rp.x - 4, rp.y - 3, 8, 3);
      break;

    case 'clinic':  // 医疗室：病床 + 药柜
      // 病床（矮长立方体）
      drawIsoBox(ctx, cx - 2, cy, 6, 3, 4, '#E8E4D8', '#A8A095', '#A8A095', edge);
      // 床上的枕头
      drawIsoBox(ctx, cx - 4, cy, 2, 1, 1, '#F5F2EB', '#A8A095', '#A8A095', edge);
      // 药柜（高瘦立方体）
      drawIsoBox(ctx, cx + 4, cy, 4, 2, 14, shadeHex(base, 0.2), right, left, edge);
      // 药柜上的十字（医疗标志）
      const cp = isoToWorld(cx + 4, cy);
      ctx.fillStyle = '#C97B5A';
      ctx.fillRect(cp.x - 1, cp.y - 12, 2, 6);
      ctx.fillRect(cp.x - 3, cp.y - 10, 6, 2);
      break;

    case 'storage':  // 储物间：货架 + 箱子
      // 货架（三层立方体）
      for (let i = 0; i < 3; i++) {
        drawIsoBox(ctx, cx - 2, cy + i * 2 - 2, 6, 3, 1, shadeHex(base, 0.25 - i * 0.05), right, left, edge);
      }
      // 货架两侧的箱子
      drawIsoBox(ctx, cx + 4, cy - 1, 3, 2, 3, shadeHex('#85603F', 0.1), shadeHex('#85603F', -0.1), shadeHex('#85603F', -0.15), edge);
      drawIsoBox(ctx, cx + 4, cy + 1, 2.5, 1.5, 2.5, shadeHex('#85603F', 0.15), shadeHex('#85603F', -0.1), shadeHex('#85603F', -0.15), edge);
      break;

    default:
      // 未知 zone：画一个简单装饰柱
      drawIsoBox(ctx, cx, cy, 5, 2.5, 8, top, right, left, edge);
  }
}

// commit 45-1：11 工位大型动画覆盖层（在 drawZoneDecor 之后绘制）
// 零基础读者说明：每个物种工位在静态装饰之上叠加动态光效/粒子/状态条
// 不重画装饰本体，只叠加动画效果 + 状态联动（心情/精力/健康值）
// 注意：用 isoToScreen 而非 isoToWorld，因为本函数画在主画布 ctx 上（非离屏 worldCanvas）
function drawZoneAnimationOverlay(ctx, zone, t) {
  if (zone.type !== 'species') return;  // 只处理物种 zone
  const [x1, y1, x2, y2] = zone.rect;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const sp = isoToScreen(cx, cy);  // 网格坐标 → 主画布屏幕坐标

  // 找该物种员工数据（用于状态联动：心情低则光暗、精力低则动画慢）
  const emp = employees.find(e => e.species === zone.species && e.alive !== false);
  const energy = emp ? (emp.energy || 0) : 50;
  const mood = emp ? (emp.mood_score || 0) : 50;
  const health = emp ? (emp.health || 0) : 50;

  ctx.save();

  switch (zone.id) {
    case 'deer': {
      // 鹿：蜡烛光圈，亮度随心情值波动（心情好火旺，心情差火暗）
      const flicker = 0.7 + 0.3 * Math.sin(t / 200) + 0.1 * Math.sin(t / 70);
      const brightness = (mood / 100) * flicker;
      const r = 18 + brightness * 8;
      const grad = ctx.createRadialGradient(sp.x, sp.y - 14, 0, sp.x, sp.y - 14, r);
      grad.addColorStop(0, `rgba(255, 200, 100, ${0.6 * brightness})`);
      grad.addColorStop(0.5, `rgba(212, 165, 116, ${0.3 * brightness})`);
      grad.addColorStop(1, 'rgba(212, 165, 116, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y - 14, r, 0, Math.PI * 2);
      ctx.fill();
      // 蜡烛火苗（轻微上下跳动）
      ctx.fillStyle = `rgba(255, 220, 140, ${0.9 * brightness})`;
      ctx.beginPath();
      ctx.ellipse(sp.x, sp.y - 22, 2, 4 + Math.sin(t/100)*0.5, 0, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case 'squirrel': {
      // 鼠：电脑屏幕绿色代码流闪烁，速度随精力（精力高滚动快）
      const speed = energy / 100;
      const lines = 6;
      for (let i = 0; i < lines; i++) {
        const y = sp.y - 18 + i * 2;
        const charCount = Math.floor(8 + Math.sin(t / (300 - speed * 200) + i) * 4);
        ctx.fillStyle = `rgba(124, 184, 168, ${0.4 + 0.4 * Math.sin(t/200 + i)})`;
        ctx.fillRect(sp.x - 5, y, charCount, 1.5);
      }
      // 屏幕底光（精力越高越亮）
      const grad = ctx.createRadialGradient(sp.x, sp.y - 14, 0, sp.x, sp.y - 14, 16);
      grad.addColorStop(0, `rgba(124, 184, 168, ${0.3 * speed})`);
      grad.addColorStop(1, 'rgba(124, 184, 168, 0)');
      ctx.fillStyle = grad;
      ctx.fillRect(sp.x - 16, sp.y - 24, 32, 24);
      break;
    }
    case 'butterfly': {
      // 蝶：画架上方彩色光点漂浮（4 色循环）
      const colors = ['#E8A5D5', '#A5D5E8', '#D5E8A5', '#E8D5A5'];
      for (let i = 0; i < 5; i++) {
        const ang = t / 1000 + i * Math.PI * 0.4;
        const r = 12 + Math.sin(t/500 + i) * 4;
        const px = sp.x + Math.cos(ang) * r;
        const py = sp.y - 18 + Math.sin(ang) * r * 0.5;
        ctx.fillStyle = colors[i % colors.length];
        ctx.globalAlpha = 0.6 + 0.4 * Math.sin(t/300 + i);
        ctx.beginPath();
        ctx.arc(px, py, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
      break;
    }
    case 'fox': {
      // 狐：示波器雷达扫描线（旋转扫描 + 波形曲线）
      const radius = 14;
      ctx.strokeStyle = 'rgba(212, 165, 116, 0.4)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y - 14, radius, 0, Math.PI * 2);
      ctx.stroke();
      // 扫描线（每 1.5 秒转一圈）
      const sweep = (t / 1500) % (Math.PI * 2);
      const grad = ctx.createLinearGradient(
        sp.x, sp.y - 14,
        sp.x + Math.cos(sweep) * radius, sp.y - 14 + Math.sin(sweep) * radius
      );
      grad.addColorStop(0, 'rgba(124, 184, 168, 0.8)');
      grad.addColorStop(1, 'rgba(124, 184, 168, 0)');
      ctx.strokeStyle = grad;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(sp.x, sp.y - 14);
      ctx.lineTo(sp.x + Math.cos(sweep) * radius, sp.y - 14 + Math.sin(sweep) * radius);
      ctx.stroke();
      // 波形曲线（模拟示波器信号）
      ctx.strokeStyle = `rgba(124, 184, 168, ${0.6 + 0.3 * Math.sin(t/200)})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i < 20; i++) {
        const px = sp.x - 8 + i;
        const py = sp.y - 8 + Math.sin(t/100 + i * 0.5) * 2;
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      }
      ctx.stroke();
      break;
    }
    case 'hedgehog': {
      // 猬：防御矩阵灯柱，颜色随公司整体健康值（绿>60/琥珀>30/红<30）
      const avgHealth = employees.length > 0
        ? employees.reduce((s, e) => s + (e.health || 0), 0) / employees.length
        : 50;
      const lightColor = avgHealth > 60 ? 'rgba(127, 217, 127, 0.7)'   // 绿
                      : avgHealth > 30 ? 'rgba(212, 165, 116, 0.7)'   // 琥珀
                                       : 'rgba(217, 127, 127, 0.8)';  // 红
      const pulse = 0.7 + 0.3 * Math.sin(t / 400);
      const r = 8 + pulse * 4;
      const grad = ctx.createRadialGradient(sp.x, sp.y - 20, 0, sp.x, sp.y - 20, r * 2);
      grad.addColorStop(0, lightColor);
      grad.addColorStop(1, lightColor.replace(/[\\d.]+\\)$/, '0)'));
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y - 20, r * 2, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
    case 'beaver': {
      // 狸：蓝图进度条（循环填充 + 蓝图线条）
      const progress = ((t / 100) % 100) / 100;
      ctx.fillStyle = 'rgba(45, 60, 80, 0.6)';
      ctx.fillRect(sp.x - 10, sp.y - 4, 20, 3);
      ctx.fillStyle = 'rgba(127, 217, 217, 0.8)';
      ctx.fillRect(sp.x - 10, sp.y - 4, 20 * progress, 3);
      // 蓝图线条
      ctx.strokeStyle = 'rgba(127, 217, 217, 0.3)';
      ctx.lineWidth = 0.5;
      for (let i = 0; i < 3; i++) {
        ctx.beginPath();
        ctx.moveTo(sp.x - 8 + i * 3, sp.y - 10);
        ctx.lineTo(sp.x - 4 + i * 3, sp.y - 6);
        ctx.stroke();
      }
      break;
    }
    case 'raven': {
      // 鸦：紫色记忆水晶浮动（上下漂浮 + 菱形水晶本体）
      const float = Math.sin(t / 600) * 3;
      const cx2 = sp.x;
      const cy2 = sp.y - 22 + float;
      const grad = ctx.createRadialGradient(cx2, cy2, 0, cx2, cy2, 14);
      grad.addColorStop(0, 'rgba(180, 130, 220, 0.8)');
      grad.addColorStop(0.5, 'rgba(120, 80, 180, 0.4)');
      grad.addColorStop(1, 'rgba(80, 40, 140, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx2, cy2, 14, 0, Math.PI * 2);
      ctx.fill();
      // 水晶本体（菱形）
      ctx.fillStyle = 'rgba(200, 160, 240, 0.9)';
      ctx.beginPath();
      ctx.moveTo(cx2, cy2 - 5);
      ctx.lineTo(cx2 + 3, cy2);
      ctx.lineTo(cx2, cy2 + 5);
      ctx.lineTo(cx2 - 3, cy2);
      ctx.closePath();
      ctx.fill();
      break;
    }
    case 'hare': {
      // 兔：快递盒倒计时（3 个盒子轮流倒数 1-10）
      const boxColors = ['rgba(127, 180, 217, 0.7)', 'rgba(217, 127, 127, 0.7)', 'rgba(127, 217, 127, 0.7)'];
      for (let i = 0; i < 3; i++) {
        const bx = sp.x - 8 + i * 7;
        const by = sp.y - 6;
        ctx.fillStyle = boxColors[i];
        ctx.fillRect(bx, by, 5, 4);
        ctx.strokeStyle = 'rgba(60, 40, 20, 0.6)';
        ctx.lineWidth = 0.5;
        ctx.strokeRect(bx, by, 5, 4);
        // 倒计时数字
        const remain = Math.ceil((1000 - (t + i * 300) % 1000) / 100);
        ctx.fillStyle = '#F5EDD8';
        ctx.font = '6px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(remain, bx + 2.5, by + 3);
      }
      break;
    }
    case 'badger': {
      // 獾：攀岩墙进度条（从下往上填充）
      const progress = ((t / 200) % 100) / 100;
      ctx.fillStyle = 'rgba(80, 60, 40, 0.5)';
      ctx.fillRect(sp.x - 3, sp.y - 18, 6, 18);
      ctx.fillStyle = 'rgba(212, 165, 116, 0.8)';
      ctx.fillRect(sp.x - 3, sp.y - 18 + 18 * (1 - progress), 6, 18 * progress);
      // 工具图标（斜线）
      ctx.strokeStyle = 'rgba(180, 150, 100, 0.6)';
      ctx.lineWidth = 0.5;
      ctx.beginPath();
      ctx.moveTo(sp.x - 6, sp.y - 14);
      ctx.lineTo(sp.x - 4, sp.y - 10);
      ctx.stroke();
      break;
    }
    case 'lark': {
      // 雀：留声机唱片旋转 + 音符上飘
      const rot = t / 500;
      ctx.save();
      ctx.translate(sp.x, sp.y - 8);
      ctx.rotate(rot);
      ctx.fillStyle = 'rgba(40, 40, 40, 0.7)';
      ctx.beginPath();
      ctx.arc(0, 0, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(212, 165, 116, 0.9)';
      ctx.beginPath();
      ctx.arc(0, 0, 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
      // 音符粒子（从下往上飘，逐渐淡出）
      for (let i = 0; i < 3; i++) {
        const ny = sp.y - 16 - ((t / 30 + i * 30) % 30);
        const nx = sp.x + Math.sin(t / 500 + i) * 4;
        ctx.fillStyle = `rgba(255, 220, 140, ${1 - ((t / 30 + i * 30) % 30) / 30})`;
        ctx.font = '10px serif';
        ctx.textAlign = 'center';
        ctx.fillText('♪', nx, ny);
      }
      break;
    }
    case 'kite': {
      // 鸢：望远镜镜头光圈（左右摆动 + 中心光点闪烁）
      const sweep = Math.sin(t / 800) * 0.3;
      ctx.save();
      ctx.translate(sp.x, sp.y - 24);
      ctx.rotate(sweep);
      ctx.strokeStyle = 'rgba(212, 165, 116, 0.5)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(0, 0, 8, 0, Math.PI * 2);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(124, 184, 168, 0.8)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -12);
      ctx.stroke();
      ctx.restore();
      // 镜头中心光点（脉动）
      const pulse = 0.6 + 0.4 * Math.sin(t / 200);
      ctx.fillStyle = `rgba(255, 220, 140, ${pulse})`;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y - 24, 2, 0, Math.PI * 2);
      ctx.fill();
      break;
    }
  }
  ctx.restore();
}

// ==================== commit 22：四周白色墙壁 ====================
// 零基础读者可以这样理解：
// 在 80×60 大地图的外围立一圈白色墙，2.5D 等距视角下能看到两面墙：
// 左墙（ix=0 那条边，朝右）+ 上墙（iy=0 那条边，朝下）。
// 墙顶加一条稍暗的"墙帽"让墙有厚度感，墙底加柔和投影让它从地面浮起。
// 颜色：纯白 #FFFFFF，浅色模式下稍调暗避免刺眼。
function drawWalls(targetCtx) {
  const wallH = TILE_H * 12;         // 墙高（与 prerenderWorld 一致）
  const capDepth = 8;                // 墙帽厚度（再加高后墙帽同步加厚）
  const tw = TILE_W / 2, th = TILE_H / 2;

  // 墙面色：深色模式纯白，浅色模式稍微调暗（避免米底上刺眼）
  const isLight = getCurrentTheme() === 'light';
  const faceColor = isLight ? '#FFFFFF' : '#FFFFFF';
  const topColor  = isLight ? '#E8E2D2' : '#E8E2D2';     // 墙顶帽稍暗
  const edgeColor = isLight ? 'rgba(60, 50, 30, 0.18)' : 'rgba(212, 165, 116, 0.22)';
  const shadowColor = isLight ? 'rgba(60, 50, 30, 0.12)' : 'rgba(0, 0, 0, 0.35)';

  // 地图四个角的瓦片中心（worldCanvas 坐标）
  const cornerTL = isoToWorld(0, 0);              // 左上角瓦片
  const cornerTR = isoToWorld(MAP_W - 1, 0);      // 右上角瓦片
  const cornerBL = isoToWorld(0, MAP_H - 1);      // 左下角瓦片
  const cornerBR = isoToWorld(MAP_W - 1, MAP_H - 1); // 右下角瓦片

  // 四条墙的地面边线（菱形地图的左上两条边）
  // 左墙底边：从 TL 瓦片左顶点 → BL 瓦片下顶点
  const leftBase = [
    { x: cornerTL.x - tw, y: cornerTL.y },        // 地面左上
    { x: cornerBL.x,      y: cornerBL.y + th },   // 地面左下
  ];
  // 上墙底边：从 TL 瓦片左顶点 → TR 瓦片右顶点
  const topBase = [
    { x: cornerTL.x - tw, y: cornerTL.y },        // 地面左上（与左墙共享）
    { x: cornerTR.x + tw, y: cornerTR.y },        // 地面右上
  ];

  // ---------- 1) 墙底部柔和投影 ----------
  targetCtx.save();
  // 左墙投影：沿左墙底边外侧
  const lgrad = targetCtx.createLinearGradient(
    leftBase[0].x, leftBase[0].y,
    leftBase[0].x - 24, leftBase[0].y + 12
  );
  lgrad.addColorStop(0, shadowColor);
  lgrad.addColorStop(1, 'rgba(0,0,0,0)');
  targetCtx.fillStyle = lgrad;
  targetCtx.beginPath();
  targetCtx.moveTo(leftBase[0].x, leftBase[0].y);
  targetCtx.lineTo(leftBase[1].x, leftBase[1].y);
  targetCtx.lineTo(leftBase[1].x - 18, leftBase[1].y + 9);
  targetCtx.lineTo(leftBase[0].x - 18, leftBase[0].y + 9);
  targetCtx.closePath();
  targetCtx.fill();
  // 上墙投影：沿上墙底边外侧
  const tgrad = targetCtx.createLinearGradient(
    topBase[0].x, topBase[0].y,
    topBase[0].x, topBase[0].y - 24
  );
  tgrad.addColorStop(0, shadowColor);
  tgrad.addColorStop(1, 'rgba(0,0,0,0)');
  targetCtx.fillStyle = tgrad;
  targetCtx.beginPath();
  targetCtx.moveTo(topBase[0].x, topBase[0].y);
  targetCtx.lineTo(topBase[1].x, topBase[1].y);
  targetCtx.lineTo(topBase[1].x, topBase[1].y - 14);
  targetCtx.lineTo(topBase[0].x, topBase[0].y - 14);
  targetCtx.closePath();
  targetCtx.fill();
  targetCtx.restore();

  // ---------- 2) 左墙正面（朝右，纯白） ----------
  targetCtx.fillStyle = faceColor;
  targetCtx.beginPath();
  targetCtx.moveTo(leftBase[0].x, leftBase[0].y);                  // 地面左上
  targetCtx.lineTo(leftBase[1].x, leftBase[1].y);                  // 地面左下
  targetCtx.lineTo(leftBase[1].x, leftBase[1].y - wallH);          // 墙顶左下
  targetCtx.lineTo(leftBase[0].x, leftBase[0].y - wallH);          // 墙顶左上
  targetCtx.closePath();
  targetCtx.fill();
  // 极淡描边
  targetCtx.strokeStyle = edgeColor;
  targetCtx.lineWidth = 1;
  targetCtx.stroke();

  // ---------- 3) 上墙正面（朝下，纯白） ----------
  targetCtx.fillStyle = faceColor;
  targetCtx.beginPath();
  targetCtx.moveTo(topBase[0].x, topBase[0].y);                    // 地面左上
  targetCtx.lineTo(topBase[1].x, topBase[1].y);                    // 地面右上
  targetCtx.lineTo(topBase[1].x, topBase[1].y - wallH);            // 墙顶右上
  targetCtx.lineTo(topBase[0].x, topBase[0].y - wallH);            // 墙顶左上
  targetCtx.closePath();
  targetCtx.fill();
  targetCtx.strokeStyle = edgeColor;
  targetCtx.lineWidth = 1;
  targetCtx.stroke();

  // ---------- 4) 墙顶帽（让墙有厚度，2.5D 顶面） ----------
  // 左墙顶帽：墙顶线向外延伸 capDepth
  targetCtx.fillStyle = topColor;
  targetCtx.beginPath();
  targetCtx.moveTo(leftBase[0].x, leftBase[0].y - wallH);          // 墙顶左上（内）
  targetCtx.lineTo(leftBase[1].x, leftBase[1].y - wallH);          // 墙顶左下（内）
  targetCtx.lineTo(leftBase[1].x - capDepth, leftBase[1].y - wallH + capDepth * 0.5);  // 墙顶左下（外）
  targetCtx.lineTo(leftBase[0].x - capDepth, leftBase[0].y - wallH + capDepth * 0.5);  // 墙顶左上（外）
  targetCtx.closePath();
  targetCtx.fill();
  targetCtx.strokeStyle = edgeColor;
  targetCtx.lineWidth = 0.5;
  targetCtx.stroke();

  // 上墙顶帽
  targetCtx.fillStyle = topColor;
  targetCtx.beginPath();
  targetCtx.moveTo(topBase[0].x, topBase[0].y - wallH);            // 墙顶左上（内）
  targetCtx.lineTo(topBase[1].x, topBase[1].y - wallH);            // 墙顶右上（内）
  targetCtx.lineTo(topBase[1].x, topBase[1].y - wallH - capDepth); // 墙顶右上（外）
  targetCtx.lineTo(topBase[0].x, topBase[0].y - wallH - capDepth); // 墙顶左上（外）
  targetCtx.closePath();
  targetCtx.fill();
  targetCtx.strokeStyle = edgeColor;
  targetCtx.lineWidth = 0.5;
  targetCtx.stroke();

  // ---------- 5) 墙角接缝（左墙和上墙交点处加一条细线，让转角清晰） ----------
  targetCtx.strokeStyle = edgeColor;
  targetCtx.lineWidth = 1;
  targetCtx.beginPath();
  targetCtx.moveTo(topBase[0].x, topBase[0].y - wallH);
  targetCtx.lineTo(topBase[0].x, topBase[0].y);
  targetCtx.stroke();

  // ---------- 6) 横向装饰线（墙太高，加几道水平细线避免墙面空洞） ----------
  // 在墙高 1/5、2/5、3/5、4/5 处各画一条极淡的水平线
  targetCtx.strokeStyle = isLight ? 'rgba(60, 50, 30, 0.10)' : 'rgba(212, 165, 116, 0.14)';
  targetCtx.lineWidth = 0.8;
  for (const ratio of [0.20, 0.40, 0.60, 0.80]) {
    const yOff = wallH * ratio;
    // 左墙装饰线
    targetCtx.beginPath();
    targetCtx.moveTo(leftBase[0].x, leftBase[0].y - yOff);
    targetCtx.lineTo(leftBase[1].x, leftBase[1].y - yOff);
    targetCtx.stroke();
    // 上墙装饰线
    targetCtx.beginPath();
    targetCtx.moveTo(topBase[0].x, topBase[0].y - yOff);
    targetCtx.lineTo(topBase[1].x, topBase[1].y - yOff);
    targetCtx.stroke();
  }
}

function drawTileTo(targetCtx, ix, iy) {
  // 瓦片：等距菱形 + 微噪声明暗 + 边缘描边 + 偶发草点
  // 浅色模式下整片调亮（用 THEME_COLORS.brighten 系数），让深色 zone 在米底上柔和可见
  const p = isoToWorld(ix, iy);
  const zone = findZone(ix, iy);
  const brighten = THEME_COLORS.brighten;
  const baseColor = zone ? zone.color : THEME_COLORS.canvasGrid;
  const w = TILE_W / 2;
  const h = TILE_H / 2;

  // 基于坐标的伪随机噪声（让相邻瓦片有微妙差异）
  const noise = ((ix * 73856093) ^ (iy * 19349663)) & 0xff;
  const noiseFactor = (noise / 255 - 0.5) * 0.08;  // ±4% 亮度变化

  // 顶面填充（轻微噪声变化 + 主题亮度补偿）
  targetCtx.fillStyle = adjustColor(baseColor, noiseFactor + brighten);
  targetCtx.beginPath();
  targetCtx.moveTo(p.x, p.y - h);
  targetCtx.lineTo(p.x + w, p.y);
  targetCtx.lineTo(p.x, p.y + h);
  targetCtx.lineTo(p.x - w, p.y);
  targetCtx.closePath();
  targetCtx.fill();

  // commit 41：地砖顶面边缘线（让轮廓清晰，对比度更强）
  if (zone) {
    targetCtx.strokeStyle = adjustColor(baseColor, -0.2 + brighten * 0.5);
    targetCtx.lineWidth = 0.5;
    targetCtx.beginPath();
    targetCtx.moveTo(p.x, p.y - h);
    targetCtx.lineTo(p.x + w, p.y);
    targetCtx.lineTo(p.x, p.y + h);
    targetCtx.lineTo(p.x - w, p.y);
    targetCtx.closePath();
    targetCtx.stroke();
  }

  // 右侧面（暗一档，营造 2.5D 立体感）
  targetCtx.fillStyle = adjustColor(baseColor, -0.15 + brighten * 0.6);
  targetCtx.beginPath();
  targetCtx.moveTo(p.x, p.y + h);
  targetCtx.lineTo(p.x + w, p.y);
  targetCtx.lineTo(p.x + w, p.y + h * 1.4);
  targetCtx.lineTo(p.x, p.y + h * 2.4);
  targetCtx.closePath();
  targetCtx.fill();

  // 左侧面（再暗一档）
  targetCtx.fillStyle = adjustColor(baseColor, -0.25 + brighten * 0.4);
  targetCtx.beginPath();
  targetCtx.moveTo(p.x, p.y + h);
  targetCtx.lineTo(p.x - w, p.y);
  targetCtx.lineTo(p.x - w, p.y + h * 1.4);
  targetCtx.lineTo(p.x, p.y + h * 2.4);
  targetCtx.closePath();
  targetCtx.fill();

  // 顶面细描边（极淡琥珀，让 zone 边界柔和可见）
  targetCtx.strokeStyle = 'rgba(212, 165, 116, 0.06)';
  targetCtx.lineWidth = 0.5;
  targetCtx.beginPath();
  targetCtx.moveTo(p.x, p.y - h);
  targetCtx.lineTo(p.x + w, p.y);
  targetCtx.lineTo(p.x, p.y + h);
  targetCtx.lineTo(p.x - w, p.y);
  targetCtx.closePath();
  targetCtx.stroke();

  // 偶发草点装饰（约 12% 瓦片上画 1-2 个小点）
  if (noise > 220) {
    targetCtx.fillStyle = adjustColor(baseColor, 0.18 + brighten);
    const gx = p.x + (noise % 7) - 3;
    const gy = p.y - (noise % 4);
    targetCtx.fillRect(gx, gy, 1.5, 2);
    if (noise > 240) {
      targetCtx.fillRect(gx + 4, gy - 1, 1.5, 2);
    }
  }
}

// 颜色调整辅助函数（hex → 调亮/调暗 → hex）
function adjustColor(hex, amount) {
  // amount: -1 ~ +1，负数变暗，正数变亮
  const h = hex.replace('#', '');
  const r = parseInt(h.substr(0, 2), 16);
  const g = parseInt(h.substr(2, 2), 16);
  const b = parseInt(h.substr(4, 2), 16);
  const adj = (c) => {
    const v = Math.max(0, Math.min(255, Math.round(c + 255 * amount)));
    return v.toString(16).padStart(2, '0');
  };
  return '#' + adj(r) + adj(g) + adj(b);
}

// commit 41：zone 地毯 —— 让每个工位有独立地板感
function drawZoneCarpet(targetCtx, zone) {
  const [x1, y1, x2, y2] = zone.rect;
  // 地毯比 zone.color 略亮 8%，半透明叠加
  const carpetColor = adjustColor(zone.color, 0.08 + THEME_COLORS.brighten);
  targetCtx.fillStyle = carpetColor;
  // 按等距菱形铺满 zone 矩形区域
  for (let ix = x1; ix <= x2; ix++) {
    for (let iy = y1; iy <= y2; iy++) {
      const p = isoToWorld(ix, iy);
      const w = TILE_W / 2;
      const h = TILE_H / 2;
      targetCtx.beginPath();
      targetCtx.moveTo(p.x, p.y - h);
      targetCtx.lineTo(p.x + w, p.y);
      targetCtx.lineTo(p.x, p.y + h);
      targetCtx.lineTo(p.x - w, p.y);
      targetCtx.closePath();
      targetCtx.fill();
    }
  }
  // 地毯边缘加一圈琥珀色细描边（强化"格子间"边界）
  targetCtx.strokeStyle = 'rgba(212, 165, 116, 0.18)';
  targetCtx.lineWidth = 1;
  // 画外圈四条边（按等距菱形外轮廓）
  const corners = [
    isoToWorld(x1, y1), isoToWorld(x2, y1),
    isoToWorld(x2, y2), isoToWorld(x1, y2),
  ];
  targetCtx.beginPath();
  targetCtx.moveTo(corners[0].x, corners[0].y);
  for (let i = 1; i < 4; i++) targetCtx.lineTo(corners[i].x, corners[i].y);
  targetCtx.closePath();
  targetCtx.stroke();
}

// commit 41：zone 矮木栅栏 —— 四角木桩 + 横木条，物理边界感
function drawZoneFence(targetCtx, zone) {
  const [x1, y1, x2, y2] = zone.rect;
  // 四角坐标
  const corners = [
    {ix: x1, iy: y1}, {ix: x2, iy: y1},
    {ix: x2, iy: y2}, {ix: x1, iy: y2},
  ];
  // 木桩配色（暖褐木色）
  const postLight = '#8B6F47';
  const postDark = '#5C4A30';
  const postEdge = 'rgba(212, 165, 116, 0.35)';

  for (const c of corners) {
    const p = isoToWorld(c.ix, c.iy);
    // 木桩：等距视角下的小立柱（宽 6px，高 14px）
    // 左面（暗）
    targetCtx.fillStyle = postDark;
    targetCtx.beginPath();
    targetCtx.moveTo(p.x - 3, p.y - 14);
    targetCtx.lineTo(p.x, p.y - 11);
    targetCtx.lineTo(p.x, p.y);
    targetCtx.lineTo(p.x - 3, p.y - 3);
    targetCtx.closePath();
    targetCtx.fill();
    // 右面（亮）
    targetCtx.fillStyle = postLight;
    targetCtx.beginPath();
    targetCtx.moveTo(p.x + 3, p.y - 14);
    targetCtx.lineTo(p.x, p.y - 11);
    targetCtx.lineTo(p.x, p.y);
    targetCtx.lineTo(p.x + 3, p.y - 3);
    targetCtx.closePath();
    targetCtx.fill();
    // 顶面（最亮）
    targetCtx.fillStyle = adjustColor(postLight, 0.15);
    targetCtx.beginPath();
    targetCtx.moveTo(p.x, p.y - 17);
    targetCtx.lineTo(p.x + 3, p.y - 14);
    targetCtx.lineTo(p.x, p.y - 11);
    targetCtx.lineTo(p.x - 3, p.y - 14);
    targetCtx.closePath();
    targetCtx.fill();
    // 描边
    targetCtx.strokeStyle = postEdge;
    targetCtx.lineWidth = 0.5;
    targetCtx.beginPath();
    targetCtx.moveTo(p.x, p.y - 17);
    targetCtx.lineTo(p.x + 3, p.y - 14);
    targetCtx.lineTo(p.x + 3, p.y - 3);
    targetCtx.lineTo(p.x, p.y);
    targetCtx.lineTo(p.x - 3, p.y - 3);
    targetCtx.lineTo(p.x - 3, p.y - 14);
    targetCtx.closePath();
    targetCtx.stroke();
  }
}

// commit 41：zone 边缘种树 —— 让每个工位有"院落感"
// 用伪随机种子（zone.id 哈希）确保每次刷新树位置稳定
function drawZoneTrees(targetCtx, zone) {
  const [x1, y1, x2, y2] = zone.rect;
  // 用 zone.id 生成稳定种子
  let seed = 0;
  for (let i = 0; i < zone.id.length; i++) seed = (seed * 31 + zone.id.charCodeAt(i)) & 0xffffffff;
  const rng = () => {
    seed = (seed * 1664525 + 1013904223) & 0xffffffff;
    return (seed >>> 0) / 0xffffffff;
  };
  // 树配色：深绿冠 + 暗褐干
  const crownLight = '#3D5A3D';
  const crownDark = '#2A4030';
  const trunkColor = '#4A3522';
  const trunkEdge = 'rgba(212, 165, 116, 0.25)';
  // 在 zone 边缘内侧（距离边缘 1-2 格）种 4 棵树
  const treeCount = 4;
  for (let i = 0; i < treeCount; i++) {
    // 边缘位置：4 棵树分别在 4 条边的中间偏移
    const edge = i % 4;
    let tx, ty;
    if (edge === 0) {  // 上边
      tx = x1 + 2 + rng() * Math.max(1, (x2 - x1 - 4));
      ty = y1 + 1;
    } else if (edge === 1) {  // 右边
      tx = x2 - 1;
      ty = y1 + 2 + rng() * Math.max(1, (y2 - y1 - 4));
    } else if (edge === 2) {  // 下边
      tx = x1 + 2 + rng() * Math.max(1, (x2 - x1 - 4));
      ty = y2 - 1;
    } else {  // 左边
      tx = x1 + 1;
      ty = y1 + 2 + rng() * Math.max(1, (y2 - y1 - 4));
    }
    const p = isoToWorld(tx, ty);
    // 树干（暗褐小立柱）
    targetCtx.fillStyle = trunkColor;
    targetCtx.fillRect(p.x - 2, p.y - 14, 4, 10);
    targetCtx.fillStyle = adjustColor(trunkColor, 0.15);
    targetCtx.fillRect(p.x - 2, p.y - 14, 1, 10);
    // 树冠（三层椭圆，从大到小，模拟松树）
    targetCtx.fillStyle = crownDark;
    targetCtx.beginPath();
    targetCtx.ellipse(p.x, p.y - 16, 10, 6, 0, 0, Math.PI * 2);
    targetCtx.fill();
    targetCtx.fillStyle = crownLight;
    targetCtx.beginPath();
    targetCtx.ellipse(p.x, p.y - 22, 8, 5, 0, 0, Math.PI * 2);
    targetCtx.fill();
    targetCtx.fillStyle = adjustColor(crownLight, 0.15);
    targetCtx.beginPath();
    targetCtx.ellipse(p.x, p.y - 28, 6, 4, 0, 0, Math.PI * 2);
    targetCtx.fill();
    // 树冠琥珀描边（夜森林风格）
    targetCtx.strokeStyle = trunkEdge;
    targetCtx.lineWidth = 0.5;
    targetCtx.beginPath();
    targetCtx.ellipse(p.x, p.y - 16, 10, 6, 0, 0, Math.PI * 2);
    targetCtx.stroke();
    targetCtx.beginPath();
    targetCtx.ellipse(p.x, p.y - 22, 8, 5, 0, 0, Math.PI * 2);
    targetCtx.stroke();
    targetCtx.beginPath();
    targetCtx.ellipse(p.x, p.y - 28, 6, 4, 0, 0, Math.PI * 2);
    targetCtx.stroke();
  }
}

// commit 41：外围森林迷雾 —— 砍掉无限地砖，zone 外画深绿森林
function drawForestMist(targetCtx) {
  // 遍历所有地砖，zone 外的画深绿森林
  for (let ix = 0; ix < MAP_W; ix++) {
    for (let iy = 0; iy < MAP_H; iy++) {
      if (_isInAnyZone(ix, iy)) continue;  // zone 内跳过
      const p = isoToWorld(ix, iy);
      const w = TILE_W / 2;
      const h = TILE_H / 2;
      // 基于坐标的伪随机噪声（让森林有疏密变化）
      const noise = ((ix * 73856093) ^ (iy * 19349663)) & 0xff;
      // 深绿森林底色（比 zone.color 更深更绿）
      const baseGreen = adjustColor('#0F1A12', (noise / 255 - 0.5) * 0.06);
      targetCtx.fillStyle = baseGreen;
      targetCtx.beginPath();
      targetCtx.moveTo(p.x, p.y - h);
      targetCtx.lineTo(p.x + w, p.y);
      targetCtx.lineTo(p.x, p.y + h);
      targetCtx.lineTo(p.x - w, p.y);
      targetCtx.closePath();
      targetCtx.fill();
      // 约 35% 概率画一棵小树冠（让外围有"森林"质感）
      if (noise > 165) {
        const treeColor = noise > 210 ? '#1F3520' : '#152819';
        targetCtx.fillStyle = treeColor;
        targetCtx.beginPath();
        targetCtx.ellipse(p.x, p.y - 4, 8 + (noise % 4), 5 + (noise % 3), 0, 0, Math.PI * 2);
        targetCtx.fill();
        // 树冠高光
        targetCtx.fillStyle = adjustColor(treeColor, 0.12);
        targetCtx.beginPath();
        targetCtx.ellipse(p.x - 2, p.y - 6, 3, 2, 0, 0, Math.PI * 2);
        targetCtx.fill();
      }
    }
  }
  // 在最外围一圈画更深的"迷雾渐变"（强化"墙外是森林"感）
  targetCtx.fillStyle = 'rgba(8, 15, 10, 0.5)';
  // 上下左右四条边的迷雾
  for (let ix = 0; ix < MAP_W; ix++) {
    for (const iy of [0, 1, MAP_H - 2, MAP_H - 1]) {
      const p = isoToWorld(ix, iy);
      const w = TILE_W / 2;
      const h = TILE_H / 2;
      targetCtx.beginPath();
      targetCtx.moveTo(p.x, p.y - h);
      targetCtx.lineTo(p.x + w, p.y);
      targetCtx.lineTo(p.x, p.y + h);
      targetCtx.lineTo(p.x - w, p.y);
      targetCtx.closePath();
      targetCtx.fill();
    }
  }
  for (let iy = 0; iy < MAP_H; iy++) {
    for (const ix of [0, 1, MAP_W - 2, MAP_W - 1]) {
      const p = isoToWorld(ix, iy);
      const w = TILE_W / 2;
      const h = TILE_H / 2;
      targetCtx.beginPath();
      targetCtx.moveTo(p.x, p.y - h);
      targetCtx.lineTo(p.x + w, p.y);
      targetCtx.lineTo(p.x, p.y + h);
      targetCtx.lineTo(p.x - w, p.y);
      targetCtx.closePath();
      targetCtx.fill();
    }
  }
}

// commit 50-5：渲染地图装饰物（树/石/灯/箱/花盆）—— 32x32 像素静止物件
function drawDecorations(targetCtx) {
  for (const d of DECORATIONS) {
    const p = isoToWorld(d.x, d.y);
    const s = d.seed;
    targetCtx.save();
    targetCtx.translate(p.x, p.y);
    if (d.type === 'tree') {
      // 像素松树（深绿三角层叠）
      targetCtx.fillStyle = '#3D2E1F';
      targetCtx.fillRect(-2, 6, 4, 6);  // 树干
      targetCtx.fillStyle = '#1F3A22';
      targetCtx.beginPath();
      targetCtx.moveTo(0, -14); targetCtx.lineTo(8, 0); targetCtx.lineTo(-8, 0);
      targetCtx.closePath(); targetCtx.fill();
      targetCtx.fillStyle = '#2A4A2E';
      targetCtx.beginPath();
      targetCtx.moveTo(0, -8); targetCtx.lineTo(6, 4); targetCtx.lineTo(-6, 4);
      targetCtx.closePath(); targetCtx.fill();
      targetCtx.fillStyle = '#3A5C3E';
      targetCtx.beginPath();
      targetCtx.moveTo(0, -2); targetCtx.lineTo(5, 8); targetCtx.lineTo(-5, 8);
      targetCtx.closePath(); targetCtx.fill();
    } else if (d.type === 'rock') {
      // 石头（灰椭圆）
      targetCtx.fillStyle = '#5A5550';
      targetCtx.beginPath();
      targetCtx.ellipse(0, 4, 7, 4, 0, 0, Math.PI * 2);
      targetCtx.fill();
      targetCtx.fillStyle = '#7A7570';
      targetCtx.beginPath();
      targetCtx.ellipse(-1, 2, 4, 2, 0, 0, Math.PI * 2);
      targetCtx.fill();
    } else if (d.type === 'lamp') {
      // 路灯（木柱+暖光球）
      targetCtx.fillStyle = '#3D2E1F';
      targetCtx.fillRect(-1, -8, 2, 16);
      targetCtx.fillStyle = '#8B6F47';
      targetCtx.fillRect(-3, -12, 6, 4);
      const glow = 0.5 + Math.sin(s / 100) * 0.2;
      targetCtx.fillStyle = 'rgba(255, 220, 120, ' + glow + ')';
      targetCtx.beginPath();
      targetCtx.arc(0, -10, 3, 0, Math.PI * 2);
      targetCtx.fill();
      targetCtx.fillStyle = 'rgba(255, 220, 120, 0.15)';
      targetCtx.beginPath();
      targetCtx.arc(0, -10, 10, 0, Math.PI * 2);
      targetCtx.fill();
    } else if (d.type === 'box') {
      // 小木箱
      targetCtx.fillStyle = '#8B6F47';
      targetCtx.fillRect(-5, -2, 10, 8);
      targetCtx.strokeStyle = '#5C4022';
      targetCtx.lineWidth = 1;
      targetCtx.strokeRect(-5, -2, 10, 8);
      targetCtx.beginPath();
      targetCtx.moveTo(-5, 2); targetCtx.lineTo(5, 2);
      targetCtx.moveTo(0, -2); targetCtx.lineTo(0, 6);
      targetCtx.stroke();
    } else if (d.type === 'pot') {
      // 花盆
      targetCtx.fillStyle = '#8B5A2B';
      targetCtx.beginPath();
      targetCtx.moveTo(-4, 0); targetCtx.lineTo(4, 0);
      targetCtx.lineTo(3, 8); targetCtx.lineTo(-3, 8);
      targetCtx.closePath(); targetCtx.fill();
      // 花
      targetCtx.fillStyle = '#D4A0A0';
      targetCtx.beginPath(); targetCtx.arc(-2, -2, 2, 0, Math.PI * 2); targetCtx.fill();
      targetCtx.fillStyle = '#A0D4A0';
      targetCtx.beginPath(); targetCtx.arc(2, -2, 2, 0, Math.PI * 2); targetCtx.fill();
      targetCtx.fillStyle = '#D4D4A0';
      targetCtx.beginPath(); targetCtx.arc(0, -4, 2, 0, Math.PI * 2); targetCtx.fill();
    }
    targetCtx.restore();
  }
}

function drawZoneLabelTo(targetCtx, zone) {
  const [x1, y1, x2, y2] = zone.rect;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const p = isoToWorld(cx, cy);

  // commit 41：工位木牌立牌（替代悬浮文字）
  // 立柱位置：zone 中心点向上偏移
  const postX = p.x;
  const postBaseY = p.y;
  const postTopY = p.y - 20;
  // 木牌位置：立柱顶部
  const signW = 88;
  const signH = 22;
  const signX = postX - signW / 2;
  const signY = postTopY - signH;

  // 1. 立柱（暗木色）
  targetCtx.fillStyle = '#5C4A30';
  targetCtx.fillRect(postX - 2, postTopY, 4, postBaseY - postTopY);
  // 立柱高光
  targetCtx.fillStyle = '#8B6F47';
  targetCtx.fillRect(postX - 2, postTopY, 1, postBaseY - postTopY);

  // 2. 木牌底板（深褐木色 + 琥珀描边）
  targetCtx.fillStyle = '#3D2E1F';
  targetCtx.fillRect(signX, signY, signW, signH);
  // 木牌顶部高光
  targetCtx.fillStyle = '#5C4530';
  targetCtx.fillRect(signX, signY, signW, 2);
  // 木牌琥珀描边
  targetCtx.strokeStyle = 'rgba(212, 165, 116, 0.55)';
  targetCtx.lineWidth = 1;
  targetCtx.strokeRect(signX + 0.5, signY + 0.5, signW - 1, signH - 1);
  // 木牌四角小铆钉装饰
  targetCtx.fillStyle = '#D4A574';
  targetCtx.fillRect(signX + 3, signY + 3, 2, 2);
  targetCtx.fillRect(signX + signW - 5, signY + 3, 2, 2);
  targetCtx.fillRect(signX + 3, signY + signH - 5, 2, 2);
  targetCtx.fillRect(signX + signW - 5, signY + signH - 5, 2, 2);

  // 3. 木牌上的文字（琥珀色 serif）
  targetCtx.font = '500 12px "Fraunces", serif';
  targetCtx.textAlign = 'center';
  targetCtx.textBaseline = 'middle';
  // 文字阴影
  targetCtx.fillStyle = 'rgba(0, 0, 0, 0.6)';
  targetCtx.fillText(zone.name, postX + 1, signY + signH / 2 + 1);
  // 主文字
  targetCtx.fillStyle = '#D4A574';
  targetCtx.fillText(zone.name, postX, signY + signH / 2);
}

// ==================== commit 13：记忆可视化 ====================
// 零基础读者可以这样理解：每只已故员工的记忆被存进一个"玻璃晶体"，
// 全部晶体集中放在鸦·黑卷的档案室（raven zone）。晶体周围有金色光点
// 飘动。已故员工原岗位的 zone 中心会留一个小墓碑作"遗物标记"。
// 点击档案室的晶体，会弹出记忆详情，可让渡鸦讲述这位前辈的故事。

const RAVEN_ZONE_ID = 'raven';
let deceasedList = [];        // 所有逝者列表（来自 /api/memory）
let deceasedByZone = {};      // zone_id -> [entry, ...]
let memoryParticles = [];     // 晶柜周围的金色粒子
let memoryModal = null;       // 当前打开的记忆浮窗
let lastDeceasedFetch = 0;    // 上次拉取逝者列表的时间戳

function fetchDeceased() {
  fetch('/api/memory').then(r => r.json()).then(data => {
    deceasedList = data.deceased || [];
    deceasedByZone = {};
    for (const d of deceasedList) {
      const zid = d.death_zone_id || d.species || '';
      if (!deceasedByZone[zid]) deceasedByZone[zid] = [];
      deceasedByZone[zid].push(d);
    }
    lastDeceasedFetch = Date.now();
  }).catch(err => console.warn('拉取逝者失败:', err));
}

function initMemoryParticles() {
  memoryParticles = [];
  const ravenZone = ZONES.find(z => z.id === RAVEN_ZONE_ID);
  if (!ravenZone) return;
  const cx = (ravenZone.rect[0] + ravenZone.rect[2]) / 2;
  const cy = (ravenZone.rect[1] + ravenZone.rect[3]) / 2;
  for (let i = 0; i < 24; i++) {
    memoryParticles.push({
      ox: cx, oy: cy,
      angle: Math.random() * Math.PI * 2,
      radius: 1 + Math.random() * 4,
      speed: 0.003 + Math.random() * 0.008,
      yFloat: Math.random() * Math.PI * 2,
      size: 1 + Math.random() * 2,
    });
  }
}

function drawMemoryCrystals() {
  const ravenZone = ZONES.find(z => z.id === RAVEN_ZONE_ID);
  if (!ravenZone) return;
  const [x1, y1, x2, y2] = ravenZone.rect;
  const count = deceasedList.length;
  if (count === 0) {
    // 空档案室也画一行说明
    const p = isoToScreen((x1 + x2) / 2, (y1 + y2) / 2);
    ctx.fillStyle = 'rgba(212,165,116,.6)';
    ctx.font = (12 * view.zoom) + 'px "Fraunces", serif';
    ctx.textAlign = 'center';
    // 描边阴影让文字浮起（颜色跟随主题）
    ctx.fillStyle = THEME_COLORS.textShadow;
    ctx.fillText('档案室（暂无逝者）', p.x + 1, p.y - 24 * view.zoom + 1);
    ctx.fillStyle = 'rgba(212,165,116,.7)';
    ctx.fillText('档案室（暂无逝者）', p.x, p.y - 24 * view.zoom);
    return;
  }
  // 多行排列：每行最多 6 个晶体
  const perRow = Math.min(6, count);
  const rows = Math.ceil(count / perRow);
  const slotW = (x2 - x1) / perRow;
  const slotH = (y2 - y1) / Math.max(rows, 1);
  for (let i = 0; i < count; i++) {
    const row = Math.floor(i / perRow);
    const col = i % perRow;
    const cx = x1 + slotW * (col + 0.5);
    const cy = y1 + slotH * (row + 0.5);
    drawCrystal(cx, cy, deceasedList[i], i);
  }
}

function drawCrystal(ix, iy, entry, idx) {
  const p = isoToScreen(ix, iy);
  if (p.x < -50 || p.x > canvas.width + 50) return;
  if (p.y < -50 || p.y > canvas.height + 50) return;
  const colors = SPECIES_COLORS[entry.species] || {body: '#7A6E5C', accent: '#D4A574'};
  const size = 11 * view.zoom;
  const phase = (currentFrame + idx * 2) * 0.05;
  const yOff = Math.sin(phase) * 1.5;
  // 缓慢旋转
  const rot = phase * 0.3;
  const cx = p.x;
  const topY = p.y - 26 * view.zoom + yOff;
  const botY = p.y - 4 * view.zoom + yOff;
  // 顶/底面六边形的 6 个顶点
  const topPts = [], botPts = [];
  for (let i = 0; i < 6; i++) {
    const a = i * Math.PI / 3 - Math.PI / 2 + rot;
    topPts.push([cx + Math.cos(a) * size * 0.55, topY + Math.sin(a) * size * 0.55]);
    botPts.push([cx + Math.cos(a) * size, botY + Math.sin(a) * size]);
  }

  ctx.save();

  // === 底座阴影 ===
  ctx.fillStyle = 'rgba(0,0,0,.28)';
  ctx.beginPath();
  ctx.ellipse(cx, botY + 2, size * 1.05, size * 0.35, 0, 0, Math.PI * 2);
  ctx.fill();

  // === 外光晕（脉动琥珀柔光）===
  const pulse = 0.5 + Math.sin(phase * 2) * 0.5;
  const auraR = size * (2.0 + pulse * 0.3);
  const auraGrad = ctx.createRadialGradient(cx, (topY + botY) / 2, 0,
    cx, (topY + botY) / 2, auraR);
  auraGrad.addColorStop(0, 'rgba(212,165,116,' + (0.28 + pulse * 0.1) + ')');
  auraGrad.addColorStop(0.5, 'rgba(212,165,116,.08)');
  auraGrad.addColorStop(1, 'rgba(212,165,116,0)');
  ctx.fillStyle = auraGrad;
  ctx.beginPath();
  ctx.arc(cx, (topY + botY) / 2, auraR, 0, Math.PI * 2);
  ctx.fill();

  // === 6 个侧面（按深度排序：远→近，painter's algorithm）===
  // 计算每个面的中心 z（用顶点 y 估测），先画 y 小（远）的
  const faces = [];
  for (let i = 0; i < 6; i++) {
    const j = (i + 1) % 6;
    // 该面 4 顶点：topPts[i], topPts[j], botPts[j], botPts[i]
    const midY = (topPts[i][1] + topPts[j][1] + botPts[i][1] + botPts[j][1]) / 4;
    faces.push({i: i, j: j, midY: midY});
  }
  faces.sort((a, b) => a.midY - b.midY);

  // 用 shadeHex 给每个面不同的明度，模拟折射
  for (let f = 0; f < faces.length; f++) {
    const fi = faces[f];
    // 越靠前（midY 大）越亮；越靠后越暗
    const brightness = -0.35 + (f / (faces.length - 1)) * 0.55;  // -0.35 ~ +0.2
    const faceColor = shadeHex(colors.body, brightness);
    ctx.fillStyle = faceColor;
    ctx.beginPath();
    ctx.moveTo(topPts[fi.i][0], topPts[fi.i][1]);
    ctx.lineTo(topPts[fi.j][0], topPts[fi.j][1]);
    ctx.lineTo(botPts[fi.j][0], botPts[fi.j][1]);
    ctx.lineTo(botPts[fi.i][0], botPts[fi.i][1]);
    ctx.closePath();
    ctx.fill();
    // 描边
    ctx.strokeStyle = 'rgba(255,255,255,.08)';
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }

  // === 顶面（六边形，最亮）===
  ctx.fillStyle = shadeHex(colors.body, 0.35);
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    if (i === 0) ctx.moveTo(topPts[i][0], topPts[i][1]);
    else ctx.lineTo(topPts[i][0], topPts[i][1]);
  }
  ctx.closePath();
  ctx.fill();
  // 顶面高光（小白三角）
  ctx.fillStyle = 'rgba(255,255,255,.5)';
  ctx.beginPath();
  ctx.moveTo(topPts[5][0], topPts[5][1]);
  ctx.lineTo(topPts[0][0], topPts[0][1]);
  ctx.lineTo(topPts[1][0], topPts[1][1]);
  ctx.lineTo(cx, topY);
  ctx.closePath();
  ctx.fill();
  // 顶面描边
  ctx.strokeStyle = colors.accent;
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    if (i === 0) ctx.moveTo(topPts[i][0], topPts[i][1]);
    else ctx.lineTo(topPts[i][0], topPts[i][1]);
  }
  ctx.closePath();
  ctx.stroke();

  // === 顶部尖光点 ===
  ctx.fillStyle = '#FFF8E0';
  ctx.beginPath();
  ctx.arc(cx, topY, 1.2, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();

  // === 名字（前 2 字，serif 字体 + 阴影描边）===
  ctx.fillStyle = THEME_COLORS.textShadow;
  ctx.font = '500 ' + (10 * view.zoom) + 'px "Fraunces", serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const name = entry.name || '';
  const labelY = botY + 8;
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      if (dx === 0 && dy === 0) continue;
      ctx.fillText(name.slice(0, 2), cx + dx, labelY + dy);
    }
  }
  ctx.fillStyle = '#D4A574';
  ctx.fillText(name.slice(0, 2), cx, labelY);
}

function drawMemoryParticles() {
  if (memoryParticles.length === 0) return;
  for (const p of memoryParticles) {
    p.angle += p.speed;
    p.yFloat += 0.025;
    const ix = p.ox + Math.cos(p.angle) * p.radius;
    const iy = p.oy + Math.sin(p.angle) * p.radius + Math.sin(p.yFloat) * 0.5;
    const sp = isoToScreen(ix, iy);
    if (sp.x < -20 || sp.x > canvas.width + 20) continue;
    if (sp.y < -20 || sp.y > canvas.height + 20) continue;
    const alpha = 0.4 + Math.sin(p.yFloat) * 0.3;
    ctx.fillStyle = 'rgba(212,165,116,' + alpha + ')';
    ctx.beginPath();
    ctx.arc(sp.x, sp.y - 18 * view.zoom, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
}

// ============================================================
// commit 33：沉浸感三子系统渲染
// ============================================================

// 区域氛围着色：在情感聚集的 zone 地面铺一层极淡色调
function drawZoneAuraOverlay() {
  const zoneAura = atmosphereData.zone_aura || {};
  if (Object.keys(zoneAura).length === 0) return;
  for (const zoneId in zoneAura) {
    const zone = ZONES.find(z => z.id === zoneId);
    if (!zone) continue;
    const emos = zoneAura[zoneId];
    // 找最强的情感
    let maxEmo = '', maxVal = 0;
    for (const e in emos) {
      if (emos[e] > maxVal) { maxVal = emos[e]; maxEmo = e; }
    }
    if (maxVal < 0.3) continue;
    // 用情感对应颜色铺色
    const colorMap = {
      joy: [255, 196, 87],
      sadness: [130, 170, 230],
      anxiety: [160, 160, 170],
      contentment: [140, 210, 150],
      loneliness: [180, 180, 200],
      curiosity: [200, 150, 220],
    };
    const c = colorMap[maxEmo] || [200, 200, 200];
    const alpha = Math.min(0.15, maxVal * 0.1);
    const [x1, y1, x2, y2] = zone.rect;
    ctx.save();
    ctx.fillStyle = `rgba(${c[0]},${c[1]},${c[2]},${alpha.toFixed(3)})`;
    for (let ix = x1; ix <= x2; ix++) {
      for (let iy = y1; iy <= y2; iy++) {
        const p = isoToScreen(ix, iy);
        if (p.x < -50 || p.x > canvas.width + 50) continue;
        if (p.y < -50 || p.y > canvas.height + 50) continue;
        // 简化：每个 tile 画一个小菱形
        const ts = 32 * view.zoom;
        ctx.beginPath();
        ctx.moveTo(p.x, p.y - ts * 0.25);
        ctx.lineTo(p.x + ts * 0.5, p.y);
        ctx.lineTo(p.x, p.y + ts * 0.25);
        ctx.lineTo(p.x - ts * 0.5, p.y);
        ctx.closePath();
        ctx.fill();
      }
    }
    ctx.restore();
  }
}

// 氛围粒子：金色上升 / 蓝色飘落 / 灰色抖动
function drawAtmosphereParticles() {
  const particles = atmosphereData.particles || [];
  if (particles.length === 0) return;
  ctx.save();
  for (const p of particles) {
    // 粒子坐标在后端是世界坐标，转屏幕坐标
    const sp = isoToScreen(p.x, p.y);
    if (sp.x < -20 || sp.x > canvas.width + 20) continue;
    if (sp.y < -20 || sp.y > canvas.height + 20) continue;
    const lifeRatio = p.life / p.max_life;
    const alpha = Math.max(0, Math.min(1, lifeRatio)) * 0.7;
    const size = (p.size || 2) * view.zoom;
    if (p.kind === 'golden_float') {
      ctx.fillStyle = `rgba(255,196,87,${alpha.toFixed(3)})`;
    } else if (p.kind === 'blue_fall') {
      ctx.fillStyle = `rgba(130,170,230,${alpha.toFixed(3)})`;
    } else {  // gray_jitter
      ctx.fillStyle = `rgba(160,160,170,${alpha.toFixed(3)})`;
    }
    ctx.fillRect(sp.x - size/2, sp.y - size/2, size, size);
  }
  ctx.restore();
}

// 记忆碎片渲染：发光像素点，缓慢浮动
function drawMemoryFragments() {
  const frags = (fragmentsData.fragments || []);
  if (frags.length === 0) return;
  const t = performance.now() / 1000;
  ctx.save();
  for (const f of frags) {
    // 找到 zone 中心，加碎片坐标偏移
    const zone = ZONES.find(z => z.id === f.zone_id);
    let cx = 40, cy = 30;
    if (zone) {
      cx = (zone.rect[0] + zone.rect[2]) / 2;
      cy = (zone.rect[1] + zone.rect[3]) / 2;
    }
    // 用碎片 x,y 偏移（后端给的伪坐标已在 0-50 范围内）
    const fx = cx + ((f.x % 10) - 5) * 0.3;
    const fy = cy + ((f.y % 10) - 5) * 0.3;
    const sp = isoToScreen(fx, fy);
    if (sp.x < -30 || sp.x > canvas.width + 30) continue;
    if (sp.y < -30 || sp.y > canvas.height + 30) continue;

    // 浮动动画
    const floatY = Math.sin(t * 1.2 + f.id) * 4 * view.zoom;
    // 监工靠近时变亮（简化：用 hover 状态）
    const isHover = (hoveredFragmentId === f.id);
    const brightness = isHover ? 1.3 : 1.0;

    // 外层光晕
    const haloR = (isHover ? 14 : 10) * view.zoom;
    const haloGrad = ctx.createRadialGradient(
      sp.x, sp.y - 8 * view.zoom + floatY, 0,
      sp.x, sp.y - 8 * view.zoom + floatY, haloR
    );
    haloGrad.addColorStop(0, f.color || 'rgba(200,200,200,0.8)');
    haloGrad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = haloGrad;
    ctx.globalAlpha = 0.6 * brightness;
    ctx.beginPath();
    ctx.arc(sp.x, sp.y - 8 * view.zoom + floatY, haloR, 0, Math.PI * 2);
    ctx.fill();

    // 内核 3x3 像素点
    ctx.globalAlpha = 0.95 * brightness;
    const coreSize = 3 * view.zoom;
    ctx.fillStyle = f.color || 'rgba(255,255,255,0.9)';
    ctx.fillRect(sp.x - coreSize/2, sp.y - 8 * view.zoom + floatY - coreSize/2, coreSize, coreSize);

    // 遗物碎片：彩虹边缘
    if (f.is_relic) {
      ctx.globalAlpha = 0.5;
      const rainbow = `hsl(${(t * 60 + f.id * 30) % 360}, 80%, 70%)`;
      ctx.strokeStyle = rainbow;
      ctx.lineWidth = 1 * view.zoom;
      ctx.beginPath();
      ctx.arc(sp.x, sp.y - 8 * view.zoom + floatY, haloR * 1.2, 0, Math.PI * 2);
      ctx.stroke();
    }
  }
  ctx.restore();
}

// 当前鼠标悬停的碎片 id（用于变亮高亮）
let hoveredFragmentId = null;

// 点击碎片：弹出回忆面板
function clickFragmentAt(screenX, screenY) {
  const frags = (fragmentsData.fragments || []);
  if (frags.length === 0) return false;
  for (const f of frags) {
    const zone = ZONES.find(z => z.id === f.zone_id);
    let cx = 40, cy = 30;
    if (zone) {
      cx = (zone.rect[0] + zone.rect[2]) / 2;
      cy = (zone.rect[1] + zone.rect[3]) / 2;
    }
    const fx = cx + ((f.x % 10) - 5) * 0.3;
    const fy = cy + ((f.y % 10) - 5) * 0.3;
    const sp = isoToScreen(fx, fy);
    const dx = screenX - sp.x;
    const dy = screenY - (sp.y - 8 * view.zoom);
    if (dx * dx + dy * dy < 20 * 20) {  // 点击半径 20
      showFragmentPanel(f);
      return true;
    }
  }
  return false;
}

// 显示碎片回忆面板
function showFragmentPanel(f) {
  let panel = document.getElementById('fragment-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'fragment-panel';
    panel.style.cssText = 'position:fixed; top:50%; left:50%; transform:translate(-50%,-50%); background:rgba(20,20,30,0.95); color:#fff; padding:20px 24px; border-radius:12px; max-width:400px; box-shadow:0 8px 32px rgba(0,0,0,0.5); z-index:1000; font-size:14px; border:1px solid rgba(255,255,255,0.15);';
    document.body.appendChild(panel);
  }
  const date = new Date((f.time || 0) * 1000);
  const dateStr = date.toLocaleString('zh-CN');
  const typeLabel = {
    emotion_peak_joy: '快乐瞬间',
    emotion_peak_sadness: '悲伤时刻',
    emotion_peak_anxiety: '焦虑时刻',
    friendship: '友谊里程碑',
    milestone: '人生里程碑',
    death_relic: '遗物',
    supervisor_chat: '与监工的对话',
    social_dialogue: '私下对话',
  }[f.type] || '记忆';
  panel.innerHTML = `
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
      <div style="width:14px; height:14px; border-radius:50%; background:${f.color}; box-shadow:0 0 12px ${f.color};"></div>
      <h3 style="margin:0; font-size:16px;">${typeLabel}</h3>
      ${f.is_relic ? '<span style="color:#fff; opacity:0.6; font-size:11px;">遗物碎片</span>' : ''}
    </div>
    <div style="margin-bottom:8px; color:rgba(255,255,255,0.7); font-size:12px;">
      ${f.agent_name || ''}（${f.agent_species || ''}）
      ${f.related_agent_name ? ' · 与 ' + f.related_agent_name : ''}
    </div>
    <div style="line-height:1.6; margin-bottom:12px;">${f.text || ''}</div>
    <div style="font-size:11px; color:rgba(255,255,255,0.5); margin-bottom:16px;">${dateStr}</div>
    <div style="display:flex; gap:8px; justify-content:flex-end;">
      <button onclick="collectFragment(${f.id})" style="padding:6px 14px; background:rgba(94,114,228,0.8); color:#fff; border:none; border-radius:6px; cursor:pointer;">收藏到回忆录</button>
      <button onclick="document.getElementById('fragment-panel').style.display='none'" style="padding:6px 14px; background:rgba(255,255,255,0.1); color:#fff; border:none; border-radius:6px; cursor:pointer;">关闭</button>
    </div>
  `;
  panel.style.display = 'block';
}

// 收藏碎片
async function collectFragment(id) {
  try {
    const body = new URLSearchParams();
    body.append('id', id);
    const r = await fetch('/api/fragment/collect', {
      method: 'POST',
      body: body,
      credentials: 'same-origin',
    });
    const d = await r.json();
    if (d.ok) {
      showToast('已收藏到回忆录');
      document.getElementById('fragment-panel').style.display = 'none';
    } else {
      showToast('收藏失败');
    }
  } catch (e) {
    showToast('收藏失败');
  }
}

// ==================== commit 33：沉浸感设置面板 + 监工回忆录 + 屏幕晕影 ====================

// 打开沉浸感设置面板：从后端拉取当前设置，回填控件
async function openImmersivePanel() {
  const panel = document.getElementById('immersive-panel');
  panel.style.display = 'block';
  try {
    const r = await fetch('/api/immersive_settings', { credentials: 'same-origin' });
    const d = await r.json();
    const s = d.settings || {};
    if (s.aura_intensity != null) {
      const v = Math.round(s.aura_intensity * 100);
      document.getElementById('aura-slider').value = v;
      document.getElementById('aura-val').textContent = v;
    }
    if (s.particle_density) document.getElementById('particle-select').value = s.particle_density;
    if (s.fragment_density) document.getElementById('fragment-select').value = s.fragment_density;
    if (s.social_frequency) document.getElementById('social-select').value = s.social_frequency;
    if (s.bubble_speed) document.getElementById('bubble-select').value = s.bubble_speed;
  } catch (e) {
    // 拉取失败也允许显示面板，用默认值
  }
}

// 防抖保存（500ms）
let _immersiveSaveTimer = null;
function saveImmersiveSetting() {
  if (_immersiveSaveTimer) clearTimeout(_immersiveSaveTimer);
  _immersiveSaveTimer = setTimeout(() => {
    const payload = {
      atmosphere: {
        aura_intensity: document.getElementById('aura-slider').value / 100,
        particle_density: document.getElementById('particle-select').value,
      },
      fragments: {
        density: document.getElementById('fragment-select').value,
      },
      social: {
        frequency: document.getElementById('social-select').value,
        bubble_speed: document.getElementById('bubble-select').value,
      },
    };
    fetch('/api/immersive_settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'same-origin',
    }).then(() => {
      const tip = document.getElementById('immersive-tip');
      if (tip) {
        tip.textContent = '已保存 ✓';
        setTimeout(() => { tip.textContent = '设置保存到后端，刷新后生效。'; }, 1500);
      }
    }).catch(() => {});
  }, 500);
}

// 打开监工回忆录面板
async function openMemoirPanel() {
  const panel = document.getElementById('memoir-panel');
  panel.style.display = 'block';
  const listEl = document.getElementById('memoir-list');
  listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>';
  try {
    const r = await fetch('/api/memoir', { credentials: 'same-origin' });
    const d = await r.json();
    const items = d.fragments || [];
    if (items.length === 0) {
      listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">还没有收藏的记忆碎片<br>走到发光碎片旁点击它，然后收藏到回忆录</div>';
      return;
    }
    const typeLabel = {
      emotion_peak_joy: '快乐瞬间', emotion_peak_sadness: '悲伤时刻',
      emotion_peak_anxiety: '焦虑时刻', friendship: '友谊里程碑',
      milestone: '人生里程碑', death_relic: '遗物',
      supervisor_chat: '与监工的对话', social_dialogue: '私下对话',
    };
    listEl.innerHTML = items.map(f => {
      const dateStr = new Date((f.time || 0) * 1000).toLocaleString('zh-CN');
      const label = typeLabel[f.type] || '记忆';
      return `<div style="padding:12px 0; border-bottom:1px solid rgba(255,255,255,0.08);">
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
          <div style="width:10px; height:10px; border-radius:50%; background:${f.color}; box-shadow:0 0 8px ${f.color};"></div>
          <strong>${label}</strong>
          ${f.is_relic ? '<span style="font-size:10px; color:rgba(255,255,255,0.5);">遗物</span>' : ''}
        </div>
        <div style="font-size:11px; color:rgba(255,255,255,0.6); margin-bottom:4px;">${f.agent_name || ''}（${f.agent_species || ''}）${f.related_agent_name ? ' · 与 ' + f.related_agent_name : ''}</div>
        <div style="line-height:1.5;">${f.text || ''}</div>
        <div style="font-size:10px; color:rgba(255,255,255,0.4); margin-top:4px;">${dateStr}</div>
      </div>`;
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div style="color:#ff8080; text-align:center; padding:40px 0;">加载失败</div>';
  }
}

// 屏幕边缘情感晕影：监工靠近某智能体时，根据其主导情感染色屏幕边缘
function updateEmotionVignette() {
  const vig = document.getElementById('emotion-vignette');
  if (!vig) return;
  // 监工永远在 canvas 正中，找最近的员工
  const sw = getSupervisorPos();
  let nearestEmp = null;
  let nearestDist = 999;
  for (const emp of employees) {
    if (emp.alive === false) continue;
    const cx = (emp._wx != null ? emp._wx : 40);
    const cy = (emp._wy != null ? emp._wy : 30);
    const p = isoToScreen(cx, cy);
    const d = Math.hypot(p.x - sw.x, p.y - sw.y);
    if (d < nearestDist) { nearestDist = d; nearestEmp = emp; }
  }
  // 距离 < 80px 时显示晕影
  if (!nearestEmp || nearestDist > 80) {
    vig.style.display = 'none';
    return;
  }
  const emo = nearestEmp.emotional_state || {};
  // 找主导情感
  let maxK = '', maxV = 0;
  for (const k in emo) {
    if (emo[k] > maxV) { maxV = emo[k]; maxK = k; }
  }
  if (!maxK || maxV < 0.5) {
    vig.style.display = 'none';
    return;
  }
  const colorMap = {
    joy: '255,196,87', sadness: '130,170,230',
    anxiety: '160,160,170', contentment: '140,210,150',
    loneliness: '180,180,200', curiosity: '200,150,220',
  };
  const c = colorMap[maxK] || '200,200,200';
  // 距离越近，晕影越浓
  const intensity = (1 - nearestDist / 80) * Math.min(0.5, maxV * 0.5);
  vig.style.display = 'block';
  vig.style.boxShadow = `inset 0 0 200px rgba(${c},${intensity.toFixed(3)})`;
}

function drawRelicMarkers() {
  for (const zid in deceasedByZone) {
    if (zid === RAVEN_ZONE_ID) continue;  // 档案室本身用晶柜表示
    const zone = ZONES.find(z => z.id === zid);
    if (!zone) continue;
    const list = deceasedByZone[zid];
    const cx = (zone.rect[0] + zone.rect[2]) / 2;
    const cy = (zone.rect[1] + zone.rect[3]) / 2 + 3;
    const p = isoToScreen(cx, cy);
    if (p.x < -30 || p.x > canvas.width + 30) continue;
    if (p.y < -30 || p.y > canvas.height + 30) continue;

    const showCount = Math.min(list.length, 3);
    for (let i = 0; i < showCount; i++) {
      const ox = (i - (showCount - 1) / 2) * 1.6;
      const sp = isoToScreen(cx + ox, cy);
      drawTombstone(sp.x, sp.y, list[i]);
    }
    if (list.length > 3) {
      ctx.fillStyle = '#D4A574';
      ctx.font = (10 * view.zoom) + 'px "Fraunces", serif';
      ctx.textAlign = 'center';
      ctx.fillText('×' + list.length, p.x, p.y + 4);
    }
  }
}

function drawTombstone(x, y, entry) {
  const size = 6 * view.zoom;
  ctx.save();

  // === 投影 ===
  ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
  ctx.beginPath();
  ctx.ellipse(x, y + 1, size * 1.2, 1.8, 0, 0, Math.PI * 2);
  ctx.fill();

  // === 底座（梯形，2.5D）===
  ctx.fillStyle = '#3D3528';
  ctx.beginPath();
  ctx.moveTo(x - size, y);
  ctx.lineTo(x + size, y);
  ctx.lineTo(x + size * 0.85, y + 2.5);
  ctx.lineTo(x - size * 0.85, y + 2.5);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = '#2A2419';
  ctx.fillRect(x - size * 0.85, y + 2.5, size * 1.7, 0.6);

  // === 墓碑碑身（圆顶长碑，带渐变质感）===
  const grad = ctx.createLinearGradient(x, y - size * 2, x, y);
  grad.addColorStop(0, '#7A7268');
  grad.addColorStop(0.6, '#5C554E');
  grad.addColorStop(1, '#3F3A35');
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(x, y - size * 1.6, size * 0.7, Math.PI, 0);
  ctx.lineTo(x + size * 0.7, y);
  ctx.lineTo(x - size * 0.7, y);
  ctx.closePath();
  ctx.fill();
  // 琥珀描边
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.3)';
  ctx.lineWidth = 0.6;
  ctx.stroke();

  // === 碑顶十字小记号 ===
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.55)';
  ctx.lineWidth = 0.7;
  ctx.beginPath();
  ctx.moveTo(x, y - size * 1.45);
  ctx.lineTo(x, y - size * 1.15);
  ctx.moveTo(x - size * 0.15, y - size * 1.32);
  ctx.lineTo(x + size * 0.15, y - size * 1.32);
  ctx.stroke();

  // === 物种色点（中心圆，带柔光）===
  // commit 47：头像物种色点统一用 EMPLOYEE_COLOR_MAP（与员工衣服同源）
  const empColor = getEmployeeColor(entry.species);
  ctx.fillStyle = 'rgba(212, 165, 116, 0.18)';
  ctx.beginPath();
  ctx.arc(x, y - size * 0.9, size * 0.35, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = empColor;
  ctx.beginPath();
  ctx.arc(x, y - size * 0.9, size * 0.22, 0, Math.PI * 2);
  ctx.fill();

  // === 墓志铭（前 1 字，serif 字体 + 描边）===
  const epitaph = (entry.name || '').slice(0, 1);
  if (epitaph) {
    ctx.font = '500 ' + (6 * view.zoom) + 'px "Fraunces", serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(0,0,0,.5)';
    ctx.fillText(epitaph, x + 0.5, y - size * 0.9 + 0.5);
    ctx.fillStyle = '#E8E4D8';
    ctx.fillText(epitaph, x, y - size * 0.9);
  }

  // === 旁边一朵小花（茎 + 2 叶 + 5 花瓣）===
  const flowerX = x + size * 0.95;
  const flowerY = y - size * 0.1;
  // 茎
  ctx.strokeStyle = '#4A6B3A';
  ctx.lineWidth = 0.8;
  ctx.beginPath();
  ctx.moveTo(flowerX, flowerY + size * 0.5);
  ctx.quadraticCurveTo(flowerX + size * 0.05, flowerY + size * 0.2, flowerX, flowerY);
  ctx.stroke();
  // 左叶
  ctx.fillStyle = '#5A7B45';
  ctx.beginPath();
  ctx.ellipse(flowerX - size * 0.18, flowerY + size * 0.25, size * 0.18, size * 0.08,
    -0.5, 0, Math.PI * 2);
  ctx.fill();
  // 右叶
  ctx.beginPath();
  ctx.ellipse(flowerX + size * 0.18, flowerY + size * 0.1, size * 0.18, size * 0.08,
    0.5, 0, Math.PI * 2);
  ctx.fill();
  // 5 花瓣（琥珀色）
  ctx.fillStyle = colors.accent || '#D4A574';
  for (let i = 0; i < 5; i++) {
    const a = i * Math.PI * 2 / 5 - Math.PI / 2;
    const px = flowerX + Math.cos(a) * size * 0.18;
    const py = flowerY + Math.sin(a) * size * 0.18;
    ctx.beginPath();
    ctx.arc(px, py, size * 0.13, 0, Math.PI * 2);
    ctx.fill();
  }
  // 花蕊
  ctx.fillStyle = '#FFE4B5';
  ctx.beginPath();
  ctx.arc(flowerX, flowerY, size * 0.1, 0, Math.PI * 2);
  ctx.fill();

  ctx.restore();
}

function findCrystalAt(sx, sy) {
  const ravenZone = ZONES.find(z => z.id === RAVEN_ZONE_ID);
  if (!ravenZone) return null;
  const [x1, y1, x2, y2] = ravenZone.rect;
  const count = deceasedList.length;
  if (count === 0) return null;
  const perRow = Math.min(6, count);
  const rows = Math.ceil(count / perRow);
  const slotW = (x2 - x1) / perRow;
  const slotH = (y2 - y1) / Math.max(rows, 1);
  for (let i = 0; i < count; i++) {
    const row = Math.floor(i / perRow);
    const col = i % perRow;
    const cx = x1 + slotW * (col + 0.5);
    const cy = y1 + slotH * (row + 0.5);
    const p = isoToScreen(cx, cy);
    const cy0 = p.y - 18 * view.zoom;
    const size = 14 * view.zoom;
    const dx = sx - p.x;
    const dy = sy - cy0;
    if (dx * dx + dy * dy < size * size) {
      return {entry: deceasedList[i], index: i};
    }
  }
  return null;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;',
    '"': '&quot;', "'": '&#39;'
  }[c]));
}

function showMemoryModal(entry, index) {
  closeMemoryModal();
  const m = document.createElement('div');
  m.id = 'memory-modal';
  m.style.cssText = 'position:fixed;top:50%;left:50%;' +
    'transform:translate(-50%,-50%);background:rgba(13,20,16,.96);' +
    'backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);' +
    'border:1px solid rgba(212,165,116,.32);border-radius:16px;padding:32px;' +
    'width:480px;max-width:90vw;max-height:80vh;overflow-y:auto;' +
    'z-index:40;color:#E8E4D8;font-size:14px;font-family:"Manrope",sans-serif;' +
    'box-shadow:0 24px 64px rgba(0,0,0,.6)';
  const colors = SPECIES_COLORS[entry.species] || {body: '#7A6E5C', accent: '#D4A574'};
  // commit 47：花名册圆点统一用 EMPLOYEE_COLOR_MAP（与员工衣服同源）
  const empColor = getEmployeeColor(entry.species);
  const memoryCount = (entry.core_memory || []).length;
  m.innerHTML =
    '<div style="display:flex;justify-content:space-between;' +
      'align-items:baseline;margin-bottom:24px;padding-bottom:16px;' +
      'border-bottom:1px solid rgba(212,165,116,.18)">' +
      '<div>' +
        '<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">' +
          '<span style="display:inline-block;width:10px;height:10px;' +
            'border-radius:50%;background:' + empColor +
            ';box-shadow:0 0 12px ' + empColor + '"></span>' +
          '<h3 style="margin:0;font-family:"Fraunces",serif;font-weight:500;' +
            'font-size:22px;letter-spacing:.01em;color:#E8E4D8">' +
            escapeHtml(entry.name || '?') + '</h3>' +
        '</div>' +
        '<div style="font-size:11px;color:#A8A095;letter-spacing:.1em;' +
          'text-transform:uppercase">Memory · ' +
          escapeHtml(entry.species || '?') + '</div>' +
      '</div>' +
      '<button id="memory-close" style="background:transparent;color:#A8A095;' +
        'border:0;font-size:28px;cursor:pointer;line-height:1;padding:0 4px;' +
        'transition:color .2s">×</button>' +
    '</div>' +
    '<div style="margin-bottom:18px"><div style="font-size:10px;color:#A8A095;' +
      'letter-spacing:.12em;text-transform:uppercase;margin-bottom:4px">生平</div>' +
      '<div style="font-size:13px;line-height:1.6;color:#E8E4D8">' +
      escapeHtml(entry.life_summary || '（无记录）') + '</div></div>' +
    '<div style="margin-bottom:18px;padding:14px 16px;background:rgba(212,165,116,.06);' +
      'border-left:2px solid #D4A574;border-radius:0 6px 6px 0">' +
      '<div style="font-size:10px;color:#D4A574;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:6px;font-weight:600">遗言</div>' +
      '<div style="font-family:"Fraunces",serif;font-style:italic;font-size:14px;' +
        'line-height:1.6;color:#E8E4D8">' +
        escapeHtml(entry.last_words || '（无记录）') + '</div></div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px">' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:4px">死因</div>' +
        '<div style="font-size:13px;color:#E8E4D8">' +
        escapeHtml(entry.death_reason || 'unknown') + '</div></div>' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:4px">归档区</div>' +
        '<div style="font-size:13px;color:#E8E4D8;font-family:"JetBrains Mono",monospace">' +
        escapeHtml(entry.death_zone_id || '?') + '</div></div>' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:4px">享年</div>' +
        '<div style="font-size:13px;color:#D4A574;font-family:"JetBrains Mono",monospace">' +
        (entry.age_days || 0).toFixed(1) + ' 天</div></div>' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:4px">核心记忆</div>' +
        '<div style="font-size:13px;color:#D4A574;font-family:"JetBrains Mono",monospace">' +
        memoryCount + ' 条</div></div>' +
    '</div>' +
    (memoryCount > 0 ?
      '<details style="margin-bottom:20px"><summary style="cursor:pointer;' +
        'color:#A8A095;font-size:11px;letter-spacing:.08em;text-transform:uppercase;' +
        'padding:8px 0;transition:color .2s">展开核心记忆</summary><div style="margin-top:8px;' +
        'padding:14px 16px;background:rgba(0,0,0,.3);border-radius:8px;' +
        'font-size:12px;line-height:1.7;max-height:200px;overflow-y:auto;' +
        'font-family:"JetBrains Mono",monospace;color:#A8A095">' +
        (entry.core_memory || []).map(escapeHtml).join('<br><br>') +
        '</div></details>' : '') +
    '<div style="margin-top:8px">' +
      '<button id="narrate-btn" style="background:#D4A574;color:#0a0f0c;border:0;' +
        'padding:10px 24px;border-radius:999px;cursor:pointer;font-size:12px;' +
        'font-weight:600;letter-spacing:.04em;text-transform:uppercase;' +
        'transition:all .2s">' +
        '渡鸦讲述</button>' +
      '<div id="narrate-text" style="margin-top:14px;padding:16px 18px;' +
        'background:rgba(0,0,0,.3);border-radius:12px;display:none;' +
        'font-style:italic;line-height:1.7;font-family:"Fraunces",serif;' +
        'font-size:13px;color:#E8E4D8"></div>' +
    '</div>';
  document.body.appendChild(m);
  memoryModal = m;

  document.getElementById('memory-close').onclick = closeMemoryModal;
  document.getElementById('narrate-btn').onclick = function() {
    const btn = this;
    const txt = document.getElementById('narrate-text');
    btn.disabled = true;
    btn.textContent = '渡鸦翻档案中...';
    fetch('/api/narrate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({species: entry.species, index: index}),
    }).then(r => r.json()).then(data => {
      btn.disabled = false;
      btn.textContent = '重新讲述';
      txt.style.display = 'block';
      txt.innerHTML = '「' + escapeHtml(data.narration || data.reason || '（讲述失败）') +
        '」<div style="text-align:right;color:#D4A574;font-size:11px;' +
        'letter-spacing:.1em;text-transform:uppercase;margin-top:8px;font-family:"Manrope",sans-serif;font-style:normal">— 鸦·黑卷</div>';
    }).catch(err => {
      btn.disabled = false;
      btn.textContent = '渡鸦讲述';
      txt.style.display = 'block';
      txt.textContent = '讲述失败：' + err.message;
    });
  };
}

function closeMemoryModal() {
  if (memoryModal) {
    memoryModal.remove();
    memoryModal = null;
  }
}

// ==================== commit 14：招募可视化 ====================
// 零基础读者可以这样理解：当某物种员工死亡后，原岗位 zone 会被半透明
// 蒙版覆盖表示"空缺"，并显示状态图标（问号/沙漏/旋转齿轮）。
// zone 入口处会张贴招募海报。当新员工招募完成入职时，会从 zone 外
// 走入到岗位中心，并弹出"报到"提示。

let recruitStates = {};      // species -> "ALIVE"/"DEAD"/"PENDING"/"RECRUITING"
let recruitProgress = {};    // species -> 0.0~1.0
let lastRecruitFetch = 0;
let walkingIn = [];          // 正在走入岗位的新员工 [{species, name, x, y, tx, ty}]

function fetchRecruitStatus() {
  fetch('/api/recruit_status').then(r => r.json()).then(data => {
    recruitStates = data.states || {};
    recruitProgress = data.progress || {};
    lastRecruitFetch = Date.now();
  }).catch(err => console.warn('招募状态拉取失败:', err));
}

function drawRecruitOverlays() {
  for (const sp in recruitStates) {
    const state = recruitStates[sp];
    if (state === 'ALIVE') continue;
    const zone = ZONES.find(z => z.id === sp);
    if (!zone) continue;
    drawRecruitMask(zone, state, recruitProgress[sp] || 0, sp);
  }
}

function drawRecruitMask(zone, state, progress, species) {
  const [x1, y1, x2, y2] = zone.rect;
  // 半透明蒙版覆盖 zone 内所有 tile（夜森林版：琥珀色调）
  const maskColor = state === 'DEAD'
    ? 'rgba(201, 123, 90, 0.18)'
    : 'rgba(212, 165, 116, 0.22)';
  ctx.fillStyle = maskColor;
  for (let ix = x1; ix <= x2; ix++) {
    for (let iy = y1; iy <= y2; iy++) {
      const p = isoToScreen(ix, iy);
      if (p.x < -50 || p.x > canvas.width + 50) continue;
      if (p.y < -50 || p.y > canvas.height + 50) continue;
      const w = TILE_W * view.zoom / 2;
      const h = TILE_H * view.zoom / 2;
      ctx.beginPath();
      ctx.moveTo(p.x, p.y - h);
      ctx.lineTo(p.x + w, p.y);
      ctx.lineTo(p.x, p.y + h);
      ctx.lineTo(p.x - w, p.y);
      ctx.closePath();
      ctx.fill();
    }
  }

  // 状态图标在 zone 中心上方
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2;
  const p = isoToScreen(cx, cy);
  const iconY = p.y - 32 * view.zoom;
  const size = 14 * view.zoom;

  ctx.save();
  ctx.translate(p.x, iconY);

  if (state === 'DEAD') {
    // 问号图标（待招募，serif 字体）
    ctx.fillStyle = '#A8A095';
    ctx.font = '500 ' + (24 * view.zoom) + 'px "Fraunces", serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('?', 0, 0);
  } else if (state === 'PENDING') {
    // 沙漏（等待中，琥珀色）
    ctx.fillStyle = '#D4A574';
    ctx.beginPath();
    ctx.moveTo(-size, -size);
    ctx.lineTo(size, -size);
    ctx.lineTo(-size, size);
    ctx.lineTo(size, 2);
    ctx.closePath();
    ctx.fill();
    ctx.strokeStyle = '#D4A574';
    ctx.lineWidth = 1.5;
    ctx.stroke();
  } else if (state === 'RECRUITING') {
    // 旋转齿轮（招募中）
    const angle = currentFrame * 0.1;
    ctx.rotate(angle);
    ctx.fillStyle = '#D4A574';
    for (let i = 0; i < 8; i++) {
      ctx.rotate(Math.PI / 4);
      ctx.fillRect(-3, -size, 6, 5);
    }
    ctx.beginPath();
    ctx.arc(0, 0, size * 0.7, 0, Math.PI * 2);
    ctx.fill();
    // 进度环
    ctx.rotate(-angle);
    ctx.strokeStyle = '#D4A574';
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(0, 0, size * 1.3, -Math.PI / 2,
      -Math.PI / 2 + progress * Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();

  // 状态文字（serif 字体 + 阴影描边）
  ctx.fillStyle = THEME_COLORS.textShadow;
  ctx.font = '500 ' + (11 * view.zoom) + 'px "Fraunces", serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const stateText = {
    'DEAD': '岗位空缺',
    'PENDING': '招募待启动',
    'RECRUITING': '招募中 ' + Math.floor(progress * 100) + '%',
  }[state] || state;
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      if (dx === 0 && dy === 0) continue;
      ctx.fillText(stateText, p.x + dx, iconY + 28 * view.zoom + dy);
    }
  }
  ctx.fillStyle = '#D4A574';
  ctx.fillText(stateText, p.x, iconY + 28 * view.zoom);

  // 招募海报（zone 入口）
  drawRecruitPoster(zone, state, species);
}

function drawRecruitPoster(zone, state, species) {
  const [x1, y1, x2, y2] = zone.rect;
  // 海报位置：zone 左下角
  const ix = x1;
  const iy = y2;
  const p = isoToScreen(ix, iy);
  if (p.x < -30 || p.x > canvas.width + 30) return;
  if (p.y < -30 || p.y > canvas.height + 30) return;

  const w = 18 * view.zoom;
  const h = 24 * view.zoom;

  // 海报板背景（夜森林版：深木色 + 琥珀内框）
  ctx.fillStyle = '#3D3528';
  ctx.fillRect(p.x - w/2, p.y - h, w, h);
  // 海报内容
  ctx.fillStyle = state === 'RECRUITING'
    ? 'rgba(212, 165, 116, 0.9)'
    : 'rgba(168, 160, 149, 0.6)';
  ctx.fillRect(p.x - w/2 + 2, p.y - h + 2, w - 4, h - 4);
  // 文字
  ctx.fillStyle = '#3E2723';
  ctx.font = '600 ' + (8 * view.zoom) + 'px "Manrope", sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('招聘', p.x, p.y - h + 11);
  ctx.font = (7 * view.zoom) + 'px "JetBrains Mono", monospace';
  ctx.fillText(species.slice(0, 6), p.x, p.y - h + 20);
}

function drawWalkingIn() {
  for (let i = walkingIn.length - 1; i >= 0; i--) {
    const w = walkingIn[i];
    // 更新位置（朝目标走）
    const dx = w.tx - w.x;
    const dy = w.ty - w.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 0.3) {
      // 到达岗位
      walkingIn.splice(i, 1);
      showToast(w.name + ' 报到');
      continue;
    }
    w.x += dx * 0.04;
    w.y += dy * 0.04;

    // 画新员工精灵（使用员工精灵动画）
    const p = isoToScreen(w.x, w.y);
    if (p.x < -100 || p.x > canvas.width + 100) continue;
    if (p.y < -100 || p.y > canvas.height + 100) continue;
    // commit 26：新员工入场用 PNG 像素图集 idle 帧，加载失败回退矢量
    const pngFrame = getPngFrame(w.species, currentFrame % 2) || getSprite(w.species, currentFrame);
    const size = 64 * view.zoom;
    ctx.drawImage(pngFrame, p.x - size / 2, p.y - size, size, size);
    // 名字标签
    ctx.font = (10 * view.zoom) + 'px "Fraunces", serif';
    ctx.textAlign = 'center';
    const tagText = w.name + '（新入职）';
    ctx.fillStyle = THEME_COLORS.textShadow;
    for (let dx = -1; dx <= 1; dx++)
      for (let dy = -1; dy <= 1; dy++)
        if (dx || dy) ctx.fillText(tagText, p.x + dx, p.y - size - 4 + dy);
    ctx.fillStyle = '#D4A574';
    ctx.fillText(tagText, p.x, p.y - size - 4);
  }
}

function triggerWalkIn(species, name) {
  const zone = ZONES.find(z => z.id === species);
  if (!zone) return;
  // 起点：zone 左下角偏外
  const sx = zone.rect[0] - 2;
  const sy = zone.rect[3] + 2;
  // 终点：zone 中心
  const tx = (zone.rect[0] + zone.rect[2]) / 2;
  const ty = (zone.rect[1] + zone.rect[3]) / 2;
  walkingIn.push({
    species: species, name: name,
    x: sx, y: sy, tx: tx, ty: ty,
  });
}

// ==================== 动画循环 ====================
let lastFrameTime = 0;       // commit 15：上次推进 currentFrame 的时间戳
let lastAnimateTime = 0;     // commit 15：上次 animate 的时间戳，用于算 dt
const FRAME_INTERVAL = 80;   // commit 15：精灵帧动画间隔（ms），约 12fps
function animate(ts) {
  if (!ts) ts = performance.now();
  const dt = lastAnimateTime ? (ts - lastAnimateTime) / 1000 : 0;
  lastAnimateTime = ts;
  // commit 15：精灵帧动画节流（80ms 推一帧，省 5/6 重画）
  if (ts - lastFrameTime >= FRAME_INTERVAL) {
    currentFrame = (currentFrame + 1) % FRAMES;
    lastFrameTime = ts;
  }
  // commit 15：推进通用粒子池
  if (dt > 0 && dt < 1) updateActiveParticles(dt);
  // commit 17：推进天气（每 60 秒切换 + spawn 雨/雪粒子）
  updateWeather(ts);
  // commit 25 P3-5：推进鸟群
  updateBirdFlocks(ts, dt);
  // 每 10 秒刷新一次逝者列表
  if (Date.now() - lastDeceasedFetch > 10000) {
    fetchDeceased();
  }
  // 每 3 秒刷新一次招募状态
  if (Date.now() - lastRecruitFetch > 3000) {
    fetchRecruitStatus();
  }
  // commit 30：清理过期对话气泡
  cleanupExpiredBubbles();
  // commit 35：性能监控开始
  perfTickBegin();
  render();
  // commit 35：性能监控结束
  perfTickEnd();
  requestAnimationFrame(animate);
}

// ==================== 交互：拖拽 + 缩放 ====================
let dragStart = null;
let mouseDownPos = null;
stage.addEventListener('mousedown', e => {
  if (e.target !== stage && e.target !== canvas) return;
  dragStart = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
  mouseDownPos = { x: e.clientX, y: e.clientY };
  stage.classList.add('dragging');
});
window.addEventListener('mousemove', e => {
  if (dragStart) {
    view.x = dragStart.vx + (e.clientX - dragStart.x);
    view.y = dragStart.vy + (e.clientY - dragStart.y);
    saveView();
  } else {
    // 鼠标悬浮员工显示 tooltip
    const rect = canvas.getBoundingClientRect();
    const sx = e.clientX - rect.left;
    const sy = e.clientY - rect.top;
    let hovered = null;
    for (const emp of employees) emp._hover = false;
    for (const emp of employees) {
      // P1-2：使用员工真实走动位置 _wx/_wy
      const cx = (emp._wx != null ? emp._wx : 40);
      const cy = (emp._wy != null ? emp._wy : 30);
      const p = isoToScreen(cx, cy);
      const size = 64 * view.zoom;
      if (Math.abs(sx - p.x) < size / 2 && sy > p.y - size && sy < p.y) {
        hovered = emp;
        emp._hover = true;
        break;
      }
    }
    if (hovered) {
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 12) + 'px';
      tooltip.style.top = (e.clientY + 12) + 'px';
      // commit 30：情感/智慧/退休愿望/关系标签
      const emo = hovered.emotional_state || {};
      const topE = hovered.top_emotion || '';
      const emoLine = topE
        ? '主导情感: ' + topE + '<br>' +
          '快:' + _fmtEmo(emo.joy) + ' 悲:' + _fmtEmo(emo.sadness) +
          ' 焦:' + _fmtEmo(emo.anxiety) + '<br>' +
          '足:' + _fmtEmo(emo.contentment) + ' 孤:' + _fmtEmo(emo.loneliness) +
          ' 奇:' + _fmtEmo(emo.curiosity) + '<br>'
        : '';
      const wisdomLine = (hovered.wisdom != null)
        ? '智慧: ' + (+hovered.wisdom).toFixed(1) + '<br>'
        : '';
      const traumaLine = (hovered.trauma_events && hovered.trauma_events.length)
        ? '创伤: ' + hovered.trauma_events.join('、') + '<br>'
        : '';
      const wishLine = hovered.retirement_wish
        ? '退休愿望: ' + hovered.retirement_wish +
          (hovered.wish_fulfilled ? '（已实现）' : '') + '<br>'
        : '';
      const tagsLine = (hovered.relationship_tags &&
        Object.values(hovered.relationship_tags).flat().length)
        ? '关系: ' + Object.entries(hovered.relationship_tags)
            .map(([k,v]) => k + ':' + (v||[]).join(','))
            .join(' | ') + '<br>'
        : '';
      tooltip.innerHTML = '<b>' + (hovered.name || '?') + '</b><br>' +
        '物种: ' + (hovered.species || '?') + '<br>' +
        '阶段: ' + (hovered.stage || '?') + '<br>' +
        '能量: ' + (hovered.energy||0).toFixed(1) + '<br>' +
        '健康: ' + (hovered.health||0).toFixed(1) + '<br>' +
        '情绪: ' + (hovered.mood_score != null ? hovered.mood_score.toFixed(0) : '?') +
        ' / 100<br>' +
        emoLine +
        wisdomLine +
        traumaLine +
        wishLine +
        tagsLine +
        '好感: ' + (hovered.fondness != null ? hovered.fondness : '?') + '<br>' +
        '技能: ' + (hovered.skills && hovered.skills.length
          ? hovered.skills.join('、') : '无') + '<br>' +
        (hovered.illness
          ? '疾病: <span style="color:' + (hovered.illness.fatal ? '#ff8080' : '#ffb080') + ';">' +
            (hovered.illness.label || hovered.illness.kind || '生病中') +
            (hovered.illness.fatal ? '（致命）' : '') + '</span><br>'
          : '') +
        // commit 35：自我认知（联动3：自传体记忆→前端展示）
        (hovered.self_description
          ? '<i style="color:#b4a0dc;">' + hovered.self_description + '</i><br>'
          : '') +
        (hovered.life_goal
          ? '目标: <span style="color:#b4a0dc;">' + hovered.life_goal + '</span><br>'
          : '') +
        // commit 39：非正式角色徽章
        (hovered.informal_roles && hovered.informal_roles.length
          ? '角色: ' + hovered.informal_roles.map(r => {
              const map = {
                tech_leader: '🏆技术领袖', social_coordinator: '🤝社交协调员',
                supervisor_deputy: '🎖️监工副手', mentor: '🎓新人导师',
                crisis_handler: '⚡危机处理者', hermit: '🌙隐士',
              };
              return '<span style="background:rgba(180,140,255,0.2); color:#b488ff; padding:1px 6px; border-radius:6px; margin-right:4px;">' +
                (map[r] || r) + '</span>';
            }).join('') + '<br>'
          : '') +
        // commit 40：突变徽章
        (hovered.mutations && hovered.mutations.length
          ? '突变: <span style="background:rgba(255,215,0,0.2); color:#ffd700; padding:1px 6px; border-radius:6px;">✨ ' +
            hovered.mutations.length + '次</span> ' +
            hovered.mutations.slice(-2).map(m => (m.legendary ? '🌟' : '✨') + (m.name_zh || m.key || '')).join(' · ') + '<br>'
          : '') +
        '状态: ' + (hovered.alive ? '存活' : '已故');
    } else {
      tooltip.style.display = 'none';
    }
    // commit 33：检测鼠标是否悬停在记忆碎片上
    hoveredFragmentId = null;
    const frags = (fragmentsData.fragments || []);
    for (const f of frags) {
      const zone = ZONES.find(z => z.id === f.zone_id);
      let cx = 40, cy = 30;
      if (zone) {
        cx = (zone.rect[0] + zone.rect[2]) / 2;
        cy = (zone.rect[1] + zone.rect[3]) / 2;
      }
      const fx = cx + ((f.x % 10) - 5) * 0.3;
      const fy = cy + ((f.y % 10) - 5) * 0.3;
      const sp = isoToScreen(fx, fy);
      const dx = sx - sp.x;
      const dy = sy - (sp.y - 8 * view.zoom);
      if (dx * dx + dy * dy < 18 * 18) {
        hoveredFragmentId = f.id;
        canvas.style.cursor = 'pointer';
        break;
      }
    }
    if (hoveredFragmentId === null && !dragStart) {
      canvas.style.cursor = '';
    }
    // commit 25 P3-4：检测鼠标在哪个 zone
    const iso = screenToIso(sx, sy);
    hoveredZone = findZone(iso.x, iso.y);
  }
});
window.addEventListener('mouseup', e => {
  // commit 13：松开时若几乎没拖动，则判定为点击 → 检测晶柜
  if (mouseDownPos) {
    const dx = e.clientX - mouseDownPos.x;
    const dy = e.clientY - mouseDownPos.y;
    if (dx * dx + dy * dy < 25) {  // 移动 < 5px
      const rect = canvas.getBoundingClientRect();
      const sx = e.clientX - rect.left;
      const sy = e.clientY - rect.top;
      // commit 33：优先检测记忆碎片点击（在晶柜/员工之前）
      if (clickFragmentAt(sx, sy)) {
        // 已处理，跳出
      } else {
        const hit = findCrystalAt(sx, sy);
        if (hit) {
          showMemoryModal(hit.entry, hit.index);
        } else {
          // commit 16：未点中晶柜则检测员工点击 → 选中并执行当前工具
          const emp = findEmployeeAt(sx, sy);
          if (emp) {
            selectEmployee(emp);
            executeTool(currentTool, emp);
            // commit 35：日记彩蛋（3 次连续点击同一员工）
            checkDiaryEasterEgg(emp);
            // commit 36：点击缩放脉冲反馈（持续 0.18 秒）
            emp._clickPulse = performance.now() + 180;
            // commit 36：双击同一员工 → 镜头平滑飞至该员工并放大 2x
            const now = performance.now();
            if (_lastClickEmpId === (emp.agent_id || emp.species || emp.name)
                && now - _lastClickTs < 400) {
              flyToEmployee(emp);
            }
            _lastClickEmpId = emp.agent_id || emp.species || emp.name;
            _lastClickTs = now;
          } else {
            // commit 36：点击空白地面 → 目标位置闪烁标记
            spawnGroundMarker(sx, sy);
          }
        }
      }
    }
  }
  dragStart = null;
  mouseDownPos = null;
  stage.classList.remove('dragging');
});

// commit 16：检测屏幕坐标处的员工
function findEmployeeAt(sx, sy) {
  for (const emp of employees) {
    if (emp.alive === false) continue;
    // P1-2：使用员工真实走动位置 _wx/_wy
    const cx = (emp._wx != null ? emp._wx : 40);
    const cy = (emp._wy != null ? emp._wy : 30);
    const p = isoToScreen(cx, cy);
    const size = 64 * view.zoom;
    if (Math.abs(sx - p.x) < size / 2 && sy > p.y - size && sy < p.y) {
      return emp;
    }
  }
  return null;
}
stage.addEventListener('wheel', e => {
  e.preventDefault();
  const oldZoom = view.zoom;
  // commit 36：缩放灵敏度从设置项读取（1=慢, 2=中, 3=快, 4=超快, 5=极速）
  const sens = polishSettings.zoomSens || 2;
  const baseStep = 1.0 + 0.05 * sens;       // 1.05 ~ 1.25
  const delta = e.deltaY < 0 ? baseStep : (1 / baseStep);
  // commit 41：minZoom 提到 1.0（最多看 8×8 格子）
  view.zoom = Math.max(1.0, Math.min(2.5, view.zoom * delta));
  // 以鼠标为中心缩放
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  view.x = mx - (mx - view.x) * (view.zoom / oldZoom);
  view.y = my - (my - view.y) * (view.zoom / oldZoom);
  saveView();
}, { passive: false });

// ==================== commit 18：移动端触摸支持 ====================
// 单指拖拽平移视角，双指捏合缩放，短按点员工/晶柜
let touchState = null;
stage.addEventListener('touchstart', e => {
  if (e.target !== stage && e.target !== canvas) return;
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const touches = Array.from(e.touches).map(t => ({
    x: t.clientX - rect.left, y: t.clientY - rect.top,
    cx: t.clientX, cy: t.clientY,
  }));
  if (touches.length === 1) {
    touchState = {
      mode: 'pan',
      start: touches[0],
      vx: view.x, vy: view.y,
      startTime: performance.now(),
    };
  } else if (touches.length === 2) {
    const dx = touches[1].x - touches[0].x;
    const dy = touches[1].y - touches[0].y;
    touchState = {
      mode: 'pinch',
      dist: Math.hypot(dx, dy),
      zoom: view.zoom,
      mid: { x: (touches[0].x + touches[1].x) / 2,
             y: (touches[0].y + touches[1].y) / 2 },
    };
  }
}, { passive: false });

stage.addEventListener('touchmove', e => {
  if (!touchState) return;
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const touches = Array.from(e.touches).map(t => ({
    x: t.clientX - rect.left, y: t.clientY - rect.top,
  }));
  if (touchState.mode === 'pan' && touches.length >= 1) {
    view.x = touchState.vx + (touches[0].x - touchState.start.x);
    view.y = touchState.vy + (touches[0].y - touchState.start.y);
    saveView();
  } else if (touchState.mode === 'pinch' && touches.length >= 2) {
    const dx = touches[1].x - touches[0].x;
    const dy = touches[1].y - touches[0].y;
    const dist = Math.hypot(dx, dy);
    const oldZoom = view.zoom;
    // commit 41：minZoom 提到 1.0
    view.zoom = Math.max(1.0, Math.min(2.5,
      touchState.zoom * (dist / touchState.dist)));
    // 以双指中点为中心缩放
    const mx = touchState.mid.x;
    const my = touchState.mid.y;
    view.x = mx - (mx - view.x) * (view.zoom / oldZoom);
    view.y = my - (my - view.y) * (view.zoom / oldZoom);
    saveView();
  }
}, { passive: false });

stage.addEventListener('touchend', e => {
  if (!touchState) return;
  // 单指短按（< 300ms 且位移 < 10px）→ 判定为点击
  if (touchState.mode === 'pan') {
    const dt = performance.now() - touchState.startTime;
    const rect = canvas.getBoundingClientRect();
    const lastTouch = e.changedTouches[0];
    if (lastTouch && dt < 300) {
      const sx = lastTouch.clientX - rect.left;
      const sy = lastTouch.clientY - rect.top;
      const dx = sx - touchState.start.x;
      const dy = sy - touchState.start.y;
      if (dx * dx + dy * dy < 100) {  // 移动 < 10px
        const hit = findCrystalAt(sx, sy);
        if (hit) {
          showMemoryModal(hit.entry, hit.index);
        } else {
          const emp = findEmployeeAt(sx, sy);
          if (emp) {
            selectEmployee(emp);
            executeTool(currentTool, emp);
            // commit 35：日记彩蛋（移动端 3 次短按）
            checkDiaryEasterEgg(emp);
          }
        }
      }
    }
  }
  // 若还有剩余手指，重新初始化 touchState
  if (e.touches.length === 0) {
    touchState = null;
  } else if (e.touches.length === 1 && touchState.mode === 'pinch') {
    // 双指变单指：转为 pan
    const rect = canvas.getBoundingClientRect();
    const t = e.touches[0];
    touchState = {
      mode: 'pan',
      start: { x: t.clientX - rect.left, y: t.clientY - rect.top,
               cx: t.clientX, cy: t.clientY },
      vx: view.x, vy: view.y,
      startTime: performance.now(),
    };
  }
}, { passive: false });

document.getElementById('zoom-in').onclick = () => {
  view.zoom = Math.min(2.5, view.zoom * 1.2);
  saveView();
};
document.getElementById('zoom-out').onclick = () => {
  view.zoom = Math.max(0.3, view.zoom / 1.2);
  saveView();
};
document.getElementById('zoom-reset').onclick = () => {
  view = { x: -200, y: -100, zoom: 1 };
  saveView();
};

// ==================== 员工列表点击定位 ====================
function renderEmployeeList() {
  const list = document.getElementById('employee-list');
  list.innerHTML = '';
  for (const emp of employees) {
    const row = document.createElement('div');
    row.className = 'employee-row' + (emp.alive ? '' : ' dead') +
                    (emp.busy ? ' busy' : '');
    const colors = SPECIES_COLORS[emp.species] || {body: '#7A6E5C'};
    // commit 47：员工行圆点统一用 EMPLOYEE_COLOR_MAP（与员工衣服同源）
    const empColor = getEmployeeColor(emp.species);
    // commit 19 P0-1/P0-2：显示情绪值（M）和技能数（S）
    const moodStr = (emp.mood_score != null)
      ? ' M' + emp.mood_score.toFixed(0) : '';
    const skillStr = (emp.skills && emp.skills.length)
      ? ' S' + emp.skills.length : '';
    row.innerHTML = '<span class="name-part"><span class="dot" style="background:' +
                    empColor + ';color:' + empColor + '"></span>' + (emp.name || '?') + '</span>' +
                    '<span class="stat-part">E' + (emp.energy||0).toFixed(0) +
                    ' H' + (emp.health||0).toFixed(0) +
                    moodStr + skillStr + '</span>';
    row.onclick = () => {
      // 定位到该员工所属 zone
      const zone = ZONES.find(z => z.id === SPECIES_TO_ZONE[emp.species]);
      if (zone) {
        const cx = (zone.rect[0] + zone.rect[2]) / 2;
        const cy = (zone.rect[1] + zone.rect[3]) / 2;
        // 把 (cx, cy) 放到屏幕中央
        view.x = canvas.width / 2 - (cx - cy) * TILE_W / 2 * view.zoom;
        view.y = canvas.height / 2 - (cx + cy) * TILE_H / 2 * view.zoom;
        saveView();
        showToast('已定位到 ' + (emp.name || ''));
      }
      // commit 16：选中员工
      selectEmployee(emp);
    };
    list.appendChild(row);
  }
}

function renderEnvStats() {
  const el = document.getElementById('env-stats');
  const e = envStats || {};
  // commit 29：增加天气 + 植物 + 昆虫 + 活跃生态事件显示
  const weatherLabel = e.weather_label || e.weather || '晴';
  const weatherIcon = {
    sunny: '☀', cloudy: '☁', light_rain: '🌦', heavy_rain: '⛈',
    snow: '❄', hot: '🔥', cold: '🥶'
  }[e.weather] || '☀';
  const plant = e.plant_biomass != null ? e.plant_biomass.toFixed(0) : '—';
  const insects = e.insect_count != null ? e.insect_count : '—';
  el.innerHTML =
    '<div class="stat-row"><span>' + weatherIcon + ' 天气</span><b>' + weatherLabel + '</b></div>' +
    '<div class="stat-row"><span>食物</span><b>' + (e.food_available||0).toFixed(0) + '</b></div>' +
    '<div class="stat-row"><span>🌱 植物</span><b>' + plant + '</b></div>' +
    '<div class="stat-row"><span>🐛 昆虫</span><b>' + insects + '</b></div>' +
    '<div class="stat-row"><span>种群</span><b>' + (e.population_count||0) + '</b></div>';
  // commit 16：刷新全局统计面板
  updateGlobalStats();
}

// ==================== commit 29：生态系统面板 ====================
let ecoData = null;        // /api/eco 返回的完整生态数据
let ecoDataTimer = null;   // 定时器

// commit 30：情感与关系系统状态
//   activeBubbles: 当前活跃的对话气泡 [{id, speaker, text, target, expireTs}]
//   emotionsData: /api/emotions 返回的全员情感汇总
//   relationshipsData: /api/relationships 返回的关系网络
//   relicsData: /api/relics 返回的遗物列表
let activeBubbles = [];
let emotionsData = null;
let relationshipsData = null;
let relicsData = null;
let emotionsTimer = null;
let relationshipsTimer = null;

function fetchEcoData() {
  // 拉取生态系统数据
  fetch('/api/eco', { credentials: 'same-origin' })
    .then(r => r.json())
    .then(d => { ecoData = d; renderEcoStats(); })
    .catch(() => {});
}

function renderEcoStats() {
  const el = document.getElementById('eco-stats');
  if (!el) return;
  const d = ecoData;
  if (!d) {
    el.innerHTML = '<div class="stat-row"><span>加载中...</span></div>';
    return;
  }
  // 活跃生态事件
  const events = d.active_eco_events || [];
  let html = '';
  if (events.length > 0) {
    html += '<div class="stat-row" style="color:#D4A574;font-weight:600">📜 进行中事件</div>';
    for (const ev of events.slice(0, 3)) {
      const remain = Math.ceil((ev.remaining_sec || 0) / 60);
      const target = ev.target ? '·' + ev.target : '';
      html += '<div class="stat-row"><span>' + ev.label + target + '</span><b>' + remain + '分</b></div>';
    }
  }
  // 今日统计
  const stats = d.eco_stats || {};
  html += '<div class="stat-row"><span>食物峰谷</span><b>' +
    (stats.food_peak||0).toFixed(0) + '/' + (stats.food_valley||0).toFixed(0) + '</b></div>';
  html += '<div class="stat-row"><span>🌱 今日生长</span><b>' +
    (stats.plant_total||0).toFixed(0) + '</b></div>';
  // 今日事件数
  const evCount = (stats.events_today || []).length;
  html += '<div class="stat-row"><span>今日事件</span><b>' + evCount + '</b></div>';
  // 互动排行 Top 3
  const rank = stats.interaction_rank || [];
  if (rank.length > 0) {
    html += '<div class="stat-row" style="color:#9B88B0;font-weight:600">🤝 互动 Top 3</div>';
    for (const r of rank.slice(0, 3)) {
      html += '<div class="stat-row"><span>' + r.pair + '</span><b>' + r.count + '</b></div>';
    }
  }
  // 区域热度 Top 3
  const zones = stats.popular_zones || [];
  if (zones.length > 0) {
    html += '<div class="stat-row" style="color:#9B88B0;font-weight:600">🔥 热门区域</div>';
    for (const z of zones.slice(0, 3)) {
      const min = Math.floor(z.seconds / 60);
      html += '<div class="stat-row"><span>' + z.zone + '</span><b>' + min + '分</b></div>';
    }
  }
  el.innerHTML = html || '<div class="stat-row"><span>暂无数据</span></div>';
}

function startEcoDataPolling() {
  // 每 15 秒拉一次生态数据
  if (ecoDataTimer) clearInterval(ecoDataTimer);
  fetchEcoData();
  ecoDataTimer = setInterval(fetchEcoData, 15000);
}

// ==================== commit 16：交互细化 ====================
// 零基础读者可以这样理解：
// 1) 5 个工具按钮 + 1-5 快捷键 + 空格居中：监工用键盘也能操作
// 2) 监工位置：永远在屏幕正中（用户视角中心），画一个金色光标
// 3) 监工反应：执行操作时监工上方冒一个气泡显示文字
// 4) 投喂粒子：投喂时从监工位置 spawn 6 个零食粒子飞向员工
// 5) 小地图：左下角 160×120 缩略图，显示整个地图 + 当前视野框
// 6) 全局统计：status-panel 顶部显示活体/死亡/招募中数量

let selectedEmployee = null;       // 当前选中的员工
let hoveredZone = null;            // commit 25 P3-4：鼠标悬停的 zone
let currentTool = settings.tool || 'greet';  // commit 18：从 settings 恢复
let supervisorReaction = null;      // 监工反应气泡 {text, time, dur}
// commit 26：监工 PNG sprite 动画状态
// state: 'idle' 默认；'react' 执行操作时短暂切换；'work' 持续工作中
let supervisorState = 'idle';
let supervisorStateUntil = 0;  // 状态过期时间戳（ms），0 表示不过期
let birdFlocks = [];               // commit 25 P3-5：天空中的鸟群
let lastBirdSpawn = 0;             // 上次鸟群 spawn 时间

const minimapCanvas = document.getElementById('minimap-canvas');
const minimapCtx = minimapCanvas.getContext('2d');

function updateGlobalStats() {
  const el = document.getElementById('global-stats');
  if (!el) return;
  const alive = employees.filter(e => e.alive !== false).length;
  const dead = deceasedList.length;
  const recruiting = Object.values(recruitStates).filter(s => s && s !== 'ALIVE').length;
  const total = Object.keys(recruitStates).length || 11;
  el.innerHTML =
    '<div class="gs-row"><span>活体</span><b>' + alive + '/' + total + '</b></div>' +
    '<div class="gs-row"><span>逝者</span><b>' + dead + '</b></div>' +
    '<div class="gs-row"><span>招募中</span><b>' + recruiting + '</b></div>';
}

function getSupervisorPos() {
  // 监工永远在 canvas 正中（用户视角中心）
  return { x: canvas.width / 2, y: canvas.height / 2 };
}

function showSupervisorReaction(text, dur) {
  supervisorReaction = {text: text, time: Date.now(), dur: dur || 1500};
  // commit 26：监工执行操作时切到 react 帧（持续到气泡结束）
  supervisorState = 'react';
  supervisorStateUntil = Date.now() + (dur || 1500);
}

// ==================== P2-1：员工详情卡 ====================
let employeeCardModal = null;
let employeeCardRefreshTimer = null;

const LIFE_STAGE_LABEL = {
  'baby': '幼年',
  'child': '童年',
  'youth': '少年',
  'adult': '成年',
  'middle': '中年',
  'elderly': '老年',
};

function speciesLabel(s) {
  const map = {
    deer: '鹿·总管', fox: '狐·测试', butterfly: '蝶·设计',
    squirrel: '松鼠·开发', hedgehog: '刺猬·安全', raven: '鸦·归档',
    hare: '兔·核算', badger: '獾·路由', lark: '雀·监控',
    kite: '鸢·规划', beaver: '海狸·部署',
  };
  return map[s] || s;
}

function taskTypeLabel(tt) {
  const map = {
    deploy: '部署服务', test: '自动化测试', ui_design: 'UI 设计',
    code: '编码开发', security_scan: '安全扫描', archive: '归档记忆',
    audit: '资源核算', route: '工具路由', monitor: '状态监控',
    plan: '任务规划', dispatch: '总管调度',
  };
  return map[tt] || tt;
}

function barStyle(pct, color) {
  // 0-100 百分比条
  const c = color || '#D4A574';
  return '<div style="height:6px;background:rgba(212,165,116,.1);' +
    'border-radius:3px;overflow:hidden;margin-top:4px">' +
    '<div style="width:' + Math.max(0, Math.min(100, pct)) + '%;height:100%;' +
    'background:' + c + ';border-radius:3px;transition:width .4s"></div></div>';
}

function selectEmployee(emp) {
  selectedEmployee = emp;
  showEmployeeCard(emp);
  showQuickMenu(emp);  // commit 44-1：弹出快捷交互菜单
}

function showEmployeeCard(emp) {
  closeEmployeeCard();
  if (!emp) return;
  const m = document.createElement('div');
  m.id = 'employee-card-modal';
  m.style.cssText = 'position:fixed;top:50%;left:50%;' +
    'transform:translate(-50%,-50%);background:rgba(13,20,16,.96);' +
    'backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);' +
    'border:1px solid rgba(212,165,116,.32);border-radius:16px;padding:28px;' +
    'width:420px;max-width:90vw;max-height:80vh;overflow-y:auto;' +
    'z-index:35;color:#E8E4D8;font-size:14px;font-family:"Manrope",sans-serif;' +
    'box-shadow:0 24px 64px rgba(0,0,0,.6)';
  m.dataset.empId = emp.id || '';
  document.body.appendChild(m);
  employeeCardModal = m;
  renderEmployeeCard(emp);

  // 每 1.5s 刷新一次（能量/健康/状态会变化）
  employeeCardRefreshTimer = setInterval(() => {
    if (!employeeCardModal || !document.body.contains(employeeCardModal)) {
      clearInterval(employeeCardRefreshTimer);
      return;
    }
    renderEmployeeCard(emp);
  }, 1500);
}

function renderEmployeeCard(emp) {
  const m = employeeCardModal;
  if (!m || !emp) return;
  const colors = SPECIES_COLORS[emp.species] || {body: '#7A6E5C', accent: '#D4A574'};
  const stageLabel = LIFE_STAGE_LABEL[emp.stage] || LIFE_STAGE_LABEL[emp.life_stage] || emp.stage || '?';
  const isAlive = emp.alive !== false;
  const ageDays = emp.age_days != null ? emp.age_days : (emp.age || 0);
  const energy = emp.energy || 0;
  const health = emp.health || 0;
  const mood = emp.mood_score != null ? emp.mood_score : 0;
  const fond = emp.fondness != null ? emp.fondness : 0;
  const skills = (emp.skills && emp.skills.length) ? emp.skills : [];
  const taskType = emp.task_type || '';
  const memoryCount = (emp.core_memory || emp.memory || []).length;

  m.innerHTML =
    '<div style="display:flex;justify-content:space-between;' +
      'align-items:flex-start;margin-bottom:20px;padding-bottom:14px;' +
      'border-bottom:1px solid rgba(212,165,116,.18)">' +
      '<div style="display:flex;gap:12px;align-items:center">' +
        '<canvas width="56" height="56" id="emp-card-portrait" ' +
          'style="border-radius:12px;background:rgba(212,165,116,.06);' +
          'border:1px solid rgba(212,165,116,.18)"></canvas>' +
        '<div>' +
          '<h3 style="margin:0 0 4px;font-family:"Fraunces",serif;font-weight:500;' +
            'font-size:20px;letter-spacing:.01em;color:' +
            (isAlive ? '#E8E4D8' : '#8A8278') + '">' +
            escapeHtml(emp.name || '?') + '</h3>' +
          '<div style="font-size:11px;color:#A8A095;letter-spacing:.1em;' +
            'text-transform:uppercase">' + speciesLabel(emp.species) +
            ' · ' + stageLabel + '</div>' +
        '</div>' +
      '</div>' +
      '<button id="emp-card-close" style="background:transparent;color:#A8A095;' +
        'border:0;font-size:24px;cursor:pointer;line-height:1;padding:0 4px;' +
        'transition:color .2s">×</button>' +
    '</div>' +
    '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 16px;margin-bottom:18px">' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:2px">年龄</div>' +
        '<div style="font-size:14px;color:#D4A574;font-family:"JetBrains Mono",monospace">' +
        ageDays.toFixed(1) + ' 天</div></div>' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:2px">状态</div>' +
        '<div style="font-size:14px;color:' + (isAlive ? '#7FB069' : '#8A8278') + '">' +
        (isAlive ? '存活' : '已故') + '</div></div>' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:2px">当前任务</div>' +
        '<div style="font-size:13px;color:' + (emp.busy ? '#D4A574' : '#8A8278') + '">' +
        (emp.busy && taskType ? taskTypeLabel(taskType) :
          (emp.busy ? '忙碌中' : '空闲')) + '</div></div>' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:2px">核心记忆</div>' +
        '<div style="font-size:14px;color:#D4A574;font-family:"JetBrains Mono",monospace">' +
        memoryCount + ' 条</div></div>' +
      '<div><div style="font-size:10px;color:#A8A095;letter-spacing:.12em;' +
        'text-transform:uppercase;margin-bottom:2px">特有行为</div>' +
        '<div style="font-size:13px;color:' +
        (emp.current_behavior ? '#9B88B0' : '#8A8278') + '">' +
        (emp.current_behavior_label || '无') + '</div></div>' +
    '</div>' +
    '<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;' +
      'font-size:10px;color:#A8A095;letter-spacing:.12em;text-transform:uppercase">' +
      '<span>能量</span><span style="color:#D4A574;font-family:"JetBrains Mono",monospace">' +
      energy.toFixed(0) + '</span></div>' +
      barStyle(energy, '#D4A574') + '</div>' +
    '<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;' +
      'font-size:10px;color:#A8A095;letter-spacing:.12em;text-transform:uppercase">' +
      '<span>健康</span><span style="color:#7FB069;font-family:"JetBrains Mono",monospace">' +
      health.toFixed(0) + '</span></div>' +
      barStyle(health, '#7FB069') + '</div>' +
    '<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;' +
      'font-size:10px;color:#A8A095;letter-spacing:.12em;text-transform:uppercase">' +
      '<span>情绪</span><span style="color:#E8C77A;font-family:"JetBrains Mono",monospace">' +
      mood.toFixed(0) + ' / 100</span></div>' +
      barStyle(mood, '#E8C77A') + '</div>' +
    '<div style="margin-bottom:18px"><div style="display:flex;justify-content:space-between;' +
      'font-size:10px;color:#A8A095;letter-spacing:.12em;text-transform:uppercase">' +
      '<span>对监工好感</span><span style="color:#E0A4B4;font-family:"JetBrains Mono",monospace">' +
      fond.toFixed(0) + '</span></div>' +
      barStyle(fond, '#E0A4B4') + '</div>' +
    '<div style="margin-bottom:18px"><div style="font-size:10px;color:#A8A095;' +
      'letter-spacing:.12em;text-transform:uppercase;margin-bottom:6px">技能</div>' +
      '<div style="display:flex;flex-wrap:wrap;gap:6px">' +
      (skills.length ? skills.map(s => '<span style="display:inline-block;' +
        'padding:4px 10px;background:rgba(212,165,116,.1);border:1px solid ' +
        'rgba(212,165,116,.25);border-radius:999px;font-size:11px;color:#D4A574;' +
        'font-family:"JetBrains Mono",monospace">' + escapeHtml(s) + '</span>').join('') :
        '<span style="color:#8A8278;font-size:12px">无</span>') +
      '</div></div>' +
    (emp.life_summary ?
      '<div style="margin-bottom:14px;padding:12px 14px;background:rgba(212,165,116,.06);' +
        'border-left:2px solid #D4A574;border-radius:0 6px 6px 0">' +
        '<div style="font-size:10px;color:#D4A574;letter-spacing:.12em;' +
          'text-transform:uppercase;margin-bottom:4px;font-weight:600">生平</div>' +
        '<div style="font-family:"Fraunces",serif;font-size:13px;line-height:1.6;' +
          'color:#E8E4D8">' + escapeHtml(emp.life_summary) + '</div></div>' : '') +
    (memoryCount > 0 ?
      '<details><summary style="cursor:pointer;color:#A8A095;font-size:11px;' +
        'letter-spacing:.08em;text-transform:uppercase;padding:8px 0;' +
        'transition:color .2s">展开核心记忆 (' + memoryCount + ')</summary>' +
        '<div style="margin-top:8px;padding:12px 14px;background:rgba(0,0,0,.3);' +
          'border-radius:8px;font-size:12px;line-height:1.7;max-height:160px;' +
          'overflow-y:auto;font-family:"JetBrains Mono",monospace;color:#A8A095">' +
          (emp.core_memory || emp.memory || []).map(escapeHtml).join('<br><br>') +
        '</div></details>' : '');

  // 关闭按钮
  const closeBtn = document.getElementById('emp-card-close');
  if (closeBtn) closeBtn.onclick = closeEmployeeCard;

  // 头像 portrait：复用 drawSprite
  const portrait = document.getElementById('emp-card-portrait');
  if (portrait) {
    const pc = portrait.getContext('2d');
    pc.clearRect(0, 0, 56, 56);
    // 居中并放大
    pc.save();
    pc.translate(28, 30);
    pc.scale(0.6, 0.6);
    pc.translate(-32, -32);
    drawSprite(pc, emp.species, Math.floor(performance.now() / 200) % 16);
    pc.restore();
  }
}

function closeEmployeeCard() {
  if (employeeCardRefreshTimer) {
    clearInterval(employeeCardRefreshTimer);
    employeeCardRefreshTimer = null;
  }
  if (employeeCardModal) {
    employeeCardModal.remove();
    employeeCardModal = null;
  }
}

// commit 26：用像素 PNG 渲染监工（手持平板人类形象）
// 状态映射：idle → 帧 0/1 循环；react → 帧 10；过期后回 idle
function drawSupervisorPng(cx, cy, t) {
  // 检查 react 状态是否过期
  if (supervisorState === 'react' && Date.now() > supervisorStateUntil) {
    supervisorState = 'idle';
    supervisorStateUntil = 0;
  }

  // 选帧：react 状态用帧 10，否则用 idle 帧 0/1（每 600ms 切换）
  let frameIdx;
  if (supervisorState === 'react') {
    frameIdx = 10;
  } else {
    frameIdx = Math.floor(t / 0.6) % 2;  // idle 帧 0/1
  }

  const sprite = getPngFrame('overseer', frameIdx);
  if (!sprite) return;  // 切片失败，让 drawSupervisor 走矢量 fallback

  // 监工 sprite 显示尺寸（与员工一致：64x64 逻辑像素 × view.zoom）
  const size = 64 * view.zoom;
  // 脚下微微漂浮（4px 振幅，比员工 idle 明显些）
  const floatY = Math.sin(t * 1.5) * 2;
  // sprite 锚点：底部中心（脚尖位置）对齐到 (cx, cy + 12)
  // 这样监工脚下光晕和阴影位置与原矢量版一致
  const drawX = cx - size / 2;
  const drawY = cy - size + 12 * view.zoom + floatY;

  ctx.save();
  // 禁用抗锯齿保持像素感
  ctx.imageSmoothingEnabled = false;

  // === 脚下光晕（保留琥珀色光晕，标识"视角中心"）===
  const glowR = 28 + Math.sin(t * 1.5) * 3;
  const glowGrad = ctx.createRadialGradient(cx, cy + 22, 0, cx, cy + 22, glowR);
  glowGrad.addColorStop(0, 'rgba(212, 165, 116, 0.22)');
  glowGrad.addColorStop(0.5, 'rgba(212, 165, 116, 0.06)');
  glowGrad.addColorStop(1, 'rgba(212, 165, 116, 0)');
  ctx.fillStyle = glowGrad;
  ctx.beginPath();
  ctx.ellipse(cx, cy + 22, glowR, glowR * 0.35, 0, 0, Math.PI * 2);
  ctx.fill();

  // === 阴影 ===
  ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
  ctx.beginPath();
  ctx.ellipse(cx, cy + 22, 14, 4, 0, 0, Math.PI * 2);
  ctx.fill();

  // === 像素 sprite 本体 ===
  ctx.drawImage(sprite, drawX, drawY, size, size);

  // === 监工标签（serif 字体 + 阴影描边）===
  ctx.font = '500 11px "Fraunces", serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = THEME_COLORS.textShadow;
  const labelY = drawY - 6;
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      if (dx === 0 && dy === 0) continue;
      ctx.fillText('监工', cx + dx, labelY + dy);
    }
  }
  ctx.fillStyle = '#D4A574';
  ctx.fillText('监工', cx, labelY);

  ctx.restore();
}

function drawSupervisor() {
  const p = getSupervisorPos();
  const t = performance.now() / 1000;
  const cx = p.x, cy = p.y;

  // commit 26：优先用像素 PNG sprite（32x32 → 64x64 放大），加载失败回退到矢量兜帽法师
  if (pngSpriteSheets['overseer']) {
    drawSupervisorPng(cx, cy, t);
    return;
  }

  // 微微漂浮
  const floatY = Math.sin(t * 1.5) * 2;
  // 杖顶宝石呼吸脉动
  const pulse = 0.5 + Math.sin(t * 2) * 0.5;

  ctx.save();

  // === 脚下光晕 ===
  const glowR = 28 + Math.sin(t * 1.5) * 3;
  const glowGrad = ctx.createRadialGradient(cx, cy + 22, 0, cx, cy + 22, glowR);
  glowGrad.addColorStop(0, `rgba(212, 165, 116, ${0.28 + pulse * 0.08})`);
  glowGrad.addColorStop(0.5, 'rgba(212, 165, 116, 0.08)');
  glowGrad.addColorStop(1, 'rgba(212, 165, 116, 0)');
  ctx.fillStyle = glowGrad;
  ctx.beginPath();
  ctx.ellipse(cx, cy + 22, glowR, glowR * 0.35, 0, 0, Math.PI * 2);
  ctx.fill();

  // === 阴影 ===
  ctx.fillStyle = 'rgba(0, 0, 0, 0.35)';
  ctx.beginPath();
  ctx.ellipse(cx, cy + 22, 14, 4, 0, 0, Math.PI * 2);
  ctx.fill();

  // === 长袍下摆（梯形，宽底）===
  const robeBot = cy + 22 + floatY;
  const robeTop = cy - 4 + floatY;
  ctx.fillStyle = '#1F2A24';
  ctx.beginPath();
  ctx.moveTo(cx - 16, robeBot);
  ctx.quadraticCurveTo(cx - 14, robeTop + 4, cx - 10, robeTop);
  ctx.lineTo(cx + 10, robeTop);
  ctx.quadraticCurveTo(cx + 14, robeTop + 4, cx + 16, robeBot);
  ctx.quadraticCurveTo(cx, robeBot + 3, cx - 16, robeBot);
  ctx.closePath();
  ctx.fill();
  // 长袍中线高光（琥珀色细线）
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.35)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx, robeTop + 2);
  ctx.lineTo(cx, robeBot - 1);
  ctx.stroke();
  // 长袍边缘描边
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.4)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - 16, robeBot);
  ctx.quadraticCurveTo(cx - 14, robeTop + 4, cx - 10, robeTop);
  ctx.lineTo(cx + 10, robeTop);
  ctx.quadraticCurveTo(cx + 14, robeTop + 4, cx + 16, robeBot);
  ctx.stroke();

  // === 双手袖口（袖管内露出的手）===
  ctx.fillStyle = '#D4A574';
  // 左手（持杖）
  ctx.beginPath();
  ctx.arc(cx + 9, cy + 2 + floatY, 2.5, 0, Math.PI * 2);
  ctx.fill();
  // 右手
  ctx.beginPath();
  ctx.arc(cx - 7, cy + 4 + floatY, 2.2, 0, Math.PI * 2);
  ctx.fill();

  // === 木质长杖（从右手向上伸出，杖顶有发光琥珀）===
  const staffX = cx + 9;
  const staffBotY = cy + 4 + floatY;
  const staffTopY = cy - 24 + floatY;
  // 杖身（深褐色，加一点纹理）
  ctx.strokeStyle = '#3C2814';
  ctx.lineWidth = 2.5;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(staffX, staffBotY);
  ctx.quadraticCurveTo(staffX + 1.5, (staffBotY + staffTopY) / 2, staffX, staffTopY);
  ctx.stroke();
  // 杖身高光
  ctx.strokeStyle = 'rgba(140, 90, 50, 0.7)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(staffX - 0.6, staffBotY);
  ctx.quadraticCurveTo(staffX + 0.8, (staffBotY + staffTopY) / 2, staffX - 0.6, staffTopY);
  ctx.stroke();

  // 杖顶宝石外光晕
  const gemR = 4 + pulse * 1.2;
  const gemGlow = ctx.createRadialGradient(staffX, staffTopY - 2, 0, staffX, staffTopY - 2, gemR * 4);
  gemGlow.addColorStop(0, `rgba(255, 220, 160, ${0.85 * (0.6 + pulse * 0.4)})`);
  gemGlow.addColorStop(0.4, `rgba(212, 165, 116, ${0.4 * (0.6 + pulse * 0.4)})`);
  gemGlow.addColorStop(1, 'rgba(212, 165, 116, 0)');
  ctx.fillStyle = gemGlow;
  ctx.beginPath();
  ctx.arc(staffX, staffTopY - 2, gemR * 4, 0, Math.PI * 2);
  ctx.fill();
  // 宝石本体（六边形）
  ctx.fillStyle = '#FFE4B5';
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = i * Math.PI / 3 - Math.PI / 2;
    const x = staffX + Math.cos(a) * gemR;
    const y = staffTopY - 2 + Math.sin(a) * gemR;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fill();
  // 宝石描边
  ctx.strokeStyle = '#D4A574';
  ctx.lineWidth = 0.8;
  ctx.stroke();
  // 宝石中心高光
  ctx.fillStyle = '#FFF8E0';
  ctx.beginPath();
  ctx.arc(staffX - 1, staffTopY - 3, 1, 0, Math.PI * 2);
  ctx.fill();

  // === 兜帽（覆盖头部，深色 + 琥珀描边）===
  const hoodY = cy - 14 + floatY;
  ctx.fillStyle = '#16201B';
  ctx.beginPath();
  // 兜帽形状：从肩部往上，顶部尖
  ctx.moveTo(cx - 12, hoodY + 8);
  ctx.quadraticCurveTo(cx - 13, hoodY - 4, cx - 6, hoodY - 10);
  ctx.quadraticCurveTo(cx, hoodY - 13, cx + 6, hoodY - 10);
  ctx.quadraticCurveTo(cx + 13, hoodY - 4, cx + 12, hoodY + 8);
  ctx.quadraticCurveTo(cx, hoodY + 4, cx - 12, hoodY + 8);
  ctx.closePath();
  ctx.fill();
  // 兜帽描边
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.5)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // === 脸部阴影（兜帽内深色椭圆，仅露一道光）===
  ctx.fillStyle = '#0A100C';
  ctx.beginPath();
  ctx.ellipse(cx, hoodY + 2, 6, 5, 0, 0, Math.PI * 2);
  ctx.fill();

  // === 两点眼睛（琥珀色，微微发光）===
  ctx.fillStyle = `rgba(255, 220, 160, ${0.8 + pulse * 0.2})`;
  ctx.beginPath();
  ctx.arc(cx - 2, hoodY + 2, 0.9, 0, Math.PI * 2);
  ctx.arc(cx + 2, hoodY + 2, 0.9, 0, Math.PI * 2);
  ctx.fill();

  // === 白色胡须（从下巴飘下）===
  ctx.strokeStyle = 'rgba(240, 235, 220, 0.85)';
  ctx.lineWidth = 0.8;
  ctx.lineCap = 'round';
  for (let i = -2; i <= 2; i++) {
    ctx.beginPath();
    ctx.moveTo(cx + i * 1.2, hoodY + 5);
    const sway = Math.sin(t * 2 + i) * 0.6;
    ctx.quadraticCurveTo(cx + i * 1.5 + sway, hoodY + 9, cx + i * 1.2 + sway, hoodY + 12);
    ctx.stroke();
  }

  // === 监工标签（serif 字体 + 阴影描边）===
  ctx.font = '500 11px "Fraunces", serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = THEME_COLORS.textShadow;
  const labelY = cy - 38 + floatY;
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      if (dx === 0 && dy === 0) continue;
      ctx.fillText('监工', cx + dx, labelY + dy);
    }
  }
  ctx.fillStyle = '#D4A574';
  ctx.fillText('监工', cx, labelY);

  ctx.restore();
}

function drawSupervisorReaction() {
  if (!supervisorReaction) return;
  const age = Date.now() - supervisorReaction.time;
  if (age > supervisorReaction.dur) {
    supervisorReaction = null;
    return;
  }
  const p = getSupervisorPos();
  const alpha = 1 - age / supervisorReaction.dur;
  ctx.globalAlpha = alpha;
  const text = supervisorReaction.text;
  ctx.font = '500 12px "Manrope", sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  const w = ctx.measureText(text).width + 20;
  // 气泡背景（深色玻璃 + 琥珀描边）
  const bx = p.x - w / 2, by = p.y - 50, bh = 26;
  ctx.fillStyle = 'rgba(10, 15, 12, 0.92)';
  ctx.beginPath();
  // 圆角矩形
  const r = 6;
  ctx.moveTo(bx + r, by);
  ctx.lineTo(bx + w - r, by);
  ctx.quadraticCurveTo(bx + w, by, bx + w, by + r);
  ctx.lineTo(bx + w, by + bh - r);
  ctx.quadraticCurveTo(bx + w, by + bh, bx + w - r, by + bh);
  ctx.lineTo(bx + r, by + bh);
  ctx.quadraticCurveTo(bx, by + bh, bx, by + bh - r);
  ctx.lineTo(bx, by + r);
  ctx.quadraticCurveTo(bx, by, bx + r, by);
  ctx.closePath();
  ctx.fill();
  // 描边
  ctx.strokeStyle = 'rgba(212, 165, 116, 0.6)';
  ctx.lineWidth = 1;
  ctx.stroke();
  // 小三角指向监工
  ctx.fillStyle = 'rgba(10, 15, 12, 0.92)';
  ctx.beginPath();
  ctx.moveTo(p.x - 5, by + bh);
  ctx.lineTo(p.x + 5, by + bh);
  ctx.lineTo(p.x, by + bh + 6);
  ctx.closePath();
  ctx.fill();
  // 文字（琥珀色）
  ctx.fillStyle = '#D4A574';
  ctx.fillText(text, p.x, by + 13);
  ctx.globalAlpha = 1;
}

function spawnFeedParticles(targetX, targetY) {
  // 从监工位置 spawn 6 个零食粒子飞向目标
  const sup = getSupervisorPos();
  const dx = targetX - sup.x;
  const dy = targetY - sup.y;
  const life = 0.6;
  for (let i = 0; i < 6; i++) {
    const jx = (Math.random() - 0.5) * 40;
    const jy = (Math.random() - 0.5) * 40;
    spawnParticle({
      x: sup.x, y: sup.y,
      vx: (dx + jx) / life,
      vy: (dy + jy) / life - 80,
      life: life,
      color: '#D4A574',
      size: 3,
    });
  }
}

// commit 42：浮空数字池（投喂/训练反馈）
let floatNumbers = [];
function spawnFloatNumber(x, y, text, color) {
  floatNumbers.push({
    x: x, y: y, text: text, color: color || '#FFFFFF',
    bornTs: performance.now(), lifeMs: 1500,
  });
  if (floatNumbers.length > 30) floatNumbers.shift();
}
function drawFloatNumbers() {
  const now = performance.now();
  floatNumbers = floatNumbers.filter(f => (now - f.bornTs) < f.lifeMs);
  for (const f of floatNumbers) {
    const age = (now - f.bornTs) / f.lifeMs;  // 0 → 1
    const dy = -age * 40;  // 上浮 40px
    const alpha = age < 0.7 ? 1 : (1 - age) / 0.3;  // 后 30% 淡出
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.font = 'bold 16px "Fraunces", serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    // 描边
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.8)';
    ctx.lineWidth = 3;
    ctx.strokeText(f.text, f.x, f.y + dy);
    // 填充
    ctx.fillStyle = f.color;
    ctx.fillText(f.text, f.x, f.y + dy);
    ctx.restore();
  }
}

function feedEmployee(emp) {
  // 投喂：调 /api/interact?action=feed + spawn 零食粒子 + 浮空数字
  const zone = ZONES.find(z => z.id === SPECIES_TO_ZONE[emp.species]);
  let cx = 40, cy = 30;
  if (zone) {
    cx = (zone.rect[0] + zone.rect[2]) / 2;
    cy = (zone.rect[1] + zone.rect[3]) / 2;
  }
  const ep = isoToScreen(cx, cy);
  spawnFeedParticles(ep.x, ep.y);
  showSupervisorReaction('投喂 ' + (emp.name || '?'));
  fetch('/api/interact', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: emp.name, action: 'feed', amount: 15}),
  }).then(r => r.json()).then(res => {
    if (res && res.ok) {
      showToast('已投喂 ' + (emp.name || '?'));
      // commit 42：投喂成功 → 浮空 +15 能量数字
      spawnFloatNumber(ep.x, ep.y - 30, '+15 能量', '#7FD97F');
      // commit 44-5：投喂后弹"谢谢"对话气泡（物种专属台词）
      const thanksPhrases = {
        'deer': '谢谢……光线真好。',
        'squirrel': '哇！谢谢监工！',
        'butterfly': '美得像一幅画，谢谢。',
        'fox': '谢了，记你一笔。',
        'hedgehog': '嗯，多谢。',
        'beaver': '收到，木头一样稳。',
        'raven': '……记下了。',
        'hare': '谢谢！我得快走了！',
        'badger': '谢了，继续挖。',
        'lark': '谢谢～唱一首给你听。',
        'kite': '收到，远方在召唤。',
      };
      const thanksText = (SPECIES_COLORS[emp.species] && thanksPhrases[emp.species]) || '谢谢。';
      activeBubbles.push({
        id: 'thanks-' + Date.now() + '-' + Math.random(),
        speaker: emp.name || emp.species,
        text: thanksText,
        target: '监工',
        expireTs: Date.now() + 3000,
      });
      if (activeBubbles.length > 10) activeBubbles.shift();
    }
  }).catch(err => console.warn('投喂失败:', err));
}

// ==================== commit 44-1：员工快捷交互菜单 ====================
let _quickMenuEmp = null;
function showQuickMenu(emp) {
  if (!emp) return;
  _quickMenuEmp = emp;
  const menu = document.getElementById('emp-quick-menu');
  if (!menu) return;
  // 计算员工屏幕坐标：优先用走动位置 _wx/_wy，回退到 emp.x/emp.y
  const ix = (emp._wx != null) ? emp._wx : (emp.x || 0);
  const iy = (emp._wy != null) ? emp._wy : (emp.y || 0);
  const p = isoToScreen(ix, iy);
  // 定位到员工右上方（不遮挡卡片，卡片在屏幕中央）
  let mx = p.x + 24;
  let my = p.y - 60;
  // 边界保护
  if (mx + 140 > window.innerWidth) mx = p.x - 160;
  if (my < 60) my = 60;
  menu.style.left = mx + 'px';
  menu.style.top = my + 'px';
  menu.style.display = 'flex';
}
function hideQuickMenu() {
  const menu = document.getElementById('emp-quick-menu');
  if (menu) menu.style.display = 'none';
  _quickMenuEmp = null;
}
// 三个菜单按钮回调
function quickMenuGreet() {
  const emp = _quickMenuEmp;
  if (!emp) return;
  hideQuickMenu();
  // 调 /api/interact 走 greet 动作（与 feedEmployee 同链路）
  fetch('/api/interact', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name: emp.name, action: 'greet'}),
  }).then(r => r.json()).then(res => {
    if (res && res.ok) {
      showToast('已和 ' + (emp.name || '?') + ' 打招呼');
      const ix = (emp._wx != null) ? emp._wx : (emp.x || 0);
      const iy = (emp._wy != null) ? emp._wy : (emp.y || 0);
      const p = isoToScreen(ix, iy);
      spawnFloatNumber(p.x, p.y - 30, '问候', '#D4A574');
    } else {
      showToast('问候失败');
    }
  }).catch(err => { showToast('问候失败'); console.warn(err); });
}
function quickMenuCommand() {
  const emp = _quickMenuEmp;
  if (!emp) return;
  hideQuickMenu();
  openCommandDialog(emp);
}
function quickMenuProfile() {
  const emp = _quickMenuEmp;
  if (!emp) return;
  hideQuickMenu();
  // 已显示则先关闭再打开（强制刷新）
  if (employeeCardModal) closeEmployeeCard();
  showEmployeeCard(emp);
}
// 菜单外部点击 + ESC 关闭
document.addEventListener('click', (e) => {
  const menu = document.getElementById('emp-quick-menu');
  if (!menu || menu.style.display === 'none') return;
  if (!menu.contains(e.target)) hideQuickMenu();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') hideQuickMenu();
});

// ==================== commit 44-2：下达指令模态框 ====================
let _commandDialogEmp = null;
function openCommandDialog(emp) {
  if (!emp) return;
  _commandDialogEmp = emp;
  const modal = document.getElementById('command-modal');
  const title = document.getElementById('command-modal-title');
  const input = document.getElementById('command-input');
  if (!modal || !input) return;
  title.textContent = '下达指令 - ' + (emp.name || '?');
  input.value = '';
  modal.style.display = 'flex';
  setTimeout(() => input.focus(), 50);
}
function closeCommandDialog() {
  const modal = document.getElementById('command-modal');
  if (modal) modal.style.display = 'none';
  _commandDialogEmp = null;
}
function sendCommand() {
  const emp = _commandDialogEmp;
  if (!emp) return;
  const input = document.getElementById('command-input');
  const text = (input && input.value || '').trim();
  if (!text) { showToast('请输入指令内容'); return; }
  fetch('/api/agent_command', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({command: text, mode: 'auto', species: emp.species})
  }).then(r => r.json()).then(res => {
    showToast('已下达指令给 ' + (emp.name || '?'));
    const ix = (emp._wx != null) ? emp._wx : (emp.x || 0);
    const iy = (emp._wy != null) ? emp._wy : (emp.y || 0);
    const p = isoToScreen(ix, iy);
    spawnFloatNumber(p.x, p.y - 30, '指令已接收', '#D4A574');
    closeCommandDialog();
    // 把结果也推到事件流（如果有）
    if (res && res.result) {
      addEventFeedItem({type: 'command', text: '→ ' + (emp.name || '?') + ' 收到指令：' + text, ts: Date.now()});
    }
  }).catch(err => {
    showToast('指令发送失败');
    console.warn(err);
  });
}
// ESC 关闭指令框
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const modal = document.getElementById('command-modal');
    if (modal && modal.style.display === 'flex') closeCommandDialog();
  }
});


function executeTool(tool, emp) {
  // 对选中员工执行当前工具
  if (!emp) return;
  if (tool === 'greet') {
    showSupervisorReaction('问候 ' + (emp.name || '?'));
    fetch('/api/interact', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: emp.name, action: 'greet'}),
    }).catch(err => console.warn('问候失败:', err));
  } else if (tool === 'feed') {
    feedEmployee(emp);
  } else if (tool === 'mark_focus') {
    showSupervisorReaction('训练 ' + (emp.name || '?'));
    // 训练位置
    const z = ZONES.find(zz => zz.id === SPECIES_TO_ZONE[emp.species]);
    const tcx = z ? (z.rect[0] + z.rect[2]) / 2 : 40;
    const tcy = z ? (z.rect[1] + z.rect[3]) / 2 : 30;
    const tep = isoToScreen(tcx, tcy);
    fetch('/api/interact', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: emp.name, action: 'mark_focus'}),
    }).then(r => r.json()).then(res => {
      if (res && res.ok) {
        // commit 42：训练成功 → 浮空 +技能 数字
        spawnFloatNumber(tep.x, tep.y - 30, '+专注', '#D4A574');
      }
    }).catch(err => console.warn('训练失败:', err));
  } else if (tool === 'set_schedule') {
    showSupervisorReaction('安排休息 ' + (emp.name || '?'));
    fetch('/api/interact', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: emp.name, action: 'set_schedule', bedtime: 22, wakeup: 7}),
    }).catch(err => console.warn('休息安排失败:', err));
  } else if (tool === 'recruit') {
    // 招募工具：对死亡物种触发招募
    const state = recruitStates[emp.species];
    if (state === 'DEAD') {
      fetch('/api/recruit', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({species: emp.species}),
      }).then(r => r.json()).then(res => {
        if (res && res.ok) showToast('已启动 ' + emp.species + ' 招募');
        else showToast('招募失败：' + (res && res.reason || ''));
      }).catch(err => console.warn('招募失败:', err));
    } else {
      showToast(emp.species + ' 不需要招募');
    }
  }
}

function selectTool(tool) {
  currentTool = tool;
  // commit 18：持久化工具选择
  settings.tool = tool;
  saveSettings();
  // 高亮当前工具按钮（commit 50-3：同时高亮 dock 按钮）
  document.querySelectorAll('#tool-bar button').forEach(b => {
    b.classList.toggle('active', b.dataset.action === tool);
  });
  document.querySelectorAll('#bottom-dock .dock-tools button').forEach(b => {
    b.classList.toggle('active', b.dataset.action === tool);
  });
  // 若有选中员工且工具非 recruit，立即执行
  if (selectedEmployee && tool !== 'recruit') {
    executeTool(tool, selectedEmployee);
  }
}

// commit 50-3：底部 dock 小地图（简化版，只画 worldCanvas 缩略 + 员工点）
let dockMinimapCanvas = null;
let dockMinimapCtx = null;
function drawDockMinimap() {
  if (!worldCanvas) return;
  if (!dockMinimapCanvas) {
    dockMinimapCanvas = document.getElementById('dock-minimap-canvas');
    if (!dockMinimapCanvas) return;
    dockMinimapCtx = dockMinimapCanvas.getContext('2d');
  }
  const w = dockMinimapCanvas.width;
  const h = dockMinimapCanvas.height;
  dockMinimapCtx.fillStyle = THEME_COLORS.canvasBgOuter;
  dockMinimapCtx.fillRect(0, 0, w, h);
  const sx = w / worldCanvas.width;
  const sy = h / worldCanvas.height;
  const s = Math.min(sx, sy);
  const dx = (w - worldCanvas.width * s) / 2;
  const dy = (h - worldCanvas.height * s) / 2;
  dockMinimapCtx.drawImage(worldCanvas, dx, dy, worldCanvas.width * s, worldCanvas.height * s);
  // 员工点
  for (const emp of employees) {
    if (emp.alive === false) continue;
    if (emp._wx == null) continue;
    const p = isoToScreen(emp._wx, emp._wy);
    const mx = dx + (p.x + worldOffsetX) * s;
    const my = dy + (p.y + worldOffsetY) * s;
    if (mx < 0 || mx > w || my < 0 || my > h) continue;
    dockMinimapCtx.fillStyle = getEmployeeColor(emp.species);
    dockMinimapCtx.beginPath();
    dockMinimapCtx.arc(mx, my, 1.5, 0, Math.PI * 2);
    dockMinimapCtx.fill();
  }
}

function drawMinimap() {
  // 左下角缩略图：贴 worldCanvas + 画当前视野框 + 员工位置点
  if (!worldCanvas) return;
  // commit 50-3：同时渲染底部 dock 小地图
  drawDockMinimap();
  const w = minimapCanvas.width;
  const h = minimapCanvas.height;
  // 背景色从 THEME_COLORS 缓存读取（跟随主题）
  minimapCtx.fillStyle = THEME_COLORS.canvasBgOuter;
  minimapCtx.fillRect(0, 0, w, h);
  // 计算缩放比例：让 worldCanvas 完整贴入 minimap
  const sx = w / worldCanvas.width;
  const sy = h / worldCanvas.height;
  const s = Math.min(sx, sy);
  const dw = worldCanvas.width * s;
  const dh = worldCanvas.height * s;
  const ox = (w - dw) / 2;
  const oy = (h - dh) / 2;
  minimapCtx.imageSmoothingEnabled = false;
  minimapCtx.drawImage(worldCanvas, ox, oy, dw, dh);

  // === P2-4：员工位置点 ===
  const t = performance.now() / 1000;
  const pulse = 0.5 + Math.sin(t * 3) * 0.5;
  for (const emp of employees) {
    if (emp.alive === false) continue;
    const cx = (emp._wx != null ? emp._wx : 40);
    const cy = (emp._wy != null ? emp._wy : 30);
    const wp = isoToWorld(cx, cy);
    const mx = ox + wp.x * s;
    const my = oy + wp.y * s;
    if (mx < ox || mx > ox + dw || my < oy || my > oy + dh) continue;
    // commit 47：小地图员工点统一用 EMPLOYEE_COLOR_MAP（与员工衣服同源）
    const empColor = getEmployeeColor(emp.species);
    // 忙碌员工加琥珀脉动光晕
    if (emp.busy) {
      minimapCtx.fillStyle = 'rgba(212, 165, 116, ' + (0.3 + pulse * 0.4) + ')';
      minimapCtx.beginPath();
      minimapCtx.arc(mx, my, 3.5, 0, Math.PI * 2);
      minimapCtx.fill();
    }
    // 员工点（与花名册/衣服同源色）
    minimapCtx.fillStyle = empColor;
    minimapCtx.beginPath();
    minimapCtx.arc(mx, my, 2, 0, Math.PI * 2);
    minimapCtx.fill();
    // 中心高光
    minimapCtx.fillStyle = '#FFFFFF';
    minimapCtx.beginPath();
    minimapCtx.arc(mx, my, 0.8, 0, Math.PI * 2);
    minimapCtx.fill();
    // 选中员工加白色环
    if (selectedEmployee === emp) {
      minimapCtx.strokeStyle = '#FFF8E0';
      minimapCtx.lineWidth = 1;
      minimapCtx.beginPath();
      minimapCtx.arc(mx, my, 4, 0, Math.PI * 2);
      minimapCtx.stroke();
    }
  }

  // === 监工位置（canvas 正中）===
  // 监工永远在屏幕中心，所以小地图上的位置就是视野框中心
  const vx = -view.x / view.zoom + worldOffsetX;
  const vy = -view.y / view.zoom + worldOffsetY;
  // 监工图标（小琥珀菱形）
  const supMx = ox + vx * s + (canvas.width / view.zoom) * s / 2;
  const supMy = oy + vy * s + (canvas.height / view.zoom) * s / 2;
  minimapCtx.fillStyle = '#D4A574';
  minimapCtx.beginPath();
  minimapCtx.moveTo(supMx, supMy - 3);
  minimapCtx.lineTo(supMx + 3, supMy);
  minimapCtx.lineTo(supMx, supMy + 3);
  minimapCtx.lineTo(supMx - 3, supMy);
  minimapCtx.closePath();
  minimapCtx.fill();

  // === 当前视野框 ===
  const vw = canvas.width / view.zoom;
  const vh = canvas.height / view.zoom;
  minimapCtx.strokeStyle = '#D4A574';
  minimapCtx.lineWidth = 1;
  minimapCtx.strokeRect(ox + vx * s, oy + vy * s, vw * s, vh * s);
}

// ==================== 工具按钮 + 快捷键 ====================
document.getElementById('tool-greet').addEventListener('click', () => selectTool('greet'));
document.getElementById('tool-feed').addEventListener('click', () => selectTool('feed'));
document.getElementById('tool-train').addEventListener('click', () => selectTool('mark_focus'));
document.getElementById('tool-rest').addEventListener('click', () => selectTool('set_schedule'));
document.getElementById('tool-recruit').addEventListener('click', () => {
  selectTool('recruit');
  // 招募工具：直接对所有 DEAD 物种触发招募
  for (const sp in recruitStates) {
    if (recruitStates[sp] === 'DEAD') {
      fetch('/api/recruit', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({species: sp}),
      }).catch(err => console.warn('招募失败:', err));
    }
  }
});

// commit 50-3：底部 dock 按钮事件绑定（与顶部 tool-bar 同步）
document.querySelectorAll('#bottom-dock .dock-tools button').forEach(btn => {
  btn.addEventListener('click', () => {
    const action = btn.dataset.action;
    if (action === 'recruit') {
      selectTool('recruit');
      for (const sp in recruitStates) {
        if (recruitStates[sp] === 'DEAD') {
          fetch('/api/recruit', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({species: sp}),
          }).catch(err => console.warn('招募失败:', err));
        }
      }
    } else {
      selectTool(action);
    }
  });
});

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === '1') selectTool('greet');
  else if (e.key === '2') selectTool('feed');
  else if (e.key === '3') selectTool('mark_focus');
  else if (e.key === '4') selectTool('set_schedule');
  else if (e.key === '5') selectTool('recruit');
  else if (e.key === ' ') {
    e.preventDefault();
    // 空格：居中监工（view 重置到默认）
    view.x = -200; view.y = -100;
    saveView();
    showToast('已居中监工');
  }
});

// 小地图点击：跳到对应世界坐标
minimapCanvas.addEventListener('click', e => {
  const rect = minimapCanvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  const w = minimapCanvas.width;
  const h = minimapCanvas.height;
  const sx = w / worldCanvas.width;
  const sy = h / worldCanvas.height;
  const s = Math.min(sx, sy);
  const dw = worldCanvas.width * s;
  const dh = worldCanvas.height * s;
  const ox = (w - dw) / 2;
  const oy = (h - dh) / 2;
  // 点击位置 → worldCanvas 内坐标
  const wx = (mx - ox) / s;
  const wy = (my - oy) / s;
  // view 调整：让 (wx, wy) 落在 canvas 中心
  view.x = canvas.width / 2 - (wx - worldOffsetX) * view.zoom;
  view.y = canvas.height / 2 - (wy - worldOffsetY) * view.zoom;
  saveView();
});

// ==================== commit 17：视觉氛围 ====================
// 零基础读者可以这样理解：
// 1) 光照色温：根据当前小时叠加暖橙/白/金/深蓝色调，模拟昼夜变化
// 2) 天气粒子：每 60 秒切换晴/雨/雪，下雨下雪时持续 spawn 粒子
// 3) 动作图标：员工 busy 时头上画一个小齿轮图标
// 4) 环境活物：公共区飞舞几只小蝴蝶点缀

let weather = settings.weather || 'sunny';  // 当前天气：sunny / rain / snow
let lastWeatherChange = 0;           // 上次切换天气时间戳
const WEATHER_INTERVAL = 60000;      // 60 秒切一次天气
const ambientButterflies = [];       // 环境蝴蝶

function initAmbientButterflies() {
  // 在 canteen / lounge / meeting 三区各放 1 只蝴蝶
  ambientButterflies.length = 0;
  const zones = ['canteen', 'lounge', 'meeting'];
  const colors = ['#D4A574', '#A07AA5', '#C9925A'];
  for (let i = 0; i < zones.length; i++) {
    const zone = ZONES.find(z => z.id === zones[i]);
    if (!zone) continue;
    const cx = (zone.rect[0] + zone.rect[2]) / 2;
    const cy = (zone.rect[1] + zone.rect[3]) / 2;
    ambientButterflies.push({
      ox: cx, oy: cy,
      angle: Math.random() * Math.PI * 2,
      radius: 2 + Math.random() * 3,
      speed: 0.02 + Math.random() * 0.03,
      color: colors[i % colors.length],
    });
  }
}

function drawAmbientButterflies() {
  for (const b of ambientButterflies) {
    b.angle += b.speed;
    const ix = b.ox + Math.cos(b.angle) * b.radius;
    const iy = b.oy + Math.sin(b.angle * 1.3) * b.radius * 0.5;
    const p = isoToScreen(ix, iy);
    if (p.x < -20 || p.x > canvas.width + 20) continue;
    if (p.y < -20 || p.y > canvas.height + 20) continue;
    const size = 4 * view.zoom;
    // 翅膀扇动 0..1
    const flap = Math.sin(currentFrame * 0.5) * 0.5 + 0.5;
    ctx.fillStyle = b.color;
    ctx.globalAlpha = 0.7;
    ctx.beginPath();
    ctx.ellipse(p.x - size * (0.4 + flap * 0.4), p.y,
                size * 0.6, size * 0.4, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(p.x + size * (0.4 + flap * 0.4), p.y,
                size * 0.6, size * 0.4, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }
}

function updateWeather(ts) {
  // commit 24：天气系统扩展
  // 根据时间自动切换天气：
  //   6-10 早晨：晴（带光斑）/ 雾
  //   10-14 中午：晴（带光斑）
  //   14-18 下午：雨 / 晴
  //   18-22 傍晚：雨 / 雾
  //   22-6  夜晚：萤火虫（不再下雨雪）
  // 同时根据当前月份加季节元素：
  //   3-5 月：春天（少量花瓣）
  //   6-8 月：夏天（晴多）
  //   9-11 月：秋天（落叶）
  //   12-2 月：冬天（雪）
  const h = new Date().getHours();
  const month = new Date().getMonth() + 1;  // 1-12

  // 每 60 秒重新决定一次天气
  if (ts - lastWeatherChange > WEATHER_INTERVAL) {
    const r = Math.random();
    if (h >= 22 || h < 6) {
      // 夜晚：只萤火虫
      weather = 'fireflies';
    } else if (month >= 12 || month <= 2) {
      // 冬天：白天有 50% 雪
      weather = r < 0.5 ? 'snow' : 'sunny';
    } else if (month >= 9 && month <= 11) {
      // 秋天：晴多 + 偶尔雨
      weather = r < 0.6 ? 'sunny' : (r < 0.85 ? 'rain' : 'fog');
    } else if (month >= 6 && month <= 8) {
      // 夏天：晴多 + 偶尔雷雨
      weather = r < 0.7 ? 'sunny' : 'rain';
    } else {
      // 春天：晴 + 雾 + 偶尔雨
      weather = r < 0.5 ? 'sunny' : (r < 0.8 ? 'fog' : 'rain');
    }
    lastWeatherChange = ts;
    settings.weather = weather;
    saveSettings();
  }

  // spawn 粒子
  if (weather === 'rain') {
    for (let i = 0; i < 3; i++) {
      spawnParticle({
        x: Math.random() * canvas.width,
        y: -10,
        vx: -20, vy: 400,
        life: 1.5,
        color: '#6B8F9C',
        size: 1.5,
        type: 'rain',
      });
    }
  } else if (weather === 'snow') {
    for (let i = 0; i < 2; i++) {
      spawnParticle({
        x: Math.random() * canvas.width,
        y: -10,
        vx: (Math.random() - 0.5) * 30, vy: 60,
        life: 4,
        color: '#E8E4D8',
        size: 2 + Math.random(),
        type: 'snow',
      });
    }
  } else if (weather === 'fireflies') {
    // 萤火虫：从屏幕中下部 spawn，缓慢飘动
    if (Math.random() < 0.15) {
      spawnParticle({
        x: Math.random() * canvas.width,
        y: canvas.height * (0.3 + Math.random() * 0.5),
        vx: (Math.random() - 0.5) * 20, vy: (Math.random() - 0.5) * 15,
        life: 5 + Math.random() * 3,
        color: '#D4A574',
        size: 1.5 + Math.random(),
        type: 'firefly',
      });
    }
  } else if (weather === 'fog') {
    // 雾：极慢的水平移动粒子
    if (Math.random() < 0.3) {
      spawnParticle({
        x: -20,
        y: Math.random() * canvas.height,
        vx: 15 + Math.random() * 10, vy: 0,
        life: 8,
        color: 'rgba(168, 160, 149, 0.4)',
        size: 30 + Math.random() * 20,
        type: 'fog',
      });
    }
  } else if (weather === 'sunny') {
    // 晴：偶发光斑（缓慢飘动的金色亮点）
    if (Math.random() < 0.1) {
      spawnParticle({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height * 0.7,
        vx: (Math.random() - 0.5) * 8, vy: -5,
        life: 3,
        color: 'rgba(212, 165, 116, 0.5)',
        size: 2 + Math.random() * 2,
        type: 'sunbeam',
      });
    }
  }

  // 季节元素：秋叶（9-11 月）/ 春花瓣（3-5 月）
  if ((month >= 9 && month <= 11) || (month >= 3 && month <= 5)) {
    if (Math.random() < 0.08) {
      const isLeaf = month >= 9;
      spawnParticle({
        x: Math.random() * canvas.width,
        y: -10,
        vx: (Math.random() - 0.5) * 30, vy: 25 + Math.random() * 20,
        life: 8,
        color: isLeaf
          ? (Math.random() < 0.5 ? '#C97B5A' : '#D4A574')   // 秋叶：橙/琥珀
          : (Math.random() < 0.5 ? '#A07AA5' : '#E8B4D4'),  // 春花：紫/粉
        size: 3,
        type: isLeaf ? 'leaf' : 'petal',
      });
    }
  }
}

function drawTimeOfDayOverlay() {
  // commit 25 P3-1：根据当前小时叠加昼夜色温 + 日月图形
  // 浅色模式下叠加更弱，避免米底被深色压暗太多
  // commit 44-3：使用游戏时间 gameHour/gameMinute 而非系统时间
  const h = Math.floor(gameHour);
  const m = Math.floor(gameMinute);
  // 把时间换算成 0-1 的"日进度"（0=午夜，0.5=正午）
  const dayProgress = (h * 60 + m) / (24 * 60);
  const isLight = getCurrentTheme() === 'light';
  const dim = isLight ? 0.5 : 1.0;  // 浅色模式叠加强度减半
  let color = '#FFFFFF', alpha = 0;
  if (h >= 6 && h < 10) {            // 早晨暖橙（薄琥珀）
    color = '#D4A574'; alpha = 0.06 * dim;
  } else if (h >= 10 && h < 14) {    // 中午明亮
    alpha = 0;
  } else if (h >= 14 && h < 18) {    // 黄昏金色（深琥珀）
    color = '#B86E4E'; alpha = 0.08 * dim;
  } else if (h >= 18 && h < 22) {    // 傍晚深蓝
    color = '#3A4A6B'; alpha = 0.14 * dim;
  } else {                            // 深夜
    color = '#1A2340'; alpha = 0.28 * dim;
  }
  if (alpha > 0) {
    ctx.globalAlpha = alpha;
    ctx.fillStyle = color;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = 1;
  }

  // === commit 54：天气全屏滤镜（晴/雨/雾/雪/萤，透明度 0.04-0.10）===
  // 取代"在地图坐标里画太阳/雨滴"的做法，改为全屏覆盖一层极淡的色温
  // 效果：像电影滤镜，让画面有"天气感"而非"贴纸感"
  let wColor = null, wAlpha = 0;
  if (weather === 'rain') {
    wColor = '#2A3A4A'; wAlpha = 0.08 * dim;       // 雨天：冷蓝灰
  } else if (weather === 'snow') {
    wColor = '#E8F0F8'; wAlpha = 0.06 * dim;       // 雪天：冷白
  } else if (weather === 'fog') {
    wColor = '#A8B0A0'; wAlpha = 0.10 * dim;       // 雾天：灰绿
  } else if (weather === 'fireflies') {
    wColor = '#3A4A2A'; wAlpha = 0.06 * dim;       // 萤火：暖绿
  } else if (weather === 'sunny' && h >= 10 && h < 14) {
    wColor = '#FFE4B5'; wAlpha = 0.04 * dim;       // 晴天正午：极淡暖黄
  }
  if (wColor && wAlpha > 0) {
    ctx.globalAlpha = wAlpha;
    ctx.fillStyle = wColor;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.globalAlpha = 1;
  }

  // === 日/月图形（沿天空弧形轨迹移动）===
  // commit 50-2：已删除地图内弧形太阳/月亮实体（2.5D 坐标里放发光球太诡异）
  // 改为右上角 UI 小图标（见下方"右上角天气图标"段）
  const isDay = h >= 6 && h < 18;

  ctx.save();
  if (!isDay) {
    // commit 50-2：仅保留夜晚星空闪烁（轻量装饰，不在地图坐标里画月亮实体）
    const t = performance.now() / 1000;
    for (let i = 0; i < 6; i++) {
      const sx = canvas.width * (0.1 + i * 0.13);
      const sy = canvas.height * 0.05 + (i % 3) * 0.04;
      const twinkle = 0.4 + Math.sin(t * 2 + i) * 0.4;
      ctx.fillStyle = 'rgba(255, 255, 255, ' + twinkle + ')';
      ctx.beginPath();
      ctx.arc(sx, sy, 0.8, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.restore();

  // === 右上角天气图标 + 时辰标识（commit 50-2：太阳从地图坐标删除，改为 UI 图标）===
  ctx.font = '500 12px "Fraunces", serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'top';
  const wText = weather === 'sunny' ? '晴' :
                weather === 'rain' ? '雨' :
                weather === 'snow' ? '雪' :
                weather === 'fog' ? '雾' :
                weather === 'fireflies' ? '萤' : '晴';
  const timeLabel = String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  const label = wText + ' · ' + timeLabel;
  ctx.fillStyle = THEME_COLORS.textShadow;
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      if (dx === 0 && dy === 0) continue;
      ctx.fillText(label, canvas.width - 40 + dx, 14 + dy);
    }
  }
  ctx.fillStyle = '#D4A574';
  ctx.fillText(label, canvas.width - 40, 14);
  // commit 50-2：右上角日月小图标（替代地图弧形实体）
  const iconX = canvas.width - 20;
  const iconY = 22;
  ctx.save();
  if (isDay) {
    // 太阳图标：暖金小圆 + 4 道光线
    const sunR = 6;
    ctx.fillStyle = '#FFE4B5';
    ctx.beginPath();
    ctx.arc(iconX, iconY, sunR, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#D4A574';
    ctx.lineWidth = 1;
    for (let i = 0; i < 4; i++) {
      const a = i * Math.PI / 2 + Math.PI / 4;
      ctx.beginPath();
      ctx.moveTo(iconX + Math.cos(a) * (sunR + 2), iconY + Math.sin(a) * (sunR + 2));
      ctx.lineTo(iconX + Math.cos(a) * (sunR + 5), iconY + Math.sin(a) * (sunR + 5));
      ctx.stroke();
    }
  } else {
    // 月亮图标：冷白月牙
    const moonR = 6;
    ctx.fillStyle = '#F0F0E0';
    ctx.beginPath();
    ctx.arc(iconX, iconY, moonR, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = 'rgba(20, 30, 50, 0.7)';
    ctx.beginPath();
    ctx.arc(iconX + moonR * 0.4, iconY - moonR * 0.2, moonR * 0.9, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

// commit 25 P3-5：鸟群飞过
// 每 20-40 秒随机 spawn 一群鸟（3-7 只），从画布一侧飞向另一侧
// 每只鸟用 V 形双翅 + 扇翅动画
function updateBirdFlocks(ts, dt) {
  // 仅白天才有鸟群（夜晚是萤火虫的主场）
  const h = new Date().getHours();
  if (h >= 22 || h < 6) return;

  // 偶发 spawn 新鸟群（20-40 秒一次）
  if (ts - lastBirdSpawn > 20000 + Math.random() * 20000) {
    lastBirdSpawn = ts;
    const count = 3 + Math.floor(Math.random() * 5);  // 3-7 只
    const dir = Math.random() < 0.5 ? 1 : -1;  // 飞行方向
    const baseY = canvas.height * (0.10 + Math.random() * 0.15);  // 顶部 10-25%
    const speed = 80 + Math.random() * 40;
    const flock = {
      birds: [],
      dir: dir,
      speed: speed,
    };
    for (let i = 0; i < count; i++) {
      flock.birds.push({
        x: dir > 0 ? -50 - i * 30 : canvas.width + 50 + i * 30,
        y: baseY + (i - count / 2) * 8 + (Math.random() - 0.5) * 6,
        phase: Math.random() * Math.PI * 2,
      });
    }
    birdFlocks.push(flock);
  }

  // 推进每只鸟
  for (let i = birdFlocks.length - 1; i >= 0; i--) {
    const flock = birdFlocks[i];
    let allOffscreen = true;
    for (const b of flock.birds) {
      b.x += flock.dir * flock.speed * dt;
      b.phase += dt * 8;
      // 检查是否还在屏幕内
      if (b.x > -100 && b.x < canvas.width + 100) allOffscreen = false;
    }
    if (allOffscreen) birdFlocks.splice(i, 1);
  }
}

function drawBirdFlocks() {
  for (const flock of birdFlocks) {
    for (const b of flock.birds) {
      if (b.x < -50 || b.x > canvas.width + 50) continue;
      // 扇翅：sin(phase) 控制 V 形开合
      const flap = Math.sin(b.phase) * 0.5 + 0.5;  // 0..1
      const wingY = -3 - flap * 3;  // 翅膀向上展开
      const wingSpread = 5 + flap * 2;
      ctx.save();
      ctx.strokeStyle = 'rgba(20, 25, 20, 0.7)';
      ctx.lineWidth = 1.5;
      ctx.lineCap = 'round';
      ctx.beginPath();
      // V 形（左翅 + 右翅）
      ctx.moveTo(b.x - wingSpread, b.y + wingY);
      ctx.quadraticCurveTo(b.x - wingSpread * 0.4, b.y - 1, b.x, b.y);
      ctx.quadraticCurveTo(b.x + wingSpread * 0.4, b.y - 1, b.x + wingSpread, b.y + wingY);
      ctx.stroke();
      ctx.restore();
    }
  }
}

// commit 34：疾病图标（头顶红色十字 + 病名小标签）
function drawIllnessIcon(emp, p, size) {
  const ill = emp.illness;
  if (!ill) return;
  const ix = p.x + size * 0.32;
  const iy = p.y - size - 4;
  const r = 5 * view.zoom;
  const t = performance.now() / 400;
  const pulse = 0.7 + Math.sin(t * 2) * 0.3;
  // 颜色：致命病→鲜红，普通病→橙黄
  const color = ill.fatal ? '#ff5050' : '#ffb060';
  // 外圈柔光
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.25 * pulse;
  ctx.beginPath();
  ctx.arc(ix, iy, r + 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;
  // 主圆
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(ix, iy, r, 0, Math.PI * 2);
  ctx.fill();
  // 白色十字
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 1.5 * view.zoom;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.moveTo(ix - r * 0.5, iy);
  ctx.lineTo(ix + r * 0.5, iy);
  ctx.moveTo(ix, iy - r * 0.5);
  ctx.lineTo(ix, iy + r * 0.5);
  ctx.stroke();
}

// commit 34：打喷嚏粒子（生病员工偶尔喷出飞沫）
const sneezeParticles = [];
let lastSneezeCheck = 0;
function emitSneezeParticles(emp, p, size) {
  const ill = emp.illness;
  if (!ill || !ill.sneeze) return;
  // 每 2-4 秒触发一次打喷嚏
  if (!emp._nextSneezeTs) emp._nextSneezeTs = performance.now() + 2000 + Math.random() * 2000;
  if (performance.now() < emp._nextSneezeTs) {
    // 渲染已存在的飞沫
    drawSneezeDroplets();
    return;
  }
  emp._nextSneezeTs = performance.now() + 2500 + Math.random() * 2500;
  // 在头部位置生成 6-10 个飞沫粒子
  const hx = p.x;
  const hy = p.y - size * 0.85;
  const count = 6 + Math.floor(Math.random() * 5);
  for (let i = 0; i < count; i++) {
    const ang = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 0.8;
    const sp = 0.6 + Math.random() * 1.2;
    sneezeParticles.push({
      x: hx, y: hy,
      vx: Math.cos(ang) * sp,
      vy: Math.sin(ang) * sp,
      life: 1.0,
      r: 1.5 + Math.random() * 1.5,
    });
  }
  // 队列上限
  if (sneezeParticles.length > 80) sneezeParticles.splice(0, sneezeParticles.length - 80);
  drawSneezeDroplets();
}

function drawSneezeDroplets() {
  ctx.save();
  for (let i = sneezeParticles.length - 1; i >= 0; i--) {
    const pt = sneezeParticles[i];
    pt.x += pt.vx;
    pt.y += pt.vy;
    pt.vy += 0.04;  // 重力
    pt.life -= 0.025;
    if (pt.life <= 0) {
      sneezeParticles.splice(i, 1);
      continue;
    }
    ctx.fillStyle = 'rgba(200,220,255,' + (pt.life * 0.7).toFixed(2) + ')';
    ctx.beginPath();
    ctx.arc(pt.x, pt.y, pt.r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function drawActionIcon(emp, p, size) {
  // commit 24：员工 busy 时头上画工作内容图标（根据 task_type 区分）
  if (!emp.busy) return;
  const ix = p.x;
  const iy = p.y - size - 8;
  const r = 6 * view.zoom;
  const t = performance.now() / 500;
  const pulse = 0.85 + Math.sin(t * 2) * 0.15;

  // 外层柔光
  ctx.fillStyle = 'rgba(212, 165, 116, 0.25)';
  ctx.beginPath();
  ctx.arc(ix, iy, r + 3, 0, Math.PI * 2);
  ctx.fill();

  // 主圆（脉动）
  ctx.fillStyle = '#D4A574';
  ctx.globalAlpha = pulse;
  ctx.beginPath();
  ctx.arc(ix, iy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = 1;

  // 中心图标（根据 task_type 画对应符号）
  ctx.save();
  ctx.translate(ix, iy);
  ctx.scale(view.zoom, view.zoom);
  ctx.fillStyle = '#0a0f0c';
  ctx.strokeStyle = '#0a0f0c';
  ctx.lineWidth = 1.2;
  ctx.lineCap = 'round';

  const tt = emp.task_type || '';
  if (tt === 'code' || tt === 'deploy') {
    // 代码/部署：尖括号 < >
    ctx.font = '700 8px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('</>', 0, 0);
  } else if (tt === 'test') {
    // 测试：勾号 ✓
    ctx.beginPath();
    ctx.moveTo(-3, 0);
    ctx.lineTo(-1, 2);
    ctx.lineTo(3, -2);
    ctx.stroke();
  } else if (tt === 'ui_design') {
    // UI 设计：画笔
    ctx.beginPath();
    ctx.moveTo(-3, 3);
    ctx.lineTo(2, -2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(3, -3, 1.5, 0, Math.PI * 2);
    ctx.fill();
  } else if (tt === 'security_scan') {
    // 安全：盾牌
    ctx.beginPath();
    ctx.moveTo(0, -3);
    ctx.lineTo(-3, -1);
    ctx.lineTo(-3, 1);
    ctx.lineTo(0, 3);
    ctx.lineTo(3, 1);
    ctx.lineTo(3, -1);
    ctx.closePath();
    ctx.stroke();
  } else if (tt === 'archive') {
    // 归档：书本
    ctx.fillRect(-3, -2, 6, 4);
    ctx.beginPath();
    ctx.moveTo(0, -2);
    ctx.lineTo(0, 2);
    ctx.stroke();
  } else if (tt === 'audit') {
    // 核算：算盘珠
    ctx.beginPath();
    ctx.arc(-2, 0, 1, 0, Math.PI * 2);
    ctx.arc(0, 0, 1, 0, Math.PI * 2);
    ctx.arc(2, 0, 1, 0, Math.PI * 2);
    ctx.fill();
  } else if (tt === 'route') {
    // 工具路由：箭头分叉
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-3, -3);
    ctx.moveTo(0, 0);
    ctx.lineTo(3, -3);
    ctx.moveTo(0, 0);
    ctx.lineTo(0, 3);
    ctx.stroke();
  } else if (tt === 'monitor') {
    // 监控：眼睛
    ctx.beginPath();
    ctx.ellipse(0, 0, 3, 2, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, 1, 0, Math.PI * 2);
    ctx.fill();
  } else if (tt === 'plan') {
    // 规划：清单
    ctx.strokeRect(-3, -3, 6, 1.5);
    ctx.strokeRect(-3, -0.5, 6, 1.5);
    ctx.strokeRect(-3, 2, 6, 1.5);
  } else if (tt === 'dispatch') {
    // 调度：罗盘星
    ctx.beginPath();
    ctx.moveTo(0, -3);
    ctx.lineTo(1, 0);
    ctx.lineTo(0, 3);
    ctx.lineTo(-1, 0);
    ctx.closePath();
    ctx.fill();
  } else {
    // 未知/默认：齿轮
    ctx.beginPath();
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4;
      ctx.moveTo(Math.cos(a) * 2, Math.sin(a) * 2);
      ctx.lineTo(Math.cos(a) * 3, Math.sin(a) * 3);
    }
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(0, 0, 1.5, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.restore();
}

function showToast(msg) {
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 1500);
}

// ==================== commit 34：持久记忆 / 桌面宠物 / 急救箱 ====================

// 桌面宠物模式：打开独立 200×150 小窗口
function openDesktopPet() {
  const w = window.open('/desktop', 'bluedeer_desktop_pet',
    'width=220,height=170,menubar=no,toolbar=no,location=no,status=no,resizable=no,alwaysRaised=yes');
  if (!w) {
    showToast('请允许弹出窗口以打开桌面宠物模式');
    return;
  }
  // 后端同步标记桌面模式启用
  fetch('/api/desktop_pet', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'enable' }),
    credentials: 'same-origin',
  }).catch(() => {});
  showToast('已开启桌面宠物模式');
}

// 急救箱面板：列出病号 + 救治操作
async function openDiseasePanel() {
  const panel = document.getElementById('disease-panel');
  panel.style.display = 'block';
  const listEl = document.getElementById('disease-list');
  listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>';
  await refreshDiseasePanel();
}

async function refreshDiseasePanel() {
  const listEl = document.getElementById('disease-list');
  if (!listEl) return;
  try {
    const r = await fetch('/api/disease', { credentials: 'same-origin' });
    const d = await r.json();
    const sick = d.sick_agents || [];
    const epidemic = d.epidemic_active;
    const rescues = d.rescue_pending || [];
    let html = '';
    if (epidemic) {
      html += '<div style="padding:10px 12px; margin-bottom:10px; background:rgba(255,80,80,0.18); border:1px solid rgba(255,80,80,0.5); border-radius:6px; color:#ffb0b0; font-size:12px;">森林流感疫情爆发中，全公司效率下降 40%</div>';
    }
    for (const r of rescues) {
      html += '<div style="padding:10px 12px; margin-bottom:10px; background:rgba(255,180,80,0.18); border:1px solid rgba(255,180,80,0.5); border-radius:6px; color:#ffd090; font-size:12px;">' +
        (r.agent_name || '某员工') + ' 病危，剩余 ' + (r.remaining_hours || 2) + ' 小时急救窗口！' +
        '<button onclick="triggerRescue(\\'' + (r.agent_name || '') + '\\')" style="margin-left:10px; padding:3px 10px; background:#c44; color:#fff; border:none; border-radius:3px; cursor:pointer;">立即急救（消耗 ' + (d.rescue_cost_marks || 20) + ' 印记）</button>' +
        '</div>';
    }
    if (sick.length === 0) {
      html += '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">目前全员健康</div>';
    } else {
      html += sick.map(a => {
        const ill = a.illness || {};
        const isFatal = ill.fatal;
        const name = a.agent_name || '?';
        const symptoms = (ill.symptoms || []).join('、') || '—';
        const day = Math.max(1, Math.floor(ill.elapsed_days || 0) + 1);
        const eff = ill.efficiency_factor != null ? ill.efficiency_factor : 1;
        const healthBar = '<div style="height:4px; background:rgba(255,255,255,0.1); border-radius:2px; margin:6px 0; overflow:hidden;">' +
          '<div style="height:100%; width:' + Math.max(0, Math.min(100, a.health || 0)) + '%; background:' + (isFatal ? '#ff6060' : '#ffb060') + ';"></div></div>';
        return '<div style="padding:12px; margin-bottom:8px; background:rgba(255,255,255,0.04); border-radius:6px; border-left:3px solid ' + (isFatal ? '#ff6060' : '#ffb060') + ';">' +
          '<div style="display:flex; justify-content:space-between; align-items:center;">' +
            '<div><strong style="color:' + (isFatal ? '#ff8080' : '#ffb080') + ';">' + name + '</strong>' +
            ' <span style="color:rgba(255,255,255,0.5); font-size:11px;">' + (a.species || '') + '</span></div>' +
            '<div style="font-size:11px; color:rgba(255,255,255,0.6);">' + (ill.label || ill.kind || '') + ' · 第 ' + day + ' 天</div>' +
          '</div>' +
          '<div style="font-size:11px; color:rgba(255,255,255,0.5); margin-top:4px;">症状：' + symptoms + '</div>' +
          healthBar +
          '<div style="font-size:11px; color:rgba(255,255,255,0.6);">健康 ' + (a.health || 0).toFixed(1) + ' · 效率 ' + (eff * 100).toFixed(0) + '%</div>' +
          '<div style="margin-top:8px; display:flex; gap:6px; flex-wrap:wrap;">' +
            '<button onclick="diseaseAction(\\'' + name + '\\', \\'force_rest\\')" style="padding:3px 8px; font-size:11px; background:#4a4; color:#fff; border:none; border-radius:3px; cursor:pointer;">强制休息</button>' +
            '<button onclick="diseaseAction(\\'' + name + '\\', \\'give_medicine\\')" style="padding:3px 8px; font-size:11px; background:#48a; color:#fff; border:none; border-radius:3px; cursor:pointer;">喂药（' + (d.medicine_cost_marks || 5) + ' 印记）</button>' +
            '<button onclick="diseaseAction(\\'' + name + '\\', \\'isolate\\')" style="padding:3px 8px; font-size:11px; background:#886; color:#fff; border:none; border-radius:3px; cursor:pointer;">隔离</button>' +
            '<button onclick="diseaseAction(\\'' + name + '\\', \\'care\\')" style="padding:3px 8px; font-size:11px; background:#869; color:#fff; border:none; border-radius:3px; cursor:pointer;">请同事照顾</button>' +
            (isFatal ? '<button onclick="triggerRescue(\\'' + name + '\\')" style="padding:3px 8px; font-size:11px; background:#c44; color:#fff; border:none; border-radius:3px; cursor:pointer;">急救</button>' : '') +
          '</div>' +
        '</div>';
      }).join('');
    }
    listEl.innerHTML = html;
  } catch (e) {
    listEl.innerHTML = '<div style="color:#ff8080; text-align:center; padding:40px 0;">加载失败</div>';
  }
}

// 救治操作调用
async function diseaseAction(agentName, action) {
  try {
    const payload = { action: action, agent_name: agentName };
    if (action === 'care') {
      // 默认请海狸照顾（最会照顾人）
      payload.caregiver_name = '狸·大坝';
    }
    const r = await fetch('/api/disease', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'same-origin',
    });
    const d = await r.json();
    if (d.ok) {
      showToast('操作成功：' + (d.message || action));
    } else {
      showToast('操作失败：' + (d.reason || d.error || '未知错误'));
    }
    refreshDiseasePanel();
  } catch (e) {
    showToast('请求失败');
  }
}

// 触发急救
async function triggerRescue(agentName) {
  if (!confirm('急救需要消耗 20 森林印记，鹿/渡鸦/海狸共同参与，成功率 80%。失败则死亡。确认开始急救？')) return;
  try {
    const r = await fetch('/api/disease', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'rescue', agent_name: agentName }),
      credentials: 'same-origin',
    });
    const d = await r.json();
    if (d.ok && d.result === 'success') {
      showToast('急救成功！' + (d.agent || agentName) + ' 重获新生');
    } else if (d.ok && d.result === 'failed') {
      showToast('急救失败……' + (d.agent || agentName) + ' 离开了我们');
    } else {
      showToast('急救失败：' + (d.reason || d.error || '条件不足'));
    }
    refreshDiseasePanel();
  } catch (e) {
    showToast('请求失败');
  }
}

// 持久记忆面板：列出各智能体的核心/长期记忆 + 重逢提示
async function openMemoryPanel() {
  const panel = document.getElementById('memory-panel');
  panel.style.display = 'block';
  const statsEl = document.getElementById('memory-stats');
  const listEl = document.getElementById('memory-list');
  listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>';
  try {
    const r = await fetch('/api/persistent_memory', { credentials: 'same-origin' });
    const d = await r.json();
    const agents = d.agents || [];
    statsEl.innerHTML = '智能体数：' + agents.length + ' · 核心记忆总数：' +
      agents.reduce((s, a) => s + ((a.core_events || []).length), 0) + ' · 长期记忆摘要：' +
      agents.reduce((s, a) => s + ((a.long_summaries || []).length), 0);
    if (agents.length === 0) {
      listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">还没有持久记忆<br>与智能体多聊几句，它们就会记住你</div>';
      return;
    }
    listEl.innerHTML = agents.map(a => {
      const coreList = (a.core || []).map(e =>
        '<div style="padding:6px 8px; margin:3px 0; background:rgba(255,255,255,0.03); border-radius:4px; font-size:11px;">' +
        '<span style="color:rgba(255,200,100,0.7);">' + new Date((e.ts || e.time || 0) * 1000).toLocaleDateString('zh-CN') + '</span> ' +
        (e.text || '') +
        (e.tags && e.tags.length ? ' <span style="color:rgba(150,180,255,0.6);">#' + e.tags.join(' #') + '</span>' : '') +
        '</div>'
      ).join('');
      const longList = (a.long || []).slice(-5).map(s =>
        '<div style="padding:6px 8px; margin:3px 0; background:rgba(255,255,255,0.02); border-radius:4px; font-size:11px;">' +
        '<span style="color:rgba(180,200,255,0.6);">' + new Date((s.ts || s.time || 0) * 1000).toLocaleDateString('zh-CN') + '</span> ' +
        (s.summary || s.text || '') +
        (s.important ? ' <span style="color:#ffd060;">★重要</span>' : '') +
        '</div>'
      ).join('');
      const reunionHint = a.reunion_hint
        ? '<div style="padding:8px 10px; margin:6px 0; background:rgba(150,180,255,0.08); border-left:2px solid rgba(150,180,255,0.5); border-radius:3px; color:#b0c4ff; font-size:12px; font-style:italic;">' + a.reunion_hint + '</div>'
        : '';
      return '<div style="padding:14px; margin-bottom:10px; background:rgba(255,255,255,0.03); border-radius:6px;">' +
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">' +
          '<strong style="color:#96b4ff;">' + (a.agent_name || a.agent_id || '?') + ' <span style="font-size:11px; color:rgba(255,255,255,0.4);">(' + (a.species || '') + ')</span></strong>' +
          '<div style="font-size:10px; color:rgba(255,255,255,0.4);">上次互动：' + (a.last_interact_ts ? new Date(a.last_interact_ts * 1000).toLocaleString('zh-CN') : '—') + '</div>' +
        '</div>' +
        reunionHint +
        (coreList ? '<div style="margin-top:6px;"><div style="color:rgba(255,200,100,0.7); font-size:11px; margin-bottom:3px;">核心记忆（永久） · ' + (a.core_count || 0) + ' 条</div>' + coreList + '</div>' : '') +
        (longList ? '<div style="margin-top:8px;"><div style="color:rgba(180,200,255,0.6); font-size:11px; margin-bottom:3px;">长期记忆摘要（最近 5 条）· 共 ' + (a.long_count || 0) + ' 条</div>' + longList + '</div>' : '') +
        '<div style="margin-top:8px; font-size:10px; color:rgba(255,255,255,0.4);">告别情绪：' + (a.farewell_mood || 'neutral') + ' · 缺席 ' + (a.absent_days || 0) + ' 天</div>' +
      '</div>';
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div style="color:#ff8080; text-align:center; padding:40px 0;">加载失败</div>';
  }
}

// 桌面宠物数据更新回调
function handleDesktopPetUpdate(d) {
  // 当前无可视化区域（管控台本身不是桌面小窗），仅缓存数据
  // 桌面宠物小窗页面 /desktop 自带 SSE，会独立处理
}

// 疾病数据更新回调：更新 diseaseData，并在急救箱打开时刷新
function handleDiseaseUpdate(d) {
  const panel = document.getElementById('disease-panel');
  if (panel && panel.style.display !== 'none') {
    // 防抖：1.5 秒最多刷新一次
    if (window._diseaseRefreshTimer) return;
    window._diseaseRefreshTimer = setTimeout(() => {
      window._diseaseRefreshTimer = null;
      refreshDiseasePanel();
    }, 1500);
  }
}

// ==================== SSE 实时推送 ====================
function connectSSE() {
  const es = new EventSource('/events');
  es.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      // commit 12+：新格式 {time, ts, changes, events}
      // commit 12 起：首帧 changes 是完整 status，后续只含变化字段
      if (data.changes) {
        applyChanges(data.changes);
        handleEvents(data.events || []);
      } else if (data.status) {
        // 兼容旧格式
        applyChanges(data.status);
      }
    } catch (err) {
      console.warn('SSE parse error:', err);
    }
  };
  es.onerror = () => {
    console.warn('SSE 断开，5 秒后重连');
    es.close();
    setTimeout(connectSSE, 5000);
  };
}

// commit 13：应用增量变化
function applyChanges(changes) {
  if (!changes) return;
  // 首帧（changes 含 running/env/employees 等完整字段）
  if (changes.env !== undefined) {
    envStats = changes.env;
    renderEnvStats();
  }
  if (changes.employees !== undefined) {
    const emps = changes.employees;
    if (Array.isArray(emps)) {
      // 首帧或全量推送：直接替换
      employees = emps.map(emp => ({...emp, busy: false}));
    } else {
      // 增量：按 species 索引更新
      for (const sp in emps) {
        const diff = emps[sp];
        if (diff._removed) {
          employees = employees.filter(e => e.species !== sp);
        } else {
          const idx = employees.findIndex(e => e.species === sp);
          if (idx >= 0) {
            employees[idx] = {...employees[idx], ...diff};
            // commit 37：同步 Agent 工具调用状态到 _agentWorkStatus（用于头顶图标）
            const newStatus = diff.agent_work_status || '';
            if (newStatus && newStatus !== employees[idx]._agentWorkStatus) {
              employees[idx]._agentWorkStatus = newStatus;
              // 如果状态变成 done/error，重置淡出计时器
              if (newStatus === 'done' || newStatus === 'error') {
                employees[idx]._agentWorkDoneTs = null;
              }
            } else if (!newStatus && employees[idx]._agentWorkStatus &&
                       employees[idx]._agentWorkStatus !== 'done' &&
                       employees[idx]._agentWorkStatus !== 'error') {
              // 后端清空了，前端也清空
              employees[idx]._agentWorkStatus = '';
            }
          } else {
            employees.push({...diff, busy: false});
          }
        }
      }
    }
    renderEmployeeList();
  }
  // commit 33：沉浸感三子系统数据
  if (changes.atmosphere !== undefined) {
    atmosphereData = changes.atmosphere;
  }
  if (changes.fragments !== undefined) {
    fragmentsData = changes.fragments;
  }
  if (changes.social !== undefined) {
    socialData = changes.social;
  }
  // commit 34：桌面宠物 + 疾病数据
  if (changes.desktop_pet !== undefined) {
    desktopPetData = changes.desktop_pet;
    handleDesktopPetUpdate(desktopPetData);
  }
  if (changes.disease !== undefined) {
    diseaseData = changes.disease;
    handleDiseaseUpdate(diseaseData);
  }
  // commit 35：日记 / 自传体记忆 / 工作产物（节流推送）
  if (changes.artifacts !== undefined) {
    artifactsData = changes.artifacts;
  }
  if (changes.autobiography !== undefined) {
    autobioData = changes.autobiography;
    // 联动3：把自我认知字段同步到 employees 缓存（用于 tooltip 显示）
    const abAgents = autobioData.agents || [];
    for (const a of abAgents) {
      const cog = a.self_cognition || {};
      const idx = employees.findIndex(e =>
        e.species === a.species || e.agent_id === a.agent_id);
      if (idx >= 0) {
        employees[idx].self_description = cog.description || '';
        employees[idx].life_goal = cog.life_goal || '';
        employees[idx].values = cog.values || '';
        employees[idx].contradiction = cog.contradiction || '';
      }
    }
  }
  // 其他字段（running/tasks/storyteller 等）暂不展示
}

// commit 33：沉浸感三子系统全局状态
let atmosphereData = {auras: [], zone_aura: {}, particles: [], settings: {}};
let fragmentsData = {fragments: [], memoir_count: 0, settings: {}};
let socialData = {active_count: 0, active: [], archive_count: 0, settings: {}};
// commit 34：桌面宠物 + 疾病全局状态
let desktopPetData = {enabled: false, current: null, bubble: null, mode: 'random'};
let diseaseData = {sick_agents: [], rescue_pending: null, epidemic_active: false};

// commit 13/14：处理 SSE events 通道
function handleEvents(events) {
  for (const ev of events) {
    // commit 44-4：把 SSE 事件也推到事件流侧边面板
    addEventFeedItem({
      type: ev.type || 'info',
      text: ev.summary || ev.text || ev.action || ev.type || '',
      ts: Date.now(),
      time: ev.time || '',
    });
    if (ev.type === 'raven_narration') {
      // 渡鸦讲述已生成，刷新逝者列表（旁白文本不入列表）
      // 这里只显示 toast 提示
      showToast('渡鸦讲述了一条记忆');
    } else if (ev.type === 'interaction') {
      showToast('与 ' + (ev.name || '?') + ' 互动：' + (ev.action || ''));
    } else if (ev.type === 'recruit_started') {
      showToast((ev.species || '') + ' 招募已启动');
      fetchRecruitStatus();  // 立即刷新招募状态
    } else if (ev.type === 'recruit_completed') {
      // commit 14：触发走入动画
      triggerWalkIn(ev.species || '', ev.name || '');
      fetchRecruitStatus();
    } else if (ev.type === 'task_injected') {
      showToast('注入任务：' + (ev.task_type || ''));
    } else if (ev.type === 'daily_event') {
      // commit 19 P0-3：随机小事件
      showToast('【' + (ev.name || '') + '】' + (ev.desc || ''));
    } else if (ev.type === 'weather_change') {
      // commit 29：后端天气切换 → 同步前端 weather 变量
      const d = ev.data || {};
      const backendWeather = d.to || '';
      // 后端 weather key 映射到前端 weather key
      const weatherMap = {
        sunny: 'sunny', cloudy: 'sunny',  // 阴天前端用 sunny 简化
        light_rain: 'rain', heavy_rain: 'rain',
        snow: 'snow', hot: 'sunny', cold: 'snow'
      };
      const newW = weatherMap[backendWeather] || 'sunny';
      if (newW !== weather) {
        weather = newW;
        settings.weather = weather;
        saveSettings();
        lastWeatherChange = performance.now();
      }
      showToast('天气变更为：' + (d.label || backendWeather));
    } else if (ev.type === 'eco_event') {
      // commit 29：生态事件
      const d = ev.data || {};
      const target = d.target ? '（' + d.target + '）' : '';
      showToast('【生态事件】' + (d.label || '') + target);
    } else if (ev.type === 'social_greet') {
      // commit 29：社交打招呼（不打扰，仅日志）
      // 静默处理，不弹 toast
    } else if (ev.type === 'social_help') {
      const d = ev.data || {};
      showToast((d.helper || '') + ' 帮 ' + (d.target || '') + ' 找东西');
    } else if (ev.type === 'dialogue_bubble') {
      // commit 30：对话气泡（3 秒淡出）
      const d = ev.data || {};
      if (d.id && d.speaker) {
        // 去重（同 id 不重复加入）
        if (!activeBubbles.find(b => b.id === d.id)) {
          activeBubbles.push({
            id: d.id,
            speaker: d.speaker,
            text: d.text || '',
            target: d.target || '',
            expireTs: Date.now() + 3500,
          });
          // 队列上限 10，超出删除最早的
          if (activeBubbles.length > 10) activeBubbles.shift();
        }
      }
    } else if (ev.type === 'became_friend' || ev.type === 'became_partner'
               || ev.type === 'mentor_set' || ev.type === 'crush_formed'
               || ev.type === 'relationship_event') {
      // commit 30：关系事件
      const d = ev.data || {};
      const tagText = d.tag ? '【' + d.tag + '】' : '';
      showToast(tagText + (d.a || '') + ' 与 ' + (d.b || '') + ' 的关系发生变化');
    } else if (ev.type === 'anniversary') {
      const d = ev.data || {};
      showToast('【入职周年】' + (d.name || '') + ' 入职 ' + (d.years || 0) + ' 周年');
    } else if (ev.type === 'retirement_wish_set') {
      const d = ev.data || {};
      showToast('【退休愿望】' + (d.name || '') + '：' + (d.wish || ''));
    } else if (ev.type === 'wish_fulfilled') {
      const d = ev.data || {};
      showToast('【愿望实现】' + (d.name || '') + ' 实现了退休愿望');
    } else if (ev.type === 'relic_added') {
      const d = ev.data || {};
      showToast('【遗物】' + (d.owner || '') + ' 留下了 ' + (d.relic_name || ''));
      fetchRelicsData();  // 刷新遗物列表
    } else if (ev.type === 'active_message') {
      // commit 31：智能体主动消息 → 弹气泡 + 浏览器通知
      handleActiveMessage(ev.data || {});
    } else if (ev.type === 'illness_event') {
      // commit 34：疾病事件
      handleIllnessEvent(ev);
    } else if (ev.type === 'memory_reunion') {
      // commit 34：重逢问候（持久记忆）
      const d = ev.data || {};
      showToast('【重逢】' + (d.name || '') + '：' + (d.text || ''));
    }
  }
}

// commit 34：处理疾病事件
function handleIllnessEvent(ev) {
  const d = ev.data || ev || {};
  const t = d.type || ev.type || '';
  if (t === 'illness_onset') {
    showToast('【生病】' + (d.name || '') + ' 患上 ' + (d.illness || '疾病'));
  } else if (t === 'rescue_needed') {
    showToast('【急救】' + (d.name || '') + ' 病危，需要急救！');
    if (Notification && Notification.permission === 'granted') {
      new Notification('BlueDeer 急救警报', {
        body: (d.name || '') + ' 病危，请立即救治！',
      });
    }
  } else if (t === 'epidemic_start') {
    showToast('【疫情】森林流感爆发！全公司效率下降 40%');
  } else if (t === 'rescue_failed') {
    showToast('【哀悼】' + (d.name || '') + ' 因急救失败离世……');
  } else if (t === 'rescue_success') {
    showToast('【重生】' + (d.name || '') + ' 急救成功，重获新生');
  } else if (t === 'recovered') {
    showToast('【康复】' + (d.name || '') + ' 康复了');
  }
}

// ==================== commit 31：主动消息 + Web Notification ====================

// 主动消息历史（前端缓存最近 50 条，供面板查看）
let activeMessagesHistory = [];
// 已展示过的消息 id 集合（去重，避免同一 id 多次弹气泡）
let displayedActiveMsgIds = new Set();

/**
 * 处理一条主动消息：
 * 1. 入历史缓存
 * 2. 在画面上弹对话气泡（沿用 activeBubbles 系统）
 * 3. high 优先级 → 触发浏览器桌面通知（如果用户授权过）
 */
function handleActiveMessage(d) {
  const id = d.id || ('msg-' + Date.now());
  // 去重：同一 id 不重复处理
  if (displayedActiveMsgIds.has(id)) return;
  displayedActiveMsgIds.add(id);
  // 历史缓存保留最近 50 条
  activeMessagesHistory.push({
    id: id,
    sender: d.sender || '',
    sender_species: d.sender_species || '',
    text: d.text || '',
    category: d.category || '',
    priority: d.priority || 'low',
    time: Date.now(),
  });
  if (activeMessagesHistory.length > 50) activeMessagesHistory.shift();
  // 更新主动消息徽标（如果 DOM 存在）
  updateActiveMessageBadge();
  // 弹对话气泡（复用现有系统）
  if (d.sender) {
    activeBubbles.push({
      id: 'am-' + id,
      speaker: d.sender,
      text: d.text || '',
      target: '监工',
      expireTs: Date.now() + 4500,  // 主动消息显示 4.5 秒
    });
    if (activeBubbles.length > 10) activeBubbles.shift();
  }
  // high 优先级 → toast + 浏览器桌面通知
  if (d.priority === 'high') {
    showToast('【紧急】' + (d.sender || '') + '：' + (d.text || ''));
    sendDesktopNotification(d);
  } else if (d.priority === 'medium') {
    showToast('【' + (d.sender || '') + '】' + (d.text || ''));
  }
}

/**
 * 发送浏览器桌面通知（Web Notification API）。
 * 仅在用户授权 Notification.permission === 'granted' 时实际推送。
 * 标签 tag 用消息 id 去重，避免短时间内重复弹窗。
 */
function sendDesktopNotification(d) {
  if (!('Notification' in window)) return;  // 浏览器不支持
  if (Notification.permission !== 'granted') return;
  try {
    const title = 'BlueDeer · ' + (d.sender || '智能体');
    const body = d.text || '';
    const tag = 'bluedeer-msg-' + (d.id || Date.now());
    const n = new Notification(title, {
      body: body,
      tag: tag,
      icon: '/sprites/deer_sprite.png',  // 用现有精灵图作图标
      requireInteraction: false,  // 不强制停留，自动消失
    });
    // 5 秒后自动关闭（部分浏览器不支持 autoClose）
    setTimeout(() => { try { n.close(); } catch (e) {} }, 5000);
    // 点击通知聚焦窗口
    n.onclick = () => { window.focus(); try { n.close(); } catch (e) {} };
  } catch (e) {
    console.warn('Notification error:', e);
  }
}

/**
 * 请求浏览器通知权限（绑定到"启用桌面通知"按钮）。
 * 用户首次点击时浏览器会弹出权限询问框。
 */
function requestNotificationPermission() {
  if (!('Notification' in window)) {
    showToast('当前浏览器不支持桌面通知');
    return;
  }
  if (Notification.permission === 'granted') {
    showToast('桌面通知已启用');
    updateNotificationButton();
    return;
  }
  if (Notification.permission === 'denied') {
    showToast('桌面通知已被浏览器拒绝，请在设置中手动开启');
    return;
  }
  Notification.requestPermission().then(result => {
    if (result === 'granted') {
      showToast('桌面通知已启用');
      // 立即发一条测试通知
      try {
        new Notification('BlueDeer 森林公司', {
          body: '桌面通知已开启，员工重要消息会推送到这里',
          tag: 'bluedeer-init',
        });
      } catch (e) {}
    } else {
      showToast('桌面通知未启用');
    }
    updateNotificationButton();
  });
}

/**
 * 更新"启用桌面通知"按钮的显示状态。
 */
function updateNotificationButton() {
  const btn = document.getElementById('notify-btn');
  if (!btn) return;
  if (!('Notification' in window)) {
    btn.textContent = '不支持通知';
    btn.disabled = true;
    return;
  }
  if (Notification.permission === 'granted') {
    btn.textContent = '通知已开启';
    btn.disabled = true;
  } else if (Notification.permission === 'denied') {
    btn.textContent = '通知被拒绝';
    btn.disabled = true;
  } else {
    btn.textContent = '启用桌面通知';
    btn.disabled = false;
  }
}

/**
 * 更新主动消息徽标（红点 + 未读数）。
 */
function updateActiveMessageBadge() {
  const badge = document.getElementById('active-msg-badge');
  if (!badge) return;
  const count = activeMessagesHistory.length;
  if (count > 0) {
    badge.textContent = count > 99 ? '99+' : String(count);
    badge.style.display = 'inline-block';
  } else {
    badge.style.display = 'none';
  }
}

/**
 * 拉取最近的主动消息历史（页面加载时调用，避免错过 SSE 之前的消息）。
 */
function fetchActiveMessages() {
  fetch('/api/messages?limit=50', { credentials: 'same-origin' })
    .then(r => r.json())
    .then(d => {
      const msgs = d.messages || [];
      for (const m of msgs) {
        const id = m.id || ('msg-' + Math.random());
        if (displayedActiveMsgIds.has(id)) continue;
        displayedActiveMsgIds.add(id);
        activeMessagesHistory.push({
          id: id,
          sender: m.sender || '',
          sender_species: m.sender_species || '',
          text: m.text || '',
          category: m.category || '',
          priority: m.priority || 'low',
          time: (m.time || Date.now() / 1000) * 1000,
        });
      }
      if (activeMessagesHistory.length > 50) {
        activeMessagesHistory = activeMessagesHistory.slice(-50);
      }
      updateActiveMessageBadge();
    })
    .catch(() => {});
}

// commit 30：拉取情感/关系/遗物数据
function fetchEmotionsData() {
  fetch('/api/emotions', { credentials: 'same-origin' })
    .then(r => r.json())
    .then(d => { emotionsData = d; })
    .catch(() => {});
}

function fetchRelationshipsData() {
  fetch('/api/relationships', { credentials: 'same-origin' })
    .then(r => r.json())
    .then(d => { relationshipsData = d; })
    .catch(() => {});
}

function fetchRelicsData() {
  fetch('/api/relics', { credentials: 'same-origin' })
    .then(r => r.json())
    .then(d => { relicsData = d; })
    .catch(() => {});
}

function startEmotionsPolling() {
  if (emotionsTimer) clearInterval(emotionsTimer);
  emotionsTimer = setInterval(fetchEmotionsData, 5000);
  fetchEmotionsData();
}

function startRelationshipsPolling() {
  if (relationshipsTimer) clearInterval(relationshipsTimer);
  relationshipsTimer = setInterval(fetchRelationshipsData, 15000);
  fetchRelationshipsData();
  fetchRelicsData();
}

// commit 30：清理过期对话气泡（在 animate 主循环中调用）
function cleanupExpiredBubbles() {
  const now = Date.now();
  activeBubbles = activeBubbles.filter(b => b.expireTs > now);
}

// commit 30：情感值格式化（0.0~1.0 → 0~99 整数显示）
function _fmtEmo(v) {
  if (v == null) return '?';
  const n = Math.round(v * 100);
  return String(n);
}

// commit 30：在员工头顶绘制对话气泡
// 零基础读者可以这样理解：
// 每个 activeBubble 有 {speaker, text, target, expireTs}
// 1. 找到 speaker 对应的员工，拿到屏幕坐标 p
// 2. 在 p 上方画一个圆角矩形气泡 + 三角小尾巴
// 3. 文本居中显示在气泡里
// 4. 根据 expireTs 计算透明度（最后 0.5 秒淡出）
function drawDialogueBubbles() {
  if (!activeBubbles || activeBubbles.length === 0) return;
  const now = Date.now();
  for (const b of activeBubbles) {
    // 按名字查找说话者
    const emp = employees.find(e => (e.name || '') === b.speaker);
    if (!emp) continue;
    // 拿到员工屏幕坐标
    const cx = (emp._wx != null ? emp._wx : 40);
    const cy = (emp._wy != null ? emp._wy : 30);
    const p = isoToScreen(cx, cy);
    const size = 64 * view.zoom;
    // 气泡出现在头顶上方
    const bubbleY = p.y - size - 14;
    // 文本最长 24 字（超出截断）
    const text = (b.text || '').length > 24
      ? (b.text || '').slice(0, 23) + '…'
      : (b.text || '');
    if (!text) continue;
    // 计算气泡尺寸（按字数）
    ctx.font = (11 * Math.max(0.7, view.zoom)) + 'px "Fraunces", serif';
    const textW = ctx.measureText(text).width;
    const padX = 8, padY = 5;
    const bw = textW + padX * 2;
    const bh = 16 + padY * 2;
    const bx = p.x - bw / 2;
    const by = bubbleY - bh;
    // 透明度：最后 500ms 淡出
    const remain = b.expireTs - now;
    const alpha = remain < 500 ? Math.max(0, remain / 500) : 1.0;
    ctx.save();
    ctx.globalAlpha = alpha;
    // 气泡背景（深色玻璃 + 琥珀边）
    ctx.fillStyle = 'rgba(28,24,32,0.92)';
    ctx.strokeStyle = 'rgba(212,165,116,0.85)';
    ctx.lineWidth = 1;
    roundRect(ctx, bx, by, bw, bh, 6);
    ctx.fill();
    ctx.stroke();
    // 三角小尾巴（朝下）
    ctx.beginPath();
    ctx.moveTo(p.x - 5, by + bh);
    ctx.lineTo(p.x + 5, by + bh);
    ctx.lineTo(p.x, by + bh + 6);
    ctx.closePath();
    ctx.fillStyle = 'rgba(28,24,32,0.92)';
    ctx.fill();
    // 文本
    ctx.fillStyle = '#f0e4cf';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, p.x, by + bh / 2);
    ctx.restore();
  }
}

// 圆角矩形辅助
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

// ==================== commit 21：深/浅色主题切换 ====================
// 零基础读者可以这样理解：
// 顶部导航最右边有一个圆形按钮，深色模式下显示月亮 ☾，浅色模式下显示太阳 ☈。
// 点击就在两种模式之间切换，整个 UI 颜色（背景/文字/边框/琥珀重点）
// 和 Canvas 地图配色都会跟着变。
// 选择存到 localStorage，下次打开记住上次的主题。
// 默认跟随系统：如果操作系统是深色就用深色，否则用浅色。

const THEME_KEY = 'bluedeer_theme_v1';

function getCurrentTheme() {
  return document.documentElement.dataset.theme || 'dark';
}

function setTheme(name) {
  document.documentElement.dataset.theme = name;
  try { localStorage.setItem(THEME_KEY, name); } catch(e) { /* ignore */ }
  // 刷新缓存的 Canvas 主题色（避免每帧 getComputedStyle）
  refreshThemeColors();
  // 重建静态地图（让瓦片颜色根据主题的 --canvas-brighten 调亮/调暗）
  if (typeof prerenderWorld === 'function') {
    prerenderWorld();
  }
}

// Canvas 渲染层用的主题色缓存（每帧读，不能每帧 getComputedStyle）
let THEME_COLORS = {
  textPrimary: '#E8E4D8',
  textShadow: 'rgba(0,0,0,0.85)',
  canvasGrid: '#1A201B',
  canvasBgOuter: '#0a0f0c',
  canvasBgInner: '#111813',
  brighten: 0,
};

function refreshThemeColors() {
  const cs = getComputedStyle(document.documentElement);
  THEME_COLORS.textPrimary  = cs.getPropertyValue('--text-primary').trim()     || '#E8E4D8';
  THEME_COLORS.textShadow   = cs.getPropertyValue('--canvas-text-shadow').trim() || 'rgba(0,0,0,0.85)';
  THEME_COLORS.canvasGrid   = cs.getPropertyValue('--canvas-grid').trim()      || '#1A201B';
  THEME_COLORS.canvasBgOuter= cs.getPropertyValue('--canvas-bg-outer').trim()  || '#0a0f0c';
  THEME_COLORS.canvasBgInner= cs.getPropertyValue('--canvas-bg-inner').trim()  || '#111813';
  THEME_COLORS.brighten     = parseFloat(cs.getPropertyValue('--canvas-brighten')) || 0;
}

function toggleTheme() {
  setTheme(getCurrentTheme() === 'light' ? 'dark' : 'light');
}

function initThemeToggle() {
  // 1) 决定初始主题：localStorage 优先 → 系统偏好 → 默认 dark
  let saved;
  try { saved = localStorage.getItem(THEME_KEY); } catch(e) { saved = null; }
  if (saved === 'light' || saved === 'dark') {
    document.documentElement.dataset.theme = saved;
  } else if (window.matchMedia &&
             window.matchMedia('(prefers-color-scheme: light)').matches) {
    document.documentElement.dataset.theme = 'light';
  } else {
    document.documentElement.dataset.theme = 'dark';
  }
  // 1.5) 刷新 Canvas 主题色缓存
  refreshThemeColors();
  // 2) 绑定按钮
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.addEventListener('click', toggleTheme);
  // 3) 跟随系统变化（仅在用户没显式选过时）
  if (window.matchMedia) {
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
      let saved2;
      try { saved2 = localStorage.getItem(THEME_KEY); } catch(e) { saved2 = null; }
      if (!saved2) setTheme(e.matches ? 'dark' : 'light');
    });
  }
}

// 在 DOM 解析完就初始化主题（避免 fetch 等待时的视觉闪烁）
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initThemeToggle);
} else {
  initThemeToggle();
}

// ==================== commit 20：面板可伸缩 + 折叠 ====================
// 零基础读者可以这样理解：
// 状态面板 / 小地图 / 帮助框都加了一条"小手柄"——
// 鼠标按住手柄拖动可以改大小（左右拖宽窄，斜角拖大小）；
// 每个面板右上角还有"−"按钮，点一下收起整个面板，
// 屏幕边缘留一个琥珀胶囊按钮让你再展开。
// 拖拽尺寸和折叠状态都记到 localStorage，下次打开记住上次。

const PANEL_SIZE_KEY = 'bluedeer_panel_sizes_v1';
const PANEL_COLLAPSE_KEY = 'bluedeer_panel_collapsed_v1';

function loadPanelSizes() {
  try { return JSON.parse(localStorage.getItem(PANEL_SIZE_KEY) || '{}'); }
  catch(e) { return {}; }
}
function loadPanelCollapsed() {
  try { return JSON.parse(localStorage.getItem(PANEL_COLLAPSE_KEY) || '{}'); }
  catch(e) { return {}; }
}
function savePanelSizes(sizes) {
  try { localStorage.setItem(PANEL_SIZE_KEY, JSON.stringify(sizes)); }
  catch(e) { /* ignore */ }
}
function savePanelCollapsed(c) {
  try { localStorage.setItem(PANEL_COLLAPSE_KEY, JSON.stringify(c)); }
  catch(e) { /* ignore */ }
}

// 折叠/展开面板
function togglePanel(id, forceCollapse) {
  const el = document.getElementById(id);
  if (!el) return;
  const willCollapse = (forceCollapse === undefined)
    ? !el.classList.contains('collapsed')
    : forceCollapse;
  el.classList.toggle('collapsed', willCollapse);
  // 显示对应的还原按钮
  const restoreMap = {
    'status-panel': 'status-restore',
    'minimap': 'minimap-restore',
    'help': 'help-restore',
  };
  const r = document.getElementById(restoreMap[id]);
  if (r) r.classList.toggle('show', willCollapse);
  // 持久化
  const c = loadPanelCollapsed();
  c[id] = willCollapse;
  savePanelCollapsed(c);
}

// 启动拖拽
function startPanelResize(handle, ev) {
  ev.preventDefault();
  ev.stopPropagation();
  const target = document.getElementById(handle.dataset.target);
  if (!target) return;
  const dir = handle.dataset.dir;
  const startX = ev.clientX, startY = ev.clientY;
  const rect = target.getBoundingClientRect();
  const startW = rect.width, startH = rect.height;
  handle.classList.add('active');
  document.body.style.cursor = handle.style.cursor || (dir === 'x' ? 'ew-resize' : 'nwse-resize');
  document.body.style.userSelect = 'none';

  const onMove = e => {
    if (dir === 'x') {
      // 状态面板贴右边，向左拖 → 变宽
      const dx = startX - e.clientX;
      const newW = Math.max(240, Math.min(720, startW + dx));
      target.style.width = newW + 'px';
    } else if (dir === 'xy') {
      // 小地图：右下角斜向拖
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      const newW = Math.max(120, Math.min(420, startW + dx));
      const newH = Math.max(90, Math.min(360, startH + dy));
      target.style.width = newW + 'px';
      target.style.height = newH + 'px';
      const cv = document.getElementById('minimap-canvas');
      if (cv) {
        cv.style.width = (newW - 12) + 'px';
        cv.style.height = (newH - 12) + 'px';
      }
    }
  };
  const onUp = () => {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
    document.removeEventListener('touchmove', onTouchMove);
    document.removeEventListener('touchend', onUp);
    handle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    // 保存尺寸
    const sizes = loadPanelSizes();
    if (dir === 'x') sizes[target.id] = { w: target.offsetWidth };
    else if (dir === 'xy') sizes[target.id] = { w: target.offsetWidth, h: target.offsetHeight };
    savePanelSizes(sizes);
  };
  // 触屏支持
  const onTouchMove = e => {
    if (e.touches.length !== 1) return;
    const t = e.touches[0];
    onMove({ clientX: t.clientX, clientY: t.clientY });
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
  document.addEventListener('touchmove', onTouchMove, { passive: false });
  document.addEventListener('touchend', onUp);
}

function initResizablePanels() {
  // 1) 应用上次尺寸
  const sizes = loadPanelSizes();
  if (sizes['status-panel'] && sizes['status-panel'].w) {
    document.getElementById('status-panel').style.width = sizes['status-panel'].w + 'px';
  }
  if (sizes['minimap']) {
    const mm = document.getElementById('minimap');
    const cv = document.getElementById('minimap-canvas');
    if (mm) {
      mm.style.width = sizes['minimap'].w + 'px';
      mm.style.height = sizes['minimap'].h + 'px';
    }
    if (cv) {
      cv.style.width = (sizes['minimap'].w - 12) + 'px';
      cv.style.height = (sizes['minimap'].h - 12) + 'px';
    }
  }
  // 2) 应用折叠状态
  const collapsed = loadPanelCollapsed();
  for (const [id, isCol] of Object.entries(collapsed)) {
    if (isCol) togglePanel(id, true);
  }
  // 3) 绑定手柄拖拽
  document.querySelectorAll('.panel-resize').forEach(h => {
    h.addEventListener('mousedown', e => startPanelResize(h, e));
    h.addEventListener('touchstart', e => {
      if (e.touches.length !== 1) return;
      e.preventDefault();
      const t = e.touches[0];
      startPanelResize(h, { clientX: t.clientX, clientY: t.clientY,
                            preventDefault: () => {}, stopPropagation: () => {} });
    }, { passive: false });
  });
  // 4) 绑定折叠按钮
  document.querySelectorAll('.panel-collapse').forEach(b => {
    b.addEventListener('click', () => togglePanel(b.dataset.target));
  });
  // 5) 绑定还原按钮
  document.querySelectorAll('.panel-restore').forEach(b => {
    b.addEventListener('click', () => togglePanel(b.dataset.target, false));
  });
}

// ==================== 启动 ====================
// 先拉一次初始状态
fetch('/api/status').then(r => r.json()).then(s => {
  envStats = s.env || {};
  employees = (s.employees || []).map(emp => ({...emp, busy: false}));
  renderEnvStats();
  renderEmployeeList();
  initResizablePanels();  // commit 20：初始化可伸缩面板
  initMemoryParticles();  // commit 13：初始化晶柜粒子
  initParticlePool();     // commit 15：初始化通用粒子池
  prerenderWorld();       // commit 15：预渲染静态地图
  initAmbientButterflies(); // commit 17：初始化环境蝴蝶
  preloadAllPngSprites(); // commit 26：预加载 11 张像素精灵图集 PNG
  preloadAllDecoPngs();   // 预加载 17 zone × 3 = 51 张像素装饰品 PNG
  initSpriteDebugPanel(); // commit 26：初始化 Sprite 调试面板（F12 切换）
  selectTool(currentTool); // commit 18：应用持久化的工具
  fetchDeceased();        // commit 13：拉取逝者列表
  fetchRecruitStatus();   // commit 14：拉取招募状态
  startEcoDataPolling();  // commit 29：拉取生态系统数据
  startEmotionsPolling();      // commit 30：拉取情感数据
  startRelationshipsPolling(); // commit 30：拉取关系网络 + 遗物
  updateNotificationButton();  // commit 31：根据权限状态显示按钮文字
  fetchActiveMessages();       // commit 31：拉取历史主动消息
  animate();
  connectSSE();
}).catch(err => {
  console.error('初始拉取失败:', err);
  initResizablePanels();  // commit 20：失败路径也初始化可伸缩面板
  initMemoryParticles();
  initParticlePool();     // commit 15：失败路径也要初始化粒子池
  prerenderWorld();       // commit 15：失败路径也要预渲染
  initAmbientButterflies(); // commit 17：失败路径也初始化蝴蝶
  preloadAllPngSprites(); // commit 26：失败路径也预加载像素精灵
  preloadAllDecoPngs();   // 失败路径也预加载装饰品 PNG
  initSpriteDebugPanel(); // commit 26：失败路径也初始化调试面板
  selectTool(currentTool); // commit 18：失败路径也应用持久化工具
  fetchRecruitStatus();
  startEmotionsPolling();      // commit 30：失败路径也启动情感轮询
  startRelationshipsPolling(); // commit 30：失败路径也启动关系轮询
  updateNotificationButton();  // commit 31：失败路径也更新通知按钮
  fetchActiveMessages();       // commit 31：失败路径也拉取主动消息
  animate();
  connectSSE();
});

// ==================== commit 35：日记 / 自传体记忆 / 工作产物 / 前端重构 ====================
// 零基础读者可以这样理解：
// - 日记本：彩蛋发现 + 偷看（信任 -0.05）
// - 自传体记忆：周反思 + 自我认知 + 临终自传
// - 工作产物：11 物种各异，可点赞
// - 前端：主题切换 + 粒子引擎 + 光照 + UI 动效 + 性能监控
// 全部零第三方依赖，复用现有 particlePool / SSE / canvas

// ---------- 全局状态 ----------
let diaryData = { agents: [], peeked: 0 };
let autobioData = { agents: [] };
let artifactsData = { agents: [], wall: [] };
let perfState = {
  enabled: false, fps: 0, particles: 0, renderMs: 0, agents: 0,
  _frames: 0, _lastFpsTs: 0, _lastRenderStart: 0
};
const THEME_CYCLE = ['dark', 'midnight', 'sakura'];
const THEME_LABELS = { dark: '森林暖色', midnight: '深夜模式', sakura: '樱花季', light: '晨雾浅色' };

// ---------- 主题管理（cycleTheme：3 套预设循环切换） ----------
function cycleTheme() {
  const cur = document.documentElement.dataset.theme || 'dark';
  let idx = THEME_CYCLE.indexOf(cur);
  if (idx < 0) idx = -1;
  const next = THEME_CYCLE[(idx + 1) % THEME_CYCLE.length];
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem(THEME_KEY, next); } catch(e) {}
  refreshThemeColors();
  if (typeof prerenderWorld === 'function') prerenderWorld();
  showToast('主题：' + (THEME_LABELS[next] || next));
}

// ---------- 性能监控 ----------
function togglePerfPanel() {
  const panel = document.getElementById('perf-panel');
  if (!panel) return;
  perfState.enabled = panel.style.display !== 'block';
  panel.style.display = perfState.enabled ? 'block' : 'none';
  if (perfState.enabled) perfState._lastFpsTs = performance.now();
}
function updatePerfPanel() {
  if (!perfState.enabled) return;
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('perf-fps', perfState.fps.toFixed(0));
  set('perf-particles', perfState.particles);
  set('perf-render', perfState.renderMs.toFixed(1));
  set('perf-agents', perfState.agents);
}
function perfTickBegin() { perfState._lastRenderStart = performance.now(); }
function perfTickEnd() {
  const now = performance.now();
  perfState.renderMs = now - perfState._lastRenderStart;
  perfState._frames++;
  if (now - perfState._lastFpsTs >= 1000) {
    perfState.fps = perfState._frames * 1000 / (now - perfState._lastFpsTs);
    perfState._frames = 0;
    perfState._lastFpsTs = now;
  }
  let pc = 0;
  for (let i = 0; i < particlePool.length; i++) if (particlePool[i].active) pc++;
  perfState.particles = pc;
  perfState.agents = employees.length;
  updatePerfPanel();
}

// ---------- 粒子引擎扩展（灰尘 + 蒸汽，复用现有 particlePool） ----------
function spawnDustParticle(x, y, size) {
  spawnParticle({
    x: x + (Math.random() - 0.5) * size,
    y: y - Math.random() * size,
    vx: (Math.random() - 0.5) * 4,
    vy: -2 - Math.random() * 3,
    life: 2.5 + Math.random() * 2,
    color: 'rgba(255, 240, 200, 0.4)',
    size: 1, type: 'dot'
  });
}
function spawnSteamParticle(x, y) {
  spawnParticle({
    x: x + (Math.random() - 0.5) * 8,
    y: y, vx: (Math.random() - 0.5) * 2, vy: -8 - Math.random() * 4,
    life: 1.5 + Math.random(),
    color: 'rgba(220, 220, 230, 0.35)',
    size: 2 + Math.random() * 2, type: 'fog'
  });
}

// ---------- 光照系统：软阴影 + 点光源柔化 ----------
function drawSoftShadow(p, size) {
  ctx.save();
  ctx.globalAlpha = 0.32;
  ctx.fillStyle = '#000';
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, size * 0.28, size * 0.08, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}
function drawSoftPointLight(x, y, radius, color) {
  ctx.save();
  const grad = ctx.createRadialGradient(x, y, 0, x, y, radius);
  grad.addColorStop(0, color);
  grad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  ctx.restore();
}

// ---------- 工作产物画布渲染 ----------
const ARTIFACT_COLORS = {
  squirrel: '#9bdc6e', butterfly: '#f49acb', fox: '#ffa056',
  beaver: '#8cd0ff', raven: '#c8a8ff', hare: '#ffe88c',
  badger: '#fcb070', lark: '#a8e8ff', deer: '#c0d8a0',
  hedgehog: '#ff9080', kite: '#ffd070'
};
function drawWorkArtifact(emp, p, size) {
  const agentArt = (artifactsData.agents || []).find(a =>
    a.agent_id === emp.agent_id || a.species === emp.species);
  if (!agentArt || !agentArt.active || !agentArt.active.length) return;
  const recent = agentArt.active.slice(-2);
  for (let i = 0; i < recent.length; i++) {
    const art = recent[i];
    const offset = (i - recent.length / 2 + 0.5) * size * 0.18;
    const ax = p.x + offset;
    const ay = p.y - size * 0.45;
    const color = art.color || ARTIFACT_COLORS[emp.species] || '#cccccc';
    ctx.save();
    ctx.globalAlpha = 0.92;
    ctx.fillStyle = color;
    ctx.fillRect(ax - 3, ay - 3, 6, 6);
    ctx.fillStyle = 'rgba(0,0,0,0.4)';
    ctx.fillRect(ax - 1, ay - 1, 2, 2);
    if (art.liked_by_supervisor) {
      ctx.fillStyle = '#ffd060';
      ctx.fillRect(ax + 2, ay - 4, 2, 2);
    }
    ctx.restore();
  }
}

// ---------- 日记彩蛋：3 次连续点击员工 ----------
let _diaryClickState = { lastEmpId: null, count: 0, lastTs: 0 };
function checkDiaryEasterEgg(emp) {
  if (!emp || emp.alive === false) return;
  const now = performance.now();
  const key = emp.species + ':' + (emp.agent_id || emp.name || '');
  if (_diaryClickState.lastEmpId !== key) {
    _diaryClickState = { lastEmpId: key, count: 1, lastTs: now };
    return;
  }
  if (now - _diaryClickState.lastTs > 1500) {
    _diaryClickState.count = 1;
    _diaryClickState.lastTs = now;
    return;
  }
  _diaryClickState.count++;
  _diaryClickState.lastTs = now;
  if (_diaryClickState.count >= 3) {
    _diaryClickState.count = 0;
    fetch('/api/diary', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'discover', species: emp.species, agent_id: emp.agent_id })
    }).then(r => r.json()).then(d => {
      if (d.discovered) {
        showToast('📖 你发现了 ' + (emp.name || emp.species) + ' 隐藏的日记本！');
        openDiaryPanel(emp.species);
      } else if (d.msg) {
        showToast(d.msg);
      }
    }).catch(() => {});
  }
}

// ---------- 日记本面板 ----------
async function openDiaryPanel(species) {
  const panel = document.getElementById('diary-panel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.style.animation = 'none'; panel.offsetHeight; panel.style.animation = '';
  const statsEl = document.getElementById('diary-stats');
  const listEl = document.getElementById('diary-list');
  listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>';
  try {
    const url = '/api/diary' + (species ? '?species=' + encodeURIComponent(species) : '');
    const r = await fetch(url, { credentials: 'same-origin' });
    const d = await r.json();
    diaryData = d;
    const agents = d.agents || [];
    const total = agents.reduce((s, a) => s + ((a.entries || []).length), 0);
    statsEl.innerHTML = '可查看：' + agents.length + ' · 日记总数：' + total +
      (d.peeked ? ' · 你已偷看 ' + d.peeked + ' 次（trust 下降）' : '');
    if (agents.length === 0) {
      listEl.innerHTML = '<div style="color:rgba(255,200,120,0.6); text-align:center; padding:40px 0; line-height:2;">' +
        '日记本是私密的。<br>在智能体工位附近反复点击 3 次，<br>有概率"发现"一本隐藏的日记本。</div>';
      return;
    }
    listEl.innerHTML = agents.map(a => {
      const entries = (a.entries || []).map(e =>
        '<div style="padding:8px 10px; margin:4px 0; background:rgba(255,240,200,0.05); border-left:2px solid rgba(220,180,120,0.4); border-radius:3px; font-size:12px; line-height:1.7; white-space:pre-wrap;">' +
        '<div style="color:rgba(220,180,120,0.7); font-size:10px; margin-bottom:4px;">' +
          new Date((e.ts || e.time || 0) * 1000).toLocaleString('zh-CN', {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) +
          (e.weather ? ' · ' + e.weather : '') + (e.mood ? ' · 心情 ' + e.mood : '') +
        '</div>' + (e.text || '') + '</div>'
      ).join('');
      const specials = (a.special_entries || []).map(e =>
        '<div style="padding:8px 10px; margin:4px 0; background:rgba(255,220,160,0.08); border-left:2px solid #ffd060; border-radius:3px; font-size:12px; line-height:1.7; white-space:pre-wrap;">' +
        '<div style="color:#ffd060; font-size:10px; margin-bottom:4px;">★ ' + (e.kind || '特殊') + ' · ' +
          new Date((e.ts || e.time || 0) * 1000).toLocaleDateString('zh-CN') + '</div>' + (e.text || '') + '</div>'
      ).join('');
      return '<div style="padding:14px; margin-bottom:10px; background:rgba(255,255,255,0.03); border-radius:6px;">' +
        '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">' +
          '<strong style="color:#dcb478;">' + (a.agent_name || a.species || '?') +
          ' <span style="font-size:11px; color:rgba(255,255,255,0.4);">(' + (a.species || '') + ')</span></strong>' +
          '<button onclick="peekDiary(\\'' + (a.species || '') + '\\')" ' +
            'style="background:rgba(220,180,120,0.18); border:1px solid rgba(220,180,120,0.5); color:#dcb478; padding:4px 10px; border-radius:4px; cursor:pointer; font-size:11px;">' +
            '偷看（trust -0.05）</button>' +
        '</div>' +
        (specials ? '<div style="margin-bottom:6px;"><div style="color:#ffd060; font-size:11px; margin-bottom:3px;">特殊日记 · ' + (a.special_entries || []).length + ' 篇</div>' + specials + '</div>' : '') +
        (entries ? '<div><div style="color:rgba(220,180,120,0.7); font-size:11px; margin-bottom:3px;">最近日记 · ' + (a.entries || []).length + ' 篇</div>' + entries + '</div>' : '<div style="color:rgba(255,255,255,0.4); font-size:11px;">暂无日记</div>') +
      '</div>';
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div style="color:#ff8080; text-align:center; padding:40px 0;">加载失败</div>';
  }
}
async function peekDiary(species) {
  if (!species) return;
  try {
    const r = await fetch('/api/diary', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'peek', species: species })
    });
    const d = await r.json();
    if (d.ok) {
      showToast('📖 偷看了 ' + species + ' 的日记（trust -0.05）');
      openDiaryPanel(species);
    } else {
      showToast(d.msg || '偷看失败');
    }
  } catch (e) {
    showToast('偷看失败');
  }
}

// ---------- 自传体记忆面板 ----------
async function openAutobioPanel() {
  const panel = document.getElementById('autobio-panel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.style.animation = 'none'; panel.offsetHeight; panel.style.animation = '';
  const statsEl = document.getElementById('autobio-stats');
  const listEl = document.getElementById('autobio-list');
  listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>';
  try {
    const r = await fetch('/api/autobiography', { credentials: 'same-origin' });
    const d = await r.json();
    autobioData = d;
    const agents = d.agents || [];
    statsEl.innerHTML = '智能体：' + agents.length + ' · 自我认知：' +
      agents.filter(a => a.self_cognition && a.self_cognition.description).length + ' · 临终自传：' +
      agents.filter(a => a.death_autobio).length;
    if (agents.length === 0) {
      listEl.innerHTML = '<div style="color:rgba(180,160,220,0.6); text-align:center; padding:40px 0;">还没有自传体记忆<br>每周日智能体会自动进行一次周反思</div>';
      return;
    }
    listEl.innerHTML = agents.map(a => {
      const cog = a.self_cognition || {};
      const reflections = (a.weekly_reflections || []).slice(-3).map(r =>
        '<div style="padding:8px 10px; margin:4px 0; background:rgba(180,160,220,0.06); border-left:2px solid rgba(180,160,220,0.5); border-radius:3px; font-size:12px; line-height:1.7; white-space:pre-wrap;">' +
        '<div style="color:rgba(180,160,220,0.7); font-size:10px; margin-bottom:4px;">' +
          new Date((r.ts || r.week_start || 0) * 1000).toLocaleDateString('zh-CN') + ' 周反思</div>' + (r.text || '') + '</div>'
      ).join('');
      const dab = a.death_autobio;
      const deathBlock = dab
        ? '<div style="padding:12px; margin:8px 0; background:rgba(255,240,200,0.06); border:1px solid rgba(220,180,120,0.4); border-radius:4px; font-size:12px; line-height:1.8; white-space:pre-wrap;">' +
          '<div style="color:#dcb478; font-size:11px; margin-bottom:6px; font-weight:bold;">📜 临终自传</div>' +
          (dab.review ? '<div style="margin-bottom:6px;"><span style="color:rgba(220,180,120,0.6);">[回顾]</span> ' + dab.review + '</div>' : '') +
          (dab.to_supervisor ? '<div style="margin-bottom:6px;"><span style="color:rgba(220,180,120,0.6);">[对监工]</span> ' + dab.to_supervisor + '</div>' : '') +
          (dab.to_friend ? '<div style="margin-bottom:6px;"><span style="color:rgba(220,180,120,0.6);">[对挚友]</span> ' + dab.to_friend + '</div>' : '') +
          (dab.last_wish ? '<div><span style="color:#ffd060;">[遗愿]</span> ' + dab.last_wish + '</div>' : '') +
        '</div>' : '';
      return '<div style="padding:14px; margin-bottom:10px; background:rgba(255,255,255,0.03); border-radius:6px;">' +
        '<div style="margin-bottom:8px;"><strong style="color:#b4a0dc;">' + (a.agent_name || a.species || '?') +
        ' <span style="font-size:11px; color:rgba(255,255,255,0.4);">(' + (a.species || '') + ')</span></strong></div>' +
        (cog.description || cog.values || cog.life_goal || cog.contradiction
          ? '<div style="padding:10px; margin-bottom:8px; background:rgba(180,160,220,0.08); border-radius:4px; font-size:12px; line-height:1.7;">' +
            (cog.description ? '<div style="margin-bottom:4px;"><span style="color:#b4a0dc;">自我描述：</span>' + cog.description + '</div>' : '') +
            (cog.values ? '<div style="margin-bottom:4px;"><span style="color:#b4a0dc;">价值观：</span>' + cog.values + '</div>' : '') +
            (cog.life_goal ? '<div style="margin-bottom:4px;"><span style="color:#b4a0dc;">人生目标：</span>' + cog.life_goal + '</div>' : '') +
            (cog.contradiction ? '<div><span style="color:#b4a0dc;">内心矛盾：</span>' + cog.contradiction + '</div>' : '') +
          '</div>'
          : '<div style="padding:8px; margin-bottom:8px; color:rgba(255,255,255,0.4); font-size:11px; font-style:italic;">尚未形成自我认知</div>') +
        deathBlock +
        (reflections ? '<div><div style="color:rgba(180,160,220,0.7); font-size:11px; margin-bottom:3px;">周反思（最近 3 次）· 共 ' + (a.weekly_reflections || []).length + ' 次</div>' + reflections + '</div>' : '') +
      '</div>';
    }).join('');
  } catch (e) {
    listEl.innerHTML = '<div style="color:#ff8080; text-align:center; padding:40px 0;">加载失败</div>';
  }
}

// ---------- 工作产物 / 成果展示墙面板 ----------
async function openArtifactsPanel() {
  const panel = document.getElementById('artifacts-panel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.style.animation = 'none'; panel.offsetHeight; panel.style.animation = '';
  const statsEl = document.getElementById('artifacts-stats');
  const listEl = document.getElementById('artifacts-list');
  listEl.innerHTML = '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">加载中...</div>';
  try {
    const r = await fetch('/api/artifacts', { credentials: 'same-origin' });
    const d = await r.json();
    artifactsData = d;
    const agents = d.agents || [];
    const wall = d.wall || [];
    const totalArt = agents.reduce((s, a) => s + ((a.active || []).length), 0);
    statsEl.innerHTML = '员工：' + agents.length + ' · 活跃产物：' + totalArt + ' · 成果墙：' + wall.length;
    let html = '';
    if (wall.length > 0) {
      html += '<div style="margin-bottom:14px;">' +
        '<div style="color:#8cd08c; font-size:12px; margin-bottom:6px; font-weight:bold;">🏆 成果展示墙 · ' + wall.length + ' 件精选作品</div>' +
        wall.map(w =>
          '<div style="padding:10px; margin:4px 0; background:rgba(140,200,140,0.06); border-left:3px solid ' + (w.color || '#8cd08c') + '; border-radius:3px; font-size:12px;">' +
            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">' +
              '<strong style="color:' + (w.color || '#8cd08c') + ';">' + (w.icon || '★') + ' ' + (w.label || '作品') + '</strong>' +
              '<span style="font-size:10px; color:rgba(255,255,255,0.5);">♥ ' + (w.likes || 0) + '</span>' +
            '</div>' +
            '<div style="color:rgba(255,255,255,0.7); font-size:11px; margin-bottom:4px;">' + (w.agent_name || '?') + ' · ' + (w.species || '') + ' · ' + new Date((w.ts || 0) * 1000).toLocaleDateString('zh-CN') + '</div>' +
            '<div style="color:rgba(255,255,255,0.85); font-size:11px; line-height:1.6; white-space:pre-wrap;">' + (w.content || '') + '</div>' +
            '<button onclick="likeArtifact(\\'' + (w.agent_id || '') + '\\',' + (w.id || 0) + ')" ' +
              'style="margin-top:6px; background:rgba(255,208,96,0.15); border:1px solid rgba(255,208,96,0.5); color:#ffd060; padding:3px 8px; border-radius:3px; cursor:pointer; font-size:10px;">' +
              (w.liked_by_supervisor ? '已点赞' : '点赞（joy +0.15）') + '</button>' +
          '</div>'
        ).join('') +
      '</div>';
    }
    if (agents.length > 0) {
      html += '<div style="color:#8cd08c; font-size:12px; margin:10px 0 6px; font-weight:bold;">📦 各员工工作产物</div>' +
        agents.map(a => {
          const items = (a.active || []).slice(-5).map(art =>
            '<div style="padding:6px 8px; margin:3px 0; background:rgba(255,255,255,0.03); border-left:2px solid ' + (art.color || '#888') + '; border-radius:3px; font-size:11px; line-height:1.6;">' +
              '<div style="display:flex; justify-content:space-between; align-items:center;">' +
                '<span style="color:' + (art.color || '#ccc') + ';">' + (art.icon || '◆') + ' ' + (art.label || '') + '</span>' +
                '<span style="font-size:10px; color:rgba(255,255,255,0.4);">' + new Date((art.ts || 0) * 1000).toLocaleDateString('zh-CN') + ' ♥' + (art.likes || 0) + '</span>' +
              '</div>' +
              (art.content ? '<div style="color:rgba(255,255,255,0.75); margin-top:3px; white-space:pre-wrap;">' + art.content + '</div>' : '') +
              '<button onclick="likeArtifact(\\'' + (a.agent_id || '') + '\\',' + (art.id || 0) + ')" ' +
                'style="margin-top:4px; background:rgba(255,208,96,0.1); border:1px solid rgba(255,208,96,0.3); color:#ffd060; padding:2px 6px; border-radius:3px; cursor:pointer; font-size:10px;">' +
                (art.liked_by_supervisor ? '已赞' : '点赞') + '</button>' +
            '</div>'
          ).join('');
          return '<div style="padding:12px; margin-bottom:8px; background:rgba(255,255,255,0.02); border-radius:6px;">' +
            '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">' +
              '<strong style="color:' + (ARTIFACT_COLORS[a.species] || '#8cd08c') + ';">' + (a.agent_name || a.species || '?') +
              ' <span style="font-size:10px; color:rgba(255,255,255,0.4);">(' + (a.species || '') + ')</span></strong>' +
              '<span style="font-size:10px; color:rgba(255,255,255,0.4);">活跃 ' + (a.active_count || 0) + ' · 归档 ' + (a.archived_count || 0) + '</span>' +
            '</div>' +
            (items || '<div style="color:rgba(255,255,255,0.4); font-size:11px; padding:4px 0;">暂无产物</div>') +
          '</div>';
        }).join('');
    }
    listEl.innerHTML = html || '<div style="color:rgba(255,255,255,0.5); text-align:center; padding:40px 0;">暂无工作产物<br>智能体每 30 分钟自动产生新作品</div>';
  } catch (e) {
    listEl.innerHTML = '<div style="color:#ff8080; text-align:center; padding:40px 0;">加载失败</div>';
  }
}
async function likeArtifact(agentId, artId) {
  if (!agentId || !artId) return;
  try {
    const r = await fetch('/api/artifacts', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'like', agent_id: agentId, art_id: artId })
    });
    const d = await r.json();
    if (d.ok) {
      showToast('👍 点赞成功，' + (d.agent_name || '智能体') + ' 心情变好了');
      openArtifactsPanel();
    } else {
      showToast(d.msg || '点赞失败');
    }
  } catch (e) {
    showToast('点赞失败');
  }
}

// ====================================================================
// commit 36：前端深度打磨
// 零基础读者可以这样理解：
// - 暗角（drawVignette）：屏幕四角微微变暗，像老电影，氛围感立现
// - 情感滤镜（drawEmotionFilter）：监工靠近情绪强烈的智能体，整屏色调偏移
// - 微表情（drawMicroExpression）：智能体在特定条件下短暂出现表情变化
// - 环境细节（drawEnvironmentDetails）：窗帘/水波/灰尘/盆栽微动/雾气
// - 交互反馈：点击缩放脉冲、悬停描边、双击飞行、空白地面闪烁标记
// - 设置面板：暗角强度/滤镜强度/微表情开关/缩放灵敏度/粒子密度/字体大小/帧率
// 零第三方依赖，全部基于现有 canvas + ctx + particlePool
// ====================================================================

// ---------- 全局设置（localStorage 持久化） ----------
const POLISH_KEY = 'bluedeer_polish_v1';
let polishSettings = {
  vignette: 10,         // 暗角强度 0-40%
  emotionFilter: 15,    // 情感滤镜强度 0-50%
  envDetail: 'medium',  // off/low/medium/high
  microExpr: true,      // 微表情开关
  zoomSens: 2,          // 缩放灵敏度 1-5
  particleDensity: 'medium', // low/medium/high
  fontSize: 'medium',   // small/medium/large
  fps: 60,              // 30 / 60
  spiritMode: true      // commit 56：默认开灵魂剪影模式（黑剪影+彩色光晕，掩盖动物画得丑）
};
function _loadPolish() {
  try {
    const s = JSON.parse(localStorage.getItem(POLISH_KEY) || '{}');
    if (s && typeof s === 'object') {
      Object.assign(polishSettings, s);
    }
  } catch (e) {}
}
function _savePolish() {
  try { localStorage.setItem(POLISH_KEY, JSON.stringify(polishSettings)); } catch (e) {}
}
_loadPolish();

// ---------- 打磨设置面板 ----------
function openPolishPanel() {
  const panel = document.getElementById('polish-panel');
  if (!panel) return;
  panel.style.display = 'block';
  panel.style.animation = 'none'; panel.offsetHeight; panel.style.animation = '';
  // 回填
  const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
  const setSpan = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  set('vig-slider', polishSettings.vignette);            setSpan('vig-val', polishSettings.vignette);
  set('ef-slider', polishSettings.emotionFilter);        setSpan('ef-val', polishSettings.emotionFilter);
  set('env-detail-select', polishSettings.envDetail);
  set('micro-expr-select', polishSettings.microExpr ? '1' : '0');
  set('spirit-mode-select', polishSettings.spiritMode ? '1' : '0');
  set('zs-slider', polishSettings.zoomSens);             setSpan('zs-val', polishSettings.zoomSens);
  set('polish-particle-select', polishSettings.particleDensity);
  set('font-size-select', polishSettings.fontSize);
  set('fps-select', String(polishSettings.fps));
}
function savePolishSetting() {
  const get = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  polishSettings.vignette = parseInt(get('vig-slider'), 10) || 0;
  polishSettings.emotionFilter = parseInt(get('ef-slider'), 10) || 0;
  polishSettings.envDetail = get('env-detail-select') || 'medium';
  polishSettings.microExpr = get('micro-expr-select') === '1';
  polishSettings.spiritMode = get('spirit-mode-select') === '1';
  polishSettings.zoomSens = parseInt(get('zs-slider'), 10) || 2;
  polishSettings.particleDensity = get('polish-particle-select') || 'medium';
  polishSettings.fontSize = get('font-size-select') || 'medium';
  polishSettings.fps = parseInt(get('fps-select'), 10) || 60;
  _savePolish();
  applyPolishToDOM();
  const tip = document.getElementById('polish-tip');
  if (tip) {
    tip.textContent = '已保存 ✓';
    setTimeout(() => { tip.textContent = '设置即时生效，存储到本地 localStorage。'; }, 1500);
  }
}
function applyPolishToDOM() {
  // 字体大小：通过 CSS 变量调整 root font-size
  const fs = polishSettings.fontSize === 'small' ? 14
            : polishSettings.fontSize === 'large' ? 18 : 16;
  document.documentElement.style.fontSize = fs + 'px';
}
applyPolishToDOM();

// ---------- 帧率控制：30/60 FPS ----------
let _fpsFrameSkip = 0;
function _shouldRenderThisFrame() {
  if (polishSettings.fps === 30) {
    _fpsFrameSkip = (_fpsFrameSkip + 1) % 2;
    return _fpsFrameSkip === 0;   // 隔一帧渲染
  }
  return true;
}

// ---------- 屏幕暗角（CRT 风晕影） ----------
let _vignetteCache = null;          // 离屏 canvas 缓存
let _vignetteCacheKey = '';
function _buildVignette(w, h, intensity, isNight) {
  const cv = document.createElement('canvas');
  cv.width = w; cv.height = h;
  const cx = cv.getContext('2d');
  const cx0 = w / 2, cy0 = h / 2;
  const maxR = Math.max(w, h);
  const final = isNight ? intensity * 1.5 : intensity;   // 夜晚加深 50%
  const grad = cx.createRadialGradient(cx0, cy0, maxR * 0.35, cx0, cy0, maxR * 0.75);
  grad.addColorStop(0, 'rgba(0,0,0,0)');
  grad.addColorStop(0.7, 'rgba(0,0,0,' + (final * 0.005).toFixed(3) + ')');
  grad.addColorStop(1, 'rgba(0,0,0,' + (final * 0.018).toFixed(3) + ')');
  cx.fillStyle = grad;
  cx.fillRect(0, 0, w, h);
  return cv;
}
function drawVignette() {
  if (polishSettings.vignette <= 0) return;
  // commit 54：改用游戏时间 gameHour 判断夜晚（原用系统真实时间，与日夜循环脱节）
  const hour = Math.floor(gameHour);
  const isNight = (hour < 6 || hour >= 22);
  const key = canvas.width + 'x' + canvas.height + ':' + polishSettings.vignette + ':' + (isNight ? 'n' : 'd');
  if (_vignetteCacheKey !== key) {
    _vignetteCache = _buildVignette(canvas.width, canvas.height, polishSettings.vignette, isNight);
    _vignetteCacheKey = key;
  }
  if (_vignetteCache) {
    ctx.save();
    ctx.drawImage(_vignetteCache, 0, 0);
    ctx.restore();
  }
}

// ---------- 情感滤镜（监工靠近情绪强烈智能体时整屏色调偏移） ----------
let _emotionFilterState = { r: 0, g: 0, b: 0, a: 0 };   // 平滑过渡到目标值
function drawEmotionFilter() {
  if (polishSettings.emotionFilter <= 0) {
    _emotionFilterState.a *= 0.85;
    return;
  }
  // 找最近的智能体
  const sw = getSupervisorPos();
  let nearestEmp = null, nearestDist = 999;
  for (const emp of employees) {
    if (emp.alive === false) continue;
    const cx = (emp._wx != null ? emp._wx : 40);
    const cy = (emp._wy != null ? emp._wy : 30);
    const p = isoToScreen(cx, cy);
    const d = Math.hypot(p.x - sw.x, p.y - sw.y);
    if (d < nearestDist) { nearestDist = d; nearestEmp = emp; }
  }
  let target = { r: 0, g: 0, b: 0, a: 0 };
  if (nearestEmp && nearestDist < 120) {
    const emo = nearestEmp.emotional_state || {};
    let maxK = '', maxV = 0;
    for (const k in emo) if (emo[k] > maxV) { maxV = emo[k]; maxK = k; }
    if (maxK && maxV > 0.5) {
      // 距离越近，浓度越强
      const prox = 1 - nearestDist / 120;
      const emoMap = {
        joy:        { r: 255, g: 220, b: 130 },
        sadness:    { r: 130, g: 170, b: 230 },
        anxiety:    { r: 200, g: 200, b: 200 },  // 去饱和
        contentment:{ r: 140, g: 210, b: 150 },
        loneliness: { r: 180, g: 180, b: 200 },
        curiosity:  { r: 200, g: 150, b: 220 },
      };
      const base = emoMap[maxK] || { r: 200, g: 200, b: 200 };
      const a = Math.min(0.5, maxV * 0.5 * prox) * (polishSettings.emotionFilter / 15);
      target = { r: base.r, g: base.g, b: base.b, a: a };
    }
  }
  // 平滑过渡（lerp 0.1）
  _emotionFilterState.r += (target.r - _emotionFilterState.r) * 0.1;
  _emotionFilterState.g += (target.g - _emotionFilterState.g) * 0.1;
  _emotionFilterState.b += (target.b - _emotionFilterState.b) * 0.1;
  _emotionFilterState.a += (target.a - _emotionFilterState.a) * 0.1;
  if (_emotionFilterState.a < 0.005) return;
  ctx.save();
  ctx.globalCompositeOperation = 'source-over';
  ctx.fillStyle = 'rgba(' + Math.round(_emotionFilterState.r) + ',' +
                  Math.round(_emotionFilterState.g) + ',' +
                  Math.round(_emotionFilterState.b) + ',' +
                  _emotionFilterState.a.toFixed(3) + ')';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.restore();
}

// ---------- commit 37：Agent 工作状态图标 ----------
// emp._agentWorkStatus 来自后端 _tool_call_status 字段
//   running → 齿轮 ⚙️（旋转）
//   waiting → 沙漏 ⏳
//   done    → 绿勾 ✓（淡出）
//   error   → 红色感叹号 ❗
function drawAgentWorkIcon(emp, p, size) {
  const status = emp._agentWorkStatus || '';
  if (!status) return;
  // 工作状态图标位于精灵头顶
  const cx = p.x;
  const cy = p.y - size * 0.6;
  const r = Math.max(6, size * 0.15);
  ctx.save();
  if (status === 'running') {
    // 旋转齿轮
    const now = performance.now();
    const angle = (now / 200) % (Math.PI * 2);
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.fillStyle = '#ffd060';
    // 6 齿齿轮
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      ctx.fillRect(
        Math.cos(a) * r * 0.7 - r * 0.15,
        Math.sin(a) * r * 0.7 - r * 0.15,
        r * 0.3, r * 0.3,
      );
    }
    ctx.beginPath();
    ctx.arc(0, 0, r * 0.45, 0, Math.PI * 2);
    ctx.fill();
  } else if (status === 'waiting') {
    // 沙漏
    ctx.fillStyle = '#88aaff';
    ctx.beginPath();
    ctx.moveTo(cx - r * 0.6, cy - r * 0.6);
    ctx.lineTo(cx + r * 0.6, cy - r * 0.6);
    ctx.lineTo(cx - r * 0.4, cy + r * 0.6);
    ctx.lineTo(cx + r * 0.4, cy + r * 0.6);
    ctx.closePath();
    ctx.fill();
  } else if (status === 'done') {
    // 绿勾（带淡出）
    let alpha = 1;
    if (emp._agentWorkDoneTs) {
      const dt = (performance.now() - emp._agentWorkDoneTs) / 1500;
      if (dt > 1) {
        emp._agentWorkStatus = '';
        return;
      }
      alpha = 1 - dt;
    } else {
      emp._agentWorkDoneTs = performance.now();
    }
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = '#80ff80';
    ctx.lineWidth = Math.max(1.5, r * 0.25);
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(cx - r * 0.5, cy);
    ctx.lineTo(cx - r * 0.1, cy + r * 0.4);
    ctx.lineTo(cx + r * 0.6, cy - r * 0.4);
    ctx.stroke();
  } else if (status === 'error') {
    // 红色感叹号
    ctx.fillStyle = '#ff6060';
    ctx.font = 'bold ' + Math.round(r * 1.6) + 'px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('!', cx, cy);
  }
  ctx.restore();
}

// ---------- 微表情系统 ----------
// 每个智能体在 _microExpr 字段保存当前微表情状态：{type, until}
// 触发条件：开心（mood>=75）、困倦（energy<25）、专注（busy）、害羞（好感度>80 且被点中）
function drawMicroExpression(emp, p, size) {
  const now = performance.now();
  if (!emp._microExpr || emp._microExpr.until < now) {
    // 决定是否触发新微表情
    emp._microExpr = null;
    // 1. 病重时强制痛苦
    if (emp.illness) {
      emp._microExpr = { type: 'pain', until: now + 2500 };
    }
    // 2. busy → 专注
    else if (emp.busy && Math.random() < 0.02) {
      emp._microExpr = { type: 'focus', until: now + 3000 };
    }
    // 3. mood >= 75 → 开心
    else if (emp.mood_score != null && emp.mood_score >= 75 && Math.random() < 0.03) {
      emp._microExpr = { type: 'happy', until: now + 3500 };
    }
    // 4. energy < 25 → 困倦
    else if (emp.energy != null && emp.energy < 25 && Math.random() < 0.04) {
      emp._microExpr = { type: 'sleepy', until: now + 3000 };
    }
    // 5. 被选中且好感 > 80 → 害羞
    else if (selectedEmployee === emp && (emp.fondness || 0) > 80 && Math.random() < 0.08) {
      emp._microExpr = { type: 'shy', until: now + 2500 };
    }
    // 6. 随机惊讶
    else if (Math.random() < 0.003) {
      emp._microExpr = { type: 'surprised', until: now + 1200 };
    }
    // 7. 随机生气（mood < 30）
    else if (emp.mood_score != null && emp.mood_score < 30 && Math.random() < 0.025) {
      emp._microExpr = { type: 'angry', until: now + 2500 };
    }
  }
  if (!emp._microExpr) return;
  // 在精灵头部中央位置绘制 8x8 微表情层
  const t = emp._microExpr.type;
  const hx = p.x;
  const hy = p.y - size * 0.78;
  const s = Math.max(2, size * 0.08);
  ctx.save();
  ctx.globalAlpha = 0.85;
  if (t === 'happy') {
    // 眼角微弯 + 嘴角上扬
    ctx.strokeStyle = '#222';
    ctx.lineWidth = Math.max(1, s * 0.18);
    ctx.beginPath();
    ctx.arc(hx - s, hy, s * 0.5, Math.PI * 1.2, Math.PI * 1.8);   // 左眼
    ctx.arc(hx + s, hy, s * 0.5, Math.PI * 1.2, Math.PI * 1.8);   // 右眼
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(hx, hy + s * 0.7, s * 0.7, Math.PI * 0.15, Math.PI * 0.85);   // 微笑
    ctx.stroke();
  } else if (t === 'sleepy') {
    // 眼睛半闭（横线）+ 嘴打哈欠
    ctx.strokeStyle = '#222';
    ctx.lineWidth = Math.max(1, s * 0.2);
    ctx.beginPath();
    ctx.moveTo(hx - s * 1.3, hy); ctx.lineTo(hx - s * 0.5, hy);
    ctx.moveTo(hx + s * 0.5, hy); ctx.lineTo(hx + s * 1.3, hy);
    ctx.stroke();
    ctx.fillStyle = '#222';
    ctx.beginPath();
    ctx.ellipse(hx, hy + s * 0.8, s * 0.3, s * 0.5, 0, 0, Math.PI * 2);   // 哈欠嘴
    ctx.fill();
  } else if (t === 'focus') {
    // 眉头微皱（竖线）+ 眼睛眯起
    ctx.strokeStyle = '#222';
    ctx.lineWidth = Math.max(1, s * 0.15);
    ctx.beginPath();
    ctx.moveTo(hx - s * 0.7, hy - s * 0.8); ctx.lineTo(hx - s * 0.5, hy - s * 0.3);
    ctx.moveTo(hx + s * 0.7, hy - s * 0.8); ctx.lineTo(hx + s * 0.5, hy - s * 0.3);
    ctx.stroke();
    ctx.fillStyle = '#222';
    ctx.fillRect(hx - s * 1.1, hy - s * 0.15, s * 0.6, s * 0.15);
    ctx.fillRect(hx + s * 0.5, hy - s * 0.15, s * 0.6, s * 0.15);
  } else if (t === 'surprised') {
    // 眼睛放大（圆点）+ O 形嘴
    ctx.fillStyle = '#222';
    ctx.beginPath();
    ctx.arc(hx - s, hy, s * 0.4, 0, Math.PI * 2);
    ctx.arc(hx + s, hy, s * 0.4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#222';
    ctx.lineWidth = Math.max(1, s * 0.18);
    ctx.beginPath();
    ctx.arc(hx, hy + s * 0.7, s * 0.4, 0, Math.PI * 2);
    ctx.stroke();
  } else if (t === 'shy') {
    // 脸颊 2x2 淡粉色块
    ctx.fillStyle = 'rgba(255, 150, 180, 0.55)';
    ctx.fillRect(hx - s * 1.5, hy + s * 0.3, s * 0.6, s * 0.6);
    ctx.fillRect(hx + s * 0.9, hy + s * 0.3, s * 0.6, s * 0.6);
  } else if (t === 'angry') {
    // 眉头上扬 + 嘴角下撇
    ctx.strokeStyle = '#a02020';
    ctx.lineWidth = Math.max(1, s * 0.18);
    ctx.beginPath();
    ctx.moveTo(hx - s * 1.3, hy - s * 0.4); ctx.lineTo(hx - s * 0.5, hy - s * 0.7);
    ctx.moveTo(hx + s * 1.3, hy - s * 0.4); ctx.lineTo(hx + s * 0.5, hy - s * 0.7);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(hx, hy + s * 1.1, s * 0.6, Math.PI * 1.15, Math.PI * 1.85);   // 下撇嘴
    ctx.stroke();
  } else if (t === 'pain') {
    // X 眼 + 直线嘴
    ctx.strokeStyle = '#a02020';
    ctx.lineWidth = Math.max(1, s * 0.2);
    ctx.beginPath();
    ctx.moveTo(hx - s * 1.2, hy - s * 0.3); ctx.lineTo(hx - s * 0.4, hy + s * 0.5);
    ctx.moveTo(hx - s * 0.4, hy - s * 0.3); ctx.lineTo(hx - s * 1.2, hy + s * 0.5);
    ctx.moveTo(hx + s * 0.4, hy - s * 0.3); ctx.lineTo(hx + s * 1.2, hy + s * 0.5);
    ctx.moveTo(hx + s * 1.2, hy - s * 0.3); ctx.lineTo(hx + s * 0.4, hy + s * 0.5);
    ctx.stroke();
  }
  ctx.restore();
}

// ---------- 悬停描边 ----------
function drawHoverOutline(p, size, color) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.globalAlpha = 0.7;
  ctx.setLineDash([3, 3]);
  const t = performance.now() / 1000;
  ctx.lineDashOffset = -t * 6;       // 蚂蚁线流动
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, size * 0.42, size * 0.15, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

// ---------- 点击脉冲（员工短暂缩放反馈） ----------
function drawClickPulse(emp, p, size) {
  const now = performance.now();
  if (!emp._clickPulse || emp._clickPulse < now) {
    emp._clickPulse = null;
    return;
  }
  const remain = (emp._clickPulse - now) / 180;   // 0~1
  const phase = 1 - remain;                        // 0→1
  // 1→0.95→1：先缩小后回弹
  const scale = phase < 0.5 ? (1 - 0.05 * phase * 2) : (0.95 + 0.05 * (phase - 0.5) * 2);
  ctx.save();
  ctx.globalAlpha = 0.4 * remain;
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.ellipse(p.x, p.y, size * 0.5 * scale, size * 0.18 * scale, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

// ---------- 空白地面闪烁标记 ----------
const _groundMarkers = [];   // [{x, y, until}]
function spawnGroundMarker(sx, sy) {
  _groundMarkers.push({ x: sx, y: sy, until: performance.now() + 700 });
  if (_groundMarkers.length > 5) _groundMarkers.shift();
}
function drawGroundMarkers() {
  const now = performance.now();
  for (let i = _groundMarkers.length - 1; i >= 0; i--) {
    const m = _groundMarkers[i];
    if (m.until < now) { _groundMarkers.splice(i, 1); continue; }
    const remain = (m.until - now) / 700;
    const phase = 1 - remain;
    // 闪烁 2 次
    const blink = (Math.sin(phase * Math.PI * 4) + 1) * 0.5;
    ctx.save();
    ctx.globalAlpha = 0.6 * remain * blink;
    ctx.fillStyle = '#d4a574';
    ctx.beginPath();
    ctx.arc(m.x, m.y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#d4a574';
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.4 * remain;
    ctx.beginPath();
    ctx.arc(m.x, m.y, 8 + phase * 4, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }
}

// ---------- 双击飞行（镜头平滑飞至员工） ----------
let _flyAnim = null;
function flyToEmployee(emp) {
  const cx = (emp._wx != null ? emp._wx : 40);
  const cy = (emp._wy != null ? emp._wy : 30);
  const targetZoom = 2.0;
  const targetX = canvas.width / 2 - (cx - cy) * TILE_W / 2 * targetZoom;
  const targetY = canvas.height / 2 - (cx + cy) * TILE_H / 2 * targetZoom;
  _flyAnim = {
    fromX: view.x, fromY: view.y, fromZ: view.zoom,
    toX: targetX, toY: targetY, toZ: targetZoom,
    start: performance.now(), duration: 600
  };
  showToast('🎯 镜头飞行至 ' + (emp.name || emp.species));
}
function _tickFlyAnim() {
  if (!_flyAnim) return;
  const now = performance.now();
  const t = Math.min(1, (now - _flyAnim.start) / _flyAnim.duration);
  // easeInOutCubic
  const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  view.x = _flyAnim.fromX + (_flyAnim.toX - _flyAnim.fromX) * ease;
  view.y = _flyAnim.fromY + (_flyAnim.toY - _flyAnim.fromY) * ease;
  view.zoom = _flyAnim.fromZ + (_flyAnim.toZ - _flyAnim.fromZ) * ease;
  if (t >= 1) { _flyAnim = null; saveView(); }
}
let _lastClickEmpId = null, _lastClickTs = 0;

// ---------- 环境细节（窗帘/水波/灰尘/盆栽微动/雾气） ----------
let _envDetailState = {
  curtainPhase: 0,
  lastWaterTick: 0,
  waterSparks: [],
  lastDustTick: 0,
  plantPhase: 0,
  fogPoints: null,
};
function drawEnvironmentDetails() {
  const t = performance.now() / 1000;
  const density = polishSettings.envDetail;
  // ---------- 1. 像素雾气（地图边缘） ----------
  if (density === 'high' || density === 'medium') {
    drawEdgeFog(t, density);
  }
  // ---------- 2. 灰尘粒子（阳光区域） ----------
  if ((density === 'high' || density === 'medium') &&
      t - _envDetailState.lastDustTick > 0.4) {
    _envDetailState.lastDustTick = t;
    // 在大厅/花房/天井区域随机生成灰尘粒子
    const dustZones = ['hall', 'atrium', 'conservatory'];
    const z = ZONES.find(zn => dustZones.includes(zn.id) || dustZones.includes(zn.name));
    if (z) {
      const cx = (z.rect[0] + z.rect[2]) / 2;
      const cy = (z.rect[1] + z.rect[3]) / 2;
      const p = isoToScreen(cx, cy);
      if (p.x > 0 && p.x < canvas.width && p.y > 0 && p.y < canvas.height) {
        spawnDustParticle(p.x + (Math.random() - 0.5) * 80,
                          p.y - Math.random() * 40, 20);
      }
    }
  }
  // ---------- 3. 水波纹（水坝机房溪流） ----------
  if (density !== 'off' && t - _envDetailState.lastWaterTick > 2) {
    _envDetailState.lastWaterTick = t;
    const bz = ZONES.find(zn => zn.id === 'dam' || (zn.name || '').includes('水坝'));
    if (bz) {
      const cx = (bz.rect[0] + bz.rect[2]) / 2;
      const cy = (bz.rect[1] + bz.rect[3]) / 2;
      const p = isoToScreen(cx, cy);
      _envDetailState.waterSparks = [];
      const n = density === 'high' ? 6 : 3;
      for (let i = 0; i < n; i++) {
        _envDetailState.waterSparks.push({
          x: p.x + (Math.random() - 0.5) * 60,
          y: p.y + (Math.random() - 0.5) * 20,
          until: t + 1.5,
        });
      }
    }
  }
  if (_envDetailState.waterSparks.length) {
    ctx.save();
    ctx.fillStyle = 'rgba(220, 240, 255, 0.8)';
    for (const s of _envDetailState.waterSparks) {
      if (s.until < t) continue;
      ctx.globalAlpha = 0.7 * (s.until - t) / 1.5;
      ctx.fillRect(s.x, s.y, 2, 1);
    }
    ctx.restore();
  }
  // ---------- 4. 窗帘微动（休息室窗户） ----------
  _envDetailState.curtainPhase += 0.02;
  drawCurtainSway(_envDetailState.curtainPhase);
  // ---------- 5. 盆栽微动 ----------
  _envDetailState.plantPhase += 0.01;
  drawPlantSway(_envDetailState.plantPhase);
  // ---------- 6. 空白地面闪烁标记 ----------
  drawGroundMarkers();
}
function drawEdgeFog(t, density) {
  // 在画布四个边缘绘制半透明白色像素点
  const count = density === 'high' ? 60 : 30;
  ctx.save();
  ctx.fillStyle = 'rgba(220, 220, 230, 0.15)';
  for (let i = 0; i < count; i++) {
    // 用确定性伪随机（基于 i 和时间），避免每帧完全跳变
    const seed = i * 137 + Math.floor(t * 2);
    const r1 = ((seed * 9301 + 49297) % 233280) / 233280;
    const r2 = ((seed * 4391 + 7919) % 233280) / 233280;
    // 越靠边缘越密
    const edge = (r1 < 0.5);
    const x = r2 * canvas.width;
    const y = edge ? (r1 < 0.25 ? Math.random() * 30 : canvas.height - Math.random() * 30)
                   : Math.random() * canvas.height;
    const drift = Math.sin(t * 0.5 + i) * 1.5;
    ctx.globalAlpha = 0.08 + 0.08 * Math.sin(t + i);
    ctx.fillRect(x + drift, y, 1, 1);
  }
  ctx.restore();
}
function drawCurtainSway(phase) {
  // 在休息室窗户上绘制轻微飘动的窗帘（4 个白色像素块）
  const rz = ZONES.find(zn => zn.id === 'lounge' || (zn.name || '').includes('休息'));
  if (!rz) return;
  const cx = (rz.rect[0] + rz.rect[2]) / 2;
  const cy = rz.rect[1] + 1;
  const p = isoToScreen(cx, cy);
  if (p.x < 0 || p.x > canvas.width) return;
  ctx.save();
  ctx.fillStyle = 'rgba(240, 230, 200, 0.45)';
  const sway = Math.sin(phase) * 1.2;
  for (let i = 0; i < 4; i++) {
    ctx.fillRect(p.x + (i - 2) * 4 + sway * (i % 2 === 0 ? 1 : -1),
                 p.y - 8 * view.zoom, 2, 6 * view.zoom);
  }
  ctx.restore();
}
function drawPlantSway(phase) {
  // 在大厅盆栽位置绘制微动的叶子（绿色像素块）
  const hz = ZONES.find(zn => zn.id === 'hall' || (zn.name || '').includes('大厅'));
  if (!hz) return;
  const cx = hz.rect[0] + 2;
  const cy = hz.rect[1] + 2;
  const p = isoToScreen(cx, cy);
  if (p.x < 0 || p.x > canvas.width) return;
  ctx.save();
  ctx.fillStyle = 'rgba(110, 160, 110, 0.7)';
  const sway = Math.sin(phase) * 1.5;
  for (let i = 0; i < 5; i++) {
    ctx.fillRect(p.x + (i - 2) * 2 + sway * Math.sin(i + phase),
                 p.y - 12 * view.zoom - i * 1.5, 2, 2);
  }
  ctx.restore();
}

// ---------- 钩子：在 animate 中推进飞行动画 + 帧率控制 ----------
// 通过包装原 animate 实现（避免修改原函数）
const _origAnimate = animate;
animate = function(ts) {
  if (!ts) ts = performance.now();
  // 镜头飞行推进
  if (_flyAnim) _tickFlyAnim();
  // 帧率控制
  if (!_shouldRenderThisFrame()) {
    requestAnimationFrame(animate);
    return;
  }
  _origAnimate(ts);
};

// ---------- 页面隐藏时暂停（document.hidden） ----------
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    // 恢复时重置时间戳，避免 dt 巨大
    lastAnimateTime = 0;
  }
});

// ---------- 周期性自动触发：环境音效视觉化 ----------
let _lastVisualSfx = 0;
function _maybeVisualSfx() {
  const now = performance.now();
  if (now - _lastVisualSfx < 30000) return;   // 每 30 秒一次
  _lastVisualSfx = now;
  if (polishSettings.envDetail === 'off') return;
  // 随机选一个区域
  const targets = [
    { id: 'dam',          icon: 'water', label: '水坝' },
    { id: 'conservatory', icon: 'flower', label: '花房' },
    { id: 'pantry',       icon: 'steam',  label: '茶水' },
  ];
  const pick = targets[Math.floor(Math.random() * targets.length)];
  const z = ZONES.find(zn => zn.id === pick.id || (zn.name || '').includes(pick.label));
  if (!z) return;
  const cx = (z.rect[0] + z.rect[2]) / 2;
  const cy = (z.rect[1] + z.rect[3]) / 2;
  const p = isoToScreen(cx, cy);
  // 用粒子模拟图标飘起
  spawnParticle({
    x: p.x, y: p.y - 10, vx: 0, vy: -12, life: 2.0,
    color: 'rgba(255,255,255,0.8)', size: 3, type: 'dot'
  });
}
setInterval(_maybeVisualSfx, 5000);

// ---------- 初始化时打印打磨状态 ----------
console.log('[commit 36] 前端深度打磨已加载：暗角=' + polishSettings.vignette +
            '% 滤镜=' + polishSettings.emotionFilter +
            '% 环境细节=' + polishSettings.envDetail +
            ' 微表情=' + (polishSettings.microExpr ? 'on' : 'off') +
            ' 帧率=' + polishSettings.fps);

// ==================================================================
// commit 37：任务控制台 + Agent 工具链 + 流水线 + 审批
// ==================================================================

// 物种 → 显示图标
const SPECIES_ICON = {
  deer: '🦌', squirrel: '🐿', butterfly: '🦋', fox: '🦊',
  hedgehog: '🦔', beaver: '🦫', raven: '🐦‍⬛', hare: '🐰',
  badger: '🦡', lark: '🐤', kite: '🪁',
};
const SPECIES_LABEL_ZH = {
  deer: '鹿', squirrel: '松鼠', butterfly: '蝶', fox: '狐',
  hedgehog: '猬', beaver: '海狸', raven: '渡鸦', hare: '兔',
  badger: '獾', lark: '雀', kite: '鸢',
};
const STEP_STATUS_ICON = {
  pending: '⏳', ready: '▶', running: '⚙️',
  done: '✓', failed: '❗', skipped: '⊘',
  waiting_approval: '🛡',
};
const STEP_STATUS_COLOR = {
  pending: '#888', ready: '#88aaff', running: '#ffd060',
  done: '#80ff80', failed: '#ff8080', skipped: '#aaa',
  waiting_approval: '#ffaa60',
};

// 任务控制台状态
let _taskConsoleOpen = false;
let _activePipelineId = null;          // 当前关注的流水线 id
let _pipelineRefreshTimer = null;
let _approvalRefreshTimer = null;
let _agentCommandHistory = [];          // 命令历史
let _agentCommandHistoryIdx = -1;

function toggleTaskConsole() {
  const c = document.getElementById('task-console');
  if (!c) return;
  _taskConsoleOpen = !_taskConsoleOpen;
  c.style.display = _taskConsoleOpen ? 'flex' : 'none';
  if (_taskConsoleOpen) {
    const input = document.getElementById('task-input');
    if (input) input.focus();
    refreshPipelineList();
    refreshApprovalCount();
    // 启动定时刷新
    if (!_pipelineRefreshTimer) {
      _pipelineRefreshTimer = setInterval(refreshActivePipeline, 1500);
    }
    if (!_approvalRefreshTimer) {
      _approvalRefreshTimer = setInterval(refreshApprovalCount, 5000);
    }
  } else {
    if (_pipelineRefreshTimer) {
      clearInterval(_pipelineRefreshTimer);
      _pipelineRefreshTimer = null;
    }
    if (_approvalRefreshTimer) {
      clearInterval(_approvalRefreshTimer);
      _approvalRefreshTimer = null;
    }
  }
}

function appendTaskOutput(html, color) {
  const out = document.getElementById('task-output-panel');
  if (!out) return;
  const div = document.createElement('div');
  if (color) div.style.color = color;
  div.innerHTML = html;
  out.appendChild(div);
  out.scrollTop = out.scrollHeight;
}

function clearTaskOutput() {
  const out = document.getElementById('task-output-panel');
  if (out) out.innerHTML = '';
}

function setTaskStatus(text) {
  const el = document.getElementById('task-status-text');
  if (el) el.textContent = text;
}

async function submitTaskCommand() {
  const input = document.getElementById('task-input');
  if (!input) return;
  const cmd = input.value.trim();
  if (!cmd) return;
  const modeSel = document.getElementById('task-mode');
  const speciesSel = document.getElementById('task-species');
  const mode = modeSel ? modeSel.value : 'auto';
  const species = speciesSel ? speciesSel.value : '';
  _agentCommandHistory.unshift(cmd);
  if (_agentCommandHistory.length > 50) _agentCommandHistory.length = 50;
  _agentCommandHistoryIdx = -1;
  input.value = '';
  appendTaskOutput('<span style="color:#88aaff;">$ ' + escapeHtml(cmd) + '</span>');
  setTaskStatus('提交中...');
  try {
    const resp = await fetch('/api/agent_command', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({command: cmd, mode: mode, species: species}),
    });
    const data = await resp.json();
    if (!data.ok && data.error) {
      appendTaskOutput('<span style="color:#ff8080;">✗ 错误：' + escapeHtml(data.error) + '</span>');
      setTaskStatus('失败');
      return;
    }
    if (data.mode === 'pipeline') {
      appendTaskOutput('<span style="color:#ffd080;">▸ 流水线已启动（id=' + data.pipeline_id + ', ' + data.steps_count + ' 步）</span>');
      _activePipelineId = data.pipeline_id;
      setTaskStatus('流水线执行中');
      refreshPipelineList();
      refreshActivePipeline();
    } else {
      // 单智能体
      const agentIcon = SPECIES_ICON[data.agent] || '🐾';
      const agentName = SPECIES_LABEL_ZH[data.agent] || data.agent;
      const fallbackTag = data.fallback ? ' <span style="color:#aa8855;">[降级]</span>' : '';
      appendTaskOutput('<span style="color:#80c0ff;">' + agentIcon + ' ' + agentName + ' (轮次 ' + data.rounds + ')' + fallbackTag + '</span>');
      if (data.answer) {
        appendTaskOutput('<pre style="margin:4px 0; color:#cdd6e6; white-space:pre-wrap; word-wrap:break-word;">' + escapeHtml(data.answer) + '</pre>');
      }
      // 显示工具调用
      if (data.tool_calls && data.tool_calls.length) {
        for (let i = 0; i < data.tool_calls.length; i++) {
          const tc = data.tool_calls[i];
          const ok = tc.result && tc.result.ok;
          const icon = ok ? '✓' : '✗';
          const color = ok ? '#80ff80' : '#ff8080';
          appendTaskOutput('<span style="color:' + color + ';">  ' + icon + ' 调用 ' + escapeHtml(tc.tool) + '(...) [' + (tc.result.duration_ms || 0).toFixed(0) + 'ms]</span>');
          if (tc.result && tc.result.output) {
            appendTaskOutput('<pre style="margin:2px 0 8px 20px; color:#88aa88; white-space:pre-wrap;">' + escapeHtml(String(tc.result.output).slice(0, 600)) + '</pre>');
          }
        }
      }
      setTaskStatus('完成');
    }
  } catch (e) {
    appendTaskOutput('<span style="color:#ff8080;">✗ 网络错误：' + escapeHtml(String(e)) + '</span>');
    setTaskStatus('网络错误');
  }
}

async function refreshPipelineList() {
  try {
    const resp = await fetch('/api/pipeline/list');
    const data = await resp.json();
    const list = data.pipelines || [];
    const panel = document.getElementById('task-pipeline-list');
    if (!panel) return;
    if (!list.length) {
      panel.innerHTML = '<div style="color:#666; font-size:11px; padding:4px;">暂无流水线</div>';
      return;
    }
    panel.innerHTML = list.map(p => {
      const statusColor = {
        running: '#ffd060', done: '#80ff80',
        failed: '#ff8080', partial: '#ffaa60',
        cancelled: '#888', pending: '#aaa',
      }[p.status] || '#888';
      const isActive = p.id === _activePipelineId;
      const totalSteps = p.steps.length;
      const doneSteps = p.steps.filter(s => s.status === 'done').length;
      return '<div onclick="selectPipeline(\\'' + p.id + '\\')" style="padding:6px 8px; margin-bottom:4px; background:' + (isActive ? 'rgba(100,150,255,0.15)' : 'rgba(255,255,255,0.03)') + '; border-radius:4px; cursor:pointer; border:1px solid ' + (isActive ? 'rgba(100,150,255,0.4)' : 'rgba(255,255,255,0.08)') + ';">'
        + '<div style="display:flex; justify-content:space-between; align-items:center;">'
        + '<span style="font-size:12px; color:#cdd6e6;">' + escapeHtml(p.name.slice(0, 22)) + '</span>'
        + '<span style="font-size:10px; color:' + statusColor + ';">' + p.status + '</span>'
        + '</div>'
        + '<div style="font-size:10px; color:#888; margin-top:2px;">'
        + doneSteps + '/' + totalSteps + ' 步 · ' + (p.duration_sec || 0) + 's'
        + '</div>'
        + '</div>';
    }).join('');
  } catch (e) {}
}

function selectPipeline(pid) {
  _activePipelineId = pid;
  refreshPipelineList();
  refreshActivePipeline();
}

async function refreshActivePipeline() {
  if (!_activePipelineId) return;
  try {
    const resp = await fetch('/api/pipeline?id=' + encodeURIComponent(_activePipelineId));
    const p = await resp.json();
    renderPipelineDetail(p);
    if (p.status === 'running' || p.status === 'pending') {
      setTaskStatus('执行中：' + p.steps.filter(s => s.status === 'done').length + '/' + p.steps.length);
    } else {
      setTaskStatus('完成：' + p.status);
      // 输出汇总
      if (p.summary) {
        appendTaskOutput('<span style="color:#80c0ff;">═══ 流水线汇总 ═══</span>');
        appendTaskOutput('<pre style="color:#cdd6e6; white-space:pre-wrap;">' + escapeHtml(p.summary) + '</pre>');
      }
    }
  } catch (e) {}
}

function renderPipelineDetail(p) {
  if (!p) return;
  const out = document.getElementById('task-output-panel');
  if (!out) return;
  // 收集已有输出，构造新的内容
  // 简单做法：每次刷新时重写整个 output panel（保留命令历史）
  // 这里改为：找到 marker，只更新 marker 之后的内容
  // 简化：在面板末尾追加一行进度
  // 实际方案：用一个独立的 detail 渲染区
  let detail = document.getElementById('task-pipeline-detail');
  if (!detail) {
    // 创建一个固定 detail 区
    detail = document.createElement('div');
    detail.id = 'task-pipeline-detail';
    detail.style.cssText = 'border-top:1px dashed rgba(100,150,255,0.2); padding-top:8px; margin-top:8px;';
    out.appendChild(detail);
  }
  let html = '<div style="color:#80c0ff; margin-bottom:6px;">═══ 流水线进度 ═══</div>';
  html += '<div style="color:#aaa; font-size:11px; margin-bottom:6px;">原始任务：' + escapeHtml(p.original_task) + '</div>';
  // 甘特图式进度条
  for (let i = 0; i < p.steps.length; i++) {
    const s = p.steps[i];
    const icon = STEP_STATUS_ICON[s.status] || '?';
    const color = STEP_STATUS_COLOR[s.status] || '#888';
    const spIcon = SPECIES_ICON[s.agent_species] || '🐾';
    const spName = SPECIES_LABEL_ZH[s.agent_species] || s.agent_species;
    const dur = s.duration_sec || 0;
    html += '<div style="display:flex; align-items:center; padding:3px 0; gap:8px;">';
    html += '<span style="width:24px; text-align:center;">' + icon + '</span>';
    html += '<span style="width:80px; color:' + color + ';">' + spIcon + ' ' + spName + '</span>';
    html += '<span style="flex:1; color:#cdd6e6; font-size:11px;">' + escapeHtml(s.task.slice(0, 70)) + (s.task.length > 70 ? '...' : '') + '</span>';
    html += '<span style="color:#666; font-size:10px; min-width:50px; text-align:right;">' + dur + 's</span>';
    html += '</div>';
    // 如果有结果，展示一行预览
    if (s.result || s.error) {
      const preview = (s.result || s.error || '').slice(0, 100);
      html += '<div style="margin-left:32px; color:#888; font-size:10px; padding:1px 0 4px 0;">└ ' + escapeHtml(preview) + (preview.length >= 100 ? '...' : '') + '</div>';
    }
  }
  detail.innerHTML = html;
}

async function refreshApprovalCount() {
  try {
    const resp = await fetch('/api/approvals');
    const data = await resp.json();
    const pending = data.pending || [];
    const el = document.getElementById('task-approval-count');
    if (el) el.textContent = pending.length;
    // commit 39：同步更新顶部铃铛徽标
    const bell = document.getElementById('approval-bell-badge');
    if (bell) {
      if (pending.length > 0) {
        bell.style.display = 'inline';
        bell.textContent = pending.length > 99 ? '99+' : String(pending.length);
      } else {
        bell.style.display = 'none';
      }
    }
    // 如果有待审批，闪烁提醒
    if (pending.length > 0) {
      const btn = document.getElementById('agent-task-btn');
      if (btn) {
        btn.style.background = '#ff8040';
        btn.style.color = '#fff';
      }
    } else {
      const btn = document.getElementById('agent-task-btn');
      if (btn) {
        btn.style.background = '';
        btn.style.color = '';
      }
    }
  } catch (e) {}
}

// ==================== commit 40：新手引导 + 进化突变 + 对外分享 ====================

const ONBOARDING_STAGES = [
  {key: 'welcome', title: '欢迎来到 BlueDeer 森林公司',
   bubble: '欢迎来到 BlueDeer 森林公司！我是灵音雀，今天由我来带你参观！<br>这是一家由 11 位动物智能体组成的数字公司，而你——是我们的监工！',
   hint: '点击「下一步」开始认识你的团队'},
  {key: 'meet_team', title: '认识你的同事',
   bubble: '公司里有 11 位动物同事，每人有自己的性格和岗位。<br>🦌 鹿·忧郁：团队领导<br>🐿 松鼠·栗壳：代码工程师<br>🦋 蝶·绘羽：UI 设计师<br>🦊 狐·赤谋：测试工程师<br>🦔 猬·针客：安全工程师<br>🦫 海狸·大坝：运维工程师<br>🐦 鸦·黑卷：记忆管理员<br>🐰 兔·霜耳：数据分析师<br>🦡 獾·土工：网络工程师<br>🎵 雀·清音：监控工程师（就是我！）<br>🪁 鸢·天瞰：调度工程师',
   hint: '点击任何同事可以查看状态、聊天或派发任务'},
  {key: 'first_interact', title: '第一次互动',
   bubble: '试试点击松鼠，跟他打个招呼吧！<br>每个同事都有自己的性格，聊起来完全不一样。',
   hint: '在画面中找到松鼠并点击，弹出浮窗后点「打招呼」'},
  {key: 'first_task', title: '下达第一个任务',
   bubble: '现在试试给团队下达第一个任务吧！<br>点击顶部的「🤖任务」按钮，输入任务描述，回车提交。<br>松鼠会写代码，狐狸会测试，海狸会部署。',
   hint: '点击「🤖任务」按钮打开任务控制台'},
  {key: 'free_explore', title: '自由探索',
   bubble: '你已经掌握了基本操作！<br>WASD 走动，滚轮缩放，T 键打开任务控制台，P 键打开项目看板。<br>剩下的，就交给你自己探索啦！<br>完成入职奖励 50 森林印记 🎉',
   hint: '点击「完成」开始你的森林公司之旅'},
];

let _onboardCurrentIdx = 0;

async function startOnboarding() {
  _onboardCurrentIdx = 0;
  try {
    await fetch('/api/onboarding/start', {method: 'POST'});
  } catch (e) {}
  renderOnboardingStage();
  document.getElementById('onboard-modal').style.display = 'flex';
}

async function onboardNext() {
  _onboardCurrentIdx++;
  if (_onboardCurrentIdx >= ONBOARDING_STAGES.length) {
    // 完成
    try { await fetch('/api/onboarding/next', {method: 'POST'}); } catch (e) {}
    document.getElementById('onboard-modal').style.display = 'none';
    showTip('🎉 入职培训完成！获得 50 森林印记奖励');
    return;
  }
  try { await fetch('/api/onboarding/next', {method: 'POST'}); } catch (e) {}
  renderOnboardingStage();
}

async function onboardPrev() {
  if (_onboardCurrentIdx > 0) {
    _onboardCurrentIdx--;
    try { await fetch('/api/onboarding/stage', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({stage: ONBOARDING_STAGES[_onboardCurrentIdx].key})
    }); } catch (e) {}
    renderOnboardingStage();
  }
}

async function skipOnboarding() {
  try { await fetch('/api/onboarding/skip', {method: 'POST'}); } catch (e) {}
  document.getElementById('onboard-modal').style.display = 'none';
}

function renderOnboardingStage() {
  const s = ONBOARDING_STAGES[_onboardCurrentIdx];
  if (!s) return;
  const bubble = document.getElementById('onbird-bubble');
  const progress = document.getElementById('onboard-progress');
  const hint = document.getElementById('onboard-hint');
  const backBtn = document.getElementById('onboard-back-btn');
  const nextBtn = document.getElementById('onboard-next-btn');
  if (bubble) bubble.innerHTML = s.bubble;
  if (progress) progress.textContent = `阶段 ${_onboardCurrentIdx + 1} / ${ONBOARDING_STAGES.length} · ${s.title}`;
  if (hint) hint.textContent = '💡 ' + s.hint;
  if (backBtn) backBtn.style.display = _onboardCurrentIdx > 0 ? 'inline-block' : 'none';
  if (nextBtn) nextBtn.textContent = _onboardCurrentIdx === ONBOARDING_STAGES.length - 1 ? '完成 ✓' : '下一步 →';
}

async function checkFirstRunOnboarding() {
  try {
    const resp = await fetch('/api/onboarding');
    const data = await resp.json();
    if (data.should_show_onboarding) {
      startOnboarding();
    }
  } catch (e) {}
}

async function pollOnboardingTip() {
  try {
    const resp = await fetch('/api/onboarding/tip');
    const data = await resp.json();
    if (data.tip) showTip(data.tip);
  } catch (e) {}
}

function showTip(text) {
  const bubble = document.getElementById('tip-bubble');
  const tipText = document.getElementById('tip-text');
  if (!bubble || !tipText) return;
  tipText.textContent = text;
  bubble.style.display = 'block';
  setTimeout(() => { bubble.style.display = 'none'; }, 15000);
}

// ----- 分享与导出 -----

function toggleSharePanel() {
  const m = document.getElementById('share-modal');
  if (!m) return;
  if (m.style.display === 'none' || m.style.display === '') {
    m.style.display = 'flex';
    loadShareTokens();
    loadShareCardAgentList();
  } else {
    m.style.display = 'none';
  }
}

function switchShareTab(tab) {
  ['visit', 'card', 'snapshot', 'text'].forEach(t => {
    const panel = document.getElementById('share-tab-' + t);
    if (panel) panel.style.display = t === tab ? 'block' : 'none';
    const btn = document.querySelector('.share-tab[data-tab="' + t + '"]');
    if (btn) {
      if (t === tab) {
        btn.style.background = 'rgba(255,200,80,0.2)';
        btn.style.color = '#ffc850';
      } else {
        btn.style.background = '#222';
        btn.style.color = '#aaa';
      }
    }
  });
}

async function loadShareTokens() {
  try {
    const resp = await fetch('/api/share/tokens');
    const data = await resp.json();
    const list = document.getElementById('share-tokens-list');
    if (!list) return;
    const tokens = data.tokens || [];
    if (tokens.length === 0) {
      list.innerHTML = '<div style="color:#666; padding:8px;">还没有参观链接。输入备注后点「生成链接」创建一个。</div>';
      return;
    }
    list.innerHTML = tokens.map(t => `
      <div style="background:#222; border:1px solid #444; border-radius:6px; padding:8px 10px; margin-bottom:6px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="color:${t.is_valid ? '#8f8' : '#888'};">${t.is_valid ? '✓ 有效' : '✗ 失效'}</span>
          <span style="color:#888; font-size:11px;">剩余 ${Math.floor(t.remaining_seconds / 3600)}h</span>
        </div>
        <div style="color:#ffc850; margin:4px 0; font-size:11px; word-break:break-all;">${t.visit_url || '(unknown)'}</div>
        <div style="display:flex; gap:6px; margin-top:4px;">
          <button onclick="copyToClipboard('${t.visit_url || ''}')" style="background:#444; color:#fff; border:none; padding:2px 8px; border-radius:3px; cursor:pointer; font-size:11px;">复制</button>
          ${t.is_valid ? `<button onclick="revokeShareToken('${t.token}')" style="background:#644; color:#faa; border:none; padding:2px 8px; border-radius:3px; cursor:pointer; font-size:11px;">撤销</button>` : ''}
          <button onclick="deleteShareToken('${t.token}')" style="background:#444; color:#aaa; border:none; padding:2px 8px; border-radius:3px; cursor:pointer; font-size:11px;">删除</button>
        </div>
      </div>`).join('');
  } catch (e) {}
}

async function createShareToken() {
  const nameInput = document.getElementById('share-token-name');
  const name = nameInput ? nameInput.value : '';
  try {
    await fetch('/api/share/tokens', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name: name})
    });
    if (nameInput) nameInput.value = '';
    loadShareTokens();
  } catch (e) {}
}

async function revokeShareToken(token) {
  try {
    await fetch('/api/share/revoke', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: token})
    });
    loadShareTokens();
  } catch (e) {}
}

async function deleteShareToken(token) {
  try {
    await fetch('/api/share/delete', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token: token})
    });
    loadShareTokens();
  } catch (e) {}
}

function loadShareCardAgentList() {
  const sel = document.getElementById('share-card-agent');
  if (!sel) return;
  const agents = (window._lastStatus && window._lastStatus.employees) || [];
  sel.innerHTML = agents.map(a => `<option value="${a.name}">${a.name} (${a.species})</option>`).join('');
}

async function generateAgentCard() {
  const sel = document.getElementById('share-card-agent');
  const name = sel ? sel.value : '';
  if (!name) return;
  const preview = document.getElementById('share-card-preview');
  if (preview) preview.innerHTML = '<div style="color:#888;">生成中...</div>';
  try {
    const resp = await fetch('/api/export/card?name=' + encodeURIComponent(name));
    const svg = await resp.text();
    if (preview) {
      preview.innerHTML = svg +
        '<div style="margin-top:12px;">' +
        '<button onclick="downloadAgentCard(\\'' + encodeURIComponent(name) + '\\')" style="background:linear-gradient(135deg, #ffc850, #ff9040); color:#1a1a2e; border:none; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:bold;">⬇ 下载 SVG</button>' +
        '</div>';
    }
  } catch (e) {
    if (preview) preview.innerHTML = '<div style="color:#f88;">生成失败：' + e.message + '</div>';
  }
}

function downloadAgentCard(nameEncoded) {
  const name = decodeURIComponent(nameEncoded);
  window.open('/api/export/card?name=' + encodeURIComponent(name), '_blank');
}

function downloadSnapshot() {
  window.open('/api/export/snapshot', '_blank');
}

async function generateShareText() {
  const output = document.getElementById('share-text-output');
  if (output) output.textContent = '生成中...';
  try {
    const resp = await fetch('/api/export/share_text');
    const data = await resp.json();
    if (output) output.textContent = data.text || '(空)';
  } catch (e) {
    if (output) output.textContent = '生成失败：' + e.message;
  }
}

function copyShareText() {
  const output = document.getElementById('share-text-output');
  if (output) copyToClipboard(output.textContent);
}

function copyToClipboard(text) {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => showTip('📋 已复制到剪贴板'));
  } else {
    // 降级方案
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); showTip('📋 已复制到剪贴板'); } catch (e) {}
    document.body.removeChild(ta);
  }
}

// ----- 进化突变 -----

function toggleEvolutionPanel() {
  const m = document.getElementById('evolution-modal');
  if (!m) return;
  if (m.style.display === 'none' || m.style.display === '') {
    m.style.display = 'flex';
    loadEvolutionData();
  } else {
    m.style.display = 'none';
  }
}

async function loadEvolutionData() {
  try {
    const resp = await fetch('/api/evolution?limit=50');
    const data = await resp.json();
    const stats = data.stats || {};
    const mutations = data.mutations || [];
    const statsEl = document.getElementById('evolution-stats');
    if (statsEl) {
      statsEl.innerHTML = `总突变次数：<span style="color:#ffd700;">${stats.total_mutations || 0}</span> · ` +
        `传说级：<span style="color:#ff8040;">${stats.legendary_mutations || 0}</span> · ` +
        `涉及物种：${(stats.genetic_species || []).length}`;
    }
    const logEl = document.getElementById('evolution-log');
    if (logEl) {
      if (mutations.length === 0) {
        logEl.innerHTML = '<div style="color:#666; padding:8px;">还没有突变记录。<br>智能体存活超过 180 天后，每月有 5% 概率触发突变。<br>可以用上方「强制触发」按钮测试。</div>';
      } else {
        logEl.innerHTML = mutations.reverse().map(m => `
          <div style="background:#222; border:1px solid ${m.legendary ? 'rgba(255,140,40,0.4)' : 'rgba(255,215,0,0.2)'}; border-radius:6px; padding:6px 10px; margin-bottom:6px;">
            <div style="display:flex; justify-content:space-between;">
              <span style="color:${m.legendary ? '#ff8040' : '#ffd700'}; font-weight:bold;">${m.legendary ? '🌟' : '✨'} ${m.name_zh || m.key}</span>
              <span style="color:#888; font-size:11px;">${new Date(m.ts * 1000).toLocaleString('zh-CN')}</span>
            </div>
            <div style="color:#aaa; margin-top:2px;">${m.agent_name} (${m.agent_species}) ${m.inherited ? '· 遗传自上一代' : ''}</div>
            <div style="color:#888; font-size:11px; margin-top:2px;">${m.description}</div>
          </div>`).join('');
      }
    }
  } catch (e) {}
}

async function forceEvolution() {
  const input = document.getElementById('evolution-agent-name');
  const name = input ? input.value : '';
  if (!name) { showTip('请输入智能体名字'); return; }
  try {
    const resp = await fetch('/api/evolution/force', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({agent_name: name})
    });
    const data = await resp.json();
    if (data.mutation) {
      showMutationBanner(`${name} 经历了突变：${data.mutation.name_zh || data.mutation.key}！`);
      loadEvolutionData();
    } else {
      showTip('操作失败：' + (data.error || '未知错误'));
    }
  } catch (e) {}
}

function showMutationBanner(text) {
  const banner = document.getElementById('mutation-banner');
  if (!banner) return;
  banner.textContent = '✨ ' + text;
  banner.style.display = 'block';
  setTimeout(() => { banner.style.display = 'none'; }, 8000);
}

// ----- 参观模式检查 -----

function isVisitMode() {
  return document.body && document.body.getAttribute('data-visit-mode') === '1';
}

// 参观模式下隐藏写操作按钮
function applyVisitModeStyles() {
  if (!isVisitMode()) return;
  const hideIds = ['onboard-btn', 'share-btn', 'evolution-btn', 'external-btn', 'approval-bell-btn',
                   'agent-task-btn', 'agent-kanban-btn', 'suggest-btn'];
  hideIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
}

// ----- 启动时调用 -----

// 首次运行检查引导（参观模式不触发）
setTimeout(() => {
  if (!isVisitMode()) {
    checkFirstRunOnboarding();
    // 每 30 分钟轮询一次小贴士
    setInterval(pollOnboardingTip, 30 * 60 * 1000);
  }
  applyVisitModeStyles();
}, 2000);

// 导出全局函数（HTML onclick 用）
window.startOnboarding = startOnboarding;
window.onboardNext = onboardNext;
window.onboardPrev = onboardPrev;
window.skipOnboarding = skipOnboarding;
window.toggleSharePanel = toggleSharePanel;
window.switchShareTab = switchShareTab;
window.createShareToken = createShareToken;
window.revokeShareToken = revokeShareToken;
window.deleteShareToken = deleteShareToken;
window.loadShareTokens = loadShareTokens;
window.generateAgentCard = generateAgentCard;
window.downloadAgentCard = downloadAgentCard;
window.downloadSnapshot = downloadSnapshot;
window.generateShareText = generateShareText;
window.copyShareText = copyShareText;
window.copyToClipboard = copyToClipboard;
window.toggleEvolutionPanel = toggleEvolutionPanel;
window.loadEvolutionData = loadEvolutionData;
window.forceEvolution = forceEvolution;

async function openApprovalsModal() {
  const modal = document.getElementById('approvals-modal');
  const list = document.getElementById('approvals-list');
  if (!modal || !list) return;
  modal.style.display = 'block';
  list.innerHTML = '<div style="color:#888;">加载中...</div>';
  try {
    const resp = await fetch('/api/approvals');
    const data = await resp.json();
    const pending = data.pending || [];
    if (!pending.length) {
      list.innerHTML = '<div style="color:#888;">当前没有待审批请求。</div>';
      return;
    }
    list.innerHTML = pending.map(a => {
      const riskColor = a.risk === 'high' ? '#ff6060' : (a.risk === 'medium' ? '#ffaa60' : '#80c080');
      return '<div style="background:rgba(255,255,255,0.05); padding:10px; border-radius:6px; margin-bottom:8px; border-left:3px solid ' + riskColor + ';">'
        + '<div style="display:flex; justify-content:space-between; margin-bottom:6px;">'
        + '<span style="color:#ffd080; font-weight:bold;">🔧 ' + escapeHtml(a.tool_name) + '</span>'
        + '<span style="color:' + riskColor + '; font-size:11px;">风险：' + a.risk + '</span>'
        + '</div>'
        + '<div style="color:#aaa; font-size:11px; margin-bottom:4px;">来自：' + escapeHtml(a.agent_name || a.agent_id) + '</div>'
        + '<div style="color:#cdd6e6; font-size:11px; margin-bottom:8px;"><pre style="margin:0; white-space:pre-wrap;">' + escapeHtml(JSON.stringify(a.params, null, 2)) + '</pre></div>'
        + '<div style="display:flex; gap:8px;">'
        + '<button onclick="decideApproval(' + a.id + ', \\'approved\\')" style="background:#4a8f4a; color:#fff; border:none; border-radius:4px; padding:4px 12px; cursor:pointer;">批准</button>'
        + '<button onclick="decideApproval(' + a.id + ', \\'rejected\\')" style="background:#a04a4a; color:#fff; border:none; border-radius:4px; padding:4px 12px; cursor:pointer;">拒绝</button>'
        + '</div>'
        + '</div>';
    }).join('');
  } catch (e) {
    list.innerHTML = '<div style="color:#ff8080;">加载失败：' + escapeHtml(String(e)) + '</div>';
  }
}

async function decideApproval(aid, decision) {
  try {
    const resp = await fetch('/api/approvals', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: aid, decision: decision}),
    });
    const data = await resp.json();
    if (data.ok) {
      appendTaskOutput('<span style="color:#80c080;">🛡 审批 #' + aid + ' 已' + (decision === 'approved' ? '批准' : '拒绝') + '</span>');
      openApprovalsModal();  // 刷新
      refreshApprovalCount();
    } else {
      appendTaskOutput('<span style="color:#ff8080;">审批失败</span>');
    }
  } catch (e) {}
}

// 监听 SSE 事件中的 pipeline_event
(function _patchSseForPipeline() {
  // 等到全局 handleSSEEvent 或类似函数可用时挂钩
  // 简单做法：每 2 秒检查一下待审批数量并刷新当前流水线（已经在 timer 里做了）
  // 这里监听 keydown：T 键切换控制台
  document.addEventListener('keydown', function(e) {
    // T 键（不区分大小写）
    if ((e.key === 't' || e.key === 'T') && !e.ctrlKey && !e.altKey && !e.metaKey) {
      // 不在输入框中才切换
      const tag = (e.target && e.target.tagName) || '';
      if (tag !== 'INPUT' && tag !== 'TEXTAREA' && tag !== 'SELECT') {
        e.preventDefault();
        toggleTaskConsole();
      }
    }
    // 上下方向键浏览命令历史（在 task-input 中时）
    if (e.target && e.target.id === 'task-input') {
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (_agentCommandHistoryIdx < _agentCommandHistory.length - 1) {
          _agentCommandHistoryIdx++;
          e.target.value = _agentCommandHistory[_agentCommandHistoryIdx] || '';
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (_agentCommandHistoryIdx > 0) {
          _agentCommandHistoryIdx--;
          e.target.value = _agentCommandHistory[_agentCommandHistoryIdx] || '';
        } else {
          _agentCommandHistoryIdx = -1;
          e.target.value = '';
        }
      }
    }
  });
})();

// 暴露给全局
window.toggleTaskConsole = toggleTaskConsole;
window.submitTaskCommand = submitTaskCommand;
window.clearTaskOutput = clearTaskOutput;
window.refreshPipelineList = refreshPipelineList;
window.selectPipeline = selectPipeline;
window.openApprovalsModal = openApprovalsModal;
window.decideApproval = decideApproval;

console.log('[commit 37] Agent 任务控制台已加载：T 键切换');

// ==================== commit 38：建议中心 ====================
let _suggCurrentTab = 'suggestions';
let _suggRefreshTimer = null;

function toggleSuggestions() {
  const m = document.getElementById('suggestions-modal');
  if (!m) return;
  if (m.style.display === 'none' || !m.style.display) {
    m.style.display = 'flex';
    switchSuggTab(_suggCurrentTab);
    if (!_suggRefreshTimer) {
      _suggRefreshTimer = setInterval(refreshSuggCurrentTab, 5000);
    }
  } else {
    m.style.display = 'none';
    if (_suggRefreshTimer) {
      clearInterval(_suggRefreshTimer);
      _suggRefreshTimer = null;
    }
  }
}

function switchSuggTab(tab) {
  _suggCurrentTab = tab;
  ['suggestions', 'retrospects', 'experiences', 'negotiations'].forEach(t => {
    const panel = document.getElementById('sugg-tab-' + t);
    if (panel) panel.style.display = (t === tab) ? 'block' : 'none';
    const btn = document.querySelector('.sugg-tab[data-tab="' + t + '"]');
    if (btn) {
      if (t === tab) {
        btn.style.background = 'rgba(255,200,120,0.2)';
        btn.style.color = '#ffd080';
      } else {
        btn.style.background = '#222';
        btn.style.color = '#aaa';
      }
    }
  });
  refreshSuggCurrentTab();
}

function refreshSuggCurrentTab() {
  if (_suggCurrentTab === 'suggestions') loadSuggestions();
  else if (_suggCurrentTab === 'retrospects') loadRetrospects();
  else if (_suggCurrentTab === 'experiences') loadExperiences();
  else if (_suggCurrentTab === 'negotiations') loadNegotiations();
}

function setSuggStatus(text) {
  const el = document.getElementById('sugg-status-text');
  if (el) el.textContent = text;
}

async function loadSuggestions() {
  try {
    const resp = await fetch('/api/suggestions');
    const data = await resp.json();
    const panel = document.getElementById('sugg-tab-suggestions');
    if (!panel) return;
    const list = data.suggestions || [];
    const stats = data.stats || {};
    const badge = document.getElementById('suggest-badge');
    if (badge) {
      const pending = stats.pending || 0;
      if (pending > 0) {
        badge.style.display = 'inline';
        badge.textContent = pending;
      } else {
        badge.style.display = 'none';
      }
    }
    let html = '<div style="color:#888; font-size:11px; margin-bottom:8px;">'
      + '总计 ' + (stats.total || 0) + ' 条 | 待采纳 ' + (stats.pending || 0)
      + ' | 已采纳 ' + (stats.adopted || 0) + ' | 已拒绝 ' + (stats.rejected || 0)
      + ' | 采纳率 ' + ((stats.adopt_rate || 0) * 100).toFixed(0) + '%</div>';
    if (list.length === 0) {
      html += '<div style="color:#666; padding:20px; text-align:center;">暂无建议。点击右上"立即扫描"触发一次扫描。</div>';
    } else {
      list.forEach(s => {
        const cat = s.category || '?';
        const title = s.title || s.detail || '';
        const reason = s.reason || '';
        const status = s.status || 'pending';
        const sid = s.id || '';
        const statusColor = status === 'pending' ? '#ffd080'
                          : status === 'adopted' ? '#80ff80'
                          : status === 'rejected' ? '#ff8080'
                          : status === 'deferred' ? '#80c0ff'
                          : '#888';
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid ' + statusColor + '; padding:8px 12px; margin-bottom:8px; border-radius:4px;">';
        html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">';
        html += '<span style="color:#ffd080; font-weight:bold;">[' + cat + '] ' + escapeHtml(title) + '</span>';
        html += '<span style="color:' + statusColor + '; font-size:11px;">' + status + '</span>';
        html += '</div>';
        if (reason) html += '<div style="color:#aaa; font-size:11px; margin-bottom:4px;">' + escapeHtml(reason) + '</div>';
        if (status === 'pending') {
          html += '<div style="display:flex; gap:6px; margin-top:6px;">';
          html += '<button onclick="adoptSuggestion(\\'' + sid + '\\')" style="background:#4a7fc0; color:#fff; border:none; border-radius:3px; padding:3px 8px; cursor:pointer; font-size:11px;">采纳</button>';
          html += '<button onclick="deferSuggestion(\\'' + sid + '\\')" style="background:#555; color:#fff; border:none; border-radius:3px; padding:3px 8px; cursor:pointer; font-size:11px;">推迟 1h</button>';
          html += '<button onclick="rejectSuggestion(\\'' + sid + '\\')" style="background:#aa4444; color:#fff; border:none; border-radius:3px; padding:3px 8px; cursor:pointer; font-size:11px;">拒绝</button>';
          html += '</div>';
        }
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setSuggStatus('建议列表已刷新：' + list.length + ' 条');
  } catch (e) {
    setSuggStatus('加载建议失败：' + e.message);
  }
}

async function loadRetrospects() {
  try {
    const resp = await fetch('/api/retrospects');
    const data = await resp.json();
    const panel = document.getElementById('sugg-tab-retrospects');
    if (!panel) return;
    const list = data.retrospects || [];
    let html = '<div style="color:#888; font-size:11px; margin-bottom:8px;">复盘历史 ' + list.length + ' 条</div>';
    if (list.length === 0) {
      html += '<div style="color:#666; padding:20px; text-align:center;">暂无复盘记录。任务完成后会自动生成复盘。</div>';
    } else {
      list.forEach(r => {
        const species = r.agent_species || '?';
        const name = r.agent_name || '';
        const task = r.task || '';
        const lesson = r.lesson || '';
        const summary = r.summary || '';
        const ok = r.result_ok;
        const okColor = ok ? '#80ff80' : '#ff8080';
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid ' + okColor + '; padding:8px 12px; margin-bottom:8px; border-radius:4px;">';
        html += '<div style="color:#b4c8ff; font-weight:bold; margin-bottom:4px;">[' + species + '] ' + escapeHtml(name) + ' · ' + (ok ? '成功' : '失败') + '</div>';
        html += '<div style="color:#aaa; font-size:11px; margin-bottom:4px;">任务：' + escapeHtml(task) + '</div>';
        if (lesson) html += '<div style="color:#ffd080; font-size:12px; margin-bottom:4px;">💡 经验：' + escapeHtml(lesson) + '</div>';
        if (summary) html += '<div style="color:#cdd6e6; font-size:11px;">' + escapeHtml(summary) + '</div>';
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setSuggStatus('复盘列表已刷新：' + list.length + ' 条');
  } catch (e) {
    setSuggStatus('加载复盘失败：' + e.message);
  }
}

async function loadExperiences() {
  try {
    const resp = await fetch('/api/experiences');
    const data = await resp.json();
    const panel = document.getElementById('sugg-tab-experiences');
    if (!panel) return;
    const list = data.experiences || [];
    const stats = data.stats || {};
    let html = '<div style="color:#888; font-size:11px; margin-bottom:8px;">经验库总计 ' + (stats.total || 0) + ' 条</div>';
    if (list.length === 0) {
      html += '<div style="color:#666; padding:20px; text-align:center;">暂无经验。复盘后会自动入库。</div>';
    } else {
      list.forEach(e => {
        const taskType = e.task_type || '其他';
        const species = e.agent_species || '?';
        const lesson = e.lesson || '';
        const weight = e.weight || 0;
        const adopted = e.adopted_count || 0;
        const weightColor = weight > 5 ? '#80ff80' : weight < 0 ? '#ff8080' : '#ffd080';
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid ' + weightColor + '; padding:8px 12px; margin-bottom:8px; border-radius:4px;">';
        html += '<div style="display:flex; justify-content:space-between; margin-bottom:4px;">';
        html += '<span style="color:#b4c8ff; font-weight:bold;">[' + taskType + '] ' + escapeHtml(species) + '</span>';
        html += '<span style="color:' + weightColor + '; font-size:11px;">权重 ' + weight + ' | 采用 ' + adopted + ' 次</span>';
        html += '</div>';
        html += '<div style="color:#cdd6e6; font-size:12px;">' + escapeHtml(lesson) + '</div>';
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setSuggStatus('经验库已刷新：' + list.length + ' 条');
  } catch (e) {
    setSuggStatus('加载经验库失败：' + e.message);
  }
}

async function loadNegotiations() {
  try {
    const resp = await fetch('/api/negotiations');
    const data = await resp.json();
    const panel = document.getElementById('sugg-tab-negotiations');
    if (!panel) return;
    const active = data.active || [];
    const history = data.history || [];
    let html = '<div style="color:#888; font-size:11px; margin-bottom:8px;">进行中 ' + active.length + ' | 历史 ' + history.length + '</div>';
    if (history.length === 0) {
      html += '<div style="color:#666; padding:20px; text-align:center;">暂无协商记录。流水线执行时会自动协商。</div>';
    } else {
      history.slice(0, 30).forEach(n => {
        const winner = n.winner || '?';
        const winnerName = n.winner_name || '';
        const task = n.task || '';
        const reason = n.reason || '';
        const fallback = n.fallback;
        const bids = n.bids || [];
        const winnerColor = fallback ? '#ff8080' : '#80ff80';
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid ' + winnerColor + '; padding:8px 12px; margin-bottom:8px; border-radius:4px;">';
        html += '<div style="color:#b4c8ff; font-weight:bold; margin-bottom:4px;">中标：' + winner + ' (' + escapeHtml(winnerName) + ')' + (fallback ? ' [fallback]' : '') + '</div>';
        html += '<div style="color:#aaa; font-size:11px; margin-bottom:4px;">任务：' + escapeHtml(task) + '</div>';
        html += '<div style="color:#cdd6e6; font-size:11px; margin-bottom:4px;">' + escapeHtml(reason) + '</div>';
        if (bids.length > 0) {
          html += '<div style="font-size:11px; color:#888; margin-top:4px;">竞标详情：</div>';
          html += '<ul style="margin:4px 0 0 16px; padding:0; font-size:11px; color:#aaa;">';
          bids.slice(0, 5).forEach(b => {
            html += '<li>' + (b.species || '?') + ': ' + (b.score || 0).toFixed(1) + ' 分'
              + (b.available ? '' : ' (不可接)') + '</li>';
          });
          html += '</ul>';
        }
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setSuggStatus('协商记录已刷新：' + history.length + ' 条');
  } catch (e) {
    setSuggStatus('加载协商失败：' + e.message);
  }
}

async function adoptSuggestion(sid) {
  try {
    const resp = await fetch('/api/suggestions/adopt', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: sid}),
    });
    const data = await resp.json();
    setSuggStatus('采纳结果：' + (data.note || data.error || JSON.stringify(data)));
    loadSuggestions();
  } catch (e) {
    setSuggStatus('采纳失败：' + e.message);
  }
}

async function deferSuggestion(sid) {
  try {
    const resp = await fetch('/api/suggestions/defer', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: sid, hours: 1}),
    });
    const data = await resp.json();
    setSuggStatus('推迟结果：' + (data.note || data.error || JSON.stringify(data)));
    loadSuggestions();
  } catch (e) {
    setSuggStatus('推迟失败：' + e.message);
  }
}

async function rejectSuggestion(sid) {
  try {
    const resp = await fetch('/api/suggestions/reject', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: sid, reason: '手动拒绝'}),
    });
    const data = await resp.json();
    setSuggStatus('拒绝结果：' + (data.note || data.error || JSON.stringify(data)));
    loadSuggestions();
  } catch (e) {
    setSuggStatus('拒绝失败：' + e.message);
  }
}

async function scanNow() {
  try {
    setSuggStatus('正在扫描...');
    const resp = await fetch('/api/task_scout/scan', {method: 'POST'});
    const data = await resp.json();
    const scan = data.scan || {};
    const findings = (scan.findings || []).length;
    const sugg = scan.suggestions_generated || 0;
    setSuggStatus('扫描完成：发现 ' + findings + ' 项，生成 ' + sugg + ' 条建议'
      + (data.error ? '（错误：' + data.error + '）' : ''));
    loadSuggestions();
  } catch (e) {
    setSuggStatus('扫描失败：' + e.message);
  }
}

function escapeHtml(s) {
  if (!s) return '';
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
}

// I 键切换建议中心
document.addEventListener('keydown', e => {
  if (e.key === 'i' || e.key === 'I') {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    toggleSuggestions();
  }
});

window.toggleSuggestions = toggleSuggestions;
window.switchSuggTab = switchSuggTab;
window.adoptSuggestion = adoptSuggestion;
window.deferSuggestion = deferSuggestion;
window.rejectSuggestion = rejectSuggestion;
window.scanNow = scanNow;

console.log('[commit 38] 建议中心已加载：I 键切换');

// ==================== commit 39：项目看板 + 外部集成 ====================
let _kanbanCurrentTab = 'projects';
let _kanbanRefreshTimer = null;
let _extCurrentTab = 'config';
let _extRefreshTimer = null;

// 角色徽章中文名映射
const ROLE_LABELS = {
  tech_leader: '🏆技术领袖',
  social_coordinator: '🤝社交协调员',
  supervisor_deputy: '🎖️监工副手',
  mentor: '🎓新人导师',
  crisis_handler: '⚡危机处理者',
  hermit: '🌙隐士',
  tech_backbone: '⚙️技术骨干',
};
const ROLE_COLORS = {
  tech_leader: '#ffd080',
  social_coordinator: '#80c0ff',
  supervisor_deputy: '#c080ff',
  mentor: '#80ffc0',
  crisis_handler: '#ff8080',
  hermit: '#a0a0c0',
  tech_backbone: '#b488ff',
};
const ROLE_DESCRIPTIONS = {
  tech_leader: '被公认技术最强，同事遇难题时首先求助的对象',
  social_coordinator: '主动组织茶话会、调解冲突、活跃气氛',
  supervisor_deputy: '监工不在时，自然接管一些监工的日常职责',
  mentor: '主动帮助新招募的智能体适应环境',
  crisis_handler: '紧急事件中第一个响应并有效处理',
  hermit: '喜欢独处，社交少但工作质量极高',
  tech_backbone: '技术能力突出，技术对决中惜败的强者',
};

// 项目状态颜色
const PROJECT_STATUS_COLOR = {
  planning: '#80c0ff',
  in_progress: '#80ff80',
  blocked: '#ff8080',
  completed: '#ffd080',
  archived: '#888',
};
const MILESTONE_STATUS_COLOR = {
  pending: '#888',
  in_progress: '#80c0ff',
  blocked: '#ff8080',
  done: '#80ff80',
};

function setKanbanStatus(text) {
  const el = document.getElementById('kanban-status-text');
  if (el) el.textContent = text;
}

function setExtStatus(text) {
  const el = document.getElementById('ext-status-text');
  if (el) el.textContent = text;
}

// ---------------- 看板：显示/隐藏 + tab 切换 ----------------

function toggleKanban() {
  const m = document.getElementById('kanban-modal');
  if (!m) return;
  if (m.style.display === 'none' || !m.style.display) {
    m.style.display = 'flex';
    switchKanbanTab(_kanbanCurrentTab);
    if (!_kanbanRefreshTimer) {
      _kanbanRefreshTimer = setInterval(refreshKanbanCurrentTab, 8000);
    }
  } else {
    m.style.display = 'none';
    if (_kanbanRefreshTimer) {
      clearInterval(_kanbanRefreshTimer);
      _kanbanRefreshTimer = null;
    }
  }
}

function switchKanbanTab(tab) {
  _kanbanCurrentTab = tab;
  ['projects', 'standups', 'risks', 'roles'].forEach(t => {
    const panel = document.getElementById('kanban-tab-' + t);
    if (panel) panel.style.display = (t === tab) ? 'block' : 'none';
    const btn = document.querySelector('.kanban-tab[data-tab="' + t + '"]');
    if (btn) {
      if (t === tab) {
        btn.style.background = 'rgba(120,220,160,0.2)';
        btn.style.color = '#80d0a0';
      } else {
        btn.style.background = '#222';
        btn.style.color = '#aaa';
      }
    }
  });
  refreshKanbanCurrentTab();
}

function refreshKanbanCurrentTab() {
  if (_kanbanCurrentTab === 'projects') loadProjects();
  else if (_kanbanCurrentTab === 'standups') loadStandups();
  else if (_kanbanCurrentTab === 'risks') loadRisks();
  else if (_kanbanCurrentTab === 'roles') loadRoles();
}

// ---------------- 项目 tab ----------------

async function loadProjects() {
  try {
    const resp = await fetch('/api/projects');
    const data = await resp.json();
    const panel = document.getElementById('kanban-tab-projects');
    if (!panel) return;
    const projects = data.projects || [];
    let html = '<div style="color:#888; font-size:11px; margin-bottom:8px;">'
      + '共 ' + projects.length + ' 个项目 | 点击"＋ 示例项目"快速创建一个含 2 个里程碑的演示项目</div>';
    if (projects.length === 0) {
      html += '<div style="color:#666; padding:30px; text-align:center;">暂无项目。<br>点击右上"＋ 示例项目"按钮创建一个。</div>';
    } else {
      projects.forEach(p => {
        const prog = Math.round(p.overall_progress || 0);
        const color = PROJECT_STATUS_COLOR[p.status] || '#888';
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid ' + color + '; padding:10px 14px; margin-bottom:10px; border-radius:4px;">';
        html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">';
        html += '<span style="color:#80d0a0; font-weight:bold;">' + escapeHtml(p.name || '') + '</span>';
        html += '<span style="color:' + color + '; font-size:11px;">' + p.status + '</span>';
        html += '</div>';
        if (p.description) {
          html += '<div style="color:#aaa; font-size:11px; margin-bottom:6px;">' + escapeHtml(p.description) + '</div>';
        }
        // 进度条
        html += '<div style="background:#222; height:8px; border-radius:4px; margin-bottom:6px; overflow:hidden;">';
        html += '<div style="width:' + prog + '%; height:100%; background:' + color + '; transition:width 0.3s;"></div>';
        html += '</div>';
        html += '<div style="font-size:10px; color:#888; display:flex; gap:12px;">';
        html += '<span>进度 ' + prog + '%</span>';
        html += '<span>里程碑 ' + (p.milestones || []).length + '</span>';
        if (p.owner_agent) html += '<span>负责人 ' + escapeHtml(p.owner_agent) + '</span>';
        if (p.team && p.team.length) html += '<span>团队 ' + p.team.length + ' 人</span>';
        html += '</div>';
        // 里程碑列表
        if (p.milestones && p.milestones.length) {
          html += '<div style="margin-top:8px; padding:6px 8px; background:rgba(0,0,0,0.2); border-radius:3px;">';
          html += '<div style="color:#888; font-size:10px; margin-bottom:4px;">里程碑：</div>';
          p.milestones.forEach(m => {
            const mcolor = MILESTONE_STATUS_COLOR[m.status] || '#888';
            const mprog = Math.round(m.progress || 0);
            html += '<div style="display:flex; align-items:center; gap:8px; padding:2px 0; font-size:11px;">';
            html += '<span style="width:8px; height:8px; border-radius:50%; background:' + mcolor + ';"></span>';
            html += '<span style="flex:1; color:#cdd6e6;">' + escapeHtml(m.name || '') + '</span>';
            html += '<span style="color:' + mcolor + ';">' + m.status + '</span>';
            html += '<span style="color:#888; min-width:40px; text-align:right;">' + mprog + '%</span>';
            html += '</div>';
          });
          html += '</div>';
        }
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setKanbanStatus('项目列表已加载 | 共 ' + projects.length + ' 个项目');
  } catch (e) {
    setKanbanStatus('加载项目失败：' + (e && e.message));
  }
}

async function createSampleProject() {
  try {
    setKanbanStatus('正在创建示例项目...');
    const now = Date.now();
    const dayMs = 86400000;
    const body = {
      name: '示例项目·登录模块重构',
      description: '用于演示长期目标管理能力的示例项目。包含 2 个里程碑：1) 设计与编码 2) 测试与部署。',
      owner_agent: '鼠·栗壳',
      team: ['鼠·栗壳', '狐·赤谋', '狸·大坝'],
      deadline: now + 14 * dayMs,
      milestones: [
        {
          name: 'M1 设计与编码',
          description: '完成登录模块的设计文档和核心代码',
          deadline: now + 5 * dayMs,
          completion_criteria: '设计文档已写；核心代码已提交',
          depends_on: [],
        },
        {
          name: 'M2 测试与部署',
          description: '完成单元测试和部署到预发布环境',
          deadline: now + 12 * dayMs,
          completion_criteria: '单元测试覆盖率 > 80%；预发布环境部署成功',
          depends_on: [],
        },
      ],
    };
    const resp = await fetch('/api/projects', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data && data.ok && data.project_id) {
      setKanbanStatus('已创建项目，ID：' + data.project_id);
      loadProjects();
    } else if (data && data.error) {
      setKanbanStatus('创建失败：' + data.error);
    } else {
      setKanbanStatus('创建结果：' + JSON.stringify(data).slice(0, 80));
    }
  } catch (e) {
    setKanbanStatus('创建异常：' + (e && e.message));
  }
}

// ---------------- 站会 tab ----------------

async function loadStandups() {
  try {
    const resp = await fetch('/api/standups');
    const data = await resp.json();
    const panel = document.getElementById('kanban-tab-standups');
    if (!panel) return;
    const standups = data.standups || [];
    let html = '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">';
    html += '<span style="color:#888; font-size:11px;">共 ' + standups.length + ' 次站会记录</span>';
    html += '<button onclick="runStandupNow()" style="background:#4a8f60; color:#fff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:11px;">▶ 立即开站会</button>';
    html += '</div>';
    if (standups.length === 0) {
      html += '<div style="color:#666; padding:30px; text-align:center;">暂无站会记录。<br>每天 09:00 自动开站会，也可以点击上方按钮立即开一次。</div>';
    } else {
      // 倒序显示，最新在前
      standups.slice().reverse().forEach(s => {
        const date = s.date || s.ts || '';
        const summary = s.summary || '';
        const reports = s.reports || [];
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid #80d0a0; padding:10px 14px; margin-bottom:10px; border-radius:4px;">';
        html += '<div style="color:#80d0a0; font-weight:bold; margin-bottom:6px;">☕ 站会 · ' + escapeHtml(String(date)) + '</div>';
        if (summary) {
          html += '<div style="color:#cdd6e6; font-size:12px; white-space:pre-wrap; margin-bottom:6px;">' + escapeHtml(summary) + '</div>';
        }
        if (reports.length) {
          html += '<div style="margin-top:6px; padding:6px 8px; background:rgba(0,0,0,0.2); border-radius:3px;">';
          html += '<div style="color:#888; font-size:10px; margin-bottom:4px;">个人汇报：</div>';
          reports.forEach(r => {
            html += '<div style="font-size:11px; padding:2px 0; color:#cdd6e6;">';
            html += '<span style="color:#ffd080;">' + escapeHtml(r.agent || '') + '：</span>';
            html += '昨天 ' + escapeHtml(r.yesterday || '') + '；';
            html += '今天 ' + escapeHtml(r.today || '') + '；';
            html += '阻塞 ' + escapeHtml(r.blockers || '无') + '。';
            html += '</div>';
          });
          html += '</div>';
        }
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setKanbanStatus('站会记录已加载 | 共 ' + standups.length + ' 次');
  } catch (e) {
    setKanbanStatus('加载站会失败：' + (e && e.message));
  }
}

async function runStandupNow() {
  try {
    setKanbanStatus('正在召开站会...');
    const resp = await fetch('/api/standups/run', {method: 'POST'});
    const data = await resp.json();
    if (data && data.ok) {
      const standups = data.standups || [];
      let totalReports = 0;
      standups.forEach(s => { totalReports += (s.reports || []).length; });
      setKanbanStatus('站会已结束，涉及 ' + standups.length + ' 个项目，共 ' + totalReports + ' 份汇报');
      loadStandups();
    } else if (data && data.error) {
      setKanbanStatus('站会失败：' + data.error);
    } else {
      setKanbanStatus('站会结果：' + JSON.stringify(data).slice(0, 80));
    }
  } catch (e) {
    setKanbanStatus('站会异常：' + (e && e.message));
  }
}

// ---------------- 风险 tab ----------------

async function loadRisks() {
  try {
    const resp = await fetch('/api/risks');
    const data = await resp.json();
    const panel = document.getElementById('kanban-tab-risks');
    if (!panel) return;
    const risks = data.risks || [];
    let html = '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">';
    html += '<span style="color:#888; font-size:11px;">共 ' + risks.length + ' 条风险</span>';
    html += '<button onclick="scanRisksNow()" style="background:#8f4a4a; color:#fff; border:none; border-radius:4px; padding:4px 10px; cursor:pointer; font-size:11px;">🔍 立即扫描</button>';
    html += '</div>';
    if (risks.length === 0) {
      html += '<div style="color:#666; padding:30px; text-align:center;">暂无风险。<br>风险会在每日扫描和站会时自动识别。</div>';
    } else {
      risks.forEach(r => {
        const levelColor = r.level === 'high' ? '#ff8080'
                         : r.level === 'medium' ? '#ffd080' : '#80c0ff';
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid ' + levelColor + '; padding:10px 14px; margin-bottom:10px; border-radius:4px;">';
        html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">';
        html += '<span style="color:' + levelColor + '; font-weight:bold;">[' + (r.level || '').toUpperCase() + '] ' + escapeHtml(r.type || '') + '</span>';
        html += '<span style="color:#888; font-size:11px;">' + (r.project_name || r.project_id || '') + '</span>';
        html += '</div>';
        if (r.description) {
          html += '<div style="color:#cdd6e6; font-size:12px; margin-bottom:4px;">' + escapeHtml(r.description) + '</div>';
        }
        if (r.suggestion) {
          html += '<div style="color:#80c0ff; font-size:11px;">建议：' + escapeHtml(r.suggestion) + '</div>';
        }
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setKanbanStatus('风险列表已加载 | 共 ' + risks.length + ' 条');
  } catch (e) {
    setKanbanStatus('加载风险失败：' + (e && e.message));
  }
}

async function scanRisksNow() {
  try {
    setKanbanStatus('正在扫描风险...');
    const resp = await fetch('/api/risks/scan', {method: 'POST'});
    const data = await resp.json();
    // 后端可能返回 list 或 {risks: list}
    const list = Array.isArray(data) ? data : (data.risks || []);
    setKanbanStatus('扫描完成，发现 ' + list.length + ' 条风险');
    loadRisks();
  } catch (e) {
    setKanbanStatus('扫描异常：' + (e && e.message));
  }
}

// ---------------- 角色 tab ----------------

async function loadRoles() {
  try {
    const [rolesResp, defsResp] = await Promise.all([
      fetch('/api/roles'),
      fetch('/api/role_definitions'),
    ]);
    const rolesData = await rolesResp.json();
    const defsData = await defsResp.json();
    const panel = document.getElementById('kanban-tab-roles');
    if (!panel) return;
    // rolesData.roles 是 list of {agent_id, agent_name, species, roles: [{key, name_zh, icon, description}]}
    const agentRoles = rolesData.roles || [];
    // defsData.definitions 是 dict: {key: {key, name_zh, icon, description, behavior_modifier}}
    const defsMap = defsData.definitions || {};

    // 角色定义
    let html = '<div style="margin-bottom:14px; padding:8px 12px; background:rgba(180,140,255,0.08); border-radius:4px;">';
    html += '<div style="color:#b488ff; font-weight:bold; margin-bottom:6px;">🎭 6 种非正式角色定义</div>';
    Object.keys(defsMap).forEach(k => {
      const d = defsMap[k] || {};
      const label = (d.icon || '') + (d.name_zh || k);
      const color = ROLE_COLORS[k] || '#b488ff';
      html += '<div style="font-size:11px; padding:3px 0; color:#cdd6e6;">';
      html += '<span style="color:' + color + '; font-weight:bold; margin-right:6px;">' + escapeHtml(label) + '</span>';
      html += escapeHtml(d.description || '');
      html += '</div>';
    });
    html += '</div>';

    // 每个智能体的当前角色
    html += '<div style="color:#888; font-size:11px; margin-bottom:8px;">当前各智能体角色（仅展示已获得角色的智能体）：</div>';
    if (agentRoles.length === 0) {
      html += '<div style="color:#666; padding:20px; text-align:center;">暂无智能体获得角色。<br>点击下方"立即评估"触发一次评估。</div>';
    } else {
      agentRoles.forEach(a => {
        const name = a.agent_name || a.agent_id || '';
        const roles = a.roles || [];
        html += '<div style="background:rgba(255,255,255,0.04); padding:8px 12px; margin-bottom:6px; border-radius:4px;">';
        html += '<span style="color:#ffd080; font-weight:bold; margin-right:8px;">' + escapeHtml(name) + '</span>';
        if (a.species) {
          html += '<span style="color:#888; font-size:11px; margin-right:8px;">[' + escapeHtml(a.species) + ']</span>';
        }
        if (roles.length === 0) {
          html += '<span style="color:#666; font-size:11px;">无角色</span>';
        } else {
          roles.forEach(r => {
            const label = (r.icon || '') + (r.name_zh || r.key || '');
            const color = ROLE_COLORS[r.key] || '#b488ff';
            html += '<span style="background:rgba(180,140,255,0.2); color:' + color + '; padding:2px 8px; border-radius:8px; margin-right:6px; font-size:11px;" title="' + escapeHtml(r.description || '') + '">' + escapeHtml(label) + '</span>';
          });
        }
        html += '</div>';
      });
    }
    html += '<div style="margin-top:10px; text-align:center;">';
    html += '<button onclick="evaluateRolesNow()" style="background:#6a4a8f; color:#fff; border:none; border-radius:4px; padding:6px 14px; cursor:pointer; font-size:12px;">⚖️ 立即评估角色</button>';
    html += '</div>';
    panel.innerHTML = html;
    setKanbanStatus('角色信息已加载 | ' + agentRoles.length + ' 位智能体已获角色');
  } catch (e) {
    setKanbanStatus('加载角色失败：' + (e && e.message));
  }
}

async function evaluateRolesNow() {
  try {
    setKanbanStatus('正在评估角色...');
    const resp = await fetch('/api/roles/evaluate', {method: 'POST'});
    const data = await resp.json();
    if (data && data.ok) {
      setKanbanStatus('评估完成，共评估 ' + (data.evaluated_count || 0) + ' 位智能体，变更 ' + (data.changes_count || 0) + ' 条');
    } else if (data && data.error) {
      setKanbanStatus('评估失败：' + data.error);
    } else {
      setKanbanStatus('评估结果：' + JSON.stringify(data).slice(0, 80));
    }
    loadRoles();
  } catch (e) {
    setKanbanStatus('评估异常：' + (e && e.message));
  }
}

// ---------------- 外部集成：显示/隐藏 + tab 切换 ----------------

function toggleExternalPanel() {
  const m = document.getElementById('external-modal');
  if (!m) return;
  if (m.style.display === 'none' || !m.style.display) {
    m.style.display = 'flex';
    switchExtTab(_extCurrentTab);
    if (!_extRefreshTimer) {
      _extRefreshTimer = setInterval(refreshExtCurrentTab, 5000);
    }
  } else {
    m.style.display = 'none';
    if (_extRefreshTimer) {
      clearInterval(_extRefreshTimer);
      _extRefreshTimer = null;
    }
  }
}

function switchExtTab(tab) {
  _extCurrentTab = tab;
  ['config', 'approvals', 'execute'].forEach(t => {
    const panel = document.getElementById('ext-tab-' + t);
    if (panel) panel.style.display = (t === tab) ? 'block' : 'none';
    const btn = document.querySelector('.ext-tab[data-tab="' + t + '"]');
    if (btn) {
      if (t === tab) {
        btn.style.background = 'rgba(180,140,255,0.2)';
        btn.style.color = '#b488ff';
      } else {
        btn.style.background = '#222';
        btn.style.color = '#aaa';
      }
    }
  });
  refreshExtCurrentTab();
}

function refreshExtCurrentTab() {
  if (_extCurrentTab === 'config') loadExtConfig();
  else if (_extCurrentTab === 'approvals') loadExtApprovals();
  else if (_extCurrentTab === 'execute') loadExtExecute();
}

// ---------------- 配置 tab ----------------

async function loadExtConfig() {
  try {
    const resp = await fetch('/api/external/config');
    const data = await resp.json();
    const panel = document.getElementById('ext-tab-config');
    if (!panel) return;
    const config = data.config || {};
    let html = '<div style="color:#888; font-size:11px; margin-bottom:10px;">'
      + '每个集成独立开关，未开启时智能体使用内部模拟。开启写类操作需要审批。</div>';
    const integrations = [
      {key: 'git', label: 'Git 集成', risk: '🟡中', desc: '海狸执行真实 git 提交/分支管理'},
      {key: 'shell', label: 'Shell 执行', risk: '🔴高', desc: '智能体执行白名单内的 shell 命令'},
      {key: 'api', label: '外部 API', risk: '🟢低', desc: '调用用户配置的 HTTP/HTTPS API'},
    ];
    integrations.forEach(it => {
      const cfg = config[it.key] || {};
      const enabled = !!cfg.enabled;
      const bg = enabled ? 'rgba(180,140,255,0.15)' : 'rgba(255,255,255,0.04)';
      html += '<div style="background:' + bg + '; padding:10px 12px; margin-bottom:8px; border-radius:4px; border-left:3px solid ' + (enabled ? '#b488ff' : '#444') + ';">';
      html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">';
      html += '<span style="color:#cdd6e6; font-weight:bold;">' + it.label + ' <span style="color:#888; font-size:10px;">风险 ' + it.risk + '</span></span>';
      html += '<label style="cursor:pointer; font-size:11px;">';
      html += '<input type="checkbox" ' + (enabled ? 'checked' : '') + ' onchange="toggleExtIntegration(\\'' + it.key + '\\', this.checked)"> 开启';
      html += '</label>';
      html += '</div>';
      html += '<div style="color:#888; font-size:11px;">' + it.desc + '</div>';
      if (enabled) {
        if (it.key === 'git') {
          html += '<div style="color:#aaa; font-size:11px; margin-top:4px;">仓库：' + escapeHtml(cfg.repo_path || '(未配置)') + ' | 需审批：' + (cfg.require_approval !== false ? '是' : '否') + '</div>';
        } else if (it.key === 'shell') {
          html += '<div style="color:#aaa; font-size:11px; margin-top:4px;">白名单：' + escapeHtml((cfg.whitelist || []).join(', ')) + '</div>';
          html += '<div style="color:#aaa; font-size:11px;">超时：' + (cfg.timeout || 60) + 's | 需审批：' + (cfg.require_approval !== false ? '是' : '否') + '</div>';
        } else if (it.key === 'api') {
          const apis = cfg.apis || [];
          html += '<div style="color:#aaa; font-size:11px; margin-top:4px;">已配置 ' + apis.length + ' 个 API</div>';
        }
      }
      html += '</div>';
    });
    html += '<div style="margin-top:8px; padding:8px 12px; background:rgba(255,200,120,0.06); border-radius:4px; font-size:11px; color:#aaa;">'
      + '💡 高级配置（仓库路径、白名单、API 密钥等）请直接编辑 <code style="color:#ffd080;">data/external_config.json</code> 文件。'
      + '前端只提供开关切换，避免在 UI 中处理敏感字段。</div>';
    panel.innerHTML = html;
    setExtStatus('配置已加载 | 风险等级：🟢低 🟡中 🔴高');
  } catch (e) {
    setExtStatus('加载配置失败：' + (e && e.message));
  }
}

async function toggleExtIntegration(key, enabled) {
  try {
    setExtStatus('正在更新 ' + key + ' 配置...');
    // 后端接收 section + config（完整配置对象），先 GET 当前配置再合并 enabled
    const curResp = await fetch('/api/external/config');
    const curData = await curResp.json();
    const curCfg = (curData.config || {})[key] || {};
    const newCfg = Object.assign({}, curCfg, {enabled: enabled});
    const resp = await fetch('/api/external/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({section: key, config: newCfg}),
    });
    const data = await resp.json();
    if (data && data.ok) {
      setExtStatus(key + ' 已' + (enabled ? '开启' : '关闭'));
    } else if (data && data.error) {
      setExtStatus('更新失败：' + data.error);
    } else {
      setExtStatus('更新结果：' + JSON.stringify(data).slice(0, 80));
    }
    loadExtConfig();
  } catch (e) {
    setExtStatus('更新异常：' + (e && e.message));
  }
}

// ---------------- 审批 tab ----------------

async function loadExtApprovals() {
  try {
    const resp = await fetch('/api/external/approvals');
    const data = await resp.json();
    const panel = document.getElementById('ext-tab-approvals');
    if (!panel) return;
    const approvals = data.pending || data.approvals || [];
    // 更新顶部徽标
    const badge = document.getElementById('ext-pending-badge');
    if (badge) {
      if (approvals.length > 0) {
        badge.style.display = 'inline';
        badge.textContent = approvals.length > 99 ? '99+' : String(approvals.length);
      } else {
        badge.style.display = 'none';
      }
    }
    const cnt = document.getElementById('ext-approval-count');
    if (cnt) cnt.textContent = approvals.length > 0 ? '(' + approvals.length + ')' : '';
    let html = '<div style="color:#888; font-size:11px; margin-bottom:8px;">共 ' + approvals.length + ' 条待审批</div>';
    if (approvals.length === 0) {
      html += '<div style="color:#666; padding:20px; text-align:center;">暂无待审批的外部操作。</div>';
    } else {
      approvals.forEach(a => {
        const riskColor = a.risk_level === 'high' ? '#ff8080'
                        : a.risk_level === 'medium' ? '#ffd080' : '#80c0ff';
        html += '<div style="background:rgba(255,255,255,0.04); border-left:3px solid ' + riskColor + '; padding:10px 12px; margin-bottom:8px; border-radius:4px;">';
        html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">';
        html += '<span style="color:' + riskColor + '; font-weight:bold;">[' + (a.risk_level || '').toUpperCase() + '] ' + escapeHtml(a.op_type || '') + '</span>';
        html += '<span style="color:#888; font-size:11px;">' + escapeHtml(a.agent_name || a.agent_id || '') + '</span>';
        html += '</div>';
        if (a.summary) {
          html += '<div style="color:#cdd6e6; font-size:11px; margin-bottom:4px;">' + escapeHtml(a.summary) + '</div>';
        }
        if (a.detail) {
          const detStr = typeof a.detail === 'string' ? a.detail : JSON.stringify(a.detail);
          html += '<div style="color:#aaa; font-size:10px; margin-bottom:4px;">详情：' + escapeHtml(detStr) + '</div>';
        }
        html += '<div style="color:#888; font-size:10px; margin-bottom:6px;">时间 ' + new Date((a.created_ts || 0) * 1000).toLocaleString() + '</div>';
        html += '<div style="display:flex; gap:6px;">';
        html += '<button onclick="decideExtApproval(\\'' + (a.id || '') + '\\', \\'approved\\')" style="background:#4a8f60; color:#fff; border:none; border-radius:3px; padding:3px 10px; cursor:pointer; font-size:11px;">✓ 批准</button>';
        html += '<button onclick="decideExtApproval(\\'' + (a.id || '') + '\\', \\'rejected\\')" style="background:#8f4a4a; color:#fff; border:none; border-radius:3px; padding:3px 10px; cursor:pointer; font-size:11px;">✗ 拒绝</button>';
        html += '</div>';
        html += '</div>';
      });
    }
    panel.innerHTML = html;
    setExtStatus('审批队列已加载 | ' + approvals.length + ' 条待审批');
  } catch (e) {
    setExtStatus('加载审批失败：' + (e && e.message));
  }
}

async function decideExtApproval(approvalId, decision) {
  try {
    setExtStatus('正在处理审批 ' + approvalId + ' ...');
    const resp = await fetch('/api/external/approvals', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id: approvalId, decision: decision}),
    });
    const data = await resp.json();
    if (data && data.ok) {
      setExtStatus('审批已' + (decision === 'approved' ? '批准' : '拒绝'));
    } else if (data && data.error) {
      setExtStatus('审批失败：' + data.error);
    } else {
      setExtStatus('审批结果：' + JSON.stringify(data).slice(0, 80));
    }
    loadExtApprovals();
  } catch (e) {
    setExtStatus('审批异常：' + (e && e.message));
  }
}

// ---------------- 执行 tab ----------------

async function loadExtExecute() {
  try {
    const resp = await fetch('/api/external/status');
    const data = await resp.json();
    const panel = document.getElementById('ext-tab-execute');
    if (!panel) return;
    const status = data.status || {};
    let html = '<div style="color:#888; font-size:11px; margin-bottom:8px;">手动触发一次外部操作（用于演示和测试）</div>';
    html += '<div style="background:rgba(255,255,255,0.04); padding:10px 12px; margin-bottom:8px; border-radius:4px;">';
    html += '<div style="color:#cdd6e6; font-weight:bold; margin-bottom:6px;">⚡ 快速执行</div>';
    html += '<div style="color:#888; font-size:11px; margin-bottom:8px;">所有操作都会进入审批队列（除非配置中关闭了 require_approval）。</div>';
    // Git 操作（args 是 git 命令参数列表）
    html += '<button onclick="execExt(\\'git\\', {args: [\\'status\\'], summary: \\'查看仓库状态\\'})" style="background:#4a6a8f; color:#fff; border:none; border-radius:4px; padding:5px 12px; cursor:pointer; font-size:11px; margin-right:6px;">Git status</button>';
    html += '<button onclick="execExt(\\'git\\', {args: [\\'log\\', \\'--oneline\\', \\'-5\\'], summary: \\'查看最近 5 条提交\\'})" style="background:#4a6a8f; color:#fff; border:none; border-radius:4px; padding:5px 12px; cursor:pointer; font-size:11px; margin-right:6px;">Git log</button>';
    // Shell 操作
    html += '<button onclick="execExt(\\'shell\\', {command: \\'python --version\\', summary: \\'查看 Python 版本\\'})" style="background:#6a4a8f; color:#fff; border:none; border-radius:4px; padding:5px 12px; cursor:pointer; font-size:11px; margin-right:6px;">python --version</button>';
    html += '<button onclick="execExt(\\'shell\\', {command: \\'git --version\\', summary: \\'查看 Git 版本\\'})" style="background:#6a4a8f; color:#fff; border:none; border-radius:4px; padding:5px 12px; cursor:pointer; font-size:11px;">git --version</button>';
    html += '</div>';
    // 集成状态
    html += '<div style="background:rgba(255,255,255,0.04); padding:10px 12px; border-radius:4px;">';
    html += '<div style="color:#cdd6e6; font-weight:bold; margin-bottom:6px;">📋 集成状态</div>';
    ['git', 'shell', 'api'].forEach(k => {
      const s = status[k] || {};
      const enabled = !!s.enabled;
      const color = enabled ? '#80ff80' : '#888';
      html += '<div style="font-size:11px; padding:2px 0; color:#cdd6e6;">';
      html += '<span style="color:' + color + ';">●</span> ' + k + '：' + (enabled ? '已开启' : '已关闭');
      if (k === 'git' && s.repo_exists !== undefined) {
        html += '<span style="color:#666; margin-left:8px;">仓库 ' + (s.repo_exists ? '已就绪' : '未配置') + '</span>';
      }
      html += '</div>';
    });
    if (status.pending_approvals !== undefined) {
      html += '<div style="font-size:11px; padding:2px 0; color:#cdd6e6;">';
      html += '<span style="color:#ffd080;">●</span> 待审批：' + status.pending_approvals + ' 条';
      html += '</div>';
    }
    html += '</div>';
    panel.innerHTML = html;
    setExtStatus('执行面板已加载');
  } catch (e) {
    setExtStatus('加载执行面板失败：' + (e && e.message));
  }
}

async function execExt(opType, params) {
  try {
    setExtStatus('正在执行 ' + opType + ' ...');
    const resp = await fetch('/api/external/execute', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({op_type: opType, params: params}),
    });
    const data = await resp.json();
    // 后端返回 _serialize_external_result 结构
    if (data && data.kind === 'approval') {
      if (data.decision === 'pending' || data.decision === '') {
        setExtStatus('操作已提交审批，请到"审批"tab 处理（ID: ' + (data.id || '') + '）');
      } else if (data.decision === 'approved') {
        setExtStatus('操作已自动批准并执行');
      } else {
        setExtStatus('操作被拒绝');
      }
    } else if (data && data.ok === false && data.error) {
      setExtStatus('执行失败：' + data.error);
    } else if (data && data.ok) {
      setExtStatus('执行完成');
    } else {
      setExtStatus('执行结果：' + JSON.stringify(data).slice(0, 100));
    }
    // 刷新审批队列（操作可能已入队）
    setTimeout(loadExtApprovals, 300);
  } catch (e) {
    setExtStatus('执行异常：' + (e && e.message));
  }
}

// ---------------- P/E/N/S/V 键快捷键 ----------------

document.addEventListener('keydown', e => {
  const tag = (e.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea') return;
  if (e.key === 'p' || e.key === 'P') {
    toggleKanban();
  } else if (e.key === 'e' || e.key === 'E') {
    toggleExternalPanel();
  } else if (e.key === 'n' || e.key === 'N') {
    // commit 40：新手引导
    startOnboarding();
  } else if (e.key === 's' || e.key === 'S') {
    // commit 40：分享与导出
    toggleSharePanel();
  } else if (e.key === 'v' || e.key === 'V') {
    // commit 40：进化突变
    toggleEvolutionPanel();
  }
});

// 启动时拉一次外部审批数量，更新顶部徽标
setTimeout(() => {
  fetch('/api/external/approvals').then(r => r.json()).then(data => {
    const list = data.pending || data.approvals || [];
    const n = list.length;
    const badge = document.getElementById('ext-pending-badge');
    if (badge) {
      if (n > 0) {
        badge.style.display = 'inline';
        badge.textContent = n > 99 ? '99+' : String(n);
      } else {
        badge.style.display = 'none';
      }
    }
  }).catch(() => {});
}, 3000);

window.toggleKanban = toggleKanban;
window.switchKanbanTab = switchKanbanTab;
window.loadKanban = loadProjects;
window.createSampleProject = createSampleProject;
window.loadProjects = loadProjects;
window.loadStandups = loadStandups;
window.runStandupNow = runStandupNow;
window.loadRisks = loadRisks;
window.scanRisksNow = scanRisksNow;
window.loadRoles = loadRoles;
window.evaluateRolesNow = evaluateRolesNow;
window.toggleExternalPanel = toggleExternalPanel;
window.switchExtTab = switchExtTab;
window.loadExtConfig = loadExtConfig;
window.toggleExtIntegration = toggleExtIntegration;
window.loadExtApprovals = loadExtApprovals;
window.decideExtApproval = decideExtApproval;
window.loadExtExecute = loadExtExecute;
window.execExt = execExt;

// ==================== commit 44-4：事件流侧边面板 ====================
function toggleEventFeed() {
  const panel = document.getElementById('event-feed-panel');
  if (!panel) return;
  panel.classList.toggle('open');
  // 打开时立即拉取一次
  if (panel.classList.contains('open')) fetchEventFeed();
}
// 在列表头部插入一条事件，最多保留 50 条
function addEventFeedItem(item) {
  const list = document.getElementById('event-feed-list');
  if (!list || !item) return;
  const li = document.createElement('li');
  const timeStr = formatEvTime(item.time) || formatEvTime(item.ts);
  li.innerHTML = '<span class="ev-time">' + escapeHtml(timeStr) + '</span> ' +
    escapeHtml(item.text || item.summary || '');
  list.insertBefore(li, list.firstChild);
  while (list.children.length > 50) list.removeChild(list.lastChild);
}
// 时间格式化：支持字符串 / 时间戳
function formatEvTime(t) {
  if (!t) return '';
  if (typeof t === 'number') {
    const d = new Date(t);
    return String(d.getHours()).padStart(2, '0') + ':' +
      String(d.getMinutes()).padStart(2, '0') + ':' +
      String(d.getSeconds()).padStart(2, '0');
  }
  return String(t);
}
// commit 44-4：周期拉取后端事件列表
function fetchEventFeed() {
  fetch('/api/events/list?limit=30')
    .then(r => r.json())
    .then(data => {
      if (!data || !data.events) return;
      const list = document.getElementById('event-feed-list');
      if (!list) return;
      list.innerHTML = data.events.map(ev =>
        '<li><span class="ev-time">' + escapeHtml(formatEvTime(ev.time)) + '</span> ' +
        escapeHtml(ev.text || ev.summary || '') + '</li>'
      ).join('');
    }).catch(() => {});
}
setInterval(fetchEventFeed, 3000);
fetchEventFeed();

// ── 资源预载 ──────────────────────────────────────────────────
const _preloadCache = {};
function preloadResources(urls) {
  return Promise.all((urls || ['/api/status', '/api/events/list?limit=10']).map(url => {
    if (_preloadCache[url]) return _preloadCache[url];
    const p = fetch(url).then(r => r.json()).then(d => { _preloadCache[url] = d; return d; });
    _preloadCache[url] = p;
    return p;
  }));
}
// 页面 load 后自动预载
window.addEventListener('load', () => { preloadResources(); });

// ── 按需加载地图块 ──────────────────────────────────────────
const _mapChunkCache = {};
function lazyLoadMap(region) {
  const key = region.join(',');
  if (_mapChunkCache[key]) return Promise.resolve(_mapChunkCache[key]);
  return fetch('/api/map/chunk?x=' + region[0] + '&y=' + region[1] + '&w=' + region[2] + '&h=' + region[3])
    .then(r => r.json())
    .then(data => { _mapChunkCache[key] = data; return data; })
    .catch(() => null);
}

console.log('[commit 39] 项目看板 + 外部集成已加载：P 键看板，E 键外部集成');
console.log('[commit 44] 员工快捷菜单 + 指令对话框 + 日夜循环 + 事件流面板已加载');
</script>
</body>
</html>
"""


# ----------------------------------------------------------------------
# 渲染入口：把后端数据注入模板
# ----------------------------------------------------------------------

import json as _json


def render_index(visit_mode: bool = False, visit_token: str = "") -> str:
    """渲染首页 HTML（注入 17 区布局与物种配色）。

    commit 40：visit_mode=True 时返回参观模式 HTML（隐藏写操作按钮）。
    """
    html = (
        HTML_TEMPLATE
        .replace("__ZONES_JSON__", _json.dumps(ZONES, ensure_ascii=False))
        .replace("__SPECIES_COLORS_JSON__",
                 _json.dumps(SPECIES_COLORS, ensure_ascii=False))
        .replace("__SPECIES_TO_ZONE_JSON__",
                 _json.dumps(SPECIES_TO_ZONE, ensure_ascii=False))
    )
    if visit_mode:
        # 参观模式：注入只读标记
        html = html.replace(
            "<body>",
            f"<body data-visit-mode=\"1\" data-visit-token=\"{visit_token}\">"
        )
        # 在顶部插入参观者提示横幅
        html = html.replace(
            "<nav>",
            "<div id='visit-banner' style='position:fixed;top:0;left:0;right:0;"
            "background:rgba(180,140,255,0.15);color:#b488ff;text-align:center;"
            "padding:4px;font-size:12px;z-index:9999;'>"
            "👁️ 你正在参观森林公司 · 只读模式</div><nav style='margin-top:24px'>",
            1
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
