/* ============ 用量图表（纯 SVG 零依赖）============
   数据 100% 来自底座 /system/usage —— 后端扫描 runs 目录下每个 final.json 真实轨迹，
   前端零计算零假数。折线=近14天运行次数；条形=各层平均耗时；环形=角色分布。 */
var CHART_C = { accent: '#1e6fff', amber: '#d97706', green: '#16a34a', violet: '#7c5cf0', rose: '#e11d68' };
var DONUT_PALETTE = ['#1e6fff', '#7c5cf0', '#0ea5a4', '#d97706', '#e11d68', '#4c8c3f', '#5b6b8c'];

/* 折线图：近14天运行次数（被拦截的天标红点） */
function lineChartRuns(days) {
  if (!days || days.length < 2) return '<div class="empty">真实运行记录不足（跑两天后自动出图）</div>';
  var w = 560, h = 170, pad = { l: 30, r: 12, t: 14, b: 22 };
  var max = Math.max.apply(null, days.map(function(d){ return d.count; })) || 1;
  var iw = w - pad.l - pad.r, ih = h - pad.t - pad.b;
  function X(i) { return pad.l + i * iw / (days.length - 1); }
  function Y(v) { return pad.t + ih - (v / max) * ih; }
  var pts = days.map(function(d, i){ return X(i).toFixed(1) + ',' + Y(d.count).toFixed(1); }).join(' ');
  var area = pad.l + ',' + (pad.t + ih) + ' ' + pts + ' ' + (w - pad.r) + ',' + (pad.t + ih);
  var dots = days.map(function(d, i){
    var c = d.blocked > 0 ? CHART_C.rose : CHART_C.accent;
    return '<circle cx="' + X(i).toFixed(1) + '" cy="' + Y(d.count).toFixed(1) + '" r="3" fill="' + c + '"><title>' +
      d.date + ' 运行 ' + d.count + ' 次 · 拦截 ' + d.blocked + '</title></circle>';
  }).join('');
  var grid = [0, .5, 1].map(function(f){
    var y = (pad.t + ih - f * ih).toFixed(1);
    return '<line x1="' + pad.l + '" y1="' + y + '" x2="' + (w - pad.r) + '" y2="' + y + '" stroke="currentColor" opacity=".08"/>' +
      '<text x="' + (pad.l - 6) + '" y="' + (+y + 3) + '" text-anchor="end" font-size="9" fill="currentColor" opacity=".45">' + Math.round(max * f) + '</text>';
  }).join('');
  var step = Math.ceil(days.length / 7), labels = '';
  days.forEach(function(d, i){
    if (i % step === 0) labels += '<text x="' + X(i).toFixed(1) + '" y="' + (h - 6) + '" text-anchor="middle" font-size="9" fill="currentColor" opacity=".45">' + d.date + '</text>';
  });
  return '<svg viewBox="0 0 ' + w + ' ' + h + '" style="width:100%;color:var(--text)"><polygon points="' + area + '" fill="' + CHART_C.accent + '" opacity=".08"/>' +
    '<polyline points="' + pts + '" fill="none" stroke="' + CHART_C.accent + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' +
    grid + dots + labels + '</svg>';
}

/* 横向条形：十三层平均耗时 ms */
function barChartLayers(layers) {
  if (!layers || !layers.length) return '<div class="empty">暂无层级耗时（开启 trace 跑几次即有）</div>';
  var max = Math.max.apply(null, layers.map(function(l){ return l.avg_ms; })) || 1;
  var rows = layers.map(function(l, i){
    var pct = Math.max(2, l.avg_ms / max * 100);
    return '<div style="display:flex;align-items:center;gap:10px;margin:7px 0">' +
      '<span class="mute" style="width:96px;font-size:11px;text-align:right;font-family:var(--mono)">' + esc(l.layer) + '</span>' +
      '<div style="flex:1;height:14px;background:rgba(128,128,128,.12);border-radius:4px;overflow:hidden"><div style="height:100%;width:' + pct.toFixed(1) + '%;background:' + DONUT_PALETTE[i % DONUT_PALETTE.length] + ';border-radius:4px"></div></div>' +
      '<span class="muted" style="width:64px;font-size:11px;font-family:var(--mono)">' + l.avg_ms + 'ms</span></div>';
  }).join('');
  return '<div style="padding:6px 0">' + rows + '</div>';
}

/* 环形图：角色/提供方占比 */
function donutChart(map, title) {
  var keys = Object.keys(map || {});
  if (!keys.length) return '<div class="empty">暂无分布数据</div>';
  var total = keys.reduce(function(s, k){ return s + map[k]; }, 0) || 1;
  var R = 54, C = 2 * Math.PI * R, off = 0;
  var segs = keys.map(function(k, i){
    var frac = map[k] / total;
    var seg = '<circle r="' + R + '" cx="70" cy="70" fill="none" stroke="' + DONUT_PALETTE[i % DONUT_PALETTE.length] +
      '" stroke-width="20" stroke-dasharray="' + (frac * C).toFixed(2) + ' ' + C.toFixed(2) +
      '" stroke-dashoffset="' + (-off).toFixed(2) + '" transform="rotate(-90 70 70)"><title>' + k + ': ' + map[k] + '</title></circle>';
    off += frac * C;
    return seg;
  }).join('');
  var legend = keys.map(function(k, i){
    return '<div style="display:flex;align-items:center;gap:6px;margin:5px 0"><span style="width:10px;height:10px;border-radius:3px;background:' +
      DONUT_PALETTE[i % DONUT_PALETTE.length] + ';flex-shrink:0"></span><span class="mute" style="font-size:12px">' + esc(k) +
      '</span><b style="margin-left:auto;font-size:12px">' + map[k] + '</b></div>';
  }).join('');
  return '<div style="display:flex;align-items:center;gap:18px"><svg width="140" height="140" viewBox="0 0 140 140">' + segs +
    '<text x="70" y="66" text-anchor="middle" font-size="20" font-weight="700" fill="currentColor" style="color:var(--text)">' + total + '</text>' +
    '<text x="70" y="84" text-anchor="middle" font-size="9" fill="currentColor" opacity=".5">' + title + '</text></svg>' +
    '<div style="flex:1;min-width:130px">' + legend + '</div></div>';
}

function renderUsage(u) {
  var box = document.getElementById('usage-charts');
  if (!box) return;
  var kpi =
    '<div class="stat-card"><div class="stat-num" style="color:var(--accent)">' + (u.total_runs || 0) + '</div><div class="stat-label">累计真实运行</div></div>' +
    '<div class="stat-card"><div class="stat-num" style="color:var(--green)">' + (u.success_rate != null ? u.success_rate : '—') + '%</div><div class="stat-label">通过率（未拦截）</div></div>' +
    '<div class="stat-card"><div class="stat-num" style="color:var(--red,#e11d48)">' + (u.blocked_runs || 0) + '</div><div class="stat-label">安全拦截次数</div></div>';
  box.innerHTML =
    '<div class="stat-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:14px">' + kpi + '</div>' +
    '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px">' +
    '<div class="card" style="margin:0"><div class="card-title">运行趋势 <span class="cnt">近14天 · runs/ 真实轨迹</span></div>' + lineChartRuns(u.runs_per_day) + '</div>' +
    '<div class="card" style="margin:0"><div class="card-title">层级耗时 <span class="cnt">平均毫秒 · final.json</span></div>' + barChartLayers(u.layer_avg_ms) + '</div>' +
    '<div class="card" style="margin:0"><div class="card-title">角色分布 <span class="cnt">按 role 统计</span></div>' + donutChart(u.role_distribution, '总运行') + '</div>' +
    '</div>';
}
