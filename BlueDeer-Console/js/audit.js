/* ============ 页面 12：审计日志（筛选/搜索，全真实 /system/audit-logs） ============ */

function loadAudit() {
  var box = document.getElementById('au-list');
  var actor = document.getElementById('au-actor').value.trim();
  var action = document.getElementById('au-action').value.trim();
  var q = document.getElementById('au-q').value.trim();
  var limit = document.getElementById('au-limit').value;
  var qs = 'limit=' + limit;
  if (actor) qs += '&actor=' + encodeURIComponent(actor);
  if (action) qs += '&action=' + encodeURIComponent(action);
  if (q) qs += '&q=' + encodeURIComponent(q);
  apiGet('/system/audit-logs?' + qs).then(function(d){
    var logs = d.logs || [];
    document.getElementById('au-count').textContent = logs.length;
    if (!logs.length) { box.innerHTML = '<div class="empty"><div class="ico">🔍</div>没有符合条件的日志。</div>'; return; }
    box.innerHTML = logs.map(function(l){
      var det = l.detail && typeof l.detail === 'object' ? JSON.stringify(l.detail) : (l.detail || '');
      return '<div class="audit-row">'
        + '<span class="tag ' + (l.actor === 'human' ? 'manager' : 'worker') + '">' + esc(l.actor) + '</span>'
        + '<span class="audit-action">' + esc(l.action || '') + '</span>'
        + (l.target ? '<span class="mute" style="font-size:11.5px;font-family:var(--mono)">' + esc(l.target) + '</span>' : '')
        + '<span class="muted" style="margin-left:auto">' + ago(l.created_at) + '</span>'
        + (det && det !== '{}' ? '<div class="mute" style="width:100%;font-size:11px;font-family:var(--mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(det.slice(0, 160)) + '</div>' : '')
        + '</div>';
    }).join('');
  }).catch(function(e){ box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}
