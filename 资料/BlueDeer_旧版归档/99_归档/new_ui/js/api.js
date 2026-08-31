/* ============ 配置 ============ */
var API = 'http://127.0.0.1:8000';   // Agent-Rotary-Station 底座
var state = { managerId: null };

/* ============ 工具 ============ */
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function toast(msg, isErr) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isErr ? ' err' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(function(){ t.className = 'toast'; }, 2600);
}
function ago(ts) {
  if (!ts) return '—';
  var s = Math.floor(Date.now() / 1000 - ts);
  if (s < 60) return s + 's 前';
  if (s < 3600) return Math.floor(s / 60) + 'm 前';
  if (s < 86400) return Math.floor(s / 3600) + 'h 前';
  return new Date(ts * 1000).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}
function req(url, opts) {
  return fetch(API + url, opts).then(function(r){
    return r.json().then(function(j){ if (!r.ok) throw new Error(j.detail || j.message || ('HTTP ' + r.status)); return j; });
  });
}
function apiGet(url) { return req(url); }
function apiPost(url, body) {
  return req(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
}
var ROLE_TEXT = { worker: '执行', manager: '管理岗', toolnode: '工具' };
var ROLE_COLOR = { worker: 'worker', manager: 'manager', toolnode: 'toolnode' };
var AVATAR_COLORS = ['#1e6fff', '#6d5ae0', '#0ea5a4', '#e08a00', '#d55f8e', '#4c8c3f', '#5b6b8c', '#b5522e'];

function avatarHtml(name) {
  var ch = (name || '?').charAt(0).toUpperCase();
  var c = AVATAR_COLORS[(name || '').length % AVATAR_COLORS.length];
  return '<span class="avatar" style="background:' + c + '">' + esc(ch) + '</span>';
}

