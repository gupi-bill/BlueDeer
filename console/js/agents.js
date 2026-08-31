/* ============ 页面 1：Agent 列表（Dify 式卡片网格 + 动物形象） ============ */
// 动物形象库（来自老 BlueDeer 角色素材）：agent 名 → 动物
var ANIMALS = ['deer', 'squirrel', 'fox', 'hedgehog', 'raven', 'hare', 'badger', 'beaver', 'butterfly', 'kite', 'lark'];
function animalFor(name) {
  var s = String(name || '').toLowerCase();
  /* 先按名字直配：agent_id/名称里含动物名就用对应头像，不再哈希乱配 */
  for (var i = 0; i < ANIMALS.length; i++) {
    if (s.indexOf(ANIMALS[i]) >= 0) return ANIMALS[i];
  }
  if (s.indexOf('mgr') >= 0 || s.indexOf('manager') >= 0 || s.indexOf('调度') >= 0) return 'deer';
  if (s.indexOf('worker') >= 0 || s.indexOf('执行') >= 0) return 'squirrel';
  if (s.indexOf('tool') >= 0 || s.indexOf('工具') >= 0) return 'beaver';
  if (s.indexOf('security') >= 0 || s.indexOf('安全') >= 0) return 'hedgehog';
  var h = 0; for (var j = 0; j < s.length; j++) h = (h * 31 + s.charCodeAt(j)) >>> 0;
  return ANIMALS[h % ANIMALS.length];
}
function animalImg(name) { return 'assets/thumbs/' + animalFor(name) + '.png'; }
function loadAgents() {
  var box = document.getElementById('agent-list');
  box.innerHTML = skeletonBox(4);
  apiGet('/agents').then(function(d){
    var agents = d.agents || [];
    document.getElementById('agent-count').textContent = agents.length;
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
    if (!agents.length) { document.getElementById('agent-list').innerHTML = '<div class="empty">暂无注册节点，用底座 /agents/register 注册后刷新。</div>'; return; }
    var h = '<div class="agent-grid">';
    agents.forEach(function(a){
      var isManager = state.managerId && a.agent_id === state.managerId;
      var caps = (a.capabilities || []).map(function(c){ return '<span class="cap-chip">' + esc(c) + '</span>'; }).join('') || '<span class="mute">—</span>';
      h += '<div class="agent-card" style="cursor:pointer" onclick="openAgentDetail(\'' + esc(a.agent_id) + '\')">'
        + '<div class="agent-card-head"><img class="agent-pic" src="' + animalImg(a.name || a.agent_id) + '" alt="">'
        + '<div class="agent-card-title"><div class="nm">' + esc(a.name || a.agent_id) + '</div>'
        + '<div class="id">' + esc(a.agent_id) + '</div></div>'
        + '<span class="tag ' + (a.status === 'online' ? 'online' : 'offline') + '" style="margin-left:auto">' + (a.status === 'online' ? '在线' : '离线') + '</span></div>'
        + '<div class="agent-card-meta">'
        + '<span class="tag ' + (ROLE_COLOR[a.role] || 'worker') + '">' + esc(ROLE_TEXT[a.role] || a.role) + '</span>'
        + (isManager ? '<span class="badge-manager">当前管理岗</span>' : '')
        + '<span class="muted" style="margin-left:auto">心跳 ' + ago(a.last_seen) + '</span></div>'
        + '<div class="caps" style="margin-top:10px">' + caps + '</div>'
        + '<div class="agent-card-foot" style="margin-top:12px;display:flex;gap:8px">'
        + '<button class="btn sm ghost" style="flex:1" onclick="event.stopPropagation();openAgentDetail(\'' + esc(a.agent_id) + '\')">详情</button>'
        + (isManager
            ? '<button class="btn sm danger" style="flex:1" onclick="event.stopPropagation();clearManager()">撤销管理岗</button>'
            : '<button class="btn sm" style="flex:1" onclick="event.stopPropagation();setManager(\'' + esc(a.agent_id) + '\')">设为管理岗</button>')
        + '</div></div>';
    });
    document.getElementById('agent-list').innerHTML = h + '</div>';
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

/* ============ Agent 详情抽屉（历史活动 + 人设提示词编辑，全真实） ============ */
var agentDetailId = null;

function openAgentDetail(agentId) {
  agentDetailId = agentId;
  var m = document.getElementById('agent-detail-modal');
  if (m) m.style.display = 'flex';
  // 头部信息
  apiGet('/agents/' + encodeURIComponent(agentId)).then(function(d){
    var a = d.agent || {};
    var head = document.getElementById('ad-head');
    if (head) {
      head.innerHTML = '<img class="agent-pic" src="' + animalImg(a.name || a.agent_id) + '" alt="" style="width:56px;height:56px;border-radius:12px;object-fit:cover">'
        + '<div><div class="ad-name">' + esc(a.name || a.agent_id) + '</div>'
        + '<div class="ad-id">' + esc(a.agent_id) + ' · ' + esc(a.role) + '</div>'
        + '<div class="muted" style="font-size:12px">状态：' + (a.status === 'online' ? '在线' : '离线') + ' · ' + (a.last_seen ? '最近活动 ' + ago(a.last_seen) : '从未活动') + '</div></div>';
    }
    var tpl = document.getElementById('ad-prompt');
    if (tpl) tpl.value = a.system_prompt || '';
    var caps = document.getElementById('ad-caps');
    if (caps) caps.textContent = (a.capabilities || []).join(' / ') || '—';
    var auto = document.getElementById('ad-auto');
    if (auto) auto.textContent = (a.auto_reply && a.auto_reply.enabled) ? '已开启' : '未开启';
  }).catch(function(){});
  loadAgentActivity(agentId);
}

function closeAgentDetail() {
  var m = document.getElementById('agent-detail-modal');
  if (m) m.style.display = 'none';
}

function saveAgentPrompt() {
  if (!agentDetailId) return;
  var tpl = document.getElementById('ad-prompt');
  var content = tpl ? tpl.value : '';
  apiPost('/agents/' + encodeURIComponent(agentDetailId) + '/update', { system_prompt: content })
    .then(function(){
      toast('人设提示词已保存');
      var msg = document.getElementById('ad-prompt-msg');
      if (msg) msg.textContent = '已保存 ✓';
      setTimeout(function(){ if (msg) msg.textContent = ''; }, 2500);
      loadAgents();
    }).catch(function(e){ toast('保存失败：' + e.message, true); });
}

/* 历史活动：消息 + 审计 合并时间线 */
function loadAgentActivity(agentId) {
  var box = document.getElementById('ad-activity');
  if (box) box.innerHTML = '<div class="loading">加载中…</div>';
  Promise.all([
    apiGet('/messages/history?from_agent=' + encodeURIComponent(agentId) + '&limit=30').catch(function(){ return { messages: [] }; }),
    apiGet('/messages/history?to_agent=' + encodeURIComponent(agentId) + '&limit=30').catch(function(){ return { messages: [] }; }),
    apiGet('/system/audit-logs?actor=' + encodeURIComponent(agentId) + '&limit=30').catch(function(){ return { logs: [] }; })
  ]).then(function(res){
    var items = [];
    (res[0].messages || []).forEach(function(m){
      items.push({ ts: m.created_at, icon: '📤', txt: '发给 ' + (m.to_agent || m.task_id || '?') + '：' + String(m.content).slice(0, 60) });
    });
    (res[1].messages || []).forEach(function(m){
      items.push({ ts: m.created_at, icon: '📥', txt: '来自 ' + m.from_agent + '：' + String(m.content).slice(0, 60) });
    });
    (res[2].logs || []).forEach(function(l){
      items.push({ ts: l.ts, icon: '📌', txt: l.action + (l.target ? ' · ' + l.target : '') });
    });
    items.sort(function(a, b){ return b.ts - a.ts; });
    items = items.slice(0, 40);
    if (!box) return;
    if (!items.length) { box.innerHTML = '<div class="empty">暂无活动记录</div>'; return; }
    box.innerHTML = '<div class="timeline">' + items.map(function(it){
      return '<div class="tl-item"><span class="tl-ico">' + it.icon + '</span>'
        + '<span class="tl-txt">' + esc(it.txt) + '</span>'
        + '<span class="tl-time">' + ago(it.ts) + '</span></div>';
    }).join('') + '</div>';
  }).catch(function(){
    if (box) box.innerHTML = '<div class="empty">活动历史读取失败</div>';
  });
}

