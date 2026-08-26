/* ============ 健康检测 ============ */
function checkApi() {
  fetch(API + '/').then(function(r){ return r.json(); }).then(function(j){
    var dot = document.getElementById('api-dot'), st = document.getElementById('api-status');
    dot.className = 'dot up'; st.textContent = '底座在线 v' + (j.version || '');
  }).catch(function(){
    var dot = document.getElementById('api-dot'), st = document.getElementById('api-status');
    dot.className = 'dot down'; st.textContent = '底座离线（' + API + '）';
  });
}

/* ============ 侧边栏折叠（借鉴 n8n 可折叠导航，状态记忆） ============ */
function toggleSidebar() {
  var sb = document.getElementById('sidebar');
  var collapsed = sb.classList.toggle('collapsed');
  try { localStorage.setItem('bd-sidebar-collapsed', collapsed ? '1' : '0'); } catch (e) {}
  var sc = document.getElementById('set-sidebar-collapsed');
  if (sc) sc.checked = collapsed;
}
(function(){
  try {
    if (localStorage.getItem('bd-sidebar-collapsed') === '1') {
      document.getElementById('sidebar').classList.add('collapsed');
    }
  } catch (e) {}
})();

/* ============ 自动刷新（设置中心可配间隔） ============ */
var _refreshTimer = null;
function startAutoRefresh() {
  if (_refreshTimer) clearInterval(_refreshTimer);
  var sec = 0;
  try { sec = parseInt(localStorage.getItem('bd-refresh') || '0', 10) || 0; } catch (e) {}
  if (!sec) return;
  _refreshTimer = setInterval(function(){
    var active = document.querySelector('.nav-item.active');
    if (!active) return;
    var name = active.getAttribute('data-page');
    if (name === 'agents') loadAgents();
    else if (name === 'approvals') loadApprovals();
    else if (name === 'messages') loadMessages();
    else if (name === 'memories') loadMemories();
    else if (name === 'skills') loadSkills();
    else if (name === 'workflows') loadWorkflows();
    else if (name === 'monitor') loadDashboard();
    else if (name === 'orchestrate') loadOrchestrate();
    else if (name === 'ide') ideRefreshTree();
    var t = document.getElementById('topbar-time');
    if (t) t.textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
  }, sec * 1000);
}
startAutoRefresh();

/* ============ 页面切换 ============ */
var PAGE_TITLES = { monitor: '总览', agents: 'Agent 列表', approvals: '审批中心', messages: '聊天会话', audit: '审计日志', memories: '记忆池', skills: '技能注册表', workflows: '工作流', projects: '项目空间', schedule: '定时任务', orchestrate: 'Agent 编排', ide: 'IDE 工作台' };
function switchPage(name) {
  document.querySelectorAll('.page').forEach(function(p){ p.classList.remove('active'); });
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(function(t){ t.classList.toggle('active', t.getAttribute('data-page') === name); });
  var crumb = document.getElementById('crumb-current');
  if (crumb) crumb.textContent = PAGE_TITLES[name] || name;
  if (name === 'agents') loadAgents();
  else if (name === 'approvals') loadApprovals();
  else if (name === 'messages') loadMessages();
  else if (name === 'memories') loadMemories();
  else if (name === 'skills') loadSkills();
  else if (name === 'workflows') loadWorkflows();
  else if (name === 'monitor') loadDashboard();
  else if (name === 'orchestrate') loadOrchestrate();
  else if (name === 'ide') loadIde();
  else if (name === 'projects') loadProjects();
  else if (name === 'schedule') loadCrons();
  else if (name === 'audit') loadAudit();
}
/* 顶栏全局刷新：调当前页的加载函数 */
function refreshCurrent() {
  var el = document.getElementById('topbar-time');
  if (el) el.textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
  var active = document.querySelector('.nav-item.active');
  var page = active ? active.getAttribute('data-page') : 'agents';
  if (page === 'ide') { ideRefreshTree(); return; }
  switchPage(page);
}
