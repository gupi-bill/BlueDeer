/* ============ 页面 6：技能注册表 ============ */
function loadSkills() {
  var box = document.getElementById('sk-list');
  box.innerHTML = skelTable(5);
  apiGet('/skills').then(function(d){
    var list = d.skills || [];
    document.getElementById('sk-count').textContent = list.length;
    // 归属视图：按提供节点分组，看哪个 Agent 拥有哪些技能
    var owners = document.getElementById('sk-owners');
    if (owners) {
      var byOwner = {};
      list.forEach(function(s){ (byOwner[s.provider_node || '未归属'] = byOwner[s.provider_node || '未归属'] || []).push(s); });
      var names = Object.keys(byOwner).sort();
      owners.innerHTML = '<div class="card-sub" style="margin-bottom:8px">按 Agent 归属（provider_node）：</div>'
        + '<div class="agent-grid">' + names.map(function(n){
            var chips = byOwner[n].slice(0, 8).map(function(s){ return '<span class="cap-chip">' + esc(s.skill_id) + '</span>'; }).join('');
            return '<div class="agent-card" style="padding:12px"><div class="agent-card-head">'
              + '<img class="agent-pic" style="width:40px;height:40px" src="' + animalImg(n) + '" onerror="this.style.display=\'none\'">'
              + '<div class="agent-card-title"><div class="nm" style="font-size:13px">' + esc(n) + '</div>'
              + '<div class="id">' + byOwner[n].length + ' 个技能</div></div></div>'
              + '<div class="caps" style="margin-top:8px">' + chips + '</div></div>';
          }).join('') + '</div>';
    }
    if (!list.length) { box.innerHTML = '<div class="empty">暂无已注册技能（status=active）。用下方表单注册第一个。</div>'; return; }
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
