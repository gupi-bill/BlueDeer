/* ============ 配置（底座 API 地址可在「设置」面板修改，存 localStorage） ============ */
try { var _saved = localStorage.getItem('bd-api'); } catch (e) { var _saved = null; }
// 集成模式：默认走主控制台同一端口 /agent/ 路由（相对路径）
var _defaultAPI = _saved && _saved.indexOf('://') >= 0 ? _saved : '/agent';
var API = _defaultAPI;
var state = { managerId: null };

/* ============ 工具 ============ */
/* 骨架屏（借鉴 Dify/n8n 加载态） */
function skeletonBox(rows) {
  var n = rows || 3;
  var h = '';
  for (var i = 0; i < n; i++) {
    h += '<div class="skel-card"><div class="skel-line" style="width:38%"></div><div class="skel-line" style="width:72%"></div><div class="skel-line" style="width:55%"></div></div>';
  }
  return '<div class="skel-grid">' + h + '</div>';
}
function skelTable(rows) {
  var n = rows || 5, h = '';
  for (var i = 0; i < n; i++) h += '<div class="skel-row"><div class="skel-line" style="width:22%"></div><div class="skel-line" style="width:30%"></div><div class="skel-line" style="width:18%"></div><div class="skel-line" style="width:14%"></div></div>';
  return h;
}
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

