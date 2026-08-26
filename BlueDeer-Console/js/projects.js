/* ============ 页面 10：项目空间（项目 = Agent 组 + 独立会话 + 工作流） ============ */

function loadProjects() {
  var box = document.getElementById('pj-list');
  apiGet('/projects').then(function(d){
    var list = d.projects || [];
    document.getElementById('pj-count').textContent = list.length;
    if (!list.length) { box.innerHTML = '<div class="empty"><div class="ico">📁</div>还没有项目，用上方表单创建第一个。</div>'; return; }
    box.innerHTML = list.map(function(p){
      var agents = (p.agent_ids || []).map(function(a){
        return '<img class="bubble-ava" src="' + animalImg(a) + '" title="' + esc(a) + '" onerror="this.style.display=\'none\'">';
      }).join('') || '<span class="mute">未分配 Agent</span>';
      return '<div class="run-item">'
        + '<div class="run-head"><b>' + esc(p.name) + '</b><span class="tag ' + (p.status === 'active' ? 'online' : 'offline') + '">' + esc(p.status) + '</span>'
        + '<span class="tag">' + esc(p.project_id) + '</span><span class="muted" style="margin-left:auto">' + ago(p.created_at) + '</span></div>'
        + '<div class="card-sub">' + esc(p.description || '') + '</div>'
        + '<div style="display:flex;align-items:center;gap:6px;margin:8px 0">成员：' + agents + '</div>'
        + '<div class="approval-actions">'
        + '<button class="btn sm primary" onclick="openProject(\'' + esc(p.project_id) + '\')">打开项目</button>'
        + '<button class="btn sm danger" onclick="deleteProject(\'' + esc(p.project_id) + '\')">删除</button>'
        + '</div><div id="pj-detail-' + esc(p.project_id) + '"></div></div>';
    }).join('');
  }).catch(function(e){ box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}

function createProject() {
  var name = document.getElementById('pj-name').value.trim();
  if (!name) { toast('请填项目名', true); return; }
  var agents = document.getElementById('pj-agents').value.split(/[,，]/).map(function(s){ return s.trim(); }).filter(Boolean);
  apiPost('/projects/create', { name: name, description: document.getElementById('pj-desc').value.trim(), agent_ids: agents })
    .then(function(){
      toast('项目「' + name + '」已创建');
      document.getElementById('pj-name').value = '';
      document.getElementById('pj-agents').value = '';
      loadProjects();
    }).catch(function(e){ toast('创建失败：' + e.message, true); });
}

function deleteProject(pid) {
  if (!confirm('删除项目 ' + pid + '？')) return;
  apiPost('/projects/' + pid + '/delete', {}).then(function(){
    toast('已删除项目');
    loadProjects();
  }).catch(function(e){ toast('删除失败：' + e.message, true); });
}

/* 项目详情：成员 + 独立会话 + 工作流 */
function openProject(pid) {
  var box = document.getElementById('pj-detail-' + pid);
  if (box.innerHTML) { box.innerHTML = ''; return; }
  apiGet('/projects/' + pid).then(function(d){
    var p = d.project || {}, agents = d.agents || [], msgs = d.messages || [];
    box.innerHTML = '<div class="pj-detail">'
      + '<div class="pj-sec-title">项目资料</div>'
      + '<div style="display:flex;flex-wrap:wrap;gap:6px">' + agents.map(function(a){
          return '<span class="tag worker">' + esc(a.name || a.agent_id) + ' (' + esc(a.agent_id) + ')</span>';
        }).join('') + '</div>'
      + '<div class="pj-sec-title" style="margin-top:14px">项目独立会话（task 频道）</div>'
      + (msgs.length
          ? msgs.slice(-8).reverse().map(function(m){
              return '<div class="bubble-row"><div class="bubble-main"><div class="bubble-meta"><span class="bubble-from">' + esc(m.from_agent) + '</span>'
                + '<span class="bubble-to">→ ' + esc(m.to_agent || '?') + '</span><span class="bubble-time">' + ago(m.created_at) + '</span></div>'
                + '<span class="bubble">' + esc(m.content) + '</span></div></div>';
            }).join('')
          : '<div class="mute" style="margin:8px 0">暂无会话消息</div>')
      + '<div style="margin-top:10px;display:flex;gap:8px">'
      + '<input id="pj-msg-' + pid + '" placeholder="在项目会话里发一条…" style="flex:1;padding:7px 10px;border:1px solid var(--border);border-radius:var(--radius-sm)">'
      + '<button class="btn primary sm" onclick="sendProjectMsg(\'' + pid + '\')">发送</button></div>'
      + '<div class="pj-sec-title" style="margin-top:14px">🔀 工作流（项目共用）</div>'
      + '<div class="mute" style="margin:8px 0">去「工作流」页查看/触发项目工作流</div>'
      + '</div>';
  }).catch(function(e){ box.innerHTML = '<div class="empty">' + esc(e.message) + '</div>'; });
}

function sendProjectMsg(pid) {
  var content = document.getElementById('pj-msg-' + pid).value.trim();
  if (!content) { toast('消息不能为空', true); return; }
  apiPost('/messages/send', { channel_type: 'task', from_agent: 'human', task_id: pid, content: content })
    .then(function(){
      toast('已发到项目会话');
      loadProjects();
    }).catch(function(e){ toast('发送失败：' + e.message, true); });
}
