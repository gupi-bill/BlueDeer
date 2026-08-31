"""BlueDeer 2D 俯视角前端（commit 58 精简版）。

零基础读者可以这样理解：
- 之前的版本有 Canvas 地图、Tile 缓存、动画循环、花名册、仪表盘、事件流，太复杂。
- 这个版本只保留核心：顶部状态栏 + 员工列表 + 点击弹出状态面板。
- 没有 Canvas 动画，没有地图渲染，纯静态 UI，性能拉满。
"""

from __future__ import annotations

import json

from game_frontend import ZONES

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

zones_json = json.dumps(
    [{**z, "rect": list(z["rect"])} for z in ZONES], ensure_ascii=False
)


def render_index() -> str:
    """渲染精简 2D 俯视角首页 HTML。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BlueDeer · 2D 俯视控制台</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@500;600&family=Manrope:wght@400;500&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet">
<style>
{CSS_STYLES}
</style>
</head>
<body>

<div id="app">

  <div id="top-bar">
    <div class="top-title"><span class="t-main">BlueDeer</span><span class="t-sub">2D 俯视控制台</span></div>
    <div id="top-info">
      <span id="info-time">--:--</span>
      <span id="info-gen">第 0 代</span>
      <span id="info-pop">0 员工</span>
    </div>
  </div>

  <div id="roster">
    <div class="roster-title">花名册</div>
    <div id="roster-list"></div>
  </div>

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
        <div class="bar-row"><span class="bar-label">精力</span><div class="bar-track"><div class="bar-fill" id="bar-energy" style="background:#2DD4BF;"></div></div><span class="bar-val" id="val-energy">0</span></div>
        <div class="bar-row"><span class="bar-label">健康</span><div class="bar-track"><div class="bar-fill" id="bar-health" style="background:#F87171;"></div></div><span class="bar-val" id="val-health">0</span></div>
        <div class="bar-row"><span class="bar-label">心情</span><div class="bar-track"><div class="bar-fill" id="bar-mood" style="background:#FBBF24;"></div></div><span class="bar-val" id="val-mood">0</span></div>
      </div>
      <div id="card-actions">
        <button class="act-btn" onclick="doAction('feed')">投喂</button>
        <button class="act-btn" onclick="doAction('train')">训练</button>
        <button class="act-btn" onclick="doAction('rest')">休息</button>
        <button class="act-btn" onclick="doAction('chat')">交谈</button>
      </div>
      <div id="card-feedback"></div>
    </div>
  </div>

</div>

<script>
const ZONES = {zones_json};
const EMPLOYEE_COLOR_MAP = {json.dumps(EMPLOYEE_COLOR_MAP)};
const SPECIES_CN = {json.dumps(SPECIES_CN)};
const SPECIES_JOB = {json.dumps(SPECIES_JOB)};

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

#app {{ width:100%; height:100%; display:flex; flex-direction:column; }}

#top-bar {{ height:48px; display:flex; align-items:center; justify-content:space-between; padding:0 20px; background:rgba(10,15,12,0.9); border-bottom:1px solid rgba(255,255,255,0.04); flex-shrink:0; }}
.top-title {{ display:flex; align-items:baseline; gap:8px; }}
.t-main {{ font-family:'Fraunces',serif; font-size:18px; font-weight:600; }}
.t-sub {{ font-size:10px; letter-spacing:0.12em; text-transform:uppercase; color:var(--text-dim); }}
#top-info {{ display:flex; gap:12px; font-size:11px; color:var(--text-dim); font-family:'JetBrains Mono',monospace; }}

#roster {{ position:fixed; top:56px; right:16px; width:160px; max-height:calc(100vh - 72px); z-index:10; background:var(--glass); backdrop-filter:blur(12px); border:1px solid var(--glass-border); border-radius:10px; padding:10px; overflow-y:auto; }}
.roster-title {{ font-size:9px; letter-spacing:0.12em; text-transform:uppercase; color:var(--accent); margin-bottom:6px; font-weight:600; }}
.roster-item {{ display:flex; align-items:center; gap:8px; padding:5px 8px; border-radius:5px; cursor:pointer; transition:background 0.12s; }}
.roster-item:hover {{ background:rgba(255,255,255,0.06); }}
.roster-item.active {{ background:rgba(212,165,116,0.15); }}
.roster-dot {{ width:8px; height:8px; border-radius:50%; flex-shrink:0; }}
.roster-name {{ font-size:11px; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.roster-item.dead .roster-name {{ color:var(--text-dim); text-decoration:line-through; }}

#card-overlay {{ position:fixed; top:0; left:0; width:100%; height:100%; z-index:100; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,0.55); }}
#status-card {{ position:relative; width:380px; max-width:90vw; background:var(--glass); border:1px solid var(--glass-border); border-radius:12px; padding:22px; }}
#card-close {{ position:absolute; top:8px; right:8px; width:26px; height:26px; border:none; border-radius:50%; background:rgba(255,255,255,0.06); color:var(--text-dim); font-size:15px; cursor:pointer; display:flex; align-items:center; justify-content:center; }}
#card-close:hover {{ background:rgba(255,255,255,0.12); color:var(--text); }}
#card-header {{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }}
#card-avatar {{ width:48px; height:48px; border-radius:12px; display:flex; align-items:center; justify-content:center; font-family:'Fraunces',serif; font-size:22px; font-weight:600; color:#E8E4D8; border:1.5px solid rgba(255,255,255,0.1); flex-shrink:0; }}
#card-name {{ font-size:15px; font-weight:600; font-family:'Fraunces',serif; }}
#card-job {{ font-size:11px; color:var(--text-dim); margin-top:2px; }}

#card-bars {{ margin-bottom:14px; }}
.bar-row {{ display:flex; align-items:center; gap:6px; margin-bottom:6px; }}
.bar-label {{ font-size:10px; color:var(--text-dim); width:20px; }}
.bar-track {{ flex:1; height:8px; background:rgba(255,255,255,0.05); border-radius:3px; overflow:hidden; }}
.bar-fill {{ height:100%; border-radius:3px; transition:width 0.3s ease; }}
.bar-val {{ font-size:10px; color:var(--text-dim); width:24px; font-family:'JetBrains Mono',monospace; }}

#card-actions {{ display:flex; gap:6px; margin-top:14px; }}
.act-btn {{ flex:1; padding:9px; border:none; border-radius:7px; background:rgba(255,255,255,0.05); color:var(--text); font-size:12px; font-weight:500; cursor:pointer; transition:background 0.12s; font-family:'Manrope',sans-serif; }}
.act-btn:hover {{ background:rgba(212,165,116,0.15); }}
#card-feedback {{ margin-top:8px; font-size:11px; color:var(--accent); text-align:center; min-height:14px; font-family:'JetBrains Mono',monospace; }}
"""


JS_CODE = r"""
let employees = [];
let selectedName = null;

async function fetchStatus() {
  try {
    const res = await fetch('/game/api/status');
    const data = await res.json();
    employees = data.employees || [];
    updateTopBar(data);
    renderRoster();
  } catch (e) {
    console.error('fetchStatus error', e);
  }
}

function updateTopBar(data) {
  const hh = String(data.env.game_hour || 8).padStart(2, '0');
  const mm = String(data.env.game_minute || 0).padStart(2, '0');
  document.getElementById('info-time').textContent = hh + ':' + mm;
  document.getElementById('info-gen').textContent = '第 ' + (data.evolution.generation || 0) + ' 代';
  const alive = employees.filter(e => e.alive !== false).length;
  document.getElementById('info-pop').textContent = alive + ' 员工';
}

function renderRoster() {
  const list = document.getElementById('roster-list');
  list.innerHTML = '';
  for (const emp of employees) {
    const color = EMPLOYEE_COLOR_MAP[emp.species] || '#1A3B5C';
    const alive = emp.alive !== false;
    const item = document.createElement('div');
    item.className = 'roster-item' + (alive ? '' : ' dead') + (selectedName === emp.name ? ' active' : '');
    item.onclick = () => selectEmployee(emp.name);
    item.innerHTML = '<div class="roster-dot" style="background:' + color + ';"></div>' +
                     '<div class="roster-name">' + (emp.name || '?') + '</div>';
    list.appendChild(item);
  }
}

function selectEmployee(name) {
  selectedName = name;
  const emp = employees.find(e => e.name === name);
  if (emp) openCard(emp);
  renderRoster();
}

function openCard(emp) {
  const color = EMPLOYEE_COLOR_MAP[emp.species] || '#1A3B5C';
  const cn = SPECIES_CN[emp.species] || '?';
  const job = SPECIES_JOB[emp.species] || '员工';

  const cav = document.getElementById('card-avatar');
  cav.style.background = color;
  cav.textContent = cn;
  cav.innerHTML = '';
  const cimg = document.createElement('img');
  cimg.src = '/static/assets/characters/' + emp.species + '.png';
  cimg.alt = cn;
  cimg.style.width = '100%';
  cimg.style.height = '100%';
  cimg.style.objectFit = 'cover';
  cimg.style.borderRadius = 'inherit';
  cimg.style.imageRendering = 'pixelated';
  cimg.onerror = () => { cimg.remove(); };
  cav.appendChild(cimg);
  document.getElementById('card-name').textContent = emp.name || '未知';
  document.getElementById('card-job').textContent = job;

  updateBar('energy', emp.energy || 0);
  updateBar('health', emp.health || 0);
  updateBar('mood', emp.mood_score || 0);

  document.getElementById('card-feedback').textContent = '';
  document.getElementById('card-overlay').style.display = 'flex';
}

function updateBar(name, val) {
  const pct = Math.min(100, Math.max(0, val));
  document.getElementById('bar-' + name).style.width = pct + '%';
  document.getElementById('val-' + name).textContent = Math.round(val);
}

function closeCard() {
  document.getElementById('card-overlay').style.display = 'none';
  selectedName = null;
  renderRoster();
}

document.getElementById('card-overlay').addEventListener('click', function(e) {
  if (e.target === this) closeCard();
});

async function doAction(action) {
  if (!selectedName) return;
  const emp = employees.find(e => e.name === selectedName);
  if (!emp) return;
  const fb = document.getElementById('card-feedback');
  fb.textContent = '执行中...';
  try {
    let res;
    if (action === 'feed') {
      res = await fetch('/game/api/interact', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:emp.name, action:'feed', amount:20})});
    } else if (action === 'rest') {
      res = await fetch('/game/api/interact', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:emp.name, action:'wake'})});
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

fetchStatus();
setInterval(fetchStatus, 3000);
"""


def status() -> dict:
    return {
        "mode": "topdown-2d",
        "version": "commit-58",
        "description": "2D 俯视控制台（精简版）",
    }
