/* ============ 设置中心（借鉴 Hermes Agent 设置面板） ============ */
/* 常规/外观/模型与API/Agent 行为/关于；UI 偏好存 localStorage，
   模型配置与 Agent 默认值存底座真实接口（/system/settings /system/probe-models）。 */

var PROVIDER_PRESETS = {
  ollama:      { base: '',            hint: '本地 Ollama 免费 · 无需密钥' },
  siliconflow: { base: 'https://api.siliconflow.cn/v1', hint: '硅基流动 · 新用户送 2000 万 token' },
  deepseek:    { base: 'https://api.deepseek.com/v1',   hint: 'DeepSeek 官方' },
  github:      { base: 'https://models.inference.ai.azure.com', hint: 'GitHub Models · 用 PAT 作密钥' },
  zhipu:       { base: 'https://open.bigmodel.cn/api/paas/v4/', hint: '智谱 BigModel' },
  custom:      { base: '',            hint: '任意 OpenAI 兼容端点' }
};
var ACCENTS = [
  { id: 'blue',   name: '蓝鹿蓝', c: '#1e6fff' },
  { id: 'violet', name: '紫罗兰', c: '#7c5cf0' },
  { id: 'teal',   name: '青碧',   c: '#0ea5a4' },
  { id: 'amber',  name: '琥珀金', c: '#d97706' },
  { id: 'rose',   name: '玫红',   c: '#e11d68' }
];

function store(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
function load(k, d) { try { var v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } }

/* ---- 开关抽屉 ---- */
function openSettings() {
  var m = document.getElementById('settings-modal');
  if (m) m.style.display = 'flex';
  loadSettingsUI();
}
function closeSettings() {
  var m = document.getElementById('settings-modal');
  if (m) m.style.display = 'none';
}

/* ---- 分类切换 + 搜索过滤 ---- */
function switchSetCat(cat) {
  document.querySelectorAll('.set-nav-item').forEach(function(b){
    b.classList.toggle('active', b.getAttribute('data-cat') === cat);
  });
  document.querySelectorAll('.set-panel').forEach(function(p){
    p.style.display = p.getAttribute('data-panel') === cat ? '' : 'none';
  });
}
function filterSettings() {
  var q = (document.getElementById('set-search').value || '').toLowerCase();
  document.querySelectorAll('.set-row').forEach(function(r){
    if (!q) { r.style.display = ''; return; }
    r.style.display = (r.getAttribute('data-kw') || '').indexOf(q) >= 0 ? '' : 'none';
  });
}

/* ---- 主题（浅/深/自动）+ 点缀色（OpenClaw 式） ---- */
function applyTheme(t) {
  store('bd-theme', t);
  var dark = t === 'dark' || (t === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.querySelectorAll('#set-theme-seg .seg-btn').forEach(function(b){
    b.classList.toggle('active', b.getAttribute('data-theme') === t);
  });
  var tb = document.getElementById('set-theme-seg');
  if (tb) tb.setAttribute('data-active', t);
}
function setTheme(t) { applyTheme(t); }
function applyAccent(a) {
  store('bd-accent', a);
  document.documentElement.setAttribute('data-accent', a);
  document.querySelectorAll('#set-accent-swatches .swatch').forEach(function(s){
    s.classList.toggle('active', s.getAttribute('data-accent') === a);
  });
}
function renderSwatches() {
  var box = document.getElementById('set-accent-swatches');
  if (!box) return;
  var cur = load('bd-accent', 'blue');
  box.innerHTML = ACCENTS.map(function(x){
    return '<button class="swatch' + (x.id === cur ? ' active' : '') + '" data-accent="' + x.id + '" title="' + x.name
      + '" style="background:' + x.c + '" onclick="applyAccent(\'' + x.id + '\')"></button>';
  }).join('');
}

/* ---- 加载设置到 UI ---- */
function loadSettingsUI() {
  var api = document.getElementById('set-api');
  if (api) api.value = API;
  var th = load('bd-theme', 'light');
  applyTheme(th);
  renderSwatches();
  var sc = document.getElementById('set-sidebar-collapsed');
  if (sc) sc.checked = load('bd-sidebar-collapsed', '0') === '1';
  var rf = document.getElementById('set-refresh');
  if (rf) rf.value = load('bd-refresh', '30');
  var dn = document.getElementById('set-density');
  if (dn) dn.value = load('bd-density', 'cozy');
  document.body.classList.toggle('density-compact', dn && dn.value === 'compact');
  var ts = document.getElementById('set-toast');
  if (ts) ts.checked = load('bd-toast', '1') === '1';
  // 模型
  var prov = load('bd-provider', 'ollama');
  var mb = document.getElementById('set-api-base');
  var mk = document.getElementById('set-api-key');
  var mm = document.getElementById('set-model');
  var mp = document.getElementById('set-provider');
  if (mp) mp.value = prov;
  if (mb) mb.value = load('bd-api-base', PROVIDER_PRESETS[prov] ? PROVIDER_PRESETS[prov].base : '');
  if (mk) mk.value = load('bd-api-key', '');
  if (mm) mm.value = load('bd-model', '');
  onProviderChange();
  // Agent 默认值（底座真实读）
  apiGet('/system/settings').then(function(d){
    var s = (d && d.settings) || {};
    var tpl = document.getElementById('set-ar-template');
    if (tpl) tpl.value = s.default_auto_reply_template || '收到，{from}。任务「{task}」已受理，正在处理…';
  }).catch(function(){});
  // 关于
  fetch(API + '/').then(function(r){ return r.json(); }).then(function(j){
    var t = document.getElementById('about-base-tag');
    var d = document.getElementById('about-base-desc');
    if (t) { t.className = 'tag online'; t.textContent = '在线 v' + (j.version || '?'); }
    if (d) d.textContent = '底座 Agent-Rotary-Station 运行中';
  }).catch(function(){
    var t = document.getElementById('about-base-tag');
    var d = document.getElementById('about-base-desc');
    if (t) { t.className = 'tag offline'; t.textContent = '离线'; }
    if (d) d.textContent = '无法连接底座（' + API + '）';
  });
}

/* ---- 保存：常规 ---- */
function saveSettings() {
  var v = document.getElementById('set-api').value.trim();
  if (!v) { setMsg('地址不能为空', true); return; }
  store('bd-api', v);
  API = v;
  var rf = document.getElementById('set-refresh');
  if (rf) store('bd-refresh', rf.value);
  var dn = document.getElementById('set-density');
  if (dn) { store('bd-density', dn.value); document.body.classList.toggle('density-compact', dn.value === 'compact'); }
  var ts = document.getElementById('set-toast');
  if (ts) store('bd-toast', ts.checked ? '1' : '0');
  setMsg('已保存 ✓');
  checkApi();
  var active = document.querySelector('.nav-item.active');
  if (active) switchPage(active.getAttribute('data-page'));
}
function setMsg(t, err) {
  var m = document.getElementById('set-msg');
  if (m) { m.textContent = t; m.style.color = err ? 'var(--red)' : ''; }
  if (err) toast(t, true);
}

/* ---- 外观：重置 ---- */
function resetAppearance() {
  store('bd-theme', 'light'); applyTheme('light');
  store('bd-accent', 'blue'); applyAccent('blue');
  renderSwatches();
  toast('外观已重置');
}

/* ---- 模型：Provider 切换（Hermes 两阶段第 1 步） ---- */
function onProviderChange() {
  var p = document.getElementById('set-provider').value;
  var preset = PROVIDER_PRESETS[p] || { base: '', hint: '' };
  store('bd-provider', p);
  var mb = document.getElementById('set-api-base');
  if (mb && !mb.value.trim() || p === 'custom') { if (mb) mb.value = preset.base; }
  var hint = document.getElementById('set-probe-msg');
  if (hint) hint.textContent = preset.hint || '';
  // 本地 Ollama 时隐藏密钥
  var mk = document.getElementById('set-api-key');
  if (mk) mk.style.display = p === 'ollama' ? 'none' : '';
  document.getElementById('set-model').innerHTML = '<option value="">先探测模型</option>';
}

/* ---- 模型：真实探测（走底座代理，前端零计算） ---- */
function probeModels() {
  var p = document.getElementById('set-provider').value;
  var base = (document.getElementById('set-api-base').value || '').trim();
  var key = (document.getElementById('set-api-key').value || '').trim();
  var msg = document.getElementById('set-probe-msg');
  var sel = document.getElementById('set-model');
  msg.textContent = '探测中…';
  sel.innerHTML = '<option value="">探测中…</option>';
  var q = 'api_base=' + encodeURIComponent(base) + '&api_key=' + encodeURIComponent(key);
  apiGet('/system/probe-models?' + q).then(function(d){
    if (!d.ok) { msg.textContent = '❌ ' + (d.error || '探测失败'); sel.innerHTML = '<option value="">无可用模型</option>'; return; }
    var models = d.models || [];
    if (!models.length) { msg.textContent = '端点可达，但无模型'; sel.innerHTML = '<option value="">无模型</option>'; return; }
    msg.textContent = (d.source === 'ollama' ? '本地 Ollama' : d.source) + ' · ' + models.length + ' 个模型';
    sel.innerHTML = models.map(function(m){ return '<option value="' + esc(m) + '">' + esc(m) + '</option>'; }).join('');
    var cur = load('bd-model', '');
    if (cur) sel.value = cur;
  }).catch(function(e){
    msg.textContent = '❌ 请求失败：' + e.message;
  });
}

/* ---- 模型：保存 ---- */
function saveModelConfig() {
  var p = document.getElementById('set-provider').value;
  var base = (document.getElementById('set-api-base').value || '').trim();
  var key = (document.getElementById('set-api-key').value || '').trim();
  var model = document.getElementById('set-model').value;
  store('bd-provider', p);
  store('bd-api-base', base);
  store('bd-api-key', key);
  store('bd-model', model);
  var m = document.getElementById('set-model-msg');
  /* 底座真实持久化：mock / ollama / openai 兼容 API 三通道 */
  var payload = null;
  if (p === 'mock') payload = { provider: 'mock' };
  else if (p === 'ollama') payload = { provider: 'ollama', ollama_base_url: base || 'http://127.0.0.1:11434', ollama_model: model || 'qwen2.5vl:7b' };
  else {
    if (!base) { if (m) m.textContent = '请先填 API 地址（Base URL）'; return; }
    if (!model) { if (m) m.textContent = '请先探测并选择模型'; return; }
    payload = { provider: 'openai', api_base: base, api_key: key, api_model: model };
  }
  if (payload) {
    apiPost('/system/settings', payload).then(function(){
      if (m) m.textContent = '已保存并写入底座 config.json';
      toast('模型配置已写入底座');
    }).catch(function(e){
      if (m) m.textContent = '浏览器已存，底座写入失败：' + e.message;
    });
  } else if (m) {
    m.textContent = '已存浏览器（该预设未写入底座）';
  }
}

/* ---- Agent 默认值：保存到底座（真实写库） ---- */
function saveAgentDefaults() {
  var tpl = document.getElementById('set-ar-template').value.trim();
  apiPost('/system/settings', { default_auto_reply_template: tpl }).then(function(d){
    var m = document.getElementById('set-agent-msg');
    if (m) m.textContent = '已保存到底座 ✓';
    toast('Agent 默认值已保存');
  }).catch(function(e){
    var m = document.getElementById('set-agent-msg');
    if (m) m.textContent = '保存失败：' + e.message;
  });
}

/* ---- 启动初始化（pre-paint 前应用主题/点缀色） ---- */
(function(){
  try {
    var t = load('bd-theme', 'light');
    var dark = t === 'dark' || (t === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-accent', load('bd-accent', 'blue'));
  } catch (e) {}
})();
