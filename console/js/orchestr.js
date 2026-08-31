/* ============ 页面 8：Agent 编排（子 Agent 拆分 + 互相委托调用） ============ */
/* 全部数据/操作来自底座真实 API：/agents /agents/{id}/autoreply /agents/delegate */

function loadOrchestrate() {
  // 注册表单预填底座默认自动应答模板（设置中心可改）
  apiGet('/system/settings').then(function(d){
    var s = (d && d.settings) || {};
    var tpl = document.getElementById('orch-template');
    if (tpl && s.default_auto_reply_template) tpl.value = s.default_auto_reply_template;
  }).catch(function(){});
  loadOrchAgents();
  loadOrchFlow();
}

/* ---- 子 Agent 列表 + 自动应答配置 + 委托下拉 ---- */
var orchAgents = [];
function loadOrchAgents() {
  var box = document.getElementById('orch-list');
  box.innerHTML = '<div class="loading">加载中…</div>';
  apiGet('/agents').then(function(d){
    orchAgents = d.agents || [];
    document.getElementById('orch-count').textContent = orchAgents.length;
    // 委托下拉
    fillOrchSelects(orchAgents);
    if (!orchAgents.length) {
      box.innerHTML = '<div class="empty"><div class="ico">🧩</div>还没有 Agent，用上方表单注册第一个子 Agent。</div>';
      return;
    }
    box.innerHTML = orchAgents.map(function(a){
      var ar = a.auto_reply || {};
      var on = !!ar.enabled;
      return '<div class="agent-card">'
        + '<div class="agent-card-head">' + avatarHtml(a.name || a.agent_id)
        + '<div class="agent-card-title"><div class="nm">' + esc(a.name || a.agent_id) + '</div>'
        + '<div class="id">' + esc(a.agent_id) + '</div></div>'
        + '<span class="tag ' + (a.status === 'online' ? 'online' : 'offline') + '" style="margin-left:auto">' + (a.status === 'online' ? '在线' : '离线') + '</span></div>'
        + '<div class="agent-card-meta"><span class="tag ' + esc(a.role) + '">' + esc(a.role) + '</span>'
        + '<span class="tag ' + (on ? 'online' : 'offline') + '">自动应答 ' + (on ? '开' : '关') + '</span></div>'
        + '<div class="mute" style="font-size:11.5px;margin-top:8px;word-break:break-all">' + esc((a.capabilities || []).join(' / ') || '—') + '</div>'
        + '<div class="form-row" style="margin-top:10px;align-items:flex-end">'
        + '<div class="field" style="flex:2.4"><label>应答模板</label><input class="ar-tpl" data-id="' + esc(a.agent_id) + '" value="' + esc(ar.reply_template || '收到，{from}。任务「{task}」已受理。') + '"></div>'
        + '<div class="field" style="width:80px"><label>自动应答</label>'
        + '<label class="switch-mini"><input type="checkbox" class="ar-sw" data-id="' + esc(a.agent_id) + '"' + (on ? ' checked' : '') + '><span></span></label></div>'
        + '<button class="btn sm" onclick="saveAutoreply(\'' + esc(a.agent_id) + '\')">保存应答</button></div>'
        + '</div>';
    }).join('');
    // 开关即时保存
    document.querySelectorAll('.ar-sw').forEach(function(cb){
      cb.addEventListener('change', function(){
        var id = cb.getAttribute('data-id');
        var tpl = document.querySelector('.ar-tpl[data-id="' + id + '"]');
        saveAutoreply(id, cb.checked, tpl ? tpl.value : '');
      });
    });
  }).catch(function(e){
    box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>';
  });
}

function fillOrchSelects(agents) {
  var f = document.getElementById('orch-from');
  var t = document.getElementById('orch-to');
  if (!f || !t) return;
  var opts = agents.map(function(a){
    return '<option value="' + esc(a.agent_id) + '">' + esc(a.name || a.agent_id) + '</option>';
  }).join('');
  f.innerHTML = opts;
  t.innerHTML = opts;
  // 默认：调用方=第一个，目标=第二个（如有）
  if (agents.length > 1) t.selectedIndex = 1;
}

/* ---- 自动应答配置：真实写库 ---- */
function saveAutoreply(id, enabled, template) {
  var tpl = (template !== undefined) ? template
    : (document.querySelector('.ar-tpl[data-id="' + id + '"]') || {}).value || '';
  var on = (enabled !== undefined) ? !!enabled
    : !!((document.querySelector('.ar-sw[data-id="' + id + '"]') || {}).checked);
  apiPost('/agents/' + encodeURIComponent(id) + '/autoreply', {
    enabled: on, reply_template: tpl
  }).then(function(d){
    toast('「' + id + '」自动应答已' + (d.auto_reply.enabled ? '开启' : '关闭'));
    loadOrchAgents();
  }).catch(function(e){ toast('保存应答失败：' + e.message, true); });
}

/* ---- 注册子 Agent ---- */
function registerSubAgent() {
  var id = document.getElementById('orch-id').value.trim();
  var name = document.getElementById('orch-name').value.trim();
  var role = document.getElementById('orch-role').value;
  var caps = document.getElementById('orch-caps').value.split(/[,，]/).map(function(s){ return s.trim(); }).filter(Boolean);
  var tpl = document.getElementById('orch-template').value.trim();
  if (!id || !name) { toast('请填 ID 和名字', true); return; }
  apiPost('/agents/register', {
    agent_id: id, name: name, role: role, capabilities: caps,
    auto_reply: { enabled: true, reply_template: tpl || '收到，{from}。任务「{task}」已受理，正在处理…' }
  }).then(function(d){
    toast('子 Agent「' + name + '」注册成功' + (d.registered_before ? '（已存在，更新）' : ''));
    document.getElementById('orch-id').value = '';
    document.getElementById('orch-name').value = '';
    document.getElementById('orch-caps').value = '';
    loadOrchAgents();
  }).catch(function(e){ toast('注册失败：' + e.message, true); });
}

/* ---- 委托调用：Agent 互相调用 ---- */
function delegateTask() {
  var from = document.getElementById('orch-from').value;
  var to = document.getElementById('orch-to').value;
  var task = document.getElementById('orch-task').value.trim();
  var box = document.getElementById('orch-result');
  if (!from || !to) { toast('请选调用方和目标 Agent', true); return; }
  if (!task) { toast('请填任务内容', true); return; }
  box.innerHTML = '<div class="loading">调用中…</div>';
  apiPost('/agents/delegate', { from_agent: from, to_agent: to, task_content: task })
    .then(function(d){
      var h = '<div class="delegate-result">';
      h += '<div class="dlg-row"><span class="dlg-tag">请求</span><b>' + esc(from) + '</b> → <b>' + esc(to) + '</b></div>';
      h += '<div class="dlg-row"><span class="dlg-tag">任务</span>' + esc(task) + '</div>';
      if (d.status === 'replied' && d.reply) {
        h += '<div class="dlg-row"><span class="dlg-tag ok">应答</span><div class="dlg-reply">' + esc(d.reply) + '</div></div>';
        h += '<div class="mute" style="margin-top:8px">目标子 Agent 已自动应答，闭环完成（消息已入流水）</div>';
      } else {
        h += '<div class="dlg-row"><span class="dlg-tag warn">待处理</span><span class="muted">' + esc(d.hint || '目标未开启自动应答，任务已进其收件箱') + '</span></div>';
      }
      h += '</div>';
      box.innerHTML = h;
      toast(d.status === 'replied' ? '委托成功，已收到应答' : '委托已发出，等待目标处理');
      document.getElementById('orch-task').value = '';
      loadOrchFlow();
    })
    .catch(function(e){
      box.innerHTML = '<div class="empty">调用失败：' + esc(e.message) + '</div>';
      toast('委托失败：' + e.message, true);
    });
}

/* ---- 编排对话流：Agent 间消息往来 ---- */
function loadOrchFlow() {
  var box = document.getElementById('orch-flow');
  apiGet('/messages/history?limit=80').then(function(d){
    var list = (d.messages || []).filter(function(m){
      // 只显示 agent 间往来（排除 system 与 task 频道），或全部 agent 参与的消息
      return m.channel_type === 'private' && m.from_agent && m.from_agent !== 'system';
    });
    if (!list.length) {
      box.innerHTML = '<div class="empty"><div class="ico">🔁</div>还没有 Agent 间委托往来，去上面发起一次调用。</div>';
      return;
    }
    var h = list.slice().reverse().map(function(m){
      return '<div class="bubble-row">'
        + avatarHtml(m.from_agent)
        + '<div class="bubble-main">'
        + '<div class="bubble-meta"><span class="bubble-from">' + esc(m.from_agent) + '</span>'
        + '<span class="bubble-to">→ ' + esc(m.to_agent || '?') + '</span>'
        + '<span class="bubble-time">' + ago(m.created_at) + '</span></div>'
        + '<span class="bubble">' + esc(m.content) + '</span>'
        + '</div></div>';
    }).join('');
    box.innerHTML = h;
  }).catch(function(e){
    box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>';
  });
}
