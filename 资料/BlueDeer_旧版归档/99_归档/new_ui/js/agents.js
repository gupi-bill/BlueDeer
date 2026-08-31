/* ============ 页面 1：Agent 列表 ============ */
function loadAgents() {
  var box = document.getElementById('agent-list');
  box.innerHTML = '<div class="loading">加载中…</div>';
  apiGet('/agents').then(function(d){
    var agents = d.agents || [];
    document.getElementById('agent-count').textContent = agents.length;
    // 当前管理岗
    return apiGet('/agents/manager/current').then(function(md){
      state.managerId = (md.manager && md.manager.agent_id) || null;
      var tag = document.getElementById('cur-manager-tag');
      if (state.managerId) {
        var m = agents.filter(function(a){ return a.agent_id === state.managerId; })[0];
        tag.style.display = '';
        tag.textContent = '管理岗：' + (m ? m.name : state.managerId);
      } else { tag.style.display = 'none'; }
      return agents;
    });
  }).then(function(agents){
    if (!agents.length) { document.getElementById('agent-list').innerHTML = '<div class="empty"><div class="ico">🤖</div>暂无注册节点，用底座 /agents/register 注册后刷新。</div>'; return; }
    var h = '<table><thead><tr><th>节点</th><th>角色</th><th>状态</th><th>能力</th><th>最后活跃</th><th style="width:130px">操作</th></tr></thead><tbody>';
    agents.forEach(function(a){
      var isManager = state.managerId && a.agent_id === state.managerId;
      var caps = (a.capabilities || []).map(function(c){ return '<span class="cap-chip">' + esc(c) + '</span>'; }).join('') || '<span class="mute">—</span>';
      var btn;
      if (isManager) {
        btn = '<button class="btn sm danger" onclick="clearManager()">撤销管理岗</button>';
      } else {
        btn = '<button class="btn sm" onclick="setManager(\'' + esc(a.agent_id) + '\')">设为管理岗</button>';
      }
      h += '<tr><td><div class="agent-cell">' + avatarHtml(a.name || a.agent_id)
        + '<div><div class="nm">' + esc(a.name || a.agent_id) + (isManager ? '<span class="badge-manager">当前管理岗</span>' : '') + '</div>'
        + '<div class="id">' + esc(a.agent_id) + '</div></div></div></td>'
        + '<td><span class="tag ' + (ROLE_COLOR[a.role] || 'worker') + '">' + esc(ROLE_TEXT[a.role] || a.role) + '</span></td>'
        + '<td><span class="tag ' + (a.status === 'online' ? 'online' : 'offline') + '">' + (a.status === 'online' ? '在线' : '离线') + '</span></td>'
        + '<td><div class="caps">' + caps + '</div></td>'
        + '<td class="muted">' + ago(a.last_seen) + '</td>'
        + '<td>' + btn + '</td></tr>';
    });
    h += '</tbody></table>';
    document.getElementById('agent-list').innerHTML = h;
  }).catch(function(e){ document.getElementById('agent-list').innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; toast('读取 Agent 列表失败', true); });
}
function setManager(agentId) {
  apiPost('/agents/manager/set', { agent_id: agentId }).then(function(d){
    toast('已设置管理岗：' + agentId);
    loadAgents();
  }).catch(function(e){ toast('设置失败：' + e.message, true); });
}
function clearManager() {
  apiPost('/agents/manager/clear', {}).then(function(d){
    toast('已撤销管理岗');
    loadAgents();
  }).catch(function(e){ toast('撤销失败：' + e.message, true); });
}

