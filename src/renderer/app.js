/* global api */
const state = {
  fidelity: null,
  projectPath: null,
  root: null,
  volumes: [],
  items: [],
  docs: [],
  fields: [],
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
};

function $(id) { return document.getElementById(id); }
function show(id) { $(id).classList.remove('hidden'); }
function hide(id) { $(id).classList.add('hidden'); }

function setDirty(n) {
  state.dirty = n > 0;
  $('dirtyMark').classList.toggle('hidden', !state.dirty);
  $('sbDirty').textContent = '未保存更改 ' + n + ' 处';
}

function toast(msg) {
  $('sbEngine').textContent = msg;
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
      const on = it.itemId === state.selectedItemId ? ' on' : '';
      const print = it.printed ? '<span class="badge-print">印</span>' : '';
      html.push(
        '<div class="tn lv2' + on + '" data-item="' + it.itemId + '">' +
        '<span class="caret">·</span>' +
        escapeHtml(String(it.seq).padStart(2, '0') + ' ' + it.name) +
        print +
        '<span class="dot d-' + (it.dot || 'gray') + '" title="' + (it.fillState || 'empty') + '"></span>' +
        '</div>'
      );
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
    { ico: 'wait', name: '等待一键成册', detail: '点 Ribbon「一键成册」调用 datafill → fill → docgen → verify', time: '' },
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
    $('mainPane').innerHTML = '<p class="empty-hint">选一份已生成的文档查看只读预览。<br>未成册的目录项先点「一键成册」。</p>';
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
  state.values = s.values || {};
  state.ledger = s.ledger;
  state.trash = s.trash || [];
  state.printStates = s.printStates || {};
  const name = state.values.projectName || '未命名工程';
  $('titleText').textContent = '验收资料编辑软件 — ' + name;
  setDirty(0);
  renderTree();
  renderFields();
  if (state.view === 'ledger') renderLedger();
  else if (state.view === 'jobs') renderJobs();
  else renderPreview();
}

function selectItem(itemId) {
  state.selectedItemId = itemId;
  const docs = state.docs.filter((d) => d.itemId === itemId);
  state.selectedDocId = docs[0] ? docs[0].docId : null;
  state.view = docs.length ? 'preview' : 'ledger';
  document.querySelectorAll('.etab').forEach((t) => t.classList.toggle('on', t.dataset.view === state.view));
  renderTree();
  if (state.view === 'preview') renderPreview();
  else renderLedger();
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
    else renderPreview();
  });
});

$('treePane').addEventListener('click', (e) => {
  const vol = e.target.closest('[data-vol]');
  if (vol) {
    const name = decodeURIComponent(vol.dataset.vol);
    if (state.collapsed.has(name)) state.collapsed.delete(name);
    else state.collapsed.add(name);
    renderTree();
    return;
  }
  const item = e.target.closest('[data-item]');
  if (item) selectItem(item.dataset.item);
});

$('btnSync').addEventListener('click', saveFields);
$('btnSave').addEventListener('click', saveFields);
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
  try {
    const payload = await api.saveFields({
      projectPath: state.projectPath,
      fields: collectFields(),
    });
    applyOpen(payload);
    toast('已写入 project.json');
  } catch (err) {
    toast('保存失败：' + err.message);
  }
}

async function onAct(act) {
  if (act === 'quit') return window.close();
  if (act === 'about') {
    const f = state.fidelity || {};
    $('aboutFidelity').textContent =
      'V1=' + f.v1 + '  V2=' + f.v2 + '  V3=' + f.v3 + '  V4=' + f.v4 +
      '  · 编辑模式 ' + (f.editorMode || 'E1');
    show('dlgAbout');
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
      { ico: 'run', name: '一键成册 · 运行中', detail: 'datafill → fill → docgen → verify', time: '' },
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
        name: '一键成册',
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
    toast('打印预览 = 当前只读页（E1）');
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
  if (act === 'noop') return;
}

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
    state.fidelity = await api.fidelity();
    const f = state.fidelity;
    $('modeBanner').textContent =
      '编辑内核：' + (f.editorMode === 'E1' ? 'E1 表单 + 只读预览' : f.editorMode) +
      '  ·  V1 ' + f.v1 + ' / V2 ' + f.v2 + ' / V3 ' + f.v3 + ' / V4 ' + f.v4 +
      (f.note ? '  — ' + f.note : '');
  } catch {
    /* ignore */
  }
})();
