"""BlueDeer 2D 俯视角前端（commit 57）。

零基础读者可以这样理解：
- 之前的 2.5D 等距视角要求复杂的 Y 轴排序和遮挡计算，容易穿模。
- 这个文件是全新的 2D 俯视角（Top-Down）前端，像《星露谷》那样从上往下看。
- 方格地图，员工静态站在工位上，点击高亮+弹出毛玻璃状态卡。
- 不再需要 Y 轴排序，不再有穿模问题。

入口函数 render_index() 返回完整 HTML 字符串。
"""

from __future__ import annotations

import json

from game_frontend import ZONES

# 11 物种深蓝色表（与花名册圆点同源）
EMPLOYEE_COLOR_MAP = {
    "deer": "#0B1A33",
    "squirrel": "#1A3B5C",
    "butterfly": "#1C2E4A",
    "fox": "#132A4A",
    "hedgehog": "#091626",
    "beaver": "#1A3B5C",
    "raven": "#040B17",
    "hare": "#2B4C7E",
    "badger": "#12304D",
    "lark": "#1A4870",
    "kite": "#213A5C",
}

SPECIES_CN = {
    "deer": "鹿",
    "squirrel": "鼠",
    "butterfly": "蝶",
    "fox": "狐",
    "hedgehog": "猬",
    "beaver": "狸",
    "raven": "鸦",
    "hare": "兔",
    "badger": "獾",
    "lark": "雀",
    "kite": "鸢",
}

SPECIES_JOB = {
    "deer": "调度官",
    "squirrel": "前端工程师",
    "butterfly": "视觉设计师",
    "fox": "测试工程师",
    "hedgehog": "安全工程师",
    "beaver": "基建工程师",
    "raven": "记忆管理员",
    "hare": "快递员",
    "badger": "矿工",
    "lark": "播音员",
    "kite": "瞭望员",
}

# 每个物种工位上的 2D 道具（俯视图）
SPECIES_PROP = {
    "squirrel": "desk",  # 电脑桌
    "fox": "desk",  # 测试台
    "hedgehog": "shield",  # 安全盾
    "beaver": "logs",  # 木料堆
    "butterfly": "easel",  # 画架
    "raven": "shelf",  # 档案架
    "hare": "mailbox",  # 信箱
    "badger": "lamp",  # 矿灯
    "lark": "speaker",  # 喇叭
    "kite": "telescope",  # 望远镜
    "deer": "roundtable",  # 圆桌
}

# 转换 ZONES 为前端用（rect 转 list）
zones_json = json.dumps(
    [{**z, "rect": list(z["rect"])} for z in ZONES], ensure_ascii=False
)


def render_index() -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BlueDeer · 2D 俯视角</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600&family=Manrope:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
{CSS_STYLES}
</style>
</head>
<body>

<canvas id="map-canvas"></canvas>

<!-- 顶部栏 -->
<div id="top-bar">
  <div class="top-title"><span class="t-main">BlueDeer</span><span class="t-sub">2D 俯视控制台</span></div>
  <div id="top-info">
    <span id="info-time">--:--</span>
    <span id="info-weather">·</span>
    <span id="info-gen">第 0 代</span>
    <span id="info-pop">11 员工</span>
  </div>
</div>

<!-- 右侧花名册 -->
<div id="roster">
  <div class="roster-title">花名册</div>
  <div id="roster-list"></div>
</div>

<!-- 右下仪表盘 -->
<div id="dashboard">
  <div class="dash-title">团队趋势</div>
  <canvas id="dash-canvas"></canvas>
</div>

<!-- 事件流（左下） -->
<div id="event-stream">
  <div class="ev-title">事件流</div>
  <div id="event-list"></div>
</div>

<!-- 员工状态卡（毛玻璃） -->
<div id="card-overlay" style="display:none;">
  <div id="status-card">
    <button id="card-close" onclick="closeCard()">×</button>
    <div id="card-header">
      <div id="card-avatar"></div>
      <div id="card-info">
        <div id="card-name"></div>
        <div id="card-job"></div>
      </div>
    </div>
    <div id="card-bars">
      <div class="bar-row"><span class="bar-label">精力</span><div class="bar-track"><div class="bar-fill" id="bar-energy" style="background:linear-gradient(180deg,#2DD4BF,#0D9488);"></div></div><span class="bar-val" id="val-energy">0</span></div>
      <div class="bar-row"><span class="bar-label">健康</span><div class="bar-track"><div class="bar-fill" id="bar-health" style="background:linear-gradient(180deg,#F87171,#DC2626);"></div></div><span class="bar-val" id="val-health">0</span></div>
      <div class="bar-row"><span class="bar-label">心情</span><div class="bar-track"><div class="bar-fill" id="bar-mood" style="background:linear-gradient(180deg,#FBBF24,#D97706);"></div></div><span class="bar-val" id="val-mood">0</span></div>
    </div>
    <div id="card-thought">...</div>
    <div id="card-skills"></div>
    <div id="card-actions">
      <button class="act-btn" onclick="doAction('feed')">投喂</button>
      <button class="act-btn" onclick="doAction('train')">训练</button>
      <button class="act-btn" onclick="doAction('rest')">休息</button>
      <button class="act-btn" onclick="doAction('chat')">交谈</button>
    </div>
    <div id="card-feedback"></div>
  </div>
</div>

<script>
const ZONES = {zones_json};
const EMPLOYEE_COLOR_MAP = {json.dumps(EMPLOYEE_COLOR_MAP)};
const SPECIES_CN = {json.dumps(SPECIES_CN)};
const SPECIES_JOB = {json.dumps(SPECIES_JOB)};
const SPECIES_PROP = {json.dumps(SPECIES_PROP)};

{JS_CODE}
</script>
</body>
</html>"""


CSS_STYLES = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {{
  --bg: #0a0f0c;
  --glass: rgba(15, 23, 42, 0.78);
  --glass-border: rgba(255,255,255,0.08);
  --text: #E8E4D8;
  --text-dim: #8A8275;
  --accent: #D4A574;
}}
html, body {{ width:100%; height:100%; overflow:hidden; background:var(--bg); font-family:'Manrope',sans-serif; color:var(--text); user-select:none; }}

#map-canvas {{ position:fixed; top:0; left:0; width:100%; height:100%; z-index:0; cursor:pointer; }}

/* 顶部栏 */
#top-bar {{ position:fixed; top:0; left:0; right:0; height:48px; z-index:10; display:flex; align-items:center; justify-content:space-between; padding:0 24px;
  background:linear-gradient(180deg,rgba(10,15,12,0.9) 0%,transparent 100%); }}
.top-title {{ display:flex; align-items:baseline; gap:10px; }}
.t-main {{ font-family:'Fraunces',serif; font-size:19px; font-weight:600; }}
.t-sub {{ font-size:11px; letter-spacing:0.16em; text-transform:uppercase; color:var(--text-dim); }}
#top-info {{ display:flex; gap:16px; font-size:12px; color:var(--text-dim); font-family:'JetBrains Mono',monospace; }}

/* 花名册 */
#roster {{ position:fixed; top:56px; right:16px; width:180px; z-index:10; background:var(--glass); backdrop-filter:blur(16px) saturate(140%); -webkit-backdrop-filter:blur(16px) saturate(140%); border:1px solid var(--glass-border); border-radius:12px; padding:12px; max-height:60vh; overflow-y:auto; }}
.roster-title {{ font-size:10px; letter-spacing:0.16em; text-transform:uppercase; color:var(--accent); margin-bottom:8px; font-weight:600; }}
.roster-item {{ display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:6px; cursor:pointer; transition:background 0.15s; }}
.roster-item:hover {{ background:rgba(255,255,255,0.06); }}
.roster-item.active {{ background:rgba(212,165,116,0.15); }}
.roster-dot {{ width:10px; height:10px; border-radius:50%; flex-shrink:0; box-shadow:0 0 6px currentColor; }}
.roster-name {{ font-size:12px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.roster-item.dead .roster-name {{ color:var(--text-dim); text-decoration:line-through; }}

/* 仪表盘 */
#dashboard {{ position:fixed; bottom:16px; right:16px; width:220px; height:110px; z-index:10; background:var(--glass); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px); border:1px solid var(--glass-border); border-radius:12px; padding:10px 12px; }}
.dash-title {{ font-size:10px; letter-spacing:0.16em; text-transform:uppercase; color:var(--accent); margin-bottom:4px; font-weight:600; }}
#dash-canvas {{ width:100%; height:80px; }}

/* 事件流 */
#event-stream {{ position:fixed; bottom:16px; left:16px; width:240px; max-height:200px; z-index:10; background:var(--glass); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px); border:1px solid var(--glass-border); border-radius:12px; padding:10px 12px; }}
.ev-title {{ font-size:10px; letter-spacing:0.16em; text-transform:uppercase; color:var(--accent); margin-bottom:6px; font-weight:600; }}
#event-list {{ max-height:160px; overflow-y:auto; font-size:11px; line-height:1.6; }}
#event-list::-webkit-scrollbar {{ width:3px; }}
#event-list::-webkit-scrollbar-thumb {{ background:rgba(255,255,255,0.1); }}
.event-item {{ padding:2px 0; color:var(--text-dim); border-bottom:1px solid rgba(255,255,255,0.03); }}
.event-item:last-child {{ border-bottom:none; }}
.event-item .ev-type {{ color:var(--accent); font-size:10px; }}

/* 状态卡 */
#card-overlay {{ position:fixed; top:0; left:0; width:100%; height:100%; z-index:100; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,0.5); backdrop-filter:blur(4px); -webkit-backdrop-filter:blur(4px); }}
#status-card {{ position:relative; width:400px; max-width:90vw; background:rgba(15,23,42,0.85); backdrop-filter:blur(24px) saturate(140%); -webkit-backdrop-filter:blur(24px) saturate(140%); border:1px solid var(--glass-border); border-radius:18px; padding:26px; box-shadow:0 16px 64px rgba(0,0,0,0.5); animation:cardIn 0.3s cubic-bezier(0.2,0.9,0.3,1); }}
@keyframes cardIn {{ from{{ transform:scale(0.92) translateY(16px); opacity:0; }} to{{ transform:scale(1) translateY(0); opacity:1; }} }}
#card-close {{ position:absolute; top:12px; right:12px; width:30px; height:30px; border:none; border-radius:50%; background:rgba(255,255,255,0.08); color:var(--text-dim); font-size:18px; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:all 0.15s; }}
#card-close:hover {{ background:rgba(255,255,255,0.18); color:var(--text); }}
#card-header {{ display:flex; align-items:center; gap:14px; margin-bottom:20px; }}
#card-avatar {{ width:56px; height:56px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-family:'Fraunces',serif; font-size:28px; font-weight:600; color:#E8E4D8; border:2px solid rgba(255,255,255,0.12); flex-shrink:0; }}
#card-name {{ font-size:17px; font-weight:600; font-family:'Fraunces',serif; }}
#card-job {{ font-size:12px; color:var(--text-dim); margin-top:2px; letter-spacing:0.06em; }}

#card-bars {{ margin-bottom:16px; }}
.bar-row {{ display:flex; align-items:center; gap:8px; margin-bottom:8px; }}
.bar-label {{ font-size:11px; color:var(--text-dim); width:28px; }}
.bar-track {{ flex:1; height:14px; background:rgba(255,255,255,0.05); border-radius:3px; overflow:hidden; border:1px solid rgba(255,255,255,0.04); }}
.bar-fill {{ height:100%; transition:width 0.6s cubic-bezier(0.2,0.9,0.3,1); box-shadow:0 0 8px currentColor; }}
.bar-val {{ font-size:11px; color:var(--text-dim); width:28px; font-family:'JetBrains Mono',monospace; }}

#card-thought {{ font-size:13px; line-height:1.6; color:var(--text); background:rgba(255,255,255,0.04); border-radius:10px; padding:12px 14px; font-style:italic; border-left:2px solid rgba(212,165,116,0.3); margin-bottom:14px; }}
#card-skills {{ display:flex; flex-wrap:wrap; gap:5px; margin-bottom:16px; }}
.skill-tag {{ font-size:10px; padding:3px 7px; border-radius:4px; background:rgba(255,255,255,0.06); color:var(--text-dim); font-family:'JetBrains Mono',monospace; }}

#card-actions {{ display:flex; gap:8px; }}
.act-btn {{ flex:1; padding:11px; border:none; border-radius:9px; background:rgba(255,255,255,0.06); color:var(--text); font-size:13px; font-weight:500; cursor:pointer; transition:all 0.15s; }}
.act-btn:hover {{ background:rgba(212,165,116,0.2); }}
.act-btn:active {{ transform:scale(0.95); }}
#card-feedback {{ margin-top:10px; font-size:12px; color:var(--accent); text-align:center; min-height:16px; font-family:'JetBrains Mono',monospace; }}
"""


JS_CODE = r"""
// ==================== 全局状态 ====================
let employees = [];
let selectedName = null;
let gameHour = 8, gameMinute = 0, weather = 'sunny', generation = 0;
let ecoHistory = [];
let empPositions = {};  // name -> {x, y} 像素坐标（用于点击命中）

// ==================== Tile 缓存系统 ====================
class TileCache {
  constructor(maxSize = 1000) {
    this._max = maxSize;
    this._cache = new Map();
  }
  get(x, y, z) {
    const key = x + ',' + y + ',' + z;
    if (this._cache.has(key)) {
      const val = this._cache.get(key);
      this._cache.delete(key);
      this._cache.set(key, val);
      return val;
    }
    return null;
  }
  set(x, y, z, data) {
    const key = x + ',' + y + ',' + z;
    if (this._cache.size >= this._max) {
      const first = this._cache.keys().next().value;
      this._cache.delete(first);
    }
    this._cache.set(key, data);
  }
  clear() {
    this._cache.clear();
  }
  get size() {
    return this._cache.size;
  }
}
const tileCache = new TileCache(1000);

function getTile(x, y, z) {
  return tileCache.get(x, y, z);
}

// ==================== 视口裁剪 ====================
function getVisibleTiles(camera) {
  const t = getMapTransform();
  const tiles = [];
  const viewLeft = 0;
  const viewTop = 0;
  const viewRight = canvas.width;
  const viewBottom = canvas.height;

  for (const zone of ZONES) {
    const [x1, y1, x2, y2] = zone.rect;
    const px1 = t.offsetX + x1 * t.scale;
    const py1 = t.offsetY + y1 * t.scale;
    const pw = (x2 - x1) * t.scale;
    const ph = (y2 - y1) * t.scale;

    if (px1 + pw < viewLeft || px1 > viewRight || py1 + ph < viewTop || py1 > viewBottom) {
      continue;
    }
    tiles.push(zone);
  }
  return tiles;
}

// ==================== Canvas 初始化 ====================
const canvas = document.getElementById('map-canvas');
const ctx = canvas.getContext('2d');

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
resizeCanvas();
window.addEventListener('resize', () => { resizeCanvas(); renderMap(); });

// ==================== 地图坐标转换 ====================
// ZONES rect 是 [x1, y1, x2, y2] 网格坐标（0-80, 0-60）
// 把整个 80x60 网格缩放铺满屏幕 80% 区域
const GRID_W = 80, GRID_H = 60;
function getMapTransform() {
  const cw = canvas.width, ch = canvas.height;
  // 留出顶部 48px、右侧 200px（花名册）、底部 130px（仪表盘+事件流）
  const availW = cw - 220;
  const availH = ch - 60 - 140;
  const scale = Math.min(availW / GRID_W, availH / GRID_H);
  const offsetX = (cw - GRID_W * scale) / 2 - 80;
  const offsetY = 56 + (availH - GRID_H * scale) / 2;
  return { scale, offsetX, offsetY };
}
function gridToPx(gx, gy) {
  const t = getMapTransform();
  return { x: t.offsetX + gx * t.scale, y: t.offsetY + gy * t.scale };
}

// ==================== 渲染地图 ====================
function renderMap() {
  const t = getMapTransform();
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 1. 深色背景
  const bg = ctx.createLinearGradient(0, 0, 0, canvas.height);
  bg.addColorStop(0, '#0a0f0c');
  bg.addColorStop(1, '#080c0a');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // 2. 视口裁剪：只画可见 zone
  const visibleZones = getVisibleTiles();
  for (const zone of visibleZones) {
    const [x1, y1, x2, y2] = zone.rect;
    const px1 = t.offsetX + x1 * t.scale;
    const py1 = t.offsetY + y1 * t.scale;
    const pw = (x2 - x1) * t.scale;
    const ph = (y2 - y1) * t.scale;

    // 地砖底色
    ctx.fillStyle = zone.color;
    ctx.fillRect(px1, py1, pw, ph);

    // 地砖网格线（极淡）
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
    ctx.lineWidth = 0.5;
    for (let gx = x1; gx <= x2; gx++) {
      const lx = t.offsetX + gx * t.scale;
      ctx.beginPath(); ctx.moveTo(lx, py1); ctx.lineTo(lx, py1 + ph); ctx.stroke();
    }
    for (let gy = y1; gy <= y2; gy++) {
      const ly = t.offsetY + gy * t.scale;
      ctx.beginPath(); ctx.moveTo(px1, ly); ctx.lineTo(px1 + pw, ly); ctx.stroke();
    }

    // zone 边框
    ctx.strokeStyle = 'rgba(212,165,116,0.15)';
    ctx.lineWidth = 1;
    ctx.strokeRect(px1, py1, pw, ph);

    // zone 名字（左上角小字）
    if (t.scale > 6) {
      ctx.fillStyle = 'rgba(232,228,216,0.4)';
      ctx.font = '10px Manrope';
      ctx.textAlign = 'left';
      ctx.fillText(zone.name, px1 + 4, py1 + 12);
    }

    // 3. 画工位道具（species zone 才有）
    if (zone.type === 'species') {
      drawProp(zone, px1, py1, pw, ph, t.scale);
    }
  }

  // 4. 画地图外圈树林边界（俯视小树）
  drawForestBorder(t);

  // 5. 画员工（俯视头像，站在工位中央）
  empPositions = {};
  for (const emp of employees) {
    drawEmployee(emp, t);
  }

  // 6. 选中高亮
  if (selectedName && empPositions[selectedName]) {
    const p = empPositions[selectedName];
    const pulse = Math.sin(performance.now() / 300) * 0.3 + 0.7;
    ctx.strokeStyle = 'rgba(212,165,116,' + pulse + ')';
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.arc(p.x, p.y, 32, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // 7. 暗角
  const vig = ctx.createRadialGradient(canvas.width/2, canvas.height/2, canvas.height*0.3, canvas.width/2, canvas.height/2, canvas.height*0.7);
  vig.addColorStop(0, 'transparent');
  vig.addColorStop(1, 'rgba(0,0,0,0.6)');
  ctx.fillStyle = vig;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

// ==================== 工位道具（俯视图） ====================
function drawProp(zone, px, py, pw, ph, scale) {
  const cx = px + pw / 2;
  const cy = py + ph / 2;
  const prop = SPECIES_PROP[zone.species] || 'desk';
  const s = Math.min(pw, ph) * 0.3;  // 道具大小
  const color = EMPLOYEE_COLOR_MAP[zone.species] || '#1A3B5C';

  ctx.save();
  ctx.translate(cx, cy);

  switch (prop) {
    case 'desk':  // 电脑桌（矩形+屏幕）
      ctx.fillStyle = '#3A2E20';
      ctx.fillRect(-s, -s*0.5, s*2, s);
      ctx.fillStyle = color;
      ctx.fillRect(-s*0.7, -s*0.35, s*1.4, s*0.5);
      ctx.fillStyle = 'rgba(45,212,191,0.3)';
      ctx.fillRect(-s*0.6, -s*0.3, s*1.2, s*0.35);
      break;
    case 'easel':  // 画架（三角）
      ctx.fillStyle = '#3A2E20';
      ctx.beginPath();
      ctx.moveTo(0, -s); ctx.lineTo(s, s*0.5); ctx.lineTo(-s, s*0.5); ctx.closePath();
      ctx.fill();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(0, -s*0.6); ctx.lineTo(s*0.7, s*0.3); ctx.lineTo(-s*0.7, s*0.3); ctx.closePath();
      ctx.fill();
      break;
    case 'logs':  // 木料堆（堆叠圆木）
      for (let i = 0; i < 3; i++) {
        ctx.fillStyle = i === 0 ? '#4A3826' : (i === 1 ? '#3A2E20' : '#2A2018');
        ctx.fillRect(-s + i*2, -s*0.5 + i*s*0.35, s*2 - i*4, s*0.3);
      }
      break;
    case 'shelf':  // 档案架（竖排方块）
      ctx.fillStyle = '#2A2418';
      ctx.fillRect(-s*0.8, -s, s*1.6, s*2);
      for (let i = 0; i < 4; i++) {
        ctx.fillStyle = color;
        ctx.fillRect(-s*0.6, -s*0.8 + i*s*0.45, s*1.2, s*0.1);
      }
      break;
    case 'mailbox':  // 信箱（圆柱+顶）
      ctx.fillStyle = '#3A2E20';
      ctx.fillRect(-s*0.4, -s*0.6, s*0.8, s*1.2);
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(0, -s*0.6, s*0.4, 0, Math.PI, true);
      ctx.fill();
      break;
    case 'lamp':  // 矿灯（柱+光球）
      ctx.fillStyle = '#3A2E20';
      ctx.fillRect(-s*0.1, -s*0.8, s*0.2, s*1.6);
      const glow = ctx.createRadialGradient(0, -s*0.8, 0, 0, -s*0.8, s*0.6);
      glow.addColorStop(0, 'rgba(251,191,36,0.6)');
      glow.addColorStop(1, 'rgba(251,191,36,0)');
      ctx.fillStyle = glow;
      ctx.beginPath(); ctx.arc(0, -s*0.8, s*0.6, 0, Math.PI*2); ctx.fill();
      break;
    case 'speaker':  // 喇叭（梯形）
      ctx.fillStyle = '#3A2E20';
      ctx.beginPath();
      ctx.moveTo(-s*0.5, s*0.5); ctx.lineTo(s*0.5, s*0.5);
      ctx.lineTo(s*0.3, -s*0.5); ctx.lineTo(-s*0.3, -s*0.5); ctx.closePath();
      ctx.fill();
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(0, 0, s*0.2, 0, Math.PI*2); ctx.fill();
      break;
    case 'telescope':  // 望远镜（三脚架+镜筒）
      ctx.strokeStyle = '#3A2E20';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(0, s*0.6); ctx.lineTo(-s*0.4, -s*0.4);
      ctx.moveTo(0, s*0.6); ctx.lineTo(s*0.4, -s*0.4);
      ctx.moveTo(0, s*0.6); ctx.lineTo(0, -s*0.6);
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.fillRect(-s*0.15, -s*0.8, s*0.3, s*0.5);
      break;
    case 'shield':  // 安全盾（盾形）
      ctx.fillStyle = '#3A2E20';
      ctx.beginPath();
      ctx.moveTo(0, -s); ctx.lineTo(s*0.7, -s*0.5); ctx.lineTo(s*0.5, s*0.6);
      ctx.lineTo(0, s); ctx.lineTo(-s*0.5, s*0.6); ctx.lineTo(-s*0.7, -s*0.5); ctx.closePath();
      ctx.fill();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.moveTo(0, -s*0.7); ctx.lineTo(s*0.5, -s*0.3); ctx.lineTo(s*0.3, s*0.4);
      ctx.lineTo(0, s*0.7); ctx.lineTo(-s*0.3, s*0.4); ctx.lineTo(-s*0.5, -s*0.3); ctx.closePath();
      ctx.fill();
      break;
    case 'roundtable':  // 圆桌（大圆）
      ctx.fillStyle = '#3A2E20';
      ctx.beginPath(); ctx.arc(0, 0, s, 0, Math.PI*2); ctx.fill();
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(0, 0, s*0.6, 0, Math.PI*2); ctx.fill();
      break;
  }
  ctx.restore();
}

// ==================== 森林边界 ====================
function drawForestBorder(t) {
  // 地图外圈一圈深色小树
  const treeColor = 'rgba(8, 20, 12, 0.9)';
  for (let i = 0; i < 60; i++) {
    // 用稳定伪随机
    const seed = i * 9301 + 49297;
    const rnd = ((seed % 233280) / 233280);
    const angle = rnd * Math.PI * 2;
    const dist = 1.5 + (rnd * 0.5);  // 网格外 1.5-2 格
    const gx = GRID_W/2 + Math.cos(angle) * (GRID_W/2 + dist);
    const gy = GRID_H/2 + Math.sin(angle) * (GRID_H/2 + dist);
    const p = gridToPx(gx, gy);
    const r = 4 + (rnd * 3);
    ctx.fillStyle = treeColor;
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle = 'rgba(15,35,22,0.7)';
    ctx.beginPath(); ctx.arc(p.x, p.y, r*0.6, 0, Math.PI*2); ctx.fill();
  }
}

// ==================== 员工（俯视头像） ====================
function drawEmployee(emp, t) {
  // 找到员工所属 zone，站在 zone 中央偏下
  const zone = ZONES.find(z => z.species === emp.species);
  if (!zone) return;
  const [x1, y1, x2, y2] = zone.rect;
  const cx = (x1 + x2) / 2;
  const cy = (y1 + y2) / 2 + (y2 - y1) * 0.15;  // 稍微偏下，不挡道具
  const p = gridToPx(cx, cy);

  const color = EMPLOYEE_COLOR_MAP[emp.species] || '#1A3B5C';
  const cn = SPECIES_CN[emp.species] || '?';
  const alive = emp.alive !== false;
  const r = Math.max(12, t.scale * 0.6);  // 头像半径

  empPositions[emp.name] = { x: p.x, y: p.y, r: r };

  if (!alive) {
    ctx.globalAlpha = 0.3;
    ctx.fillStyle = '#444';
    ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI*2); ctx.fill();
    ctx.globalAlpha = 1;
    return;
  }

  // 呼吸光晕
  const avg = ((emp.energy||0) + (emp.health||0) + (emp.mood_score||0)) / 3;
  const pulse = Math.sin(performance.now() / 800 + cx) * 0.15 + 0.85;
  const glow = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, r * 2.5 * pulse);
  glow.addColorStop(0, color + '88');
  glow.addColorStop(0.5, color + '33');
  glow.addColorStop(1, color + '00');
  ctx.fillStyle = glow;
  ctx.beginPath(); ctx.arc(p.x, p.y, r * 2.5 * pulse, 0, Math.PI*2); ctx.fill();

  // 头像底色（圆角方块）
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(p.x, p.y, r, 0, Math.PI*2);
  ctx.fill();

  // 中文字（物种首字）
  ctx.fillStyle = '#E8E4D8';
  ctx.font = 'bold ' + Math.floor(r * 1.2) + 'px Fraunces';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(cn, p.x, p.y + 1);

  // 描边
  ctx.strokeStyle = 'rgba(255,255,255,0.2)';
  ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI*2); ctx.stroke();

  // 名字（头像下方）
  if (t.scale > 8) {
    ctx.fillStyle = 'rgba(232,228,216,0.6)';
    ctx.font = '10px JetBrains Mono';
    const shortName = (emp.name || '').split('·')[1] || emp.name || '';
    ctx.fillText(shortName, p.x, p.y + r + 10);
  }
}

// ==================== 数据拉取 ====================
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    employees = data.employees || [];
    generation = data.evolution ? data.evolution.generation || 0 : 0;
    if (data.env) {
      gameHour = data.env.game_hour || 8;
      gameMinute = data.env.game_minute || 0;
      weather = data.env.weather || 'sunny';
    }
    updateTopBar();
    renderRoster();
    updateDashboard(data);
    renderMap();
  } catch (e) { console.error('fetchStatus', e); }
}

async function fetchEvents() {
  try {
    const res = await fetch('/api/events/list?limit=12');
    const data = await res.json();
    const list = document.getElementById('event-list');
    if (!data.events || data.events.length === 0) {
      list.innerHTML = '<div class="event-item">暂无事件</div>';
      return;
    }
    list.innerHTML = data.events.reverse().map(ev =>
      '<div class="event-item"><span class="ev-type">[' + ev.type + ']</span> ' + ev.text + '</div>'
    ).join('');
  } catch (e) {}
}

// ==================== 顶部栏 ====================
function updateTopBar() {
  const hh = String(Math.floor(gameHour)).padStart(2, '0');
  const mm = String(Math.floor(gameMinute)).padStart(2, '0');
  document.getElementById('info-time').textContent = hh + ':' + mm;
  const wMap = {sunny:'晴', rain:'雨', snow:'雪', fog:'雾', fireflies:'萤'};
  document.getElementById('info-weather').textContent = wMap[weather] || '晴';
  document.getElementById('info-gen').textContent = '第 ' + generation + ' 代';
  const alive = employees.filter(e => e.alive !== false).length;
  document.getElementById('info-pop').textContent = alive + ' 员工';
}

// ==================== 花名册 ====================
function renderRoster() {
  const list = document.getElementById('roster-list');
  list.innerHTML = '';
  for (const emp of employees) {
    const color = EMPLOYEE_COLOR_MAP[emp.species] || '#1A3B5C';
    const alive = emp.alive !== false;
    const item = document.createElement('div');
    item.className = 'roster-item' + (alive ? '' : ' dead') + (selectedName === emp.name ? ' active' : '');
    item.onclick = () => selectEmployee(emp.name);
    item.innerHTML = '<div class="roster-dot" style="background:' + color + ';color:' + color + ';"></div>' +
                     '<div class="roster-name">' + (emp.name || '?') + '</div>';
    list.appendChild(item);
  }
}

// ==================== 选中员工 ====================
function selectEmployee(name) {
  selectedName = name;
  const emp = employees.find(e => e.name === name);
  if (emp) openCard(emp);
  renderRoster();
  renderMap();
}

// ==================== Canvas 点击命中 ====================
canvas.addEventListener('click', function(e) {
  const rect = canvas.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  for (const [name, p] of Object.entries(empPositions)) {
    const dx = mx - p.x, dy = my - p.y;
    if (dx*dx + dy*dy < p.r * p.r * 1.5) {
      selectEmployee(name);
      return;
    }
  }
});

// ==================== 状态卡 ====================
function openCard(emp) {
  const overlay = document.getElementById('card-overlay');
  overlay.style.display = 'flex';
  const color = EMPLOYEE_COLOR_MAP[emp.species] || '#1A3B5C';
  const cn = SPECIES_CN[emp.species] || '?';
  const job = SPECIES_JOB[emp.species] || '员工';
  const avatar = document.getElementById('card-avatar');
  avatar.style.background = 'linear-gradient(135deg,' + color + ',#2a3a5c)';
  avatar.textContent = cn;
  document.getElementById('card-name').textContent = emp.name || '未知';
  document.getElementById('card-job').textContent = job + ' · ' + (emp.species || '');
  updateBar('energy', emp.energy || 0);
  updateBar('health', emp.health || 0);
  updateBar('mood', emp.mood_score || 0);
  // 心里话
  const thoughts = ['代码写得好累...想去外面吹吹风','今天的心情像阳光一样温暖','有点饿了','在思考生命的意义...','今天的工作完成了','想和朋友聊天','森林里真安静','感觉精力充沛！'];
  let thought = emp.current_behavior_label ? ('正在' + emp.current_behavior_label + '...') : thoughts[Math.floor(Math.random()*thoughts.length)];
  if (emp.alive === false) thought = '已离开森林，愿灵魂安息';
  document.getElementById('card-thought').textContent = thought;
  // 技能
  const sk = document.getElementById('card-skills');
  sk.innerHTML = (emp.skills && emp.skills.length) ? emp.skills.map(s=>'<span class="skill-tag">'+s+'</span>').join('') : '<span class="skill-tag">暂无技能</span>';
  document.getElementById('card-feedback').textContent = '';
}
function updateBar(name, val) {
  const pct = Math.min(100, Math.max(0, val));
  document.getElementById('bar-'+name).style.width = pct + '%';
  document.getElementById('val-'+name).textContent = Math.round(val);
}
function closeCard() {
  document.getElementById('card-overlay').style.display = 'none';
  selectedName = null;
  renderRoster();
  renderMap();
}
document.getElementById('card-overlay').addEventListener('click', function(e) {
  if (e.target === this) closeCard();
});

// ==================== 操作按钮 ====================
async function doAction(action) {
  if (!selectedName) return;
  const emp = employees.find(e => e.name === selectedName);
  if (!emp) return;
  const fb = document.getElementById('card-feedback');
  fb.textContent = '执行中...';
  try {
    let res;
    if (action === 'feed') {
      res = await fetch('/api/interact', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:emp.name, action:'feed', amount:20})});
    } else if (action === 'rest') {
      res = await fetch('/api/interact', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:emp.name, action:'wake'})});
    } else if (action === 'train') {
      res = await fetch('/api/agent_command', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({command:'训练', mode:'single', species:emp.species})});
    } else if (action === 'chat') {
      res = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({agent_name:emp.name, message:'你好呀'})});
    }
    const data = await res.json();
    if (data.ok !== false) {
      fb.textContent = '✓ 操作成功'; fb.style.color = '#D4A574';
      setTimeout(fetchStatus, 300);
    } else {
      fb.textContent = '✗ ' + (data.reason || data.msg || '失败'); fb.style.color = '#F87171';
    }
  } catch(e) { fb.textContent = '✗ 网络错误'; fb.style.color = '#F87171'; }
}

// ==================== 仪表盘 ====================
const dashCanvas = document.getElementById('dash-canvas');
const dashCtx = dashCanvas.getContext('2d');
function updateDashboard(data) {
  const alive = (data.employees || []).filter(e => e.alive !== false);
  const avgMood = alive.length ? alive.reduce((s,e)=>s+(e.mood_score||0),0)/alive.length : 0;
  const avgEng = alive.length ? alive.reduce((s,e)=>s+(e.energy||0),0)/alive.length : 0;
  ecoHistory.push({mood:avgMood, energy:avgEng, pop:alive.length});
  if (ecoHistory.length > 40) ecoHistory.shift();
  drawDashboard();
}
function drawDashboard() {
  const w = dashCanvas.offsetWidth, h = dashCanvas.offsetHeight;
  dashCanvas.width = w; dashCanvas.height = h;
  dashCtx.clearRect(0,0,w,h);
  if (ecoHistory.length < 2) {
    dashCtx.fillStyle = 'rgba(255,255,255,0.2)';
    dashCtx.font = '10px JetBrains Mono'; dashCtx.textAlign = 'center';
    dashCtx.fillText('数据采集中...', w/2, h/2);
    return;
  }
  const draw = (key, color) => {
    const vals = ecoHistory.map(d=>d[key]);
    const max = Math.max(...vals, 100);
    dashCtx.strokeStyle = color; dashCtx.lineWidth = 1.5;
    dashCtx.beginPath();
    vals.forEach((v,i) => {
      const x = (i/(vals.length-1))*w;
      const y = h - (v/max)*h*0.9 - 2;
      if (i===0) dashCtx.moveTo(x,y); else dashCtx.lineTo(x,y);
    });
    dashCtx.stroke();
  };
  draw('mood','#FBBF24'); draw('energy','#2DD4BF'); draw('pop','#D4A574');
  dashCtx.font = '9px JetBrains Mono'; dashCtx.textAlign = 'left';
  dashCtx.fillStyle = '#FBBF24'; dashCtx.fillText('心情', 4, 10);
  dashCtx.fillStyle = '#2DD4BF'; dashCtx.fillText('精力', 40, 10);
  dashCtx.fillStyle = '#D4A574'; dashCtx.fillText('种群', 76, 10);
}

// ==================== 动画循环 ====================
function animLoop() {
  renderMap();
  requestAnimationFrame(animLoop);
}

// ==================== 启动 ====================
fetchStatus();
fetchEvents();
setInterval(fetchStatus, 3000);
setInterval(fetchEvents, 5000);
animLoop();
"""


def status() -> dict:
    return {
        "mode": "topdown-2d",
        "version": "commit-57",
        "description": "2D 俯视角控制台（无 Y 轴排序，无穿模）",
    }
