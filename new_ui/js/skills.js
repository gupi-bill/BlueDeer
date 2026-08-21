/* ============ 页面 6：技能注册表 ============ */
function loadSkills() {
  var box = document.getElementById('sk-list');
  box.innerHTML = '<div class="loading">加载中…</div>';
  apiGet('/skills').then(function(d){
    var list = d.skills || [];
    document.getElementById('sk-count').textContent = list.length;
    if (!list.length) { box.innerHTML = '<div class="empty"><div class="ico">🧩</div>暂无已注册技能（status=active）。用下方表单注册第一个。</div>'; return; }
    var h = '<table><thead><tr><th>技能</th><th>说明</th><th>提供节点</th><th>参数</th><th style="width:90px">操作</th></tr></thead><tbody>';
    list.forEach(function(s){
      var params = Object.keys(s.param_schema || {}).length
        ? Object.keys(s.param_schema).map(function(k){ return '<span class="cap-chip">' + esc(k) + '</span>'; }).join('')
        : '<span class="mute">—</span>';
      h += '<tr><td><div class="agent-cell"><span class="avatar" style="background:#6d5ae0">⚙</span><div><div class="nm">' + esc(s.name || s.skill_id) + '</div><div class="id">' + esc(s.skill_id) + '</div></div></div></td>'
        + '<td class="muted">' + esc(s.description || '') + '</td>'
        + '<td class="muted">' + esc(s.provider_node || '—') + '</td>'
        + '<td><div class="caps">' + params + '</div></td>'
        + '<td><button class="btn sm danger" onclick="disableSkill(\'' + esc(s.skill_id) + '\')">禁用</button></td></tr>';
    });
    box.innerHTML = h + '</tbody></table>';
  }).catch(function(e){ box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; toast('读取技能失败', true); });
}
function registerSkill() {
  var body = {
    skill_id: document.getElementById('sk-id').value.trim(),
    name: document.getElementById('sk-name').value.trim(),
    description: document.getElementById('sk-desc').value.trim(),
    endpoint_url: document.getElementById('sk-url').value.trim(),
    provider_node: document.getElementById('sk-provider').value.trim()
  };
  if (!body.skill_id || !body.name || !body.endpoint_url) { toast('技能 ID、名称、endpoint_url 必填', true); return; }
  var ps = document.getElementById('sk-params').value.trim();
  try { body.param_schema = ps ? JSON.parse(ps) : {}; }
  catch (e) { toast('param_schema 不是合法 JSON：' + e.message, true); return; }
  apiPost('/skills/register', body).then(function(d){
    toast('技能已注册：' + d.skill_id);
    document.getElementById('sk-id').value = ''; document.getElementById('sk-name').value = '';
    document.getElementById('sk-desc').value = ''; document.getElementById('sk-url').value = '';
    document.getElementById('sk-provider').value = ''; document.getElementById('sk-params').value = '';
    loadSkills();
  }).catch(function(e){ toast('注册失败：' + e.message, true); });
}
function disableSkill(id) {
  if (!confirm('禁用技能「' + id + '」？禁用后从注册表消失（register 可重新激活）。')) return;
  apiPost('/skills/' + encodeURIComponent(id) + '/disable', {}).then(function(){
    toast('已禁用 ' + id);
    loadSkills();
  }).catch(function(e){ toast('禁用失败：' + e.message, true); });
}
