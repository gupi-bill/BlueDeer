# -*- coding: utf-8 -*-
"""
BlueDeer 14 模块可视化 UI。
铁律：能画图不堆字段卡片；消耗类用面积波形图；平台/角色/状态用图形；数值卡片配 sparkline。
纯原生 HTML+CSS+SVG，本地优先，不引第三方前端库。
"""
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

MODULES = [
    {"key": "overview", "name": "概览", "icon": "◉"},
    {"key": "channels", "name": "频道", "icon": "⌁"},
    {"key": "instances", "name": "实例", "icon": "▣"},
    {"key": "sessions", "name": "会话", "icon": "◌"},
    {"key": "usage", "name": "使用情况", "icon": "▤"},
    {"key": "cron", "name": "定时任务", "icon": "◷"},
    {"key": "agents", "name": "代理", "icon": "✦"},
    {"key": "skills", "name": "技能", "icon": "⚒"},
    {"key": "nodes", "name": "节点", "icon": "◫"},
    {"key": "config", "name": "配置", "icon": "⚙"},
    {"key": "comm", "name": "通信", "icon": "⇄"},
    {"key": "appearance", "name": "外观", "icon": "◨"},
    {"key": "automation", "name": "自动化", "icon": "↻"},
    {"key": "infrastructure", "name": "基础设施", "icon": "▦"},
]

THEME_CSS = """
:root{
  --bd-primary:#1E6FFF;--bd-primary-2:#3B82F6;--bd-bg:#F5F7FA;
  --bd-card:#FFFFFF;--bd-text:#1F2329;--bd-muted:#6B7280;
  --bd-border:#E5E7EB;--bd-ok:#22C55E;--bd-warn:#F59E0B;--bd-err:#EF4444;
  --bd-shadow:0 1px 3px rgba(0,0,0,.06);--bd-radius:12px;
}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'PingFang SC','Microsoft YaHei',system-ui,sans-serif;background:var(--bd-bg);color:var(--bd-text);font-size:14px;height:100vh;overflow:hidden}
.app{display:flex;height:100vh}
.sidebar{width:216px;min-width:216px;background:linear-gradient(180deg,#0F2B5B 0%,#0D2246 60%,#0A1A35 100%);color:#CFE0FF;display:flex;flex-direction:column}
.brand{display:flex;align-items:center;gap:10px;padding:18px 16px 16px;border-bottom:1px solid rgba(255,255,255,.08)}
.logo{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#3B82F6,#1E6FFF);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:15px;box-shadow:0 2px 8px rgba(30,111,255,.45)}
.brand .name{font-weight:700;font-size:15px;color:#fff}.brand .sub{font-size:11px;color:#7F9FD8;margin-top:2px}
.nav{flex:1;overflow-y:auto;padding:8px 0}
.nav a{display:flex;align-items:center;gap:10px;padding:9px 16px;color:#B9CEF0;text-decoration:none;font-size:13px;border-left:3px solid transparent;transition:all .15s}
.nav a:hover{background:rgba(255,255,255,.06);color:#fff}
.nav a.active{background:linear-gradient(90deg,rgba(30,111,255,.28),rgba(30,111,255,.02));color:#fff;border-left-color:#3B82F6}
.nav .ico{width:20px;text-align:center;opacity:.85}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.topbar{height:56px;min-height:56px;background:var(--bd-card);border-bottom:1px solid var(--bd-border);display:flex;align-items:center;gap:14px;padding:0 20px}
.topbar .title{font-size:17px;font-weight:700}.topbar .crumb{color:var(--bd-muted);font-size:12px}.spacer{flex:1}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.dot.ok{background:var(--bd-ok);box-shadow:0 0 0 4px rgba(34,197,94,.14)}
.dot.warn{background:var(--bd-warn);box-shadow:0 0 0 4px rgba(245,158,11,.14)}
.dot.err{background:var(--bd-err);box-shadow:0 0 0 4px rgba(239,68,68,.14)}
.dot.gray{background:#CBD5E1}
.content{flex:1;overflow-y:auto;padding:20px}
.card{background:var(--bd-card);border-radius:var(--bd-radius);box-shadow:var(--bd-shadow);border:1px solid var(--bd-border);padding:16px}
.card h3{font-size:14px;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.sub{color:var(--bd-muted);font-size:12px}
.grid{display:grid;gap:16px}
.grid.cols-4{grid-template-columns:repeat(4,1fr)}
.grid.cols-3{grid-template-columns:repeat(3,1fr)}
.grid.cols-2{grid-template-columns:repeat(2,1fr)}
@media(max-width:1100px){.grid.cols-4{grid-template-columns:repeat(2,1fr)}.grid.cols-3{grid-template-columns:1fr}}
.stat{display:flex;flex-direction:column;gap:6px}
.stat .label{color:var(--bd-muted);font-size:12px}.stat .value{font-size:26px;font-weight:800;letter-spacing:-.5px}.stat .spark{height:32px;margin-top:2px}
.chart-box{position:relative;width:100%}.chart-box svg{display:block;width:100%}
.tooltip{position:absolute;pointer-events:none;background:rgba(17,24,39,.92);color:#fff;padding:6px 8px;border-radius:6px;font-size:11px;white-space:nowrap;opacity:0;transition:opacity .1s;z-index:20}
.ring-wrap{display:flex;align-items:center;gap:16px}
.ring-center{font-size:22px;font-weight:800;text-align:center}.ring-center small{display:block;font-size:11px;color:var(--bd-muted);font-weight:400}
.legend{display:flex;flex-direction:column;gap:6px;font-size:12px}
.legend .item{display:flex;align-items:center;gap:8px}.legend .sw{width:10px;height:10px;border-radius:3px}
.row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #F1F3F7}.row:last-child{border-bottom:none}
.placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:60px 20px;text-align:center}
.p-ico{width:64px;height:64px;border-radius:16px;background:linear-gradient(135deg,#E8F1FF,#CFE0FF);display:flex;align-items:center;justify-content:center;font-size:28px;color:var(--bd-primary)}
.p-title{font-size:17px;font-weight:700}.p-desc{color:var(--bd-muted);font-size:13px;max-width:420px;line-height:1.7}
.badge{display:inline-flex;align-items:center;gap:6px;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:600}
.badge.blue{background:#E8F1FF;color:#1E6FFF}.badge.green{background:#E8FBF0;color:#15803D}.badge.amber{background:#FEF3E2;color:#B45309}.badge.red{background:#FEE9E9;color:#B91C1C}
.chip{display:inline-flex;padding:3px 10px;border-radius:999px;background:#F1F5F9;color:#475569;font-size:11px;margin:2px}
.range-bar{display:flex;gap:6px}
.range-btn{padding:4px 12px;border-radius:8px;border:1px solid var(--bd-border);background:#fff;font-size:12px;color:var(--bd-muted);cursor:pointer}
.range-btn.active{background:#E8F1FF;border-color:#3B82F6;color:#1E6FFF;font-weight:600}
"""


def _ui_shell(active_key, title, content, crumb=""):
    nav_parts = []
    for m in MODULES:
        cls = ' class="active"' if m["key"] == active_key else ""
        href = "/ui/" + m["key"]
        nav_parts.append('<a href="' + href + '"' + cls + '>'
                         '<span class="ico">' + m["icon"] + '</span><span>' + m["name"] + '</span></a>')
    nav = "".join(nav_parts)
    crumb_html = '<span class="crumb">' + crumb + '</span>' if crumb else ""
    html_parts = []
    html_parts.append('<!DOCTYPE html>')
    html_parts.append('<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">')
    html_parts.append('<title>' + title + ' · BlueDeer</title><style>' + THEME_CSS + '</style></head>')
    html_parts.append('<body><div class="app">')
    html_parts.append('<aside class="sidebar"><div class="brand"><div class="logo">BD</div><div><div class="name">BlueDeer</div><div class="sub">森林公司控制台</div></div></div><nav class="nav">' + nav + '</nav></aside>')
    html_parts.append('<div class="main"><div class="topbar"><span class="title">' + title + '</span>' + crumb_html)
    html_parts.append('<span class="spacer"></span><span class="dot ok"></span><span style="font-size:12px;color:var(--bd-muted)">网关运行中</span></div>')
    html_parts.append('<div class="content">' + content + '</div></div></div></body></html>')
    return ''.join(html_parts)

def _area_chart(points, labels, width=600, height=200, color="#3B82F6", fill_id="g", threshold=None):
    if not points:
        points = [0]
    n = len(points)
    pad_l, pad_r, pad_t, pad_b = 8, 8, 14, 22
    w = max(width - pad_l - pad_r, 50)
    h = max(height - pad_t - pad_b, 30)
    mn, mx = min(points), max(points)
    if mx == mn:
        mx = mn + 1
    rng = mx - mn
    xs = [pad_l + w * i / (n - 1) for i in range(n)] if n > 1 else [pad_l + w / 2]
    ys = [pad_t + h * (1 - (p - mn) / rng) for p in points]
    line_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area_pts = f"{xs[0]:.1f},{pad_t + h:.1f} " + line_pts + f" {xs[-1]:.1f},{pad_t + h:.1f}"
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{color}" onmousemove="showTip(event,\'{label}\',{p:.2f})" onmouseout="hideTip()" style="cursor:pointer"/>'
        for x, y, p, label in zip(xs, ys, points, labels)
    )
    thr = ""
    if threshold is not None:
        ty = pad_t + h * (1 - (threshold - mn) / rng)
        thr = f'<line x1="{pad_l}" y1="{ty:.1f}" x2="{pad_l + w}" y2="{ty:.1f}" stroke="#EF4444" stroke-width="1" stroke-dasharray="4 3" opacity=".7"/>'
    x_axis = ""
    if labels:
        step = max(1, (n - 1) // 5)
        x_axis = "".join(
            f'<text x="{xs[i]:.1f}" y="{height - 4}" font-size="10" fill="#9CA3AF" text-anchor="middle">{labels[i]}</text>'
            for i in range(0, n, step)
        )
    return f"""<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="height:{height}px">
<defs><linearGradient id="{fill_id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="{color}" stop-opacity=".32"/><stop offset="100%" stop-color="{color}" stop-opacity=".02"/></linearGradient></defs>
{thr}<polygon points="{area_pts}" fill="url(#{fill_id})"/><polyline points="{line_pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>{dots}{x_axis}</svg>"""


def _donut(percent, size=120, color="#3B82F6", label=""):
    r = size / 2 - 10
    c = 2 * 3.1415926535 * r
    pct = max(0, min(100, percent))
    filled = c * pct / 100
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}"><circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="#E8F0FE" stroke-width="10"/><circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{color}" stroke-width="10" stroke-dasharray="{filled:.1f} {c - filled:.1f}" stroke-linecap="round" transform="rotate(-90 {size/2} {size/2})"/><text x="50%" y="48%" text-anchor="middle" font-size="22" font-weight="800" fill="#1F2329">{round(pct)}%</text><text x="50%" y="62%" text-anchor="middle" font-size="10" fill="#6B7280">{label}</text></svg>"""


_USAGE_SCRIPT = """
function showTip(e,label,val){var t=document.getElementById('tip');t.innerHTML=label+'：'+val;t.style.opacity=1;t.style.left=(e.clientX+12)+'px';t.style.top=(e.clientY-30)+'px';}
function hideTip(){document.getElementById('tip').style.opacity=0;}
function switchRange(r){document.querySelectorAll('.range-btn').forEach(function(b){b.classList.remove('active')});document.getElementById('btn-'+r).classList.add('active');document.getElementById('rangeLabel').textContent = r==='24h'?'近 24 小时':'近 7 天';}
"""


def _usage_page():
    hours = ["00", "02", "04", "06", "08", "10", "12", "14", "16", "18", "20", "22"]
    tokens = [12, 18, 15, 10, 22, 35, 48, 42, 55, 63, 52, 30]
    costs = [0.8, 1.2, 1.0, 0.7, 1.5, 2.4, 3.2, 2.9, 3.8, 4.3, 3.5, 2.0]
    days = ["07", "08", "09", "10", "11", "12", "13"]
    tokens_7d = [180, 210, 196, 240, 320, 390, 410]
    rate = [3, 5, 4, 8, 12, 9, 15, 18, 14, 11, 16, 13]
    models = [("deepseek-chat", 48, "#1E6FFF"), ("qwen-max", 24, "#60A5FA"), ("claude-sonnet", 16, "#93C5FD"), ("本地模型", 12, "#CBD5E1")]
    model_legend = "".join(f'<div class="item"><span class="sw" style="background:{c}"></span>{n} · {p}%</div>' for n, p, c in models)
    quota_cards = ""
    for name, used, limit, color in [("deepseek-chat", 420000, 600000, "#1E6FFF"), ("qwen-max", 310000, 500000, "#60A5FA"), ("claude-sonnet", 90000, 200000, "#93C5FD")]:
        pct = round(used / limit * 100)
        quota_cards += f"""<div class="card"><h3>{name}</h3><div class="ring-wrap">{_donut(pct, 90, color, '已用')}<div class="legend" style="margin-left:auto"><div class="item"><span class="sw" style="background:{color}"></span>已用 {used:,} tokens</div><div class="item"><span class="sw" style="background:#E8F0FE"></span>配额 {limit:,}</div></div></div></div>"""
    content = f"""<div id="tip" class="tooltip"></div>
<div style="display:flex;align-items:center;margin-bottom:16px"><div class="range-bar"><button class="range-btn active" id="btn-24h" onclick="switchRange('24h')">24 小时</button><button class="range-btn" id="btn-7d" onclick="switchRange('7d')">7 天</button></div><span class="sub" style="margin-left:12px" id="rangeLabel">近 24 小时</span><span class="spacer"></span><span class="badge blue">数据刷新于 {time.strftime('%H:%M:%S')}</span></div>
<div class="grid cols-2" style="margin-bottom:16px"><div class="card"><h3>Token 消耗波形 <span class="sub">X=时间，Y=tokens</span></h3><div class="chart-box">{_area_chart(tokens, hours, 600, 200, '#1E6FFF', 'gTokens', 30)}</div></div><div class="card"><h3>费用折线 <span class="sub">X=时间，Y=¥</span></h3><div class="chart-box">{_area_chart(costs, hours, 600, 200, '#10B981', 'gCost', 2.5)}</div></div></div>
<div class="grid cols-2" style="margin-bottom:16px"><div class="card"><h3>近 7 天 Token 趋势</h3><div class="chart-box">{_area_chart(tokens_7d, days, 600, 180, '#3B82F6', 'gTokens7d')}</div></div><div class="card"><h3>限流速率实时波形 <span class="sub">Y=请求/秒，红线=阈值</span></h3><div class="chart-box">{_area_chart(rate, hours, 600, 180, '#F59E0B', 'gRate', 12)}</div></div></div>
<div class="grid cols-2" style="margin-bottom:16px"><div class="card"><h3>各模型 Token 占比</h3><div class="ring-wrap">{_donut(48, 150, '#1E6FFF', 'deepseek-chat')}<div class="legend" style="margin-left:auto">{model_legend}</div></div></div><div class="card"><h3>预算与告警</h3><div class="row"><span class="dot ok"></span>本月预算：¥120 / ¥300</div><div class="row"><span class="dot warn"></span>单日上限：¥4.3 / ¥10</div><div class="row"><span class="dot ok"></span>告警阈值：80%（未触发）</div><div class="row"><span class="dot gray"></span>用量明细脱敏：已开启 redactSensitive</div></div></div>
<div class="grid cols-3">{quota_cards}</div>
<script>{_USAGE_SCRIPT}</script>"""
    return _ui_shell("usage", "使用情况 Usage", content, "核心仪表盘 · Token / 费用 / 配额 / 限流")


_PLACEHOLDER_DESC = {
    "overview": "顶部状态条 + 4 统计大卡（sparkline）+ 网关健康环形 + 最近会话时间线。",
    "channels": "平台官方 logo 图标网格 + 连接状态徽章 + 1h 消息吞吐波形。",
    "instances": "实例卡片（状态灯）+ CPU / 内存 / 网络资源波形 + 重启/停止/日志按钮。",
    "sessions": "会话列表状态灯 + Token 消耗迷你条 + 全量活跃度面积图。",
    "cron": "甘特图时间线 + 下次执行倒计时环形 + 成功/失败堆叠面积图。",
    "agents": "角色卡网格（几何图标）+ 领域 chip + 各 agent 负载 sparkline。",
    "skills": "技能 icon 卡 + 启用开关 + 近 7 天调用量条形。",
    "nodes": "工作流 DAG 可视化 + 选中节点输入/输出波形（五类节点）。",
    "config": "分组折叠面板 + 校验状态点（gateway/agents/models/mcp）。",
    "comm": "Webhook 地址卡 + 事件类型 chip + 投递状态时间线 + 成功率环形。",
    "appearance": "主题色板 + LOGO 预览 + 字体样例。",
    "automation": "触发器 → 动作链路图 + 引擎 CPU/队列健康波形。",
    "infrastructure": "服务健康仪表盘 + 备份时间线 + 磁盘/内存/网络波形。",
}


def _placeholder_page(key):
    m = next(x for x in MODULES if x["key"] == key)
    desc = _PLACEHOLDER_DESC.get(key, "")
    content = f"""<div class="card"><div class="placeholder"><div class="p-ico">{m['icon']}</div><div class="p-title">{m['name']} 模块</div><div class="p-desc">{desc}</div><span class="badge amber">规划中 · 按优先级逐步落地</span></div></div>"""
    return _ui_shell(key, m["name"], content, "14 模块可视化 · 渐进实现")


@router.get("/ui", response_class=HTMLResponse)
@router.get("/ui/", response_class=HTMLResponse)
async def ui_root(request: Request):
    return _usage_page()


@router.get("/ui/usage", response_class=HTMLResponse)
async def ui_usage(request: Request):
    return _usage_page()


@router.get("/ui/{module_key}", response_class=HTMLResponse)
async def ui_module(request: Request, module_key: str):
    if module_key not in [m["key"] for m in MODULES]:
        return _ui_shell("overview", "404", "<div class='card'>模块不存在</div>")
    if module_key == "usage":
        return _usage_page()
    return _placeholder_page(module_key)


@router.get("/api/usage")
async def api_usage():
    now = time.time()
    hour = 3600
    tokens_series = [
        {"ts": int(now - (11 - i) * 2 * hour), "input": int(v * 0.6), "output": int(v * 0.4), "total": v * 1000}
        for i, v in enumerate([12, 18, 15, 10, 22, 35, 48, 42, 55, 63, 52, 30])
    ]
    return {
        "providers": [
            {"provider": "deepseek-chat", "tokens": {"input": 252000, "output": 168000, "total": 420000}, "cost": 18.6, "quota": {"limit": 600000, "reset": int(now + hour * 72)}},
            {"provider": "qwen-max", "tokens": {"input": 186000, "output": 124000, "total": 310000}, "cost": 9.2, "quota": {"limit": 500000, "reset": int(now + hour * 48)}},
            {"provider": "claude-sonnet", "tokens": {"input": 54000, "output": 36000, "total": 90000}, "cost": 7.4, "quota": {"limit": 200000, "reset": int(now + hour * 120)}},
        ],
        "rateLimit": {"requestRate": [3, 5, 4, 8, 12, 9, 15, 18, 14, 11, 16, 13], "threshold": 12, "window": "1h"},
        "series": {
            "24h": {"labels": ["00", "02", "04", "06", "08", "10", "12", "14", "16", "18", "20", "22"], "tokens": tokens_series},
            "7d": {"labels": ["07", "08", "09", "10", "11", "12", "13"], "tokens": [180000, 210000, 196000, 240000, 320000, 390000, 410000]},
        },
        "budget": {"monthlyUsed": 120.0, "monthlyLimit": 300.0, "dailyUsed": 4.3, "dailyLimit": 10.0},
        "redactSensitive": True,
    }
