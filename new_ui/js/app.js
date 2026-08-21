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

/* ============ 页面切换 ============ */
function switchPage(name) {
  document.querySelectorAll('.page').forEach(function(p){ p.classList.remove('active'); });
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.tab').forEach(function(t){ t.classList.toggle('active', t.getAttribute('data-page') === name); });
  if (name === 'agents') loadAgents();
  else if (name === 'approvals') loadApprovals();
  else if (name === 'messages') loadMessages();
  else if (name === 'memories') loadMemories();
  else if (name === 'skills') loadSkills();
  else if (name === 'workflows') loadWorkflows();
  else if (name === 'monitor') loadDashboard();
}
