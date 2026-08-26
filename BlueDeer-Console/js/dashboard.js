/* ============ 页面 1：总览仪表盘（默认首页） ============ */
/* 在线 Agent / 待审批 / 进行中任务 / 紧急刹车 / 最近事件日志；
   统计值全部来自底座 /system/stats 与 /system/audit-logs，前端不做统计计算。
   用量三图(折线/柱状/环形)来自底座 /system/usage —— 扫描 runs 目录下每个 final.json 的真实轨迹。 */
var STAT_DEFS = [
  { key: 'agents_online', label: '在线 Agent', sub: 'agents_total', color: 'var(--accent)' },
  { key: 'approvals_pending', label: '待审批（记忆）', sub: 'memory_approvals', color: 'var(--amber)' },
  { key: 'tool_pending', label: '待审批（工具）', sub: 'tool_requests', color: 'var(--amber)' },
  { key: 'workflows_running', label: '运行中工作流', sub: 'workflow_runs', color: 'var(--green)' },
  { key: 'workflows_active', label: '活跃工作流', sub: 'workflows', color: '#6d5ae0' },
  { key: 'tasks_pending', label: '进行中任务', sub: 'tasks', color: 'var(--green)' },
  { key: 'messages_total', label: '消息总量', sub: 'messages', color: 'var(--muted)' }
];
/* 历史趋势（前端展示用，仅记录底座返回的数值序列） */
window._trend = { agents_online: [], approvals_pending: [], workflows_running: [], messages_total: [] };
function sparkline(series, color, w, h) {
  var pts = series.slice(-14);
  if (pts.length < 2) return '';
  var max = Math.max.apply(null, pts), min = Math.min.apply(null, pts);
  var span = (max - min) || 1;
  var step = w / (pts.length - 1);
  var coords = pts.map(function(v, i){ return (i * step).toFixed(1) + ',' + (h - 4 - ((v - min) / span) * (h - 8)).toFixed(1); });
  return '<svg width="' + w + '" height="' + h + '" style="display:block"><polyline points="' + coords.join(' ') + '" fill="none" stroke="' + color + '" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" opacity=".85"/></svg>';
}
function loadDashboard() {
  apiGet('/system/stats').then(function(d){
    var st = d.stats || {};
    document.getElementById('mon-time').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
    // 累积历史曲线（只记录底座数值）
    ['agents_online', 'approvals_pending', 'workflows_running', 'messages_total'].forEach(function(k){
      if (st[k] != null) { window._trend[k].push(Number(st[k])); if (window._trend[k].length > 30) window._trend[k].shift(); }
    });
    // 统计卡（带 mini 趋势线）
    var grid = document.getElementById('mon-cards');
    grid.innerHTML = STAT_DEFS.map(function(s){
      var v = st[s.key] != null ? st[s.key] : '—';
      var sp = window._trend[s.key] && window._trend[s.key].length > 1 ? sparkline(window._trend[s.key], s.color, 120, 30) : '';
      return '<div class="stat-card"><div class="stat-num" style="color:' + s.color + '">' + esc(String(v)) + '</div><div class="stat-label">' + esc(s.label) + '</div><div class="mute" style="font-size:11px">' + esc(s.sub) + '</div>' + (sp ? '<div style="margin-top:10px">' + sp + '</div>' : '') + '</div>';
    }).join('');
    // 紧急刹车
    var eb = !!st.emergency_block;
    var el = document.getElementById('mon-eb');
    el.innerHTML = '<div class="eb-state ' + (eb ? 'on' : 'off') + '"><b>' + (eb ? '紧急刹车已开启' : '正常 · 未刹车') + '</b><span class="muted">开启后底座拒绝所有消息发送与写记忆</span></div>'
      + '<button class="btn ' + (eb ? '' : 'danger') + '" onclick="toggleEmergency()">' + (eb ? '解除紧急刹车' : '开启紧急刹车') + '</button>';
    // 审计日志（真实接口）
    loadAuditLogs();
    // 用量三图（真实 runs 轨迹）
    apiGet('/system/usage').then(renderUsage).catch(function(){
      var c = document.getElementById('usage-charts');
      if (c) c.innerHTML = '<div class="empty">用量轨迹读取失败（底座未开启 trace 或无运行记录）</div>';
    });
  }).catch(function(e){
    document.getElementById('mon-cards').innerHTML = '<div class="empty" style="grid-column:1/-1">读取统计失败：' + esc(e.message) + '</div>';
    document.getElementById('mon-eb').innerHTML = '<div class="empty">紧急刹车状态读取失败</div>';
    toast('读取监控数据失败', true);
  });
}
function loadAuditLogs() {
  var box = document.getElementById('mon-audit');
  if (!box) return;
  apiGet('/system/audit-logs?limit=12').then(function(d){
    var logs = d.logs || [];
    if (!logs.length) { box.innerHTML = '<div class="empty">暂无审计日志</div>'; return; }
    box.innerHTML = logs.map(function(l){
      var det = l.detail && typeof l.detail === 'object' ? JSON.stringify(l.detail) : (l.detail || '');
      return '<div class="audit-row"><span class="tag ' + (l.actor === 'human' ? 'manager' : 'worker') + '">' + esc(l.actor) + '</span>'
        + '<span class="audit-action">' + esc(l.action || '') + '</span>'
        + '<span class="muted" style="margin-left:auto">' + ago(l.created_at) + '</span>'
        + (det && det !== '{}' ? '<div class="mute" style="width:100%;font-size:11px;font-family:var(--mono)">' + esc(det.slice(0, 120)) + '</div>' : '')
        + '</div>';
    }).join('');
  }).catch(function(){ if (box) box.innerHTML = '<div class="empty">审计日志读取失败</div>'; });
}
function toggleEmergency() {
  // 先读当前状态，取反后真实调用底座 toggle
  apiGet('/system/stats').then(function(d){
    var next = !(d.stats && d.stats.emergency_block);
    apiPost('/system/emergency-block/toggle?active=' + next, {}).then(function(r){
      toast(next ? '紧急刹车已开启' : '已解除紧急刹车');
      loadDashboard();
    }).catch(function(e){ toast('切换失败：' + e.message, true); });
  }).catch(function(e){ toast('读取状态失败：' + e.message, true); });
}
