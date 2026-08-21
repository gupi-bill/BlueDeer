/* ============ 页面 7：监控仪表盘 ============ */
/* 全部统计来自底座 /system/stats，前端零计算。 */
var STAT_DEFS = [
  { key: 'agents_online', label: '在线 Agent', sub: 'agents_total', color: 'var(--accent)' },
  { key: 'approvals_pending', label: '待审批（记忆）', sub: 'memory_approvals', color: 'var(--amber)' },
  { key: 'tool_pending', label: '待审批（工具）', sub: 'tool_requests', color: 'var(--amber)' },
  { key: 'workflows_running', label: '运行中工作流', sub: 'workflow_runs', color: 'var(--green)' },
  { key: 'workflows_active', label: '活跃工作流', sub: 'workflows', color: 'var(--accent-2, #6d5ae0)' },
  { key: 'tasks_pending', label: '进行中任务', sub: 'tasks', color: 'var(--green)' },
  { key: 'messages_total', label: '消息总量', sub: 'messages', color: 'var(--text-dim)' }
];
function loadDashboard() {
  apiGet('/system/stats').then(function(d){
    var st = d.stats || {};
    document.getElementById('mon-time').textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
    // 统计卡
    var grid = document.getElementById('mon-cards');
    grid.innerHTML = STAT_DEFS.map(function(s){
      var v = st[s.key] != null ? st[s.key] : '—';
      return '<div class="stat-card"><div class="stat-num" style="color:' + s.color + '">' + esc(String(v)) + '</div><div class="stat-label">' + esc(s.label) + '</div><div class="mute" style="font-size:11px">' + esc(s.sub) + '</div></div>';
    }).join('');
    // 紧急刹车
    var eb = !!st.emergency_block;
    var el = document.getElementById('mon-eb');
    el.innerHTML = '<div class="eb-state ' + (eb ? 'on' : 'off') + '"><b>' + (eb ? '🛑 紧急刹车已开启' : '✅ 正常 · 未刹车') + '</b><span class="muted">开启后底座拒绝所有消息发送与写记忆</span></div>'
      + '<button class="btn ' + (eb ? '' : 'danger') + '" onclick="toggleEmergency()">' + (eb ? '解除紧急刹车' : '开启紧急刹车') + '</button>';
  }).catch(function(e){
    document.getElementById('mon-cards').innerHTML = '<div class="empty" style="grid-column:1/-1">读取统计失败：' + esc(e.message) + '</div>';
    document.getElementById('mon-eb').innerHTML = '<div class="empty">紧急刹车状态读取失败</div>';
    toast('读取监控数据失败', true);
  });
}
function toggleEmergency() {
  // 先读当前状态，取反后真实调用底座 toggle
  apiGet('/system/stats').then(function(d){
    var next = !(d.stats && d.stats.emergency_block);
    apiPost('/system/emergency-block/toggle?active=' + next, {}).then(function(r){
      toast(next ? '🛑 紧急刹车已开启' : '✅ 已解除紧急刹车');
      loadDashboard();
    }).catch(function(e){ toast('切换失败：' + e.message, true); });
  }).catch(function(e){ toast('读取状态失败：' + e.message, true); });
}
