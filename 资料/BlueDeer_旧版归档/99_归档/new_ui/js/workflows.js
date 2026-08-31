/* ============ 页面 5：工作流（n8n 式：画布 + 右侧节点配置面板） ============ */
var NODE_COLOR = { agent:'#1e6fff', tool:'#6d5ae0', memory_write:'#0ea5a4', memory_read:'#0ea5a4', approval:'#e08a00' };
var NODE_HINT = { agent:'给 Agent 发消息', tool:'调用技能(走审批)', memory_write:'写记忆(走审批)', memory_read:'读记忆', approval:'审批挂起点' };
function loadWorkflows() {
  apiGet('/workflows').then(function(d){
    var list = d.workflows || [];
    document.getElementById('wf-count').textContent = list.length;
    var box = document.getElementById('wf-list');
    if (!list.length) { box.innerHTML = '<div class="empty"><div class="ico">🔀</div>暂无工作流，用上方表单创建。</div>'; return; }
    box.innerHTML = list.map(function(wf){
      return '<div class="run-item"><div class="run-head"><b>' + esc(wf.name || wf.workflow_id) + '</b>'
        + '<span class="tag">' + esc(wf.workflow_id) + '</span>'
        + '<span class="tag ' + (wf.status === 'active' ? 'online' : 'offline') + '">' + esc(wf.status || 'active') + '</span>'
        + '<span class="mute" style="margin-left:auto">点击画布节点查看/编辑配置</span></div>'
        + '<div class="card-sub">' + esc(wf.description || '') + '</div>'
        + '<div class="wf-layout"><div class="wf-canvas">' + renderWfSvg(wf.definition, wf.workflow_id) + '</div>'
        + '<div class="wf-panel" id="wf-panel-' + esc(wf.workflow_id) + '"><div class="mute" style="padding:14px;font-size:12px">点选画布节点，在此查看 / 编辑节点配置（保存调用底座 update，真实生效）</div></div></div>'
        + '<div class="approval-actions" style="margin-top:10px">'
        + '<button class="btn primary sm" onclick="runWorkflow(\'' + esc(wf.workflow_id) + '\')">▶ 运行</button>'
        + '<button class="btn sm" onclick="loadWorkflowRuns(\'' + esc(wf.workflow_id) + '\')">查看 run</button>'
        + '<button class="btn danger sm" onclick="deleteWorkflow(\'' + esc(wf.workflow_id) + '\')">删除</button>'
        + '</div><div id="wf-runs-' + esc(wf.workflow_id) + '"></div></div>';
    }).join('');
  }).catch(function(e){ document.getElementById('wf-list').innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}
function renderWfSvg(def, wfId) {
  var nodes = (def && def.nodes) || [];
  var edges = (def && def.edges) || [];
  var pos = {}; var perRow = 3;
  nodes.forEach(function(n, i){ var c = i % perRow, r = Math.floor(i / perRow); pos[n.id] = { x: 110 + c * 180, y: 55 + r * 100 }; });
  var w = Math.max(540, perRow * 180 + 90);
  var h = Math.max(150, Math.ceil(nodes.length / perRow) * 100 + 70);
  var s = '<svg viewBox="0 0 ' + w + ' ' + h + '" width="100%" height="240">';
  s += '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="#9aa0a8"/></marker></defs>';
  edges.forEach(function(e){ var a = pos[e.source], b = pos[e.target]; if (!a || !b) return; s += '<line class="wf-edge" x1="' + a.x + '" y1="' + a.y + '" x2="' + b.x + '" y2="' + b.y + '" marker-end="url(#arrow)"/>'; });
  nodes.forEach(function(n){ var p = pos[n.id]; if (!p) return; var c = NODE_COLOR[n.type] || '#1e6fff';
    s += '<g transform="translate(' + p.x + ',' + p.y + ')" class="wf-node" style="cursor:pointer" onclick="showWfNode(\'' + esc(wfId) + '\',\'' + esc(n.id) + '\')" title="' + esc((NODE_HINT[n.type]||'') + ' · 点击编辑') + '">';
    s += '<rect x="-70" y="-20" width="140" height="40" rx="9"/>';
    s += '<rect x="-70" y="-20" width="6" height="40" rx="3" fill="' + c + '"/>';
    s += '<text class="wf-node-text" x="-56" y="-4" font-weight="600">' + esc(n.type) + '</text>';
    s += '<text class="wf-node-text" x="-56" y="13" font-size="9" fill="#9aa0a8">' + esc(n.id) + '</text>';
    s += '</g>'; });
  s += '</svg>';
  return s;
}
/* 右侧配置面板：查看/编辑单个节点（n8n 式） */
function showWfNode(wfId, nodeId) {
  apiGet('/workflows/' + wfId).then(function(d){
    var wf = d.workflow || {};
    var def = wf.definition || { nodes: [], edges: [] };
    var node = (def.nodes || []).filter(function(n){ return n.id === nodeId; })[0];
    var panel = document.getElementById('wf-panel-' + wfId);
    if (!panel) return;
    if (!node) { panel.innerHTML = '<div class="mute" style="padding:14px">节点不存在</div>'; return; }
    panel.innerHTML = '<div class="wf-panel-head"><b>节点配置</b><span class="tag">' + esc(node.type) + '</span><button class="btn ghost sm" style="margin-left:auto" onclick="document.getElementById(\'wf-panel-' + esc(wfId) + '\').innerHTML=\'<div class=&quot;mute&quot; style=&quot;padding:14px;font-size:12px&quot;>点选画布节点，在此查看 / 编辑节点配置</div>\'">✕</button></div>'
      + '<div class="muted" style="margin:6px 0 10px">' + esc(NODE_HINT[node.type] || '') + ' · 节点 <b>' + esc(nodeId) + '</b></div>'
      + '<label style="font-size:11px;color:var(--mute)">id</label>'
      + '<input id="wf-nd-id" value="' + esc(node.id) + '" style="width:100%;margin:3px 0 8px">'
      + '<label style="font-size:11px;color:var(--mute)">type</label>'
      + '<input id="wf-nd-type" value="' + esc(node.type) + '" style="width:100%;margin:3px 0 8px">'
      + '<label style="font-size:11px;color:var(--mute)">data (JSON)</label>'
      + '<textarea id="wf-nd-data" rows="6" style="width:100%;font-family:var(--mono);font-size:11.5px;margin:3px 0 10px">' + esc(JSON.stringify(node.data || {}, null, 2)) + '</textarea>'
      + '<button class="btn primary sm" style="width:100%" onclick="saveWfNode(\'' + esc(wfId) + '\',\'' + esc(nodeId) + '\')">保存节点（调底座 update）</button>';
  }).catch(function(e){
    var panel = document.getElementById('wf-panel-' + wfId);
    if (panel) panel.innerHTML = '<div class="mute" style="padding:14px">读取失败：' + esc(e.message) + '</div>';
  });
}
function saveWfNode(wfId, nodeId) {
  apiGet('/workflows/' + wfId).then(function(d){
    var wf = d.workflow || {};
    var def = wf.definition || { nodes: [], edges: [] };
    var node = (def.nodes || []).filter(function(n){ return n.id === nodeId; })[0];
    if (!node) { toast('节点不存在', true); return; }
    node.id = document.getElementById('wf-nd-id').value.trim() || node.id;
    node.type = document.getElementById('wf-nd-type').value.trim() || node.type;
    var dataText = document.getElementById('wf-nd-data').value.trim();
    try { node.data = dataText ? JSON.parse(dataText) : {}; }
    catch (e) { toast('data 不是合法 JSON：' + e.message, true); return; }
    apiPost('/workflows/' + wfId + '/update', { definition: def }).then(function(){
      toast('节点已保存（真实写入底座）✓');
      loadWorkflows();
    }).catch(function(e){ toast('保存失败：' + e.message, true); });
  }).catch(function(e){ toast('读取失败：' + e.message, true); });
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

