/* global api */
const state = {
  fidelity: null,
  projectPath: null,
  root: null,
  volumes: [],
  items: [],
  docs: [],
  fields: [],
  tables: [],
  tableKey: 'deviceList',
  pendingFields: null,
  values: {},
  ledger: null,
  trash: [],
  printStates: {},
  selectedItemId: null,
  selectedDocId: null,
  leftTab: 'tree',
  view: 'ledger',
  collapsed: new Set(),
  dirty: false,
  panelOpen: true,
  jobs: [],
  ai: { available: false, reason: 'no-api-key', hasKey: false },
  rewriteMode: 'polish',
  rewriteTarget: 'projectBackground',
  editor: { available: false, reason: '', sessionId: null, html: '', relPath: '' },
};

function $(id) { return document.getElementById(id); }
function show(id) { $(id).classList.remove('hidden'); }
function hide(id) { $(id).classList.add('hidden'); }

let toastTimer = null;
function toast(msg) {
  let el = $('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = String(msg || '');
  el.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('on'), 2800);
}

function setDirty(n) {
  state.dirty = n > 0;
  $('dirtyMark').classList.toggle('hidden', !state.dirty);
  $('sbDirty').textContent = '未保存更改 ' + n + ' 处';
}

function applyAiGate(status) {
  if (status && typeof status === 'object') {
    state.ai = Object.assign({}, state.ai, status.available != null ? status : (status.stats || status));
    if (status.stats && status.stats.available != null) state.ai = Object.assign({}, state.ai, status.stats);
    if (status.available != null) state.ai.available = status.available;
    if (status.reason) state.ai.reason = status.reason;
    if (status.hasKey != null) state.ai.hasKey = status.hasKey;
  }
  const on = !!state.ai.available;
  document.querySelectorAll('.ai-only').forEach((el) => {
    el.disabled = !on;
    el.classList.toggle('ai-off', !on);
    el.title = on
      ? 'AI 可用'
      : ('AI 不可用：' + (state.ai.reason || 'offline') + '（其余功能不受影响）');
  });
  const chip = $('sbAi');
  if (chip) {
    chip.textContent = on ? 'AI 在线' : ('AI 离线（' + (state.ai.reason || 'no-key') + '）');
  }
}

async function refreshAiGate() {
  try {
    const payload = await api.aiStatus();
    const st = (payload && payload.stats) || payload || {};
    applyAiGate(st);
  } catch {
    applyAiGate({ available: false, reason: 'status-error', hasKey: false });
  }
}

function fillChip(fill) {
  if (fill === 'complete') return '<span class="chip c-green">已完成</span>';
  if (fill === 'draft') return '<span class="chip c-blue">部分填充</span>';
  if (fill === 'error') return '<span class="chip c-red">必填缺失</span>';
  return '<span class="chip c-gray">未开始</span>';
}

function renderTree() {
  const pane = $('treePane');
  if (state.leftTab === 'search') {
    pane.innerHTML = '<p class="empty-hint">查找结果（P4 stub）<br>用顶部「查找」过滤目录项名称。</p>';
    return;
  }
  if (state.leftTab === 'trash') {
    if (!state.trash.length) {
      pane.innerHTML = '<p class="empty-hint">回收站是空的。<br>在目录树右键或选中文档后删除（stub）。</p>';
      return;
    }
    pane.innerHTML = state.trash.map((t) => (
      '<div class="tn lv2"><span class="caret">·</span>' +
      escapeHtml(t.docNo || t.docId || t.trashId) +
      '<span class="badge-n">' + escapeHtml(t.deletedAt || '') + '</span></div>'
    )).join('');
    return;
  }
  if (!state.volumes.length) {
    pane.innerHTML = '<p class="empty-hint">还没有打开工程</p>';
    return;
  }
  const html = [];
  for (const vol of state.volumes) {
    const collapsed = state.collapsed.has(vol.volume);
    html.push(
      '<div class="tn lv1" data-vol="' + encodeURIComponent(vol.volume) + '">' +
      '<span class="caret">' + (collapsed ? '▶' : '▼') + '</span>' +
      escapeHtml(vol.volume) +
      '<span class="badge-n">' + vol.count + '</span></div>'
    );
    if (collapsed) continue;
    for (const it of vol.items) {
      const on = it.itemId === state.selectedItemId && !state.selectedDocId ? ' on' : '';
      const print = it.printed ? '<span class="badge-print">印</span>' : '';
      const docs = (it.docs || []).filter((d) => d && (d.exists !== false));
      const empty = docs.length === 0;
      const required = it.inclusion === 'required';
      const emptyCls = empty ? (required ? ' empty-req' : ' empty-opt') : '';
      const inc = required ? '必选' : '可选';
      const title = empty
        ? (required ? (inc + ' · 未生成') : (inc + ' · 尚未创建（不是缺项）'))
        : (inc + ' · ' + (it.fillState || 'empty'));
      html.push(
        '<div class="tn lv2' + on + emptyCls + '" data-item="' + it.itemId +
        '" data-kind="table">' +
        '<span class="caret">·</span>' +
        escapeHtml(String(it.seq).padStart(2, '0') + ' ' + it.name) +
        print +
        '<span class="dot d-' + (it.dot || 'gray') + '" title="' + escapeHtml(title) + '"></span>' +
        '</div>'
      );
      for (const doc of docs) {
        const don = doc.docId === state.selectedDocId ? ' on' : '';
        const label = doc.docNo || (doc.relPath || '').split('/').pop() || doc.docId;
        html.push(
          '<div class="tn lv3' + don + '" data-item="' + it.itemId + '" data-doc="' +
          escapeHtml(doc.docId) + '" data-kind="instance">' +
          '<span class="caret">·</span>' +
          escapeHtml(label) +
          '</div>'
        );
      }
    }
  }
  pane.innerHTML = html.join('');
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function renderFields() {
  const body = $('fieldBody');
  if (!state.fields.length) {
    body.innerHTML = '<p class="empty-hint">打开工程后显示 39 个字段</p>';
    return;
  }
  let g = null;
  const parts = [];
  for (const f of state.fields) {
    if (f.group !== g) {
      g = f.group;
      parts.push('<div class="fp-grp">' + escapeHtml(g) + '</div>');
    }
    const src = f.by === 'engine' ? 's-auto' : (f.value ? 's-manual' : 's-none');
    const srcLb = f.by === 'engine' ? '推' : (f.value ? '手' : '—');
    const ro = f.key === 'docNo' ? ' disabled' : '';
    const isLong = f.type === 'longtext';
    const val = f.value == null ? '' : f.value;
    const ctl = isLong
      ? '<textarea class="fp-val" rows="2" data-key="' + f.key + '"' + ro + '>' + escapeHtml(val) + '</textarea>'
      : '<input class="fp-val" data-key="' + f.key + '" value="' + escapeHtml(val) + '"' + ro + '>';
    parts.push(
      '<div class="fp-item"><span class="fp-name" title="' + escapeHtml(f.label) + '">' +
      escapeHtml(f.label) + '</span>' + ctl +
      '<span class="src ' + src + '">' + srcLb + '</span></div>'
    );
  }
  body.innerHTML = parts.join('');
  body.querySelectorAll('.fp-val').forEach((el) => {
    el.addEventListener('input', () => setDirty(1));
  });
}

function collectFields() {
  const out = {};
  document.querySelectorAll('#fieldBody .fp-val').forEach((el) => {
    out[el.dataset.key] = el.value;
  });
  return out;
}

function currentTable() {
  return state.tables.find((t) => t.key === state.tableKey) || state.tables[0];
}

function renderTables() {
  if (!state.tables.length) {
    $('mainPane').innerHTML = '<p class="empty-hint">打开工程后编辑 8 张子表。保存后由 subtable_engine 写入已生成文档（不动模板）。</p>';
    return;
  }
  if (!state.tables.some((t) => t.key === state.tableKey)) {
    state.tableKey = state.tables[0].key;
  }
  const tbl = currentTable();
  const opts = state.tables.map((t) => (
    '<option value="' + t.key + '"' + (t.key === tbl.key ? ' selected' : '') + '>' +
    escapeHtml(t.label) + '</option>'
  )).join('');
  const cols = tbl.columns || [];
  const rows = Array.isArray(tbl.rows) ? tbl.rows : [];
  const head = cols.map((c) => '<th>' + escapeHtml(c) + '</th>').join('') + '<th></th>';
  const body = rows.map((row, ri) => {
    const cells = cols.map((c) => {
      const v = row && row[c] != null ? row[c] : '';
      return '<td><input class="sg-cell" data-r="' + ri + '" data-c="' + escapeHtml(c) +
        '" value="' + escapeHtml(v) + '"></td>';
    }).join('');
    return '<tr>' + cells + '<td><button class="mini-btn sg-del" data-r="' + ri + '">删</button></td></tr>';
  }).join('');
  $('mainPane').innerHTML =
    '<div class="subtable">' +
    '<div class="st-bar">' +
    '<label>子表 <select id="stSelect">' + opts + '</select></label>' +
    '<span class="st-note">' + escapeHtml(tbl.note || tbl.usedBy && tbl.usedBy.join('、') || '') + '</span>' +
    '<span class="tool-sp">' +
    '<button class="mini-btn" id="stAdd">+ 行</button>' +
    '<button class="mini-btn" id="stSave">保存并写入文档</button>' +
    '</span></div>' +
    '<div class="st-wrap"><table class="sg-tbl"><thead><tr>' + head +
    '</tr></thead><tbody id="stBody">' + (body || '<tr><td colspan="' + (cols.length + 1) +
    '" class="empty-hint">暂无数据（空表保留模板静态行）</td></tr>') +
    '</tbody></table></div></div>';
  const sel = $('stSelect');
  if (sel) {
    sel.addEventListener('change', () => {
      collectCurrentTable();
      state.tableKey = sel.value;
      renderTables();
    });
  }
  $('mainPane').querySelectorAll('.sg-cell').forEach((el) => {
    el.addEventListener('input', () => {
      const t = currentTable();
      if (!t.rows[el.dataset.r]) t.rows[el.dataset.r] = {};
      t.rows[el.dataset.r][el.dataset.c] = el.value;
      setDirty(1);
    });
  });
  $('mainPane').querySelectorAll('.sg-del').forEach((el) => {
    el.addEventListener('click', () => {
      const t = currentTable();
      t.rows.splice(Number(el.dataset.r), 1);
      setDirty(1);
      renderTables();
    });
  });
  const add = $('stAdd');
  if (add) {
    add.addEventListener('click', () => {
      const t = currentTable();
      const row = {};
      (t.columns || []).forEach((c) => { row[c] = ''; });
      t.rows = t.rows || [];
      t.rows.push(row);
      setDirty(1);
      renderTables();
    });
  }
  const save = $('stSave');
  if (save) save.addEventListener('click', saveTables);
}

function collectCurrentTable() {
  const t = currentTable();
  if (!t) return;
  const rows = [];
  $('mainPane').querySelectorAll('#stBody tr').forEach((tr) => {
    const cells = tr.querySelectorAll('.sg-cell');
    if (!cells.length) return;
    const row = {};
    cells.forEach((el) => { row[el.dataset.c] = el.value; });
    rows.push(row);
  });
  if (document.getElementById('stBody')) t.rows = rows;
}

async function saveTables() {
  if (!state.projectPath) return;
  collectCurrentTable();
  const assets = {};
  state.tables.forEach((t) => { assets[t.key] = t.rows || []; });
  toast('正在写入子表…');
  try {
    const payload = await api.saveAssets({
      projectPath: state.projectPath,
      assets,
      apply: true,
    });
    applyOpen(payload);
    state.view = 'tables';
    document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'tables'));
    renderTables();
    toast(payload.summary || '子表已写入工程文档');
  } catch (err) {
    toast('子表保存失败：' + err.message);
  }
}

function renderLedger() {
  const L = state.ledger;
  if (!L) {
    $('mainPane').innerHTML = '<p class="empty-hint">打开工程后显示台账</p>';
    return;
  }
  const tot = L.total || 1;
  const g = (L.complete / tot) * 100;
  const b = (L.draft / tot) * 100;
  const r = (L.error / tot) * 100;
  const rows = (L.rows || []).map((row) => (
    '<tr data-open="' + row.itemId + '"><td>' + String(row.seq).padStart(2, '0') +
    '</td><td>' + escapeHtml(row.name) + '</td><td>' + escapeHtml(row.volume) +
    '</td><td>' + fillChip(row.fillState) +
    (row.printed ? ' <span class="chip c-amber">已打印</span>' : '') +
    '</td><td>' + escapeHtml((row.missing || []).join('、') || '—') +
    '</td><td style="color:var(--accent);cursor:pointer">打开 →</td></tr>'
  )).join('');
  $('mainPane').innerHTML =
    '<div class="ledger" style="border:none;padding:0">' +
    '<div class="metric-row">' +
    '<div class="metric"><div class="lab">目录项总数</div><div class="num">' + L.total + '</div></div>' +
    '<div class="metric"><div class="lab">有模板项</div><div class="num">' + L.withTemplate + '</div></div>' +
    '<div class="metric"><div class="lab">已完成</div><div class="num" style="color:var(--green)">' + L.complete + '</div></div>' +
    '<div class="metric"><div class="lab">必填缺失</div><div class="num" style="color:var(--red)">' + L.error + '</div></div>' +
    '</div>' +
    '<div class="bar"><i style="width:' + g + '%;background:var(--green)"></i>' +
    '<i style="width:' + b + '%;background:var(--accent)"></i>' +
    '<i style="width:' + r + '%;background:var(--red)"></i></div>' +
    '<table class="lg-tbl"><tr><th>序号</th><th>目录项名称</th><th>分册</th><th>状态</th><th>缺什么</th><th></th></tr>' +
    rows + '</table></div>';
  $('mainPane').querySelectorAll('[data-open]').forEach((tr) => {
    tr.addEventListener('click', () => selectItem(tr.getAttribute('data-open')));
  });
  const pct = Math.round((L.complete / tot) * 100);
  $('sbDone').textContent = '本册完成度 ' + pct + '%';
}

function renderJobs() {
  const jobs = state.jobs.length ? state.jobs : [
    { ico: 'wait', name: '等待生成必选', detail: '点 Ribbon「生成必选」只生成必选目录项（datafill → fill → docgen → verify）', time: '' },
  ];
  $('mainPane').innerHTML = '<div class="jobs" style="border:none">' + jobs.map((j) => (
    '<div class="job"><span class="j-ico j-' + j.ico + '">' +
    (j.ico === 'ok' ? '✓' : j.ico === 'err' ? '!' : j.ico === 'run' ? '▶' : '·') +
    '</span><span class="j-name">' + escapeHtml(j.name) + '</span>' +
    '<span class="j-detail">' + escapeHtml(j.detail) + '</span>' +
    '<span class="j-time">' + escapeHtml(j.time || '') + '</span></div>'
  )).join('') + '</div>';
}

async function renderPreview() {
  const doc = currentDoc();
  if (!doc) {
    $('mainPane').innerHTML = '<p class="empty-hint">选一份已生成的文档查看只读预览。<br>可选未创建是灰点（不是缺项）；必选未生成是红点。点实例才打开右侧，右键「新建表格」创建。</p>';
    return;
  }
  $('mainPane').innerHTML = '<p class="empty-hint">正在打开预览…</p>';
  try {
    const payload = await api.preview({ projectPath: state.projectPath, docId: doc.docId });
    const st = payload.stats || {};
    const print = st.printState && st.printState.printed
      ? '<span class="chip c-amber">已打印 ×' + (st.printState.times || 1) + '</span>'
      : '<span class="chip c-gray">未打印</span>';
    $('mainPane').innerHTML =
      '<p class="pg-h1">' + escapeHtml(doc.relPath.split('/').pop()) + '</p>' +
      '<p style="text-align:center;font-family:var(--sans);font-size:12px;color:var(--muted)">' +
      fillChip(st.fillState) + ' ' + print +
      (st.docNo ? ' · ' + escapeHtml(st.docNo) : '') + '</p>' +
      (st.html || '<p class="empty-hint">无法提取正文</p>');
  } catch (err) {
    $('mainPane').innerHTML = '<p class="empty-hint">' + escapeHtml(err.message) + '</p>';
  }
}

function collectEditorEdits() {
  const edits = [];
  document.querySelectorAll('#mainPane [data-go-edit]').forEach((el) => {
    const idx = Number(el.dataset.goIdx);
    if (Number.isNaN(idx)) return;
    if (el.dataset.goEdit === 'paragraph') {
      edits.push({ kind: 'paragraph', docxIndex: idx, text: el.textContent || '' });
    } else if (el.dataset.goEdit === 'table-cell') {
      edits.push({
        kind: 'table-cell',
        docxIndex: idx,
        row: Number(el.dataset.goRow),
        col: Number(el.dataset.goCol),
        text: el.textContent || '',
      });
    }
  });
  return edits;
}

function paintEditor(html, note) {
  const mode = state.editor.available ? '嵌入编辑（GenOffice 源码）' : 'E1 回退';
  $('mainPane').innerHTML =
    '<div class="go-bar">' +
    '<span>' + escapeHtml(mode) + (note ? ' · ' + escapeHtml(note) : '') + '</span>' +
    '<span class="go-bar-hint">只写工程副本，永不写 templates</span></div>' +
    (html || '<p class="empty-hint">无正文</p>');
  $('mainPane').querySelectorAll('[data-go-edit]').forEach((el) => {
    el.addEventListener('input', () => setDirty(1));
  });
  $('sbPage').textContent = state.editor.available ? '嵌入正文编辑' : 'E1 只读预览';
}

async function renderEditor() {
  const doc = currentDoc();
  if (!doc) {
    $('mainPane').innerHTML = '<p class="empty-hint">选一份已生成的文档编辑正文 / 表格文字。<br>未创建的目录项请右键「新建表格」。点已有实例才打开编辑。模板资产不可打开写入。</p>';
    return;
  }
  if (!state.editor.available) {
    $('mainPane').innerHTML =
      '<p class="empty-hint">嵌入编辑不可用：' + escapeHtml(state.editor.reason || 'bundle missing') +
      '<br>已回退 E1 只读预览。可切换「预览」页查看。</p>';
    $('sbPage').textContent = 'E1 回退（嵌入不可用）';
    return;
  }
  $('mainPane').innerHTML = '<p class="empty-hint">正在用 GenOffice 引擎打开…</p>';
  try {
    if (state.editor.sessionId) {
      try { await api.editorClose(state.editor.sessionId); } catch { /* ignore */ }
    }
    const payload = await api.editorOpen({
      projectPath: state.projectPath,
      relPath: doc.relPath,
    });
    if (!payload.ok) {
      state.editor.sessionId = null;
      $('mainPane').innerHTML =
        '<p class="empty-hint">无法打开嵌入编辑：' + escapeHtml(payload.reason || 'unknown') +
        '<br>已保持 E1 可用。点「预览」查看只读页。</p>';
      $('sbPage').textContent = 'E1 回退';
      return;
    }
    state.editor.sessionId = payload.sessionId;
    state.editor.html = payload.html;
    state.editor.relPath = payload.relPath;
    const st = payload.stats || {};
    paintEditor(payload.html, (st.visible || 0) + ' 块 / 表 ' + (st.tables || 0));
  } catch (err) {
    $('mainPane').innerHTML = '<p class="empty-hint">' + escapeHtml(err.message) + '</p>';
  }
}

async function saveEditorDocx() {
  if (!state.editor.available || !state.editor.sessionId) {
    toast(state.editor.available ? '先打开一份工程文档' : ('嵌入不可用：' + (state.editor.reason || '')));
    return;
  }
  try {
    const payload = await api.editorSave({
      sessionId: state.editor.sessionId,
      edits: collectEditorEdits(),
    });
    if (!payload.ok) {
      toast(payload.reason || '保存失败');
      return;
    }
    paintEditor(payload.html, '已写回工程副本');
    setDirty(0);
    toast('正文已保存到工程文档（未改 templates）');
  } catch (err) {
    toast('保存失败：' + err.message);
  }
}

function showMainView() {
  if (state.view === 'ledger') renderLedger();
  else if (state.view === 'jobs') renderJobs();
  else if (state.view === 'tables') renderTables();
  else if (state.view === 'edit') renderEditor();
  else renderPreview();
}

function currentDoc() {
  const mine = state.docs.filter((d) => d.itemId === state.selectedItemId && d.exists);
  if (state.selectedDocId) {
    return mine.find((d) => d.docId === state.selectedDocId) || mine[0];
  }
  return mine[0];
}

function applyOpen(payload) {
  const s = payload.stats || {};
  state.projectPath = s.projectPath;
  state.root = s.root;
  state.volumes = s.volumes || [];
  state.items = s.items || [];
  state.docs = s.docs || [];
  state.fields = s.fields || [];
  state.tables = s.tables || [];
  state.values = s.values || {};
  state.ledger = s.ledger;
  state.trash = s.trash || [];
  state.printStates = s.printStates || {};
  if (s.ai) applyAiGate(s.ai);
  const name = state.values.projectName || '未命名工程';
  $('titleText').textContent = '验收资料编辑软件 — ' + name;
  setDirty(0);
  renderTree();
  renderFields();
  if (state.view === 'ledger') renderLedger();
  else if (state.view === 'jobs') renderJobs();
  else if (state.view === 'tables') renderTables();
  else if (state.view === 'edit') renderEditor();
  else renderPreview();
}

function liveDocsFor(itemId) {
  return state.docs.filter((d) => d.itemId === itemId && d.exists);
}

function selectCatalogRow(itemId) {
  state.selectedItemId = itemId;
  state.selectedDocId = null;
  renderTree();
}

function selectInstance(itemId, docId) {
  state.selectedItemId = itemId;
  const docs = liveDocsFor(itemId);
  if (docId && docs.some((d) => d.docId === docId)) {
    state.selectedDocId = docId;
  } else {
    state.selectedDocId = docs[0] ? docs[0].docId : null;
  }
  if (!state.selectedDocId) {
    toast('尚未创建实例，请先「新建表格」');
    renderTree();
    return;
  }
  state.view = state.editor.available ? 'edit' : 'preview';
  document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === state.view));
  renderTree();
  showMainView();
}

function selectItem(itemId, docId) {
  if (docId) selectInstance(itemId, docId);
  else selectCatalogRow(itemId);
}

function hideTreeMenu() {
  const menu = $('treeMenu');
  if (menu) menu.classList.add('hidden');
}

async function newTable(itemId) {
  if (!state.projectPath || !itemId) {
    toast('请先打开工程并选中目录项');
    return;
  }
  hideTreeMenu();
  toast('正在新建表格…');
  try {
    const payload = await api.generateItem({
      projectPath: state.projectPath,
      itemId,
      count: 1,
    });
    if (!payload.ok) {
      toast(payload.summary || '新建表格失败');
      return;
    }
    applyOpen(payload);
    const gen = (payload.stats && payload.stats.generate) || {};
    const created = ((gen.items || payload.items) || []).find((x) => x.action === 'created')
      || ((gen.items || [])[0]);
    if (created && created.docId) selectInstance(itemId, created.docId);
    else selectCatalogRow(itemId);
    toast(payload.summary || gen.summary || '已新建表格');
  } catch (err) {
    toast('新建表格失败：' + err.message);
  }
}

document.querySelectorAll('[data-act]').forEach((el) => {
  el.addEventListener('click', () => onAct(el.dataset.act));
});
document.querySelectorAll('[data-close]').forEach((el) => {
  el.addEventListener('click', () => hide(el.dataset.close));
});
document.querySelectorAll('.tab').forEach((el) => {
  el.addEventListener('click', () => {
    state.leftTab = el.dataset.tab;
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('on', t === el));
    renderTree();
  });
});
document.querySelectorAll('.etab').forEach((el) => {
  el.addEventListener('click', () => {
    state.view = el.dataset.view;
    document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t === el));
    if (state.view === 'ledger') renderLedger();
    else if (state.view === 'jobs') renderJobs();
    else if (state.view === 'tables') renderTables();
    else if (state.view === 'edit') renderEditor();
    else renderPreview();
  });
});

$('treePane').addEventListener('click', (e) => {
  hideTreeMenu();
  const vol = e.target.closest('[data-vol]');
  if (vol) {
    const name = decodeURIComponent(vol.dataset.vol);
    if (state.collapsed.has(name)) state.collapsed.delete(name);
    else state.collapsed.add(name);
    renderTree();
    return;
  }
  const node = e.target.closest('[data-item]');
  if (node) {
    if (node.dataset.doc) selectInstance(node.dataset.item, node.dataset.doc);
    else selectCatalogRow(node.dataset.item);
  }
});

$('treePane').addEventListener('contextmenu', (e) => {
  const node = e.target.closest('[data-item]');
  if (!node) return;
  e.preventDefault();
  const menu = $('treeMenu');
  if (!menu) return;
  menu.dataset.item = node.dataset.item;
  menu.dataset.doc = node.dataset.doc || '';
  menu.style.left = e.clientX + 'px';
  menu.style.top = e.clientY + 'px';
  menu.classList.remove('hidden');
});

document.addEventListener('click', (e) => {
  if (!e.target.closest('#treeMenu')) hideTreeMenu();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') hideTreeMenu();
});
const treeMenu = $('treeMenu');
if (treeMenu) {
  treeMenu.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-ctx]');
    if (!btn) return;
    const itemId = treeMenu.dataset.item;
    const docId = treeMenu.dataset.doc || '';
    if (btn.dataset.ctx === 'new-table') newTable(itemId);
    else if (btn.dataset.ctx === 'open') openTable(itemId, docId);
    else if (btn.dataset.ctx === 'delete') deleteTable(itemId, docId);
  });
}

function openTable(itemId, docId) {
  hideTreeMenu();
  const docs = liveDocsFor(itemId);
  const target = docId && docs.find((d) => d.docId === docId);
  if (target) {
    selectInstance(itemId, target.docId);
    return;
  }
  if (docs[0]) {
    selectInstance(itemId, docs[0].docId);
    return;
  }
  toast('尚未创建实例，请先「新建表格」');
}

async function deleteTable(itemId, docId) {
  hideTreeMenu();
  if (!state.projectPath) {
    toast('请先打开工程');
    return;
  }
  const docs = liveDocsFor(itemId);
  const target = (docId && docs.find((d) => d.docId === docId)) || docs[0];
  if (!target) {
    toast('没有可删除的实例');
    return;
  }
  if (!window.confirm('删除该实例？编号不重排（删 02 留 03）。')) return;
  try {
    const payload = await api.trashPut({
      projectPath: state.projectPath,
      docId: target.docId,
    });
    if (!payload.ok) {
      toast(payload.summary || '删除失败');
      return;
    }
    applyOpen(payload);
    selectCatalogRow(itemId);
    toast(payload.summary || '已删除（编号不重排）');
  } catch (err) {
    toast('删除失败：' + err.message);
  }
}

$('btnSync').addEventListener('click', saveFields);
$('btnSave').addEventListener('click', () => {
  if (state.view === 'edit') saveEditorDocx();
  else saveFields();
});
$('btnSaveDocx').addEventListener('click', saveEditorDocx);
$('btnSyncRevert').addEventListener('click', () => confirmSync('revert'));
$('btnSyncThis').addEventListener('click', () => confirmSync('this'));
$('btnSyncAll').addEventListener('click', () => confirmSync('all'));
$('btnCollapse').addEventListener('click', () => {
  state.panelOpen = !state.panelOpen;
  $('fieldPanel').classList.toggle('collapsed', !state.panelOpen);
});
$('btnPanel').addEventListener('click', () => {
  state.panelOpen = !state.panelOpen;
  $('fieldPanel').classList.toggle('collapsed', !state.panelOpen);
});
$('btnCreateGo').addEventListener('click', async () => {
  const fields = {
    projectName: $('c_projectName').value.trim(),
    ownerUnit: $('c_ownerUnit').value.trim(),
    constructionUnit: $('c_constructionUnit').value.trim(),
    contractNo: $('c_contractNo').value.trim(),
  };
  if (!fields.projectName || !fields.ownerUnit || !fields.constructionUnit) {
    toast('工程名称 / 建设单位 / 施工单位 必填');
    return;
  }
  hide('dlgCreate');
  try {
    const payload = await api.createProject(fields);
    if (payload.cancelled) return;
    applyOpen(payload);
    toast('工程已创建');
  } catch (err) {
    toast('创建失败：' + err.message);
  }
});

function renderHealth(payload) {
  const items = payload.items || (payload.stats && payload.stats.items) || [];
  const list = $('healthList');
  const sum = $('healthSummary');
  const ok = payload.ok !== false && !items.some((it) => it.level === 'fail');
  sum.className = 'health-sum ' + (ok ? 'ok' : 'bad');
  sum.textContent = payload.summary || (ok ? '体检通过' : '体检失败');
  const markClass = { pass: 'hc-pass', fail: 'hc-fail', warn: 'hc-warn', skip: 'hc-skip' };
  list.innerHTML = items.map((it) => {
    const lv = it.level || (it.ok ? 'pass' : 'fail');
    const lab = { pass: '通过', fail: '失败', warn: '警告', skip: '可选' }[lv] || lv;
    return '<div class="hc"><span class="hc-mark ' + (markClass[lv] || '') + '">' + lab +
      '</span><div class="hc-body"><span class="hc-key">' + escapeHtml(it.key || '') +
      '</span><span class="hc-detail">' + escapeHtml(it.detail || '') + '</span></div></div>';
  }).join('') || '<p class="empty-hint">无结果</p>';
}

async function runHealthCheck() {
  $('healthSummary').className = 'health-sum';
  $('healthSummary').textContent = '正在体检…';
  $('healthList').innerHTML = '';
  try {
    const payload = await api.health();
    renderHealth(payload);
    toast(payload.summary || '体检完成');
  } catch (err) {
    $('healthSummary').className = 'health-sum bad';
    $('healthSummary').textContent = '体检失败：' + err.message;
    toast('体检失败：' + err.message);
  }
}

$('btnHealthGo').addEventListener('click', runHealthCheck);
$('btnExportGo').addEventListener('click', async () => {
  hide('dlgExport');
  if (!state.projectPath) return;
  const mode = document.querySelector('input[name="exmode"]:checked').value;
  const force = $('exForce').checked;
  const doc = currentDoc();
  toast('正在导出…');
  try {
    const payload = await api.exportPdf({
      projectPath: state.projectPath,
      mode,
      docId: mode === 'single' ? (doc && doc.docId) : '',
      force,
    });
    toast(payload.summary || '导出完成');
    if (payload.ok) {
      const st = payload.stats || {};
      const out = (st.stats && st.stats.out) || (st.out);
      applyOpen(await api.openPath(state.root));
    }
  } catch (err) {
    toast('导出失败：' + err.message);
  }
});

async function saveFields() {
  if (!state.projectPath) return;
  const fields = collectFields();
  try {
    const preview = await api.syncPreview({
      projectPath: state.projectPath,
      fields,
    });
    const changes = (preview.stats && preview.stats.changes) || [];
    const hasDocs = changes.some((c) => (c.docCount || 0) > 0) || (state.docs || []).some((d) => d.exists);
    if (changes.length && hasDocs) {
      state.pendingFields = fields;
      const n = Math.max(...changes.map((c) => c.docCount || 0), 0);
      $('syncIntro').textContent =
        '改动 ' + changes.length + ' 个项目级字段。另有最多 ' + n + ' 份已生成文档可能包含这些字段。';
      $('syncBody').innerHTML = changes.map((c) => (
        '<div class="sync-row"><b>' + escapeHtml(c.label || c.key) + '</b>' +
        '<div class="sync-old">档案值：' + escapeHtml(c.old) + '</div>' +
        '<div class="sync-new">新值：' + escapeHtml(c.new) + '</div>' +
        '<div class="sync-n">影响 ' + (c.anchorCount || 0) + ' 份锚点 / ' + (c.docCount || 0) + ' 份文档</div></div>'
      )).join('');
      const doc = currentDoc();
      $('btnSyncThis').disabled = !doc;
      $('btnSyncThis').title = doc ? '' : '先在目录树选一份已生成的文档';
      show('dlgSync');
      return;
    }
    const payload = await api.saveFields({
      projectPath: state.projectPath,
      fields,
      syncMode: 'project',
    });
    applyOpen(payload);
    toast('已写入 project.json');
  } catch (err) {
    toast('保存失败：' + err.message);
  }
}

async function confirmSync(mode) {
  hide('dlgSync');
  const fields = state.pendingFields;
  state.pendingFields = null;
  if (!fields) return;
  if (mode === 'revert') {
    renderFields();
    setDirty(0);
    toast('已撤销，未写入');
    return;
  }
  const doc = currentDoc();
  try {
    const payload = await api.saveFields({
      projectPath: state.projectPath,
      fields,
      relPath: mode === 'this' && doc ? doc.relPath : '',
      syncMode: mode,
    });
    applyOpen(payload);
    toast(mode === 'this' ? '仅本份已覆盖，其他文档未改' : '已同步到项目档案');
  } catch (err) {
    toast('同步失败：' + err.message);
  }
}

async function onAct(act) {
  if (act === 'quit') return window.close();
  if (['ai-draft', 'ai-polish', 'ai-expand', 'ai-fill', 'ai-qa'].includes(act) && !state.ai.available) {
    toast('AI 不可用：' + (state.ai.reason || 'offline') + '（其余功能不受影响）');
    return;
  }
  if (act === 'about') {
    const f = state.fidelity || {};
    const ed = state.editor || {};
    $('aboutFidelity').textContent =
      'V1=' + f.v1 + '  V2=' + f.v2 + '  V3=' + f.v3 + '  V4=' + f.v4 +
      '  · 编辑模式 ' + (f.editorMode || 'E1') +
      (ed.available ? '（嵌入可用）' : ('（嵌入不可用，E1 回退：' + (ed.reason || '') + '）'));
    show('dlgAbout');
    return;
  }
  if (act === 'manual') {
    api.openManual().then((r) => {
      if (!r || !r.ok) toast('未找到使用手册（docs/使用手册.md）');
    }).catch((err) => toast(err.message));
    return;
  }
  if (act === 'health') {
    show('dlgHealth');
    return;
  }
  if (act === 'create') { show('dlgCreate'); return; }
  if (act === 'open') {
    try {
      const payload = await api.openProject();
      if (payload.cancelled) return;
      applyOpen(payload);
      state.view = 'ledger';
      document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'ledger'));
      renderLedger();
      toast('已打开工程');
    } catch (err) { toast('打开失败：' + err.message); }
    return;
  }
  if (act === 'info') {
    state.view = 'ledger';
    document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'ledger'));
    renderLedger();
    return;
  }
  if (act === 'ledger') {
    state.view = 'ledger';
    document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'ledger'));
    renderLedger();
    return;
  }
  if (act === 'find') {
    state.leftTab = 'search';
    document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('on', t.dataset.tab === 'search'));
    const q = prompt('查找目录项名称');
    if (q) {
      const hits = state.items.filter((it) => (it.name || '').includes(q));
      $('treePane').innerHTML = hits.length
        ? hits.map((it) => '<div class="tn lv2" data-item="' + it.itemId + '">' + escapeHtml(it.name) + '</div>').join('')
        : '<p class="empty-hint">没有匹配</p>';
    } else renderTree();
    return;
  }
  if (act === 'booklet') {
    if (!state.projectPath) { toast('请先打开工程'); return; }
    state.view = 'jobs';
    document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'jobs'));
    state.jobs = [
      { ico: 'run', name: '生成必选 · 运行中', detail: '仅必选 · datafill → fill → docgen → verify', time: '' },
      { ico: 'wait', name: 'datafill 取值装配', detail: '等待', time: '' },
      { ico: 'wait', name: 'fill 填充', detail: '等待', time: '' },
      { ico: 'wait', name: 'docgen 生成', detail: '等待', time: '' },
      { ico: 'wait', name: 'verify 校验', detail: '等待', time: '' },
    ];
    renderJobs();
    try {
      const payload = await api.booklet(state.projectPath);
      const stages = (payload.stages || (payload.stats && payload.stats.stages) || []);
      state.jobs = stages.map((s) => ({
        ico: s.exit === 0 || s.ok ? 'ok' : 'err',
        name: s.stage,
        detail: s.summary || ('exit ' + s.exit),
        time: '',
      }));
      state.jobs.unshift({
        ico: payload.ok ? 'ok' : 'err',
        name: '生成必选',
        detail: payload.summary || '',
        time: '',
      });
      renderJobs();
      applyOpen(await api.openPath(state.root));
      toast(payload.summary || '成册结束');
    } catch (err) {
      toast('成册失败：' + err.message);
    }
    return;
  }
  if (act === 'print-preview') {
    const doc = currentDoc();
    if (!doc) { toast('先选一份已生成的文档'); return; }
    state.view = 'preview';
    document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'preview'));
    await renderPreview();
    toast('打印预览 = 当前只读页');
    return;
  }
  if (act === 'print-mark') {
    const doc = currentDoc();
    if (!doc || !state.projectPath) { toast('先选一份文档'); return; }
    try {
      await api.markPrinted({ projectPath: state.projectPath, docId: doc.docId, printed: true });
      applyOpen(await api.openPath(state.root));
      toast('已标记打印（写入 _printStates，关软件重开仍在）');
    } catch (err) { toast(err.message); }
    return;
  }
  if (act === 'export') {
    if (!state.projectPath) { toast('请先打开工程'); return; }
    show('dlgExport');
    return;
  }
  if (act === 'weekly' || act === 'monthly') {
    await runAggregate(act === 'weekly' ? 'week' : 'month');
    return;
  }
  if (act === 'ai-draft' || act === 'ai-polish' || act === 'ai-expand') {
    openRewrite(act.replace('ai-', ''));
    return;
  }
  if (act === 'ai-fill') {
    $('exCands').innerHTML = '';
    $('btnExApply').disabled = true;
    show('dlgExtract');
    return;
  }
  if (act === 'ai-qa') {
    await runQa();
    return;
  }
  if (act === 'noop') return;
}

async function runAggregate(period) {
  if (!state.projectPath) { toast('请先打开工程'); return; }
  state.view = 'jobs';
  document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'jobs'));
  state.jobs = [{ ico: 'run', name: 'aggregate', detail: period + ' 汇总中（确定性规则，不调用模型）', time: '' }];
  renderJobs();
  try {
    const payload = await api.aggregate({ projectPath: state.projectPath, period: period });
    state.jobs = [{
      ico: payload.ok ? 'ok' : 'err',
      name: period === 'week' ? '周报' : '月报',
      detail: payload.summary || '',
      time: '',
    }];
    renderJobs();
    if (state.root) applyOpen(await api.openPath(state.root));
    toast(payload.summary || '汇总结束');
  } catch (err) {
    toast('汇总失败：' + err.message);
  }
}

function openRewrite(mode) {
  state.rewriteMode = mode;
  const titles = { draft: 'AI 起草', polish: 'AI 润色', expand: 'AI 扩写' };
  $('rwTitle').textContent = titles[mode] || 'AI';
  $('rwOut').value = '';
  $('btnRwApply').disabled = true;
  const bg = (collectFields().projectBackground || state.values.projectBackground || '');
  if (mode !== 'draft' && bg && !$('rwSrc').value) $('rwSrc').value = bg;
  $('rwHint').textContent = '模型：' + (state.ai.model || 'deepseek-flash') + '。确认后才写入字段。失败不会伪造正文。';
  show('dlgRewrite');
}

async function runQa() {
  if (!state.projectPath) { toast('请先打开工程'); return; }
  show('dlgQa');
  $('qaSummary').textContent = '正在校验…';
  $('qaBody').textContent = '';
  try {
    const payload = await api.aiQa(state.projectPath);
    const st = payload.stats || {};
    $('qaSummary').textContent = payload.summary || '';
    const live = st.liveModel ? ('\n\n【模型解说 · ' + (st.model || '') + '】\n' + (payload.narration || '')) : '\n\n（未调用模型或调用失败，以上为校验闸门原文，不是伪造的模型答复）';
    $('qaBody').textContent = JSON.stringify(payload.verify || payload.items || {}, null, 2) + live;
    toast(payload.summary || '查错完成');
  } catch (err) {
    $('qaSummary').textContent = '查错失败';
    $('qaBody').textContent = err.message;
  }
}

function renderExtractCands(items) {
  const box = $('exCands');
  if (!items.length) {
    box.innerHTML = '<p class="empty-hint">没有抽到候选</p>';
    $('btnExApply').disabled = true;
    return;
  }
  box.innerHTML = items.map((c, i) => (
    '<label class="cand"><input type="checkbox" checked data-i="' + i + '">' +
    '<span class="k">' + escapeHtml(c.label || c.key) + '</span>' +
    '<input type="text" data-val="' + i + '" value="' + escapeHtml(c.value || '') + '">' +
    '<span class="src s-import">' + escapeHtml(c.source || 'rules') + '</span></label>'
  )).join('');
  box._items = items;
  $('btnExApply').disabled = false;
}

$('btnRwRun').addEventListener('click', async () => {
  if (!state.ai.available) { toast('AI 不可用'); return; }
  const text = $('rwSrc').value.trim();
  if (!text) { toast('请先填写原文'); return; }
  $('btnRwRun').disabled = true;
  try {
    const payload = await api.aiRewrite({
      projectPath: state.projectPath,
      mode: state.rewriteMode,
      text: text,
    });
    if (!payload.ok) {
      $('rwOut').value = '';
      toast(payload.summary || '模型不可用，未伪造回复');
      return;
    }
    $('rwOut').value = payload.text || ((payload.items || [])[0] && payload.items[0].text) || '';
    $('btnRwApply').disabled = !$('rwOut').value;
    toast(payload.summary || '已生成');
  } catch (err) {
    $('rwOut').value = '';
    toast(err.message);
  } finally {
    $('btnRwRun').disabled = false;
  }
});

$('btnRwApply').addEventListener('click', () => {
  const text = $('rwOut').value;
  if (!text) return;
  const key = state.rewriteTarget || 'projectBackground';
  const el = document.querySelector('#fieldBody .fp-val[data-key="' + key + '"]');
  if (el) {
    el.value = text;
    setDirty(1);
  }
  hide('dlgRewrite');
  toast('已写入 ' + key + '（尚未点保存）');
});

$('btnExRun').addEventListener('click', async () => {
  if (!state.ai.available) { toast('AI 不可用'); return; }
  const text = $('exSrc').value.trim();
  if (!text) { toast('请先粘贴资料'); return; }
  try {
    const payload = await api.aiExtract({ text: text });
    renderExtractCands(payload.items || (payload.stats && payload.stats.items) || []);
    toast(payload.summary || '已抽取');
  } catch (err) { toast(err.message); }
});

$('btnExApply').addEventListener('click', async () => {
  const box = $('exCands');
  const items = box._items || [];
  const confirmed = [];
  box.querySelectorAll('input[type=checkbox]:checked').forEach((cb) => {
    const i = Number(cb.dataset.i);
    const src = items[i];
    if (!src) return;
    const typed = box.querySelector('input[data-val="' + i + '"]');
    confirmed.push({
      key: src.key,
      label: src.label,
      value: typed ? typed.value : src.value,
      source: src.source,
    });
  });
  if (!confirmed.length) { toast('请勾选要回写的字段'); return; }
  if (!state.projectPath) { toast('请先打开工程'); return; }
  try {
    const payload = await api.aiApply({
      projectPath: state.projectPath,
      payload: { confirmed: confirmed },
    });
    if (!payload.ok) { toast(payload.summary || '回写被拒绝'); return; }
    hide('dlgExtract');
    applyOpen(await api.openPath(state.root));
    toast(payload.summary || '已回写');
  } catch (err) { toast(err.message); }
});

api.onProgress((line) => {
  toast(line.replace('#PROGRESS ', '').replace('#STAGE ', '阶段 '));
  if (line.startsWith('#STAGE')) {
    const m = line.match(/#STAGE (\S+) (\w+)/);
    if (m) {
      const name = m[1];
      const ev = m[2];
      const job = state.jobs.find((j) => j.name === name);
      if (job) {
        job.ico = ev === 'start' ? 'run' : 'ok';
        job.detail = line;
        if (state.view === 'jobs') renderJobs();
      }
    }
  }
});

(async function init() {
  try {
    const ed = await api.editorStatus();
    state.editor.available = !!ed.available;
    state.editor.reason = ed.reason || '';
  } catch (err) {
    state.editor.available = false;
    state.editor.reason = err.message || 'status-error';
  }
  try {
    state.fidelity = await api.fidelity();
    const f = state.fidelity;
    const ed = state.editor;
    const mode = (f && f.editorMode) || (ed && ed.available ? 'genoffice-embed' : 'E1');
    $('modeBanner').textContent =
      (ed && ed.available
        ? '编辑内核：嵌入 GenOffice 源码（正文/表格文字可写回工程副本；模板只读）'
        : '编辑内核：E1 表单 + 只读预览（嵌入不可用：' + ((ed && ed.reason) || '未构建') + '）') +
      '  ·  V1 ' + (f && f.v1) + ' / V2 ' + (f && f.v2) + ' / V3 ' + (f && f.v3) + ' / V4 ' + (f && f.v4) +
      '  · 模式 ' + mode;
    $('sbPage').textContent = ed && ed.available ? '嵌入正文编辑就绪' : 'E1 只读预览';
  } catch {
    /* ignore */
  }
  applyAiGate({ available: false, reason: 'pending', hasKey: false });
  await refreshAiGate();
  try {
    const auto = await api.autoProject();
    if (auto) {
      const payload = await api.openPath(auto);
      applyOpen(payload);
      state.view = 'ledger';
      document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === 'ledger'));
      renderLedger();
      toast('已自动打开工程');
    }
  } catch (err) {
    toast('自动打开失败：' + err.message);
  }
})();
