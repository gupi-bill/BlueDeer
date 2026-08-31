/* ============ 页面 2：审批中心 ============ */
function loadApprovals() {
  var box = document.getElementById('approval-list');
  box.innerHTML = '<div class="loading">加载中…</div>';
  apiGet('/memories/approvals/pending').then(function(d){
    var list = d.pending || [];
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
    if (!list.length) { document.getElementById('approval-list').innerHTML = '<div class="empty"><div class="ico">✅</div>当前没有待审批事项。</div>'; return; }
    var h = '';
    list.forEach(function(r){
      var act = r.action || '';
      var dom = r.domain || '';
      h += '<div class="approval-item">'
        + '<div class="approval-head">' + avatarHtml(r.agent_id)
        + '<div><div class="approval-title">' + esc(dom) + ' · ' + esc(act) + '</div>'
        + '<div class="muted">请求方：<b>' + esc(r.agent_id) + '</b> · 单号 ' + esc(r.request_id) + ' · ' + ago(r.created_at) + '</div></div></div>'
        + '<div class="approval-body">' + esc(r.payload || JSON.stringify(r, null, 2)) + '</div>'
        + '<div class="approval-actions">'
        + '<button class="btn primary sm" onclick="decide(\'' + esc(r.request_id) + '\', true)">同意</button>'
        + '<button class="btn danger sm" onclick="decide(\'' + esc(r.request_id) + '\', false)">拒绝</button>'
        + '</div></div>';
    });
    document.getElementById('approval-list').innerHTML = h;
  }).catch(function(e){ document.getElementById('approval-list').innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; toast('读取审批队列失败', true); });
}
function decide(requestId, approve) {
  if (!state.managerId) { toast('请先在 Agent 列表设置管理岗', true); return; }
  apiPost('/memories/approvals/decide', { request_id: requestId, manager_id: state.managerId, approve: approve })
    .then(function(d){
      toast((approve ? '已同意' : '已拒绝') + ' ' + requestId);
      loadApprovals();
    }).catch(function(e){ toast('操作失败：' + e.message, true); });
}

