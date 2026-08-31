/* ============ 页面 3：消息调试 ============ */
function loadMessages() {
  apiGet('/messages/history?limit=60').then(function(d){
    var list = d.messages || [];
    document.getElementById('msg-count').textContent = list.length;
    var box = document.getElementById('msg-stream');
    if (!list.length) { box.innerHTML = '<div class="empty"><div class="ico">💬</div>暂无消息，发一条试试。</div>'; return; }
    var h = '';
    list.slice().reverse().forEach(function(m){
      var isCode = typeof m.content === 'string' && m.content.charAt(0) === '{';
      var from = m.from_agent || '?';
      var to = m.channel_type === 'task' ? ('任务 ' + (m.task_id || '')) : (m.to_agent || '群聊');
      h += '<div class="msg-row"><div class="msg-main">'
        + '<div class="msg-meta">' + avatarHtml(from)
        + '<span class="msg-from">' + esc(from) + '</span>'
        + '<span class="msg-to">→ ' + esc(to) + '</span>'
        + '<span class="ch-tag">' + esc(m.channel_type) + '</span>'
        + '<span class="msg-time">' + ago(m.created_at) + '</span></div>'
        + '<div class="msg-content' + (isCode ? ' code' : '') + '">' + esc(m.content) + '</div>'
        + '</div></div>';
    });
    box.innerHTML = h;
  }).catch(function(e){ document.getElementById('msg-stream').innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}
function sendMessage() {
  var body = {
    channel_type: document.getElementById('msg-channel').value,
    from_agent: document.getElementById('msg-from').value.trim(),
    to_agent: document.getElementById('msg-to').value.trim(),
    task_id: document.getElementById('msg-task').value.trim(),
    content: document.getElementById('msg-content').value.trim()
  };
  if (!body.from_agent || !body.content) { toast('发信人和内容必填', true); return; }
  if (body.channel_type === 'task' && !body.task_id) { toast('任务频道需要 task_id', true); return; }
  apiPost('/messages/send', body).then(function(d){
    toast('已发送 ' + d.msg_id);
    document.getElementById('msg-content').value = '';
    loadMessages();
  }).catch(function(e){ toast('发送失败：' + e.message, true); });
}

