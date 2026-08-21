/* ============ 页面 5：工作流 ============ */
var NODE_COLOR = { agent:'#1e6fff', tool:'#6d5ae0', memory_write:'#0ea5a4', memory_read:'#0ea5a4', approval:'#e08a00' };
function loadWorkflows() {
  apiGet('/workflows').then(function(d){
    var list = d.workflows || [];
    document.getElementById('wf-count').textContent = list.length;
    var box = document.getElementById('wf-list');
    if (!list.length) { box.innerHTML = '<div class="empty"><div class="ico">🔀</div>暂无工作流，用上方表单创建。</div>'; return; }
    box.innerHTML = list.map(function(wf){
      return '<div class="run-item"><div class="run-head"><b>' + esc(wf.name || wf.workflow_id) + '</b>'
        + '<span class="tag">' + esc(wf.workflow_id) + '</span>'
        + '<span class="tag ' + (wf.status === 'active' ? 'online' : 'offline') + '">' + esc(wf.status || 'active') + '</span></div>'
        + '<div class="card-sub">' + esc(wf.description || '') + '</div>'
        + '<div class="wf-canvas">' + renderWfSvg(wf.definition) + '</div>'
        + '<div class="approval-actions" style="margin-top:10px">'
        + '<button class="btn primary sm" onclick="runWorkflow(\'' + esc(wf.workflow_id) + '\')">▶ 运行</button>'
        + '<button class="btn sm" onclick="loadWorkflowRuns(\'' + esc(wf.workflow_id) + '\')">查看 run</button>'
        + '<button class="btn danger sm" onclick="deleteWorkflow(\'' + esc(wf.workflow_id) + '\')">删除</button>'
        + '</div><div id="wf-runs-' + esc(wf.workflow_id) + '"></div></div>';
    }).join('');
  }).catch(function(e){ document.getElementById('wf-list').innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}
function renderWfSvg(def) {
  var nodes = (def && def.nodes) || [];
  var edges = (def && def.edges) || [];
  var pos = {}; var perRow = 4;
  nodes.forEach(function(n, i){ var c = i % perRow, r = Math.floor(i / perRow); pos[n.id] = { x: 100 + c * 170, y: 50 + r * 90 }; });
  var w = Math.max(500, perRow * 170 + 80);
  var h = Math.max(140, Math.ceil(nodes.length / perRow) * 90 + 60);
  var s = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="230">';
  s += '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#9aa0a8"/></marker></defs>';
  edges.forEach(function(e){ var a = pos[e.source], b = pos[e.target]; if (!a || !b) return; s += '<line class="wf-edge" x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" marker-end="url(#arrow)"/>'; });
  nodes.forEach(function(n){ var p = pos[n.id]; if (!p) return; var c = NODE_COLOR[n.type] || '#1e6fff';
    s += '<g transform="translate(' + p.x + ',' + p.y + ')">';
    s += '<rect class="wf-node" x="-66" y="-19" width="132" height="38" rx="8"/>';
    s += '<rect x="-66" y="-19" width="6" height="38" rx="3" fill="' + c + '"/>';
    s += '<text class="wf-node-text" x="-52" y="-3">' + esc(n.type) + '</text>';
    s += '<text class="wf-node-text" x="-52" y="12" font-size="9" fill="#9aa0a8">' + esc(n.id) + '</text>';
    s += '</g>'; });
  s += '</svg>';
  return s;
}
function createWorkflow() {
  var name = document.getElementById('wf-name').value.trim();
  var defText = document.getElementById('wf-def').value.trim();
  if (!name || !defText) { toast('名称和 Definition 必填', true); return; }
  var def;
  try { def = JSON.parse(defText); } catch(e) { toast('Definition 不是合法 JSON：' + e.message, true); return; }
  apiPost('/workflows/create', { name: name, description: document.getElementById('wf-desc').value.trim(), definition: def }).then(function(d){
    toast('已创建 ' + d.workflow_id);
    loadWorkflows();
  }).catch(function(e){ toast('创建失败：' + e.message, true); });
}
function runWorkflow(id) {
  apiPost('/workflows/' + id + '/run?trigger_by=human', {}).then(function(d){
    toast('运行：' + esc(d.status || '已触发') + (d.run_id ? ' · ' + d.run_id : ''));
    loadWorkflowRuns(id);
  }).catch(function(e){ toast('运行失败：' + e.message, true); });
}
function loadWorkflowRuns(id) {
  var box = document.getElementById('wf-runs-' + id);
  box.innerHTML = '<div class="loading">读取 run…</div>';
  apiGet('/workflows/' + id + '/runs').then(function(d){
    var runs = d.runs || [];
    if (!runs.length) { box.innerHTML = '<div class="mute" style="padding:8px 0">暂无运行记录。</div>'; return; }
    box.innerHTML = runs.map(function(r){
      var awaiting = r.status === 'awaiting_approval';
      var statusTag = { running:'进行中', done:'完成', failed:'失败', awaiting_approval:'待审批', pending:'待执行' }[r.status] || r.status;
      var actions = awaiting
        ? '<button class="btn primary sm" onclick="decideWorkflowRun(\'' + esc(r.run_id) + '\', true)">通过</button>'
          + '<button class="btn danger sm" onclick="decideWorkflowRun(\'' + esc(r.run_id) + '\', false)">拒绝</button>'
        : '';
      return '<div class="run-item" style="margin-top:10px"><div class="run-head"><b>' + esc(r.run_id) + '</b><span class="tag">' + esc(statusTag) + '</span>'
        + (r.current_node ? '<span class="muted">当前节点 ' + esc(r.current_node) + '</span>' : '') + '</div>'
        + (r.error ? '<div class="muted" style="color:var(--red)">' + esc(r.error) + '</div>' : '') + actions + '</div>';
    }).join('');
  }).catch(function(e){ box.innerHTML = '<div class="muted">读取失败：' + esc(e.message) + '</div>'; });
}
function decideWorkflowRun(runId, approve) {
  var path = '/workflows/runs/' + runId + '/' + (approve ? 'approve' : 'deny') + '?manager_id=human';
  apiPost(path, {}).then(function(d){ toast(approve ? '已通过' : '已拒绝'); loadWorkflows(); })
    .catch(function(e){ toast('操作失败：' + e.message, true); });
}
function deleteWorkflow(id) {
  apiPost('/workflows/' + id + '/delete', {}).then(function(d){ toast('已删除'); loadWorkflows(); })
    .catch(function(e){ toast('删除失败：' + e.message, true); });
}

