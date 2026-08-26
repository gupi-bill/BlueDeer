/* ============ 页面 3：聊天会话（会话列表 + 聊天窗口 + 工具卡片 + 停止） ============ */
/* 数据全真实：/agents 会话目标、/messages/history 历史、/messages/send 发送。 */

var chatTarget = null;      // 当前对话的 Agent
var chatFrom = 'human';     // 发信人（管理岗优先）
var _streamTimer = null;

function loadMessages() {
  // 会话列表 = Agent 列表（真实）
  Promise.all([
    apiGet('/agents').catch(function(){ return { agents: [] }; }),
    apiGet('/agents/manager/current').catch(function(){ return { manager: null }; })
  ]).then(function(res){
    var agents = res[0].agents || [];
    var mgr = (res[1].manager && res[1].manager.agent_id) || null;
    chatFrom = mgr || 'human';
    var box = document.getElementById('chat-targets');
    if (!agents.length) { box.innerHTML = '<div class="empty">暂无 Agent，先去「Agent 列表」看看</div>'; return; }
    box.innerHTML = agents.map(function(a){
      return '<div class="chat-target' + (chatTarget === a.agent_id ? ' active' : '') + '" data-target="' + esc(a.agent_id) + '">'
        + '<img class="bubble-ava" src="' + animalImg(a.name || a.agent_id) + '" alt="" onerror="this.style.display=\'none\'">'
        + '<div style="min-width:0"><div class="ct-name">' + esc(a.name || a.agent_id) + '</div>'
        + '<div class="mute" style="font-size:11px">' + esc(a.agent_id) + (a.status === 'online' ? ' · 在线' : ' · 离线') + '</div></div></div>';
    }).join('');
  });
  if (chatTarget) loadChatHistory();
}

document.addEventListener('click', function(e){
  var t = e.target.closest('.chat-target');
  if (t) { chatTarget = t.getAttribute('data-target'); loadMessages(); }
});

function loadChatHistory() {
  var head = document.getElementById('chat-head');
  if (head) head.innerHTML = '<b>与 ' + esc(chatTarget) + ' 的会话</b><span class="mute" style="font-size:12px" id="chat-head-sub">发信人：' + esc(chatFrom) + ' · 真实消息流</span>';
  apiGet('/messages/history?limit=80').then(function(d){
    var all = d.messages || [];
    var list = all.filter(function(m){
      return m.channel_type === 'private'
        && ((m.from_agent === chatFrom && m.to_agent === chatTarget)
         || (m.from_agent === chatTarget && m.to_agent === chatFrom));
    });
    var box = document.getElementById('msg-stream');
    if (!box) return;
    if (!list.length) { box.innerHTML = '<div class="empty">还没有对话，发第一条吧。</div>'; return; }
    // 打字机渲染（数据真实，仅渲染动效）：最后一条逐字出
    var rendered = list.slice(0, -1);
    box.innerHTML = rendered.map(function(m){ return msgBubbleHtml(m); }).join('');
    var last = list[list.length - 1];
    typewrite(last);
    box.scrollTop = box.scrollHeight;
  }).catch(function(e){
    var box = document.getElementById('msg-stream');
    if (box) box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>';
  });
}

function msgBubbleHtml(m) {
  var isCode = typeof m.content === 'string' && m.content.charAt(0) === '{';
  var mine = m.from_agent === chatFrom;
  // 工具调用识别：内容含 skill_id / toolreq 等 → 工具卡片
  var isTool = /skill_id|toolreq|tool_call|request_id/.test(String(m.content));
  if (isTool && isCode) {
    return '<div class="bubble-row ' + (mine ? 'mine' : '') + '">'
      + (mine ? '' : '<img class="bubble-ava" src="' + animalImg(m.from_agent) + '" onerror="this.style.display=\'none\'">')
      + '<div class="bubble-main"><div class="bubble-meta"><span class="bubble-from">' + esc(m.from_agent) + '</span>'
      + '<span class="bubble-to">→ ' + esc(m.to_agent || '?') + '</span><span class="bubble-time">' + ago(m.created_at) + '</span></div>'
      + '<div class="tool-card"><div class="tool-card-head">工具调用</div><pre>' + esc(m.content) + '</pre></div></div>'
      + (mine ? '<img class="bubble-ava" src="' + animalImg(m.from_agent) + '" onerror="this.style.display=\'none\'">' : '')
      + '</div>';
  }
  return '<div class="bubble-row ' + (mine ? 'mine' : '') + '">'
    + (mine ? '' : '<img class="bubble-ava" src="' + animalImg(m.from_agent) + '" onerror="this.style.display=\'none\'">')
    + '<div class="bubble-main"><div class="bubble-meta"><span class="bubble-from">' + esc(m.from_agent) + '</span>'
    + '<span class="bubble-to">→ ' + esc(m.to_agent || '?') + '</span><span class="bubble-time">' + ago(m.created_at) + '</span></div>'
    + '<span class="bubble' + (isCode ? ' code' : '') + '">' + esc(m.content) + '</span></div>'
    + (mine ? '<img class="bubble-ava" src="' + animalImg(m.from_agent) + '" onerror="this.style.display=\'none\'">' : '')
    + '</div>';
}

function typewrite(m) {
  var box = document.getElementById('msg-stream');
  var el = document.createElement('div');
  el.className = 'bubble-row';
  var mine = m.from_agent === chatFrom;
  el.innerHTML = (mine ? '' : '<img class="bubble-ava" src="' + animalImg(m.from_agent) + '" onerror="this.style.display=\'none\'">')
    + '<div class="bubble-main"><div class="bubble-meta"><span class="bubble-from">' + esc(m.from_agent) + '</span>'
    + '<span class="bubble-time">' + ago(m.created_at) + '</span></div><span class="bubble"></span></div>'
    + (mine ? '<img class="bubble-ava" src="' + animalImg(m.from_agent) + '" onerror="this.style.display=\'none\'">' : '');
  box.appendChild(el);
  box.scrollTop = box.scrollHeight;
  var txt = String(m.content || '');
  var i = 0;
  if (_streamTimer) clearInterval(_streamTimer);
  var bubble = el.querySelector('.bubble');
  _streamTimer = setInterval(function(){
    if (i >= txt.length) { clearInterval(_streamTimer); return; }
    bubble.textContent = txt.slice(0, i + 8);
    i += 8;
    box.scrollTop = box.scrollHeight;
  }, 16);
}

function sendMessage() {
  var content = document.getElementById('msg-content').value.trim();
  if (!chatTarget) { toast('先在左侧选择要对话的 Agent', true); return; }
  if (!content) { toast('消息不能为空', true); return; }
  apiPost('/messages/send', { channel_type: 'private', from_agent: chatFrom, to_agent: chatTarget, content: content })
    .then(function(){
      document.getElementById('msg-content').value = '';
      toast('已发送 → ' + chatTarget);
      loadChatHistory();
    }).catch(function(e){ toast('发送失败：' + e.message, true); });
}

function stopStream() {
  if (_streamTimer) { clearInterval(_streamTimer); _streamTimer = null; }
  toast('已停止输出');
}
