/* ============ 页面 4：记忆池 ============ */
var memState = { reader: 'human', domain: null };
function loadMemories() { loadMemoryDomains(); }
function loadMemoryDomains() {
  var reader = memState.reader;
  apiGet('/memories/list-domains?reader=' + encodeURIComponent(reader)).then(function(d){
    var domains = d.domains || [];
    document.getElementById('mem-domain-count').textContent = domains.length;
    var box = document.getElementById('mem-domains');
    if (!domains.length) { box.innerHTML = '<div class="empty">暂无可见记忆域。</div>'; document.getElementById('mem-list').innerHTML = '<div class="empty">暂无记忆</div>'; return; }
    box.innerHTML = domains.map(function(dom){
      var active = memState.domain === dom ? ' active' : '';
      return '<span class="domain-chip' + active + '" onclick="selectDomain(\'' + esc(dom) + '\')">' + esc(dom) + '</span>';
    }).join('');
    if (!memState.domain || domains.indexOf(memState.domain) < 0) { selectDomain(domains[0]); }
    else { readMemories(memState.domain); }
  }).catch(function(e){ document.getElementById('mem-domains').innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}
function selectDomain(dom) { memState.domain = dom; loadMemoryDomains(); }
function readMemories(dom) {
  var box = document.getElementById('mem-list');
  box.innerHTML = '<div class="loading">读取 ' + esc(dom) + ' …</div>';
  apiGet('/memories/read?reader=' + encodeURIComponent(memState.reader) + '&domain=' + encodeURIComponent(dom)).then(function(d){
    var list = d.memories || [];
    document.getElementById('mem-count').textContent = list.length;
    if (!list.length) { box.innerHTML = '<div class="empty">该域暂无记忆。</div>'; return; }
    box.innerHTML = list.map(function(m){
      return '<div class="mem-item"><div class="mem-key">' + esc(m.mem_key) + '</div><div class="mem-content">' + esc(m.content) + '</div><div class="muted">' + esc(m.owner_agent || '') + ' · 更新 ' + ago(m.updated_at) + '</div></div>';
    }).join('');
  }).catch(function(e){ box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>'; });
}
function writeMemory() {
  var body = { agent_id: memState.reader, domain: document.getElementById('mem-w-domain').value.trim(), mem_key: document.getElementById('mem-w-key').value.trim(), content: document.getElementById('mem-w-content').value.trim() };
  if (!body.domain || !body.mem_key) { toast('域和键必填', true); return; }
  toast('提交中（底座同步等待审批）…');
  apiPost('/memories/write', body).then(function(d){
    var st = d.status || '';
    if (st === 'approved') toast('已审批通过并落库');
    else if (st === 'pending') toast('已提交，等待管理岗审批');
    else if (st === 'denied') toast('审批被拒绝', true);
    else toast('已提交：' + esc(st));
    loadMemoryDomains();
  }).catch(function(e){ toast('写入失败：' + e.message, true); });
}
function deleteMemory() {
  var body = { agent_id: memState.reader, domain: document.getElementById('mem-d-domain').value.trim(), mem_key: document.getElementById('mem-d-key').value.trim() };
  if (!body.domain || !body.mem_key) { toast('域和键必填', true); return; }
  toast('提交中（底座同步等待审批）…');
  apiPost('/memories/delete', body).then(function(d){
    var st = d.status || '';
    if (st === 'approved') toast('删除已审批通过');
    else if (st === 'pending') toast('已提交，等待管理岗审批');
    else if (st === 'denied') toast('审批被拒绝', true);
    else toast('已提交：' + esc(st));
    loadMemoryDomains();
  }).catch(function(e){ toast('删除失败：' + e.message, true); });
}

