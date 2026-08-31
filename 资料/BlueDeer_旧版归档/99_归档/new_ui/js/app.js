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
}
(function(){
  try {
    if (localStorage.getItem('bd-sidebar-collapsed') === '1') {
      document.getElementById('sidebar').classList.add('collapsed');
    }
  } catch (e) {}
})();

/* ============ 页面切换 ============ */
var PAGE_TITLES = { agents: 'Agent 列表', approvals: '审批中心', messages: '消息调试', memories: '记忆池', skills: '技能注册表', workflows: '工作流', monitor: '监控' };
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
}
/* 顶栏全局刷新：调当前页的加载函数 */
function refreshCurrent() {
  var el = document.getElementById('topbar-time');
  if (el) el.textContent = '更新于 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
  var active = document.querySelector('.nav-item.active');
  var page = active ? active.getAttribute('data-page') : 'agents';
  switchPage(page);
}
