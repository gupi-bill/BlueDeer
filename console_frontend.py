"""BlueDeer 极简森林桌面控制中心（commit 55）。

零基础读者可以这样理解：
- 之前的前端是 2.5D 地图，角色走来走去，但看起来很乱。
- 这个文件是一个全新的"控制台"前端，放弃地图，改成桌面卡片式。
- 整个页面只有：静态森林背景 + 底部员工 Dock 栏 + 点击弹出的状态面板。
- 极简、高冷、科技感，像 macOS 的 Dock + 毛玻璃面板。

入口函数 render_index() 返回完整 HTML 字符串，由 game_server.py 调用。
"""

from __future__ import annotations

# 11 物种深蓝色表（与 game_frontend.py EMPLOYEE_COLOR_MAP 同源）
SPECIES_COLORS = {
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

# 物种中文名（用于头像首字）
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

# 物种职位（用于面板标题）
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


def render_index() -> str:
    """渲染极简控制台首页 HTML。"""
    import json

    colors_json = json.dumps(SPECIES_COLORS)
    cn_json = json.dumps(SPECIES_CN)
    job_json = json.dumps(SPECIES_JOB)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BlueDeer · 森林控制中心</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Manrope:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
{CSS_STYLES}
</style>
</head>
<body>

<!-- 静态森林背景 Canvas -->
<canvas id="bg-canvas"></canvas>

<!-- 暗角遮罩 -->
<div id="vignette"></div>

<!-- 顶部状态栏 -->
<div id="top-bar">
  <div id="top-title">
    <span class="title-main">BlueDeer</span>
    <span class="title-sub">森林控制中心</span>
  </div>
  <div id="top-info">
    <span id="info-time">--:--</span>
    <span id="info-weather">·</span>
    <span id="info-gen">第 0 代</span>
    <span id="info-pop">11 员工</span>
  </div>
</div>

<!-- 事件流（右上角） -->
<div id="event-stream">
  <div class="event-header">事件流</div>
  <div id="event-list"></div>
</div>

<!-- 关系连线 Canvas（覆盖在 Dock 上方） -->
<canvas id="relation-canvas"></canvas>

<!-- 底部 Dock 栏 -->
<div id="dock">
  <div id="dock-inner"></div>
</div>

<!-- 系统仪表盘（右下角） -->
<div id="dashboard">
  <div class="dash-title">团队趋势</div>
  <canvas id="dash-canvas"></canvas>
</div>

<!-- 员工状态面板（点击头像弹出） -->
<div id="panel-overlay" style="display:none;">
  <div id="panel">
    <button id="panel-close" onclick="closePanel()">×</button>
    <div id="panel-header">
      <div id="panel-avatar"></div>
      <div id="panel-info">
        <div id="panel-name"></div>
        <div id="panel-job"></div>
      </div>
    </div>
    <div id="panel-body">
      <div class="panel-section">
        <div class="section-label">核心状态</div>
        <div id="energy-bars">
          <div class="ebar"><div class="ebar-label">精力</div><div class="ebar-track"><div class="ebar-fill" id="bar-energy" style="background:#2DD4BF;"></div></div><div class="ebar-val" id="val-energy">0</div></div>
          <div class="ebar"><div class="ebar-label">健康</div><div class="ebar-track"><div class="ebar-fill" id="bar-health" style="background:#F87171;"></div></div><div class="ebar-val" id="val-health">0</div></div>
          <div class="ebar"><div class="ebar-label">心情</div><div class="ebar-track"><div class="ebar-fill" id="bar-mood" style="background:#FBBF24;"></div></div><div class="ebar-val" id="val-mood">0</div></div>
        </div>
      </div>
      <div class="panel-section">
        <div class="section-label">当前心里话</div>
        <div id="panel-thought">...</div>
      </div>
      <div class="panel-section">
        <div class="section-label">技能</div>
        <div id="panel-skills"></div>
      </div>
    </div>
    <div id="panel-actions">
      <button class="act-btn" onclick="doAction('feed')">投喂</button>
      <button class="act-btn" onclick="doAction('train')">训练</button>
      <button class="act-btn" onclick="doAction('rest')">休息</button>
      <button class="act-btn" onclick="doAction('chat')">交谈</button>
    </div>
    <div id="panel-feedback"></div>
  </div>
</div>

<script>
const SPECIES_COLORS = {colors_json};
const SPECIES_CN = {cn_json};
const SPECIES_JOB = {job_json};

{JS_CODE}
</script>
</body>
</html>"""


# ======================================================================
# CSS 样式
# ======================================================================

CSS_STYLES = """
* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg-deep: #0a0f0c;
  --bg-mid: #0d1410;
  --glass-bg: rgba(15, 23, 42, 0.72);
  --glass-border: rgba(255, 255, 255, 0.08);
  --glass-hover: rgba(255, 255, 255, 0.12);
  --text: #E8E4D8;
  --text-dim: #8A8275;
  --accent: #D4A574;
  --accent-dim: rgba(212, 165, 116, 0.3);
}

html, body {
  width: 100%; height: 100%; overflow: hidden;
  background: var(--bg-deep);
  font-family: 'Manrope', sans-serif;
  color: var(--text);
  user-select: none;
}

/* === 静态森林背景 === */
#bg-canvas {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  z-index: 0;
}

/* === 暗角 === */
#vignette {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  z-index: 1; pointer-events: none;
  background: radial-gradient(ellipse 80% 70% at 50% 45%, transparent 30%, rgba(0,0,0,0.6) 100%);
}

/* === 顶部状态栏 === */
#top-bar {
  position: fixed; top: 0; left: 0; right: 0; height: 52px;
  z-index: 10; display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px;
  background: linear-gradient(180deg, rgba(10,15,12,0.85) 0%, transparent 100%);
}
#top-title { display: flex; align-items: baseline; gap: 10px; }
.title-main {
  font-family: 'Fraunces', serif; font-size: 20px; font-weight: 600;
  letter-spacing: 0.02em; color: var(--text);
}
.title-sub {
  font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--text-dim);
}
#top-info {
  display: flex; gap: 16px; font-size: 12px; color: var(--text-dim);
  font-family: 'JetBrains Mono', monospace;
}
#top-info span { letter-spacing: 0.05em; }

/* === 事件流 === */
#event-stream {
  position: fixed; top: 60px; right: 20px; width: 260px;
  max-height: 300px; z-index: 10;
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: 12px; padding: 12px 14px;
  overflow: hidden;
}
.event-header {
  font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 8px; font-weight: 600;
}
#event-list {
  max-height: 240px; overflow-y: auto;
  font-size: 11px; line-height: 1.6;
}
#event-list::-webkit-scrollbar { width: 3px; }
#event-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
.event-item {
  padding: 3px 0; color: var(--text-dim);
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.event-item:last-child { border-bottom: none; }
.event-item .ev-type { color: var(--accent); font-size: 10px; }

/* === 关系连线 === */
#relation-canvas {
  position: fixed; bottom: 0; left: 0; width: 100%; height: 140px;
  z-index: 8; pointer-events: none;
}

/* === 底部 Dock 栏 === */
#dock {
  position: fixed; bottom: 0; left: 0; right: 0; height: 120px;
  z-index: 9; display: flex; align-items: center; justify-content: center;
  padding: 0 20px;
  background: linear-gradient(0deg, rgba(10,15,12,0.9) 0%, transparent 100%);
}
#dock-inner {
  display: flex; gap: 14px; align-items: flex-end;
  padding: 10px 20px;
  background: rgba(15, 23, 42, 0.5);
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: 18px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}

/* === 员工卡片 === */
.dock-card {
  position: relative; display: flex; flex-direction: column; align-items: center;
  cursor: pointer; transition: transform 0.2s ease;
}
.dock-card:hover { transform: translateY(-6px) scale(1.08); }
.dock-card.dead { opacity: 0.3; filter: grayscale(1); }

.card-glow {
  position: absolute; bottom: 28px; left: 50%; transform: translateX(-50%);
  width: 52px; height: 52px; border-radius: 50%;
  opacity: 0.6; animation: breathe 3s ease-in-out infinite;
  pointer-events: none;
}
@keyframes breathe {
  0%, 100% { transform: translateX(-50%) scale(1); opacity: 0.4; }
  50% { transform: translateX(-50%) scale(1.25); opacity: 0.7; }
}
.card-glow.danger { animation: dangerPulse 0.8s ease-in-out infinite; }
@keyframes dangerPulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.9; }
}

.card-avatar {
  width: 48px; height: 48px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Fraunces', serif; font-size: 22px; font-weight: 600;
  color: #E8E4D8; position: relative; z-index: 1;
  border: 1.5px solid rgba(255,255,255,0.15);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

.card-name {
  margin-top: 6px; font-size: 10px; color: var(--text-dim);
  max-width: 60px; text-align: center; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  font-family: 'JetBrains Mono', monospace;
}

/* === 系统仪表盘 === */
#dashboard {
  position: fixed; bottom: 130px; right: 20px;
  width: 220px; height: 120px; z-index: 10;
  background: var(--glass-bg);
  backdrop-filter: blur(16px) saturate(140%);
  -webkit-backdrop-filter: blur(16px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: 12px; padding: 10px 12px;
}
.dash-title {
  font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 4px; font-weight: 600;
}
#dash-canvas { width: 100%; height: 85px; }

/* === 状态面板 === */
#panel-overlay {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  z-index: 100; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
#panel {
  position: relative; width: 440px; max-width: 90vw;
  background: rgba(15, 23, 42, 0.82);
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
  border: 1px solid var(--glass-border);
  border-radius: 20px; padding: 28px;
  box-shadow: 0 16px 64px rgba(0,0,0,0.5), 0 0 0 1px rgba(212,165,116,0.06);
  animation: panelIn 0.3s cubic-bezier(0.2, 0.9, 0.3, 1);
}
@keyframes panelIn {
  from { transform: scale(0.92) translateY(20px); opacity: 0; }
  to { transform: scale(1) translateY(0); opacity: 1; }
}
#panel-close {
  position: absolute; top: 14px; right: 14px;
  width: 30px; height: 30px; border: none; border-radius: 50%;
  background: rgba(255,255,255,0.08); color: var(--text-dim);
  font-size: 18px; cursor: pointer; transition: all 0.15s;
  display: flex; align-items: center; justify-content: center;
}
#panel-close:hover { background: rgba(255,255,255,0.18); color: var(--text); }

#panel-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
#panel-avatar {
  width: 64px; height: 64px; border-radius: 16px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Fraunces', serif; font-size: 30px; font-weight: 600;
  color: #E8E4D8; border: 2px solid rgba(255,255,255,0.12);
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  flex-shrink: 0;
}
#panel-name { font-size: 18px; font-weight: 600; font-family: 'Fraunces', serif; }
#panel-job { font-size: 12px; color: var(--text-dim); margin-top: 2px; letter-spacing: 0.08em; }

#panel-body { margin-bottom: 20px; }
.panel-section { margin-bottom: 18px; }
.section-label {
  font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 8px; font-weight: 600;
}

/* 像素能量条 */
#energy-bars { display: flex; gap: 16px; }
.ebar { display: flex; align-items: center; gap: 6px; }
.ebar-label { font-size: 10px; color: var(--text-dim); width: 24px; }
.ebar-track {
  width: 80px; height: 8px; background: rgba(255,255,255,0.06);
  border-radius: 4px; overflow: hidden;
}
.ebar-fill {
  height: 100%; border-radius: 4px;
  transition: width 0.6s cubic-bezier(0.2, 0.9, 0.3, 1);
  box-shadow: 0 0 8px currentColor;
}
.ebar-val { font-size: 10px; color: var(--text-dim); width: 28px; font-family: 'JetBrains Mono', monospace; }

#panel-thought {
  font-size: 13px; line-height: 1.6; color: var(--text);
  background: rgba(255,255,255,0.04); border-radius: 10px;
  padding: 12px 14px; font-style: italic;
  border-left: 2px solid var(--accent-dim);
}
#panel-skills { display: flex; flex-wrap: wrap; gap: 6px; }
.skill-tag {
  font-size: 10px; padding: 3px 8px; border-radius: 4px;
  background: rgba(255,255,255,0.06); color: var(--text-dim);
  font-family: 'JetBrains Mono', monospace;
}

#panel-actions { display: flex; gap: 10px; }
.act-btn {
  flex: 1; padding: 12px; border: none; border-radius: 10px;
  background: rgba(255,255,255,0.06); color: var(--text);
  font-size: 13px; font-weight: 500; cursor: pointer;
  transition: all 0.15s; font-family: 'Manrope', sans-serif;
}
.act-btn:hover { background: rgba(212,165,116,0.2); border: 1px solid var(--accent-dim); }
.act-btn:active { transform: scale(0.95); }

#panel-feedback {
  margin-top: 12px; font-size: 12px; color: var(--accent);
  text-align: center; min-height: 16px;
  font-family: 'JetBrains Mono', monospace;
}
"""


# ======================================================================
# JavaScript 代码
# ======================================================================

JS_CODE = r"""
// ==================== 全局状态 ====================
let employees = [];
let relationships = [];
let ecoHistory = [];  // 仪表盘历史数据
let selectedEmp = null;
let gameHour = 8, gameMinute = 0, weather = 'sunny', generation = 0;

// ==================== 背景森林 Canvas ====================
const bgCanvas = document.getElementById('bg-canvas');
const bgCtx = bgCanvas.getContext('2d');
let snowflakes = [];

function resizeBg() {
  bgCanvas.width = window.innerWidth;
  bgCanvas.height = window.innerHeight;
}
resizeBg();
window.addEventListener('resize', resizeBg);

// 生成飘雪/落叶粒子
function initParticles() {
  snowflakes = [];
  for (let i = 0; i < 40; i++) {
    snowflakes.push({
      x: Math.random() * bgCanvas.width,
      y: Math.random() * bgCanvas.height,
      r: 0.8 + Math.random() * 1.5,
      vy: 0.3 + Math.random() * 0.6,
      vx: (Math.random() - 0.5) * 0.3,
      alpha: 0.3 + Math.random() * 0.4,
    });
  }
}
initParticles();

function drawBackground() {
  const w = bgCanvas.width, h = bgCanvas.height;

  // 深色天空渐变
  const sky = bgCtx.createLinearGradient(0, 0, 0, h);
  sky.addColorStop(0, '#0a0f14');
  sky.addColorStop(0.5, '#0d1410');
  sky.addColorStop(1, '#080c0a');
  bgCtx.fillStyle = sky;
  bgCtx.fillRect(0, 0, w, h);

  // 远山剪影（淡蓝色）
  bgCtx.fillStyle = 'rgba(30, 45, 60, 0.4)';
  bgCtx.beginPath();
  bgCtx.moveTo(0, h * 0.55);
  for (let x = 0; x <= w; x += 20) {
    const y = h * 0.55 + Math.sin(x * 0.008) * 25 + Math.sin(x * 0.02) * 10;
    bgCtx.lineTo(x, y);
  }
  bgCtx.lineTo(w, h); bgCtx.lineTo(0, h); bgCtx.closePath();
  bgCtx.fill();

  // 近景松树剪影（深色三角）
  bgCtx.fillStyle = 'rgba(8, 18, 12, 0.85)';
  for (let i = 0; i < 25; i++) {
    const tx = (i / 25) * w + Math.sin(i * 7.3) * 30;
    const ty = h * 0.65 + Math.sin(i * 3.1) * 15;
    const tw = 30 + (i % 4) * 8;
    const th = 80 + (i % 5) * 20;
    // 松树 = 3 层三角
    for (let layer = 0; layer < 3; layer++) {
      const ly = ty + layer * th * 0.3;
      const lw = tw * (1 - layer * 0.2);
      bgCtx.beginPath();
      bgCtx.moveTo(tx, ly);
      bgCtx.lineTo(tx + lw, ly + th * 0.4);
      bgCtx.lineTo(tx - lw, ly + th * 0.4);
      bgCtx.closePath();
      bgCtx.fill();
    }
  }

  // 飘雪粒子
  const t = performance.now() / 1000;
  for (const p of snowflakes) {
    p.y += p.vy;
    p.x += p.vx + Math.sin(t + p.x * 0.01) * 0.2;
    if (p.y > h) { p.y = -5; p.x = Math.random() * w; }
    if (p.x < 0) p.x = w; if (p.x > w) p.x = 0;
    bgCtx.fillStyle = 'rgba(255, 250, 245, ' + p.alpha + ')';
    bgCtx.beginPath();
    bgCtx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    bgCtx.fill();
  }

  _tickFPS();
  requestAnimationFrame(drawBackground);
}
drawBackground();

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
    renderDock();
    updateDashboard(data);
  } catch (e) {
    console.error('fetchStatus error', e);
  }
}

async function fetchEvents() {
  try {
    const res = await fetch('/api/events/list?limit=15');
    const data = await res.json();
    const list = document.getElementById('event-list');
    if (!data.events || data.events.length === 0) {
      list.innerHTML = '<div class="event-item">暂无事件</div>';
      return;
    }
    list.innerHTML = data.events.reverse().map(ev =>
      '<div class="event-item"><span class="ev-type">[' + ev.type + ']</span> ' + ev.text + '</div>'
    ).join('');
  } catch (e) { /* 静默 */ }
}

async function fetchRelationships() {
  try {
    const res = await fetch('/api/relationships');
    const data = await res.json();
    relationships = data.network || [];
    drawRelations();
  } catch (e) { /* 静默 */ }
}

// ==================== 顶部状态栏 ====================
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

// ==================== Dock 栏渲染 ====================
function renderDock() {
  const inner = document.getElementById('dock-inner');
  inner.innerHTML = '';
  for (const emp of employees) {
    const color = SPECIES_COLORS[emp.species] || '#1A3B5C';
    const cn = SPECIES_CN[emp.species] || '?';
    const alive = emp.alive !== false;
    const energy = emp.energy || 0;
    const health = emp.health || 0;
    const mood = emp.mood_score || 0;
    const avg = (energy + health + mood) / 3;
    const isDanger = alive && (health < 25 || energy < 15);

    const card = document.createElement('div');
    card.className = 'dock-card' + (alive ? '' : ' dead');
    card.onclick = () => openPanel(emp);

    // 呼吸光晕（颜色 = 物种色，大小随状态变化）
    const glow = document.createElement('div');
    glow.className = 'card-glow' + (isDanger ? ' danger' : '');
    const glowSize = alive ? (0.4 + avg / 200) : 0.2;
    glow.style.background = 'radial-gradient(circle, ' + color + ' 0%, transparent 70%)';
    glow.style.opacity = glowSize;
    glow.style.animationDuration = isDanger ? '0.8s' : (3 + (100 - avg) / 50) + 's';
    card.appendChild(glow);

    // 头像（方块圆角 + 物种首字）
    const avatar = document.createElement('div');
    avatar.className = 'card-avatar';
    avatar.style.background = 'linear-gradient(135deg, ' + color + ' 0%, ' + shadeColor(color, 30) + ' 100%)';
    avatar.textContent = cn;
    card.appendChild(avatar);

    // 名字
    const name = document.createElement('div');
    name.className = 'card-name';
    const shortName = (emp.name || '').split('·')[1] || emp.name || '';
    name.textContent = shortName;
    card.appendChild(name);

    inner.appendChild(card);
  }
  drawRelations();
}

// 颜色加深/变亮
function shadeColor(hex, percent) {
  const num = parseInt(hex.replace('#', ''), 16);
  const r = Math.min(255, (num >> 16) + percent);
  const g = Math.min(255, ((num >> 8) & 0xff) + percent);
  const b = Math.min(255, (num & 0xff) + percent);
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
}

// ==================== 关系连线 ====================
const relCanvas = document.getElementById('relation-canvas');
const relCtx = relCanvas.getContext('2d');

function drawRelations() {
  relCanvas.width = window.innerWidth;
  relCanvas.height = 140;
  relCtx.clearRect(0, 0, relCanvas.width, relCanvas.height);
  if (!relationships || relationships.length === 0) return;

  // 获取每个卡片的屏幕坐标
  const cards = document.querySelectorAll('.dock-card');
  if (cards.length === 0) return;
  const positions = [];
  cards.forEach(card => {
    const rect = card.getBoundingClientRect();
    positions.push({ x: rect.left + rect.width / 2, y: rect.top + 24 });
  });

  // 画关系连线
  for (const rel of relationships) {
    const aIdx = employees.findIndex(e => e.name === rel.a || e._name === rel.a);
    const bIdx = employees.findIndex(e => e.name === rel.b || e._name === rel.b);
    if (aIdx < 0 || bIdx < 0) continue;
    if (!positions[aIdx] || !positions[bIdx]) continue;

    const pa = positions[aIdx], pb = positions[bIdx];
    const affection = rel.affinity || rel.affection || 50;
    const isClose = affection > 60;
    const isBroken = affection < 20;

    relCtx.strokeStyle = isBroken ? 'rgba(248, 113, 113, 0.5)' : 'rgba(212, 165, 116, ' + (affection / 150) + ')';
    relCtx.lineWidth = isClose ? 1.5 : 0.8;
    if (isBroken) {
      relCtx.setLineDash([4, 4]);
    } else {
      relCtx.setLineDash([]);
    }
    relCtx.beginPath();
    relCtx.moveTo(pa.x, pa.y);
    // 弧线
    const midX = (pa.x + pb.x) / 2;
    const midY = Math.min(pa.y, pb.y) - 30 - Math.abs(pa.x - pb.x) * 0.15;
    relCtx.quadraticCurveTo(midX, midY, pb.x, pb.y);
    relCtx.stroke();
    relCtx.setLineDash([]);
  }
}

// ==================== 状态面板 ====================
function openPanel(emp) {
  selectedEmp = emp;
  const overlay = document.getElementById('panel-overlay');
  overlay.style.display = 'flex';

  const color = SPECIES_COLORS[emp.species] || '#1A3B5C';
  const cn = SPECIES_CN[emp.species] || '?';
  const job = SPECIES_JOB[emp.species] || '员工';

  // 头像
  const avatar = document.getElementById('panel-avatar');
  avatar.style.background = 'linear-gradient(135deg, ' + color + ' 0%, ' + shadeColor(color, 40) + ' 100%)';
  avatar.textContent = cn;

  // 名字 + 职位
  document.getElementById('panel-name').textContent = emp.name || '未知';
  document.getElementById('panel-job').textContent = job + ' · ' + (emp.species || '');

  // 能量条
  updateBar('energy', emp.energy || 0, 100);
  updateBar('health', emp.health || 0, 100);
  updateBar('mood', emp.mood_score || 0, 100);

  // 心里话
  const thoughts = [
    '代码写得好累...想去外面吹吹风',
    '今天的心情像阳光一样温暖',
    '有点饿了，想吃点浆果',
    '在思考生命的意义...',
    '今天的工作完成了，很满足',
    '想和朋友们聊聊天',
    '森林里真安静啊',
    '感觉精力充沛，准备干活！',
  ];
  const thoughtIdx = Math.floor(Math.random() * thoughts.length);
  let thought = thoughts[thoughtIdx];
  if (emp.current_behavior_label) {
    thought = '正在' + emp.current_behavior_label + '...';
  }
  if (emp.alive === false) {
    thought = '已离开森林，愿灵魂安息';
  }
  document.getElementById('panel-thought').textContent = thought;

  // 技能
  const skillsDiv = document.getElementById('panel-skills');
  if (emp.skills && emp.skills.length > 0) {
    skillsDiv.innerHTML = emp.skills.map(s => '<span class="skill-tag">' + s + '</span>').join('');
  } else {
    skillsDiv.innerHTML = '<span class="skill-tag">暂无技能</span>';
  }

  // 清空反馈
  document.getElementById('panel-feedback').textContent = '';
}

function updateBar(name, val, max) {
  const pct = Math.min(100, Math.max(0, (val / max) * 100));
  document.getElementById('bar-' + name).style.width = pct + '%';
  document.getElementById('val-' + name).textContent = Math.round(val);
}

function closePanel() {
  document.getElementById('panel-overlay').style.display = 'none';
  selectedEmp = null;
}

// 点击遮罩关闭
document.getElementById('panel-overlay').addEventListener('click', function(e) {
  if (e.target === this) closePanel();
});

// ==================== 操作按钮 ====================
async function doAction(action) {
  if (!selectedEmp) return;
  const emp = selectedEmp;
  const feedback = document.getElementById('panel-feedback');
  feedback.textContent = '执行中...';

  try {
    let res;
    if (action === 'feed') {
      res = await fetch('/api/interact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: emp.name, action: 'feed', amount: 20 }),
      });
    } else if (action === 'rest') {
      res = await fetch('/api/interact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: emp.name, action: 'wake' }),
      });
    } else if (action === 'train') {
      res = await fetch('/api/agent_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'single', target: emp.name, task_type: 'training' }),
      });
    } else if (action === 'chat') {
      res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: emp.name, message: '你好呀' }),
      });
    }
    const data = await res.json();
    if (data.ok !== false) {
      feedback.textContent = '✓ 操作成功';
      feedback.style.color = '#D4A574';
      // 立即刷新数据
      setTimeout(fetchStatus, 300);
    } else {
      feedback.textContent = '✗ ' + (data.reason || data.msg || '操作失败');
      feedback.style.color = '#F87171';
    }
  } catch (e) {
    feedback.textContent = '✗ 网络错误';
    feedback.style.color = '#F87171';
  }
}

// ==================== 系统仪表盘 ====================
const dashCanvas = document.getElementById('dash-canvas');
const dashCtx = dashCanvas.getContext('2d');

function updateDashboard(data) {
  // 记录历史
  const aliveEmps = (data.employees || []).filter(e => e.alive !== false);
  const avgMood = aliveEmps.length > 0
    ? aliveEmps.reduce((s, e) => s + (e.mood_score || 0), 0) / aliveEmps.length
    : 0;
  const avgEnergy = aliveEmps.length > 0
    ? aliveEmps.reduce((s, e) => s + (e.energy || 0), 0) / aliveEmps.length
    : 0;
  const pop = aliveEmps.length;

  ecoHistory.push({ mood: avgMood, energy: avgEnergy, pop: pop });
  if (ecoHistory.length > 40) ecoHistory.shift();

  drawDashboard();
}

function drawDashboard() {
  const w = dashCanvas.offsetWidth;
  const h = dashCanvas.offsetHeight;
  dashCanvas.width = w;
  dashCanvas.height = h;
  dashCtx.clearRect(0, 0, w, h);

  if (ecoHistory.length < 2) {
    dashCtx.fillStyle = 'rgba(255,255,255,0.2)';
    dashCtx.font = '10px JetBrains Mono';
    dashCtx.textAlign = 'center';
    dashCtx.fillText('数据采集中...', w / 2, h / 2);
    return;
  }

  const draw = (key, color) => {
    const vals = ecoHistory.map(d => d[key]);
    const max = Math.max(...vals, 100);
    dashCtx.strokeStyle = color;
    dashCtx.lineWidth = 1.5;
    dashCtx.beginPath();
    vals.forEach((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - (v / max) * h * 0.9 - 2;
      if (i === 0) dashCtx.moveTo(x, y);
      else dashCtx.lineTo(x, y);
    });
    dashCtx.stroke();
  };

  draw('mood', '#FBBF24');    // 心情=黄
  draw('energy', '#2DD4BF');  // 精力=青
  draw('pop', '#D4A574');     // 种群=琥珀

  // 图例
  dashCtx.font = '9px JetBrains Mono';
  dashCtx.textAlign = 'left';
  dashCtx.fillStyle = '#FBBF24'; dashCtx.fillText('心情', 4, 10);
  dashCtx.fillStyle = '#2DD4BF'; dashCtx.fillText('精力', 40, 10);
  dashCtx.fillStyle = '#D4A574'; dashCtx.fillText('种群', 76, 10);
}

// ==================== FPS 计数器 ====================
let fps = 60;
let _fpsFrames = 0;
let _fpsLast = performance.now();
function _tickFPS() {
  _fpsFrames++;
  const now = performance.now();
  if (now - _fpsLast >= 1000) {
    fps = Math.round(_fpsFrames * 1000 / (now - _fpsLast));
    _fpsFrames = 0;
    _fpsLast = now;
  }
}

// ==================== 异步渲染 ====================
async function renderFrame() {
  _tickFPS();
  drawBackground();
  drawRelations();
}

// ==================== 懒加载 ====================
function lazyLoadChunk(region) {
  if (!region) return;
  const emp = employees.find(e => e.species === region || e.name === region);
  if (emp) {
    const dock = document.getElementById('dock-inner');
    if (!dock.querySelector(`[data-emp="${emp.name}"]`)) {
      fetchStatus();
    }
  }
}

// ==================== 启动 ====================
fetchStatus();
fetchEvents();
fetchRelationships();

// 每 3 秒刷新数据
setInterval(fetchStatus, 3000);
setInterval(fetchEvents, 5000);
setInterval(fetchRelationships, 10000);

// 窗口缩放时重绘
window.addEventListener('resize', () => {
  drawRelations();
  drawDashboard();
});

"""


def status() -> dict:
    """前端状态报告（供 server 调用）。"""
    return {
        "mode": "console",
        "version": "commit-55",
        "description": "极简森林桌面控制中心",
    }
