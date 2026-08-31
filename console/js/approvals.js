/* ============ 页面 3：审批中心（记忆审批 + 工具调用审批，全真实） ============ */
/* 审批逻辑全在底座：前端只拉 pending 列表、转发同意/拒绝。 */

function loadApprovals() {
  var box = document.getElementById('approval-list');
  box.innerHTML = skeletonBox(3);
  // 并行拉记忆审批 + 工具审批
  Promise.all([
    apiGet('/memories/approvals/pending').catch(function(){ return { pending: [] }; }),
    apiGet('/tools/requests/pending').catch(function(){ return { pending: [] }; })
  ]).then(function(res){
    var mems = (res[0].pending || []).map(function(r){
      return {
        type: 'memory', request_id: r.request_id, agent_id: r.agent_id,
        title: (r.domain || '') + ' · ' + (r.action || ''),
        sub: '记忆审批',
        body: r.content || JSON.stringify(r, null, 2),
        created_at: r.created_at, kind: 'mem'
      };
    });
    var tools = (res[1].pending || []).map(function(r){
      var params = '';
      try { params = JSON.stringify(JSON.parse(r.params || '{}'), null, 2); } catch (e) { params = r.params || ''; }
      return {
        type: 'tool', request_id: r.request_id, agent_id: r.agent_id,
        title: '技能调用 · ' + (r.skill_id || '?'),
        sub: 'MCP 工具审批',
        body: (params ? '参数：\n' + params : '(无参数)'),
        created_at: r.created_at, kind: 'tool'
      };
    });
    var list = mems.concat(tools);
    document.getElementById('approval-count').textContent = list.length;
    var hint = document.getElementById('approval-hint');
    return apiGet('/agents/manager/current').then(function(md){
      state.managerId = (md.manager && md.manager.agent_id) || null;
      hint.innerHTML = state.managerId
        ? ('审批人 = <b>当前管理岗「' + esc(state.managerId) + '」</b>（底座要求只有管理岗能审批）')
        : '<span style="color:var(--red)">⚠️ 当前无管理岗在岗 —— 请先在「Agent 列表」设置管理岗，否则无法审批。</span>';
      return list;
    });
  }).then(function(list){
    if (!list.length) { document.getElementById('approval-list').innerHTML = '<div class="empty">当前没有待审批事项。</div>'; return; }
    var h = '';
    list.forEach(function(r){
      h += '<div class="approval-item">'
        + '<div class="approval-head">' + avatarHtml(r.agent_id)
        + '<div><div class="approval-title">' + esc(r.title) + '</div>'
        + '<div class="muted">' + esc(r.sub) + ' · 请求方：<b>' + esc(r.agent_id) + '</b> · ' + esc(r.request_id) + ' · ' + ago(r.created_at) + '</div></div>'
        + '<span class="tag ' + (r.kind === 'tool' ? 'online' : 'amber') + '" style="margin-left:auto">' + (r.kind === 'tool' ? '工具' : '记忆') + '</span></div>'
        + '<div class="approval-body">' + esc(r.body) + '</div>'
        + '<div class="approval-actions">'
        + '<button class="btn primary sm" onclick="decide(\'' + esc(r.request_id) + '\', true, \'' + r.kind + '\')">同意</button>'
        + '<button class="btn danger sm" onclick="decide(\'' + esc(r.request_id) + '\', false, \'' + r.kind + '\')">拒绝</button>'
        + '</div></div>';
    });
    document.getElementById('approval-list').innerHTML = h;
  }).catch(function(e){ document.getElementById('approval-list').innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; toast('读取审批队列失败', true); });
}

function decide(requestId, approve, kind) {
  if (!state.managerId) { toast('请先在 Agent 列表设置管理岗', true); return; }
  var url = kind === 'tool' ? '/tools/approvals/decide' : '/memories/approvals/decide';
  apiPost(url, { request_id: requestId, manager_id: state.managerId, approve: approve })
    .then(function(d){
      toast((approve ? '已同意' : '已拒绝') + ' ' + requestId);
      loadApprovals();
    }).catch(function(e){ toast('操作失败：' + e.message, true); });
}
