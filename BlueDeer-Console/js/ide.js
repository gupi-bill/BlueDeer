/* ============ 页面 9：IDE 工作台（VS Code/Hermes 式） ============ */
/* 文件树/读写/新建/删除全走底座真实接口 /files/*；编辑器内核 = 本地 Monaco。 */

var IDE = {
  treeLoaded: {},
  openTabs: {},       // path -> {name, language, dirty}
  activePath: null,
  editor: null,
  monaco: null,
  treeCache: {}       // path -> entries
};

/* ---- Monaco 初始化（本地 vendor，离线可用） ---- */
function ideInitMonaco(cb) {
  if (IDE.monaco) { cb(); return; }
  var loading = document.getElementById('ide-status-right');
  if (loading) loading.textContent = '加载编辑器内核…';
  require.config({ paths: { vs: 'vendor/monaco/min/vs' } });
  require(['vs/editor/editor.main'], function(){
    IDE.monaco = monaco;
    monaco.editor.defineTheme('bd-light', {
      base: 'vs', inherit: true,
      rules: [], colors: { 'editor.background': '#ffffff' }
    });
    monaco.editor.defineTheme('bd-dark', {
      base: 'vs-dark', inherit: true,
      rules: [], colors: { 'editor.background': '#1a1c20' }
    });
    cb();
  }, function(err){
    if (loading) loading.textContent = '编辑器内核加载失败：' + (err && err.message || '未知错误');
  });
}

function ideCreateEditor() {
  var el = document.getElementById('ide-editor');
  if (!el || IDE.editor) return;
  var dark = (document.documentElement.getAttribute('data-theme') === 'dark');
  IDE.editor = IDE.monaco.editor.create(el, {
    value: '// 从左侧文件树选择文件开始编辑',
    language: 'plaintext',
    theme: dark ? 'bd-dark' : 'bd-light',
    fontSize: 13,
    fontFamily: '"JetBrains Mono", Consolas, monospace',
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 2,
    wordWrap: 'on'
  });
  IDE.editor.onDidChangeCursorPosition(function(e){
    var sb = document.getElementById('ide-status-right');
    if (sb && IDE.activePath) {
      sb.textContent = IDE.activePath + ' · Ln ' + e.position.lineNumber + ', Col ' + e.position.column;
    }
  });
  IDE.editor.onDidChangeModelContent(function(){
    if (!IDE.activePath) return;
    var t = IDE.openTabs[IDE.activePath];
    if (t && !t.dirty) {
      t.dirty = true;
      ideRenderTabs();
    }
  });
}

/* ---- 进入页面 ---- */
function loadIde() {
  ideInitMonaco(function(){
    ideCreateEditor();
    if (!IDE.treeLoaded['']) ideLoadTree('');
  });
}

/* ---- 文件树（懒加载） ---- */
function ideLoadTree(path) {
  var box = document.getElementById('ide-tree');
  apiGet('/files/list?path=' + encodeURIComponent(path)).then(function(d){
    IDE.treeCache[path] = d.entries || [];
    IDE.treeLoaded[path] = true;
    box.innerHTML = ideTreeHtml('', 0);
  }).catch(function(e){
    box.innerHTML = '<div class="empty">读取失败：' + esc(e.message) + '</div>';
  });
}

function ideTreeHtml(path, depth) {
  var entries = IDE.treeCache[path] || [];
  var h = '';
  entries.forEach(function(en){
    var full = en.path;
    var pad = 'style="padding-left:' + (10 + depth * 16) + 'px"';
    if (en.is_dir) {
      var open = !!IDE.treeLoaded[full];
      h += '<div class="ide-tree-item" ' + pad + ' data-path="' + esc(full) + '">'
        + '<span class="ide-arrow ' + (open ? 'open' : '') + '">' + (open ? '▾' : '▸') + '</span>'
        + '<span class="ide-ico">' + (open ? '📂' : '📁') + '</span><span class="ide-name">' + esc(en.name) + '</span></div>';
      if (open) h += ideTreeHtml(full, depth + 1);
    } else {
      h += '<div class="ide-tree-item file" ' + pad + ' data-path="' + esc(full) + '">'
        + '<span class="ide-ico">' + ideFileIco(en.name) + '</span><span class="ide-name">' + esc(en.name) + '</span></div>';
    }
  });
  return h;
}

function ideFileIco(name) {
  var ext = (name.split('.').pop() || '').toLowerCase();
  return { py: '🐍', js: '🟨', ts: '🔷', json: '📋', md: '📝', html: '🌐', css: '🎨',
           yaml: '⚙️', yml: '⚙️', sql: '🗄', txt: '📄', sh: '⚡', bat: '🪟' }[ext] || '📄';
}

/* 树点击：目录展开/收起，文件打开 */
document.addEventListener('click', function(e){
  var item = e.target.closest('.ide-tree-item');
  if (!item) return;
  var path = item.getAttribute('data-path');
  if (!path) return;
  var en = (IDE.treeCache[path.split('/').slice(0, -1).join('/')] || []).filter(function(x){ return x.path === path; })[0];
  var isDir = en ? en.is_dir : false;
  if (isDir) {
    if (IDE.treeLoaded[path]) { delete IDE.treeLoaded[path]; ideRenderTree(); }
    else ideLoadTree(path);
  } else {
    ideOpenFile(path);
  }
});

function ideRenderTree() {
  var box = document.getElementById('ide-tree');
  if (box) box.innerHTML = ideTreeHtml('', 0);
}
function ideRefreshTree() { IDE.treeCache = {}; IDE.treeLoaded = {}; ideLoadTree(''); }

/* ---- 打开文件 ---- */
function ideOpenFile(path) {
  if (!IDE.monaco) return;
  if (IDE.openTabs[path]) { ideActivateTab(path); return; }
  apiGet('/files/content?path=' + encodeURIComponent(path)).then(function(d){
    IDE.openTabs[path] = { name: d.name, language: d.language, dirty: false };
    ideActivateTab(path);
    var model = IDE.monaco.editor.createModel(d.content, d.language);
    if (IDE.activePath && IDE.openTabs[IDE.activePath]) {
      // 保持旧模型以便回切（简单起见：切换时直接换模型，放弃旧模型引用）
    }
    IDE.editor.setModel(model);
    ideRenderTabs();
    var sb = document.getElementById('ide-status-right');
    if (sb) sb.textContent = path + ' · ' + d.language;
  }).catch(function(e){
    toast('打开失败：' + e.message, true);
  });
}

function ideActivateTab(path) {
  IDE.activePath = path;
  ideRenderTabs();
}
function ideCloseTab(path) {
  delete IDE.openTabs[path];
  if (IDE.activePath === path) {
    var keys = Object.keys(IDE.openTabs);
    IDE.activePath = keys.length ? keys[keys.length - 1] : null;
    if (IDE.activePath) {
      var t = IDE.openTabs[IDE.activePath];
      apiGet('/files/content?path=' + encodeURIComponent(IDE.activePath)).then(function(d){
        if (!IDE.editor) return;
        IDE.editor.setModel(IDE.monaco.editor.createModel(d.content, d.language));
        var sb = document.getElementById('ide-status-right');
        if (sb) sb.textContent = IDE.activePath + ' · ' + d.language;
      });
    } else if (IDE.editor) {
      IDE.editor.setModel(IDE.monaco.editor.createModel('// 从左侧文件树选择文件开始编辑', 'plaintext'));
      var sb = document.getElementById('ide-status-right');
      if (sb) sb.textContent = '';
    }
  }
  ideRenderTabs();
}
function ideRenderTabs() {
  var box = document.getElementById('ide-tabs');
  var keys = Object.keys(IDE.openTabs);
  if (!keys.length) { box.innerHTML = '<div class="ide-empty-tab">未打开文件 — 点击左侧文件开始编辑</div>'; return; }
  box.innerHTML = keys.map(function(p){
    var t = IDE.openTabs[p];
    return '<span class="ide-tab' + (p === IDE.activePath ? ' active' : '') + '" data-path="' + esc(p) + '">'
      + esc(t.name) + (t.dirty ? ' ●' : '')
      + '<button class="ide-tab-x" data-close="' + esc(p) + '" title="关闭">×</button></span>';
  }).join('');
}
document.addEventListener('click', function(e){
  var tab = e.target.closest('.ide-tab');
  if (tab && !e.target.closest('.ide-tab-x')) ideActivateTab(tab.getAttribute('data-path'));
  var x = e.target.closest('.ide-tab-x');
  if (x) { e.stopPropagation(); ideCloseTab(x.getAttribute('data-close')); }
});

/* ---- 保存（真实写盘） ---- */
function ideSaveFile() {
  if (!IDE.activePath) { toast('没有打开的文件', true); return; }
  var t = IDE.openTabs[IDE.activePath];
  var content = IDE.editor.getValue();
  apiPost('/files/content', { path: IDE.activePath, content: content }).then(function(d){
    t.dirty = false;
    ideRenderTabs();
    var sb = document.getElementById('ide-status-right');
    if (sb) sb.textContent = '已保存 ' + IDE.activePath + ' (' + d.size + ' B)';
    toast('已保存 ' + IDE.activePath);
    ideRefreshTree();
  }).catch(function(e){ toast('保存失败：' + e.message, true); });
}
document.addEventListener('keydown', function(e){
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    if (document.getElementById('page-ide').classList.contains('active')) ideSaveFile();
  }
});

/* ---- 新建 / 删除 ---- */
function ideNewFile() {
  var path = prompt('新建文件路径（相对底座项目根，如 docs/notes.md）：');
  if (!path) return;
  apiPost('/files/create', { path: path.trim(), is_dir: false }).then(function(){
    toast('已创建 ' + path);
    ideRefreshTree();
    ideOpenFile(path.trim());
  }).catch(function(e){ toast('创建失败：' + e.message, true); });
}
function ideNewDir() {
  var path = prompt('新建文件夹路径（相对底座项目根）：');
  if (!path) return;
  apiPost('/files/create', { path: path.trim(), is_dir: true }).then(function(){
    toast('已创建文件夹 ' + path);
    ideRefreshTree();
  }).catch(function(e){ toast('创建失败：' + e.message, true); });
}
function ideDeleteNode() {
  if (!IDE.activePath) { toast('先在编辑器里打开要删除的文件', true); return; }
  if (!confirm('确定删除 ' + IDE.activePath + ' ？（不可恢复）')) return;
  apiPost('/files/delete', { path: IDE.activePath }).then(function(){
    toast('已删除 ' + IDE.activePath);
    delete IDE.openTabs[IDE.activePath];
    IDE.activePath = null;
    if (IDE.editor) IDE.editor.setModel(IDE.monaco.editor.createModel('', 'plaintext'));
    ideRenderTabs();
    ideRefreshTree();
  }).catch(function(e){ toast('删除失败：' + e.message, true); });
}
