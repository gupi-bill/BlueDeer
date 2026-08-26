/* ============ 页面 11：定时任务（/crons 启停/触发/历史，全真实） ============ */

function loadCrons() {
  var box = document.getElementById('cr-list');
  apiGet('/crons').then(function(d){
    var list = d.crons || [];
    document.getElementById('cr-count').textContent = list.length;
    if (!list.length) { box.innerHTML = '<div class="empty">还没有定时任务，用上方表单创建。创建后由底座调度线程按间隔自动执行。</div>'; return; }
    box.innerHTML = list.map(function(c){
      var on = !!c.enabled;
      return '<div class="run-item">'
        + '<div class="run-head"><b>' + esc(c.name) + '</b>'
        + '<span class="tag ' + (on ? 'online' : 'offline') + '">' + (on ? '运行中' : '已暂停') + '</span>'
        + '<span class="tag">每 ' + esc(c.interval_sec) + 's</span>'
        + '<span class="tag ' + (c.action === 'workflow' ? 'manager' : 'worker') + '">' + (c.action === 'workflow' ? '触发工作流' : '发消息') + '</span>'
        + '<span class="muted" style="margin-left:auto">目标：' + esc(c.target || '—') + '</span></div>'
        + '<div class="approval-actions" style="margin-top:8px">'
        + '<button class="btn sm primary" onclick="runCronNow(\'' + esc(c.cron_id) + '\')">▶ 手动触发</button>'
        + '<button class="btn sm" onclick="toggleCron(\'' + esc(c.cron_id) + '\')">' + (on ? '⏸ 暂停' : '▶ 启用') + '</button>'
        + '<button class="btn sm" onclick="loadCronHistory(\'' + esc(c.cron_id) + '\')">历史</button>'
        + '<button class="btn sm danger" onclick="deleteCron(\'' + esc(c.cron_id) + '\')">删除</button>'
        + '</div>'
        + '<div class="mute" style="font-size:11px;margin-top:6px">上次执行 ' + (c.last_run_at ? ago(c.last_run_at) : '从未') + (c.next_run_at ? ' · 下次 ' + ago(c.next_run_at) + '后' : '') + '</div>'
        + '<div id="cr-history-' + esc(c.cron_id) + '"></div></div>';
    }).join('');
  }).catch(function(e){ box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}

function createCron() {
  var name = document.getElementById('cr-name').value.trim();
  if (!name) { toast('请填任务名', true); return; }
  var interval = parseInt(document.getElementById('cr-interval').value, 10) || 3600;
  var action = document.getElementById('cr-action').value;
  var target = document.getElementById('cr-target').value.trim();
  var content = document.getElementById('cr-content').value.trim();
  if (action === 'workflow' && !target) { toast('触发工作流需填工作流 ID', true); return; }
  apiPost('/crons/create', { name: name, interval_sec: interval, action: action, target: target, payload: { content: content } })
    .then(function(){
      toast('定时任务「' + name + '」已创建');
      document.getElementById('cr-name').value = '';
      loadCrons();
    }).catch(function(e){ toast('创建失败：' + e.message, true); });
}

function toggleCron(cid) {
  apiPost('/crons/' + cid + '/toggle', {}).then(function(d){
    toast(d.enabled ? '已启用' : '已暂停');
    loadCrons();
  }).catch(function(e){ toast('操作失败：' + e.message, true); });
}

function runCronNow(cid) {
  apiPost('/crons/' + cid + '/run', {}).then(function(d){
    toast('已触发执行：' + (d.status === 'success' ? '成功' : '失败 ' + (d.detail || '')));
    loadCrons();
    loadCronHistory(cid);
  }).catch(function(e){ toast('触发失败：' + e.message, true); });
}

function deleteCron(cid) {
  if (!confirm('删除定时任务？')) return;
  apiPost('/crons/' + cid + '/delete', {}).then(function(){
    toast('已删除');
    loadCrons();
  }).catch(function(e){ toast('删除失败：' + e.message, true); });
}

function loadCronHistory(cid) {
  var box = document.getElementById('cr-history-' + cid);
  if (box.innerHTML) { box.innerHTML = ''; return; }
  apiGet('/crons/' + cid + '/history?limit=10').then(function(d){
    var runs = d.runs || [];
    box.innerHTML = '<div style="margin-top:10px;border-top:1px solid var(--border);padding-top:8px">'
      + (runs.length
          ? runs.map(function(r){
              return '<div class="audit-row"><span class="tag ' + (r.status === 'success' ? 'online' : 'offline') + '">' + esc(r.status) + '</span>'
                + '<span class="muted" style="font-size:11.5px">' + esc(r.triggered_by) + '</span>'
                + '<span class="mute" style="font-size:11.5px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + esc(r.detail) + '</span>'
                + '<span class="muted" style="font-size:11px">' + ago(r.created_at) + '</span></div>';
            }).join('')
          : '<div class="mute">暂无执行记录</div>')
      + '</div>';
  }).catch(function(){ box.innerHTML = ''; });
}
