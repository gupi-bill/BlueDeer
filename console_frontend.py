"""BlueDeer 极简控制台前端（commit 56 精简版）。

零基础读者可以这样理解：
- 之前的版本有背景动画、事件流、关系连线、仪表盘，太花哨。
- 这个版本只保留核心：顶部状态栏 + 底部员工 Dock + 点击弹出状态面板。
- 没有 Canvas 动画，没有背景渲染，纯静态 UI，性能拉满。
"""

from __future__ import annotations

import json

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
    "deer": "团队领导·编排者",
    "squirrel": "工程师·代码编写",
    "butterfly": "设计师·UI美化",
    "fox": "测试工程师·质量把关",
    "hedgehog": "安全工程师·漏洞防御",
    "beaver": "运维工程师·环境部署",
    "raven": "记忆管理员·资料归档",
    "hare": "数据分析师·性能统计",
    "badger": "网络工程师·接口维护",
    "lark": "监控工程师·告警观察",
    "kite": "调度工程师·任务排期",
}


def render_index() -> str:
    """渲染极简控制台首页 HTML。"""
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
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Manrope:wght@300;400;500&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
{CSS_STYLES}
</style>
</head>
<body>

<div id="app">

  <div id="top-bar">
    <div id="top-title">
      <span class="title-main">BlueDeer</span>
      <span class="title-sub">森林控制中心</span>
    </div>
    <div id="top-info">
      <span id="info-time">--:--</span>
      <span id="info-gen">第 0 代</span>
      <span id="info-pop">0 员工</span>
    </div>
  </div>

  <div id="dock">
    <div id="dock-inner"></div>
  </div>

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
          <div class="section-label">状态</div>
          <div id="energy-bars">
            <div class="ebar">
              <div class="ebar-label">精力</div>
              <div class="ebar-track"><div class="ebar-fill" id="bar-energy" style="background:#2DD4BF;"></div></div>
              <div class="ebar-val" id="val-energy">0</div>
            </div>
            <div class="ebar">
              <div class="ebar-label">健康</div>
              <div class="ebar-track"><div class="ebar-fill" id="bar-health" style="background:#F87171;"></div></div>
              <div class="ebar-val" id="val-health">0</div>
            </div>
            <div class="ebar">
              <div class="ebar-label">心情</div>
              <div class="ebar-track"><div class="ebar-fill" id="bar-mood" style="background:#FBBF24;"></div></div>
              <div class="ebar-val" id="val-mood">0</div>
            </div>
          </div>
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

</div>

<script>
const SPECIES_COLORS = {colors_json};
const SPECIES_CN = {cn_json};
const SPECIES_JOB = {job_json};

{JS_CODE}
</script>
</body>
</html>"""


CSS_STYLES = """
* { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #0a0f0c;
  --glass-bg: rgba(15, 23, 42, 0.75);
  --glass-border: rgba(255, 255, 255, 0.08);
  --text: #E8E4D8;
  --text-dim: #8A8275;
  --accent: #D4A574;
}

html, body {
  width: 100%; height: 100%; overflow: hidden;
  background: var(--bg);
  font-family: 'Manrope', sans-serif;
  color: var(--text);
}

#app {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
}

#top-bar {
  height: 48px; display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px;
  background: rgba(10, 15, 12, 0.9);
  border-bottom: 1px solid rgba(255,255,255,0.04);
  flex-shrink: 0;
}
#top-title { display: flex; align-items: baseline; gap: 8px; }
.title-main {
  font-family: 'Fraunces', serif; font-size: 18px; font-weight: 600;
  letter-spacing: 0.02em;
}
.title-sub {
  font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--text-dim);
}
#top-info {
  display: flex; gap: 12px; font-size: 11px; color: var(--text-dim);
  font-family: 'JetBrains Mono', monospace;
}

#dock {
  flex: 1; display: flex; align-items: center; justify-content: center;
  padding: 20px;
}
#dock-inner {
  display: flex; gap: 16px; align-items: flex-end; flex-wrap: wrap;
  justify-content: center;
}

.dock-card {
  display: flex; flex-direction: column; align-items: center;
  cursor: pointer; transition: transform 0.15s ease;
  padding: 8px;
}
.dock-card:hover { transform: translateY(-4px); }
.dock-card.dead { opacity: 0.25; filter: grayscale(1); }

.card-avatar {
  width: 44px; height: 44px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Fraunces', serif; font-size: 20px; font-weight: 600;
  color: #E8E4D8;
  border: 1px solid rgba(255,255,255,0.1);
}
.card-name {
  margin-top: 5px; font-size: 9px; color: var(--text-dim);
  max-width: 56px; text-align: center; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  font-family: 'JetBrains Mono', monospace;
}

#panel-overlay {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  z-index: 100; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.55);
}
#panel {
  position: relative; width: 400px; max-width: 90vw;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: 14px; padding: 24px;
}
#panel-close {
  position: absolute; top: 10px; right: 10px;
  width: 28px; height: 28px; border: none; border-radius: 50%;
  background: rgba(255,255,255,0.06); color: var(--text-dim);
  font-size: 16px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
#panel-close:hover { background: rgba(255,255,255,0.12); color: var(--text); }

#panel-header { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
#panel-avatar {
  width: 52px; height: 52px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Fraunces', serif; font-size: 24px; font-weight: 600;
  color: #E8E4D8; border: 1.5px solid rgba(255,255,255,0.1);
  flex-shrink: 0;
}
#panel-name { font-size: 16px; font-weight: 600; font-family: 'Fraunces', serif; }
#panel-job { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

#panel-body { margin-bottom: 16px; }
.panel-section { margin-bottom: 14px; }
.section-label {
  font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 6px; font-weight: 600;
}

#energy-bars { display: flex; gap: 12px; }
.ebar { display: flex; align-items: center; gap: 4px; }
.ebar-label { font-size: 9px; color: var(--text-dim); width: 20px; }
.ebar-track {
  width: 64px; height: 6px; background: rgba(255,255,255,0.06);
  border-radius: 3px; overflow: hidden;
}
.ebar-fill {
  height: 100%; border-radius: 3px;
  transition: width 0.4s ease;
}
.ebar-val { font-size: 9px; color: var(--text-dim); width: 24px; font-family: 'JetBrains Mono', monospace; }

#panel-actions { display: flex; gap: 8px; }
.act-btn {
  flex: 1; padding: 10px; border: none; border-radius: 8px;
  background: rgba(255,255,255,0.05); color: var(--text);
  font-size: 12px; font-weight: 500; cursor: pointer;
  transition: background 0.12s; font-family: 'Manrope', sans-serif;
}
.act-btn:hover { background: rgba(212,165,116,0.15); }

#panel-feedback {
  margin-top: 10px; font-size: 11px; color: var(--accent);
  text-align: center; min-height: 14px;
  font-family: 'JetBrains Mono', monospace;
}
"""


JS_CODE = r"""
let employees = [];

async function fetchStatus() {
  try {
    const res = await fetch('/game/api/status');
    const data = await res.json();
    // commit 56 修复：/api/status 实际只返回 population_status 计数，没有 employees 字段。
    // 这里从 by_species 派生员工卡片列表（每个物种 × 数量），保证 dock 区有内容。
    const bySpecies = (data.population_status && data.population_status.by_species) || {};
    const list = [];
    let idx = 0;
    for (const sp of Object.keys(bySpecies)) {
      const count = bySpecies[sp] || 0;
      const cn = SPECIES_CN[sp] || sp;
      for (let i = 0; i < count; i++) {
        idx += 1;
        list.push({
          species: sp,
          name: cn + '#' + idx,
          alive: data.population_status ? (data.population_status.alive > 0) : true
        });
      }
    }
    employees = list;
    renderDock();
    updateTopBar(data);
  } catch (e) {
    console.error('fetchStatus error', e);
  }
}

function updateTopBar(data) {
  const alive = employees.filter(e => e.alive !== false).length;
  const season = data.season || '--';
  const weather = data.weather_label || '';
  document.getElementById('info-time').textContent = season + ' · ' + weather;
  document.getElementById('info-gen').textContent = '人口 ' + (data.population_count || 0);
  document.getElementById('info-pop').textContent = alive + ' / ' + (data.population_status ? data.population_status.total : 0) + ' 员工';
}

function renderDock() {
  const inner = document.getElementById('dock-inner');
  inner.innerHTML = '';
  for (const emp of employees) {
    const color = SPECIES_COLORS[emp.species] || '#1A3B5C';
    const cn = SPECIES_CN[emp.species] || '?';
    const alive = emp.alive !== false;

    const card = document.createElement('div');
    card.className = 'dock-card' + (alive ? '' : ' dead');
    card.onclick = () => openPanel(emp);

    const avatar = document.createElement('div');
    avatar.className = 'card-avatar';
    avatar.style.background = color;
    avatar.textContent = cn;
    const img = document.createElement('img');
    img.src = '/static/assets/characters/' + emp.species + '.png';
    img.alt = cn;
    img.style.width = '100%';
    img.style.height = '100%';
    img.style.objectFit = 'cover';
    img.style.borderRadius = 'inherit';
    img.style.imageRendering = 'pixelated';
    img.onerror = () => { img.remove(); };
    avatar.appendChild(img);
    card.appendChild(avatar);

    const name = document.createElement('div');
    name.className = 'card-name';
    const shortName = (emp.name || '').split('·')[1] || emp.name || '';
    name.textContent = shortName;
    card.appendChild(name);

    inner.appendChild(card);
  }
}

function openPanel(emp) {
  const color = SPECIES_COLORS[emp.species] || '#1A3B5C';
  const cn = SPECIES_CN[emp.species] || '?';
  const job = SPECIES_JOB[emp.species] || '员工';

  const pav = document.getElementById('panel-avatar');
  pav.style.background = color;
  pav.textContent = cn;
  pav.innerHTML = '';
  const pimg = document.createElement('img');
  pimg.src = '/static/assets/characters/' + emp.species + '.png';
  pimg.alt = cn;
  pimg.style.width = '100%';
  pimg.style.height = '100%';
  pimg.style.objectFit = 'cover';
  pimg.style.borderRadius = 'inherit';
  pimg.style.imageRendering = 'pixelated';
  pimg.onerror = () => { pimg.remove(); };
  pav.appendChild(pimg);
  document.getElementById('panel-avatar').textContent = cn;
  document.getElementById('panel-name').textContent = emp.name || '未知';
  document.getElementById('panel-job').textContent = job;

  updateBar('energy', emp.energy || 0, 100);
  updateBar('health', emp.health || 0, 100);
  updateBar('mood', emp.mood_score || 0, 100);

  document.getElementById('panel-feedback').textContent = '';
  document.getElementById('panel-overlay').style.display = 'flex';
}

function updateBar(name, val, max) {
  const pct = Math.min(100, Math.max(0, (val / max) * 100));
  document.getElementById('bar-' + name).style.width = pct + '%';
  document.getElementById('val-' + name).textContent = Math.round(val);
}

function closePanel() {
  document.getElementById('panel-overlay').style.display = 'none';
}

document.getElementById('panel-overlay').addEventListener('click', function(e) {
  if (e.target === this) closePanel();
});

async function doAction(action) {
  const overlay = document.getElementById('panel-overlay');
  const name = document.getElementById('panel-name').textContent;
  const feedback = document.getElementById('panel-feedback');
  feedback.textContent = '执行中...';

  try {
    let res;
    if (action === 'feed') {
      res = await fetch('/game/api/interact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, action: 'feed', amount: 20 }),
      });
    } else if (action === 'rest') {
      res = await fetch('/game/api/interact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, action: 'wake' }),
      });
    } else if (action === 'train') {
      res = await fetch('/api/agent_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: 'single', target: name, task_type: 'training' }),
      });
    } else if (action === 'chat') {
      res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, message: '你好呀' }),
      });
    }
    const data = await res.json();
    if (data.ok !== false) {
      feedback.textContent = '✓ 操作成功';
      feedback.style.color = '#D4A574';
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

fetchStatus();
setInterval(fetchStatus, 3000);
"""


def status() -> dict:
    """前端状态报告（供 server 调用）。"""
    return {
        "mode": "console",
        "version": "commit-56",
        "description": "极简森林控制中心（精简版）",
    }
