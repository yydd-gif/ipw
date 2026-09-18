const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  fidelity: () => ipcRenderer.invoke('fidelity'),
  repoInfo: () => ipcRenderer.invoke('repo-info'),
  autoProject: () => ipcRenderer.invoke('auto-project'),
  createProject: (fields) => ipcRenderer.invoke('create-project', fields),
  openProject: () => ipcRenderer.invoke('open-project'),
  openPath: (dir) => ipcRenderer.invoke('open-path', dir),
  saveFields: (opts) => ipcRenderer.invoke('save-fields', opts),
  syncPreview: (opts) => ipcRenderer.invoke('sync-preview', opts),
  saveAssets: (opts) => ipcRenderer.invoke('save-assets', opts),
  applySubtables: (opts) => ipcRenderer.invoke('apply-subtables', opts),
  booklet: (projectPath) => ipcRenderer.invoke('booklet', projectPath),
  createItem: (opts) => ipcRenderer.invoke('create-item', opts),
  pickUpload: () => ipcRenderer.invoke('pick-upload'),
  preview: (opts) => ipcRenderer.invoke('preview', opts),
  markPrinted: (opts) => ipcRenderer.invoke('mark-printed', opts),
  exportPdf: (opts) => ipcRenderer.invoke('export-pdf', opts),
  trashPut: (opts) => ipcRenderer.invoke('trash-put', opts),
  trashList: (dir) => ipcRenderer.invoke('trash-list', dir),
  showItem: (p) => ipcRenderer.invoke('show-item', p),
  revealRoot: (dir) => ipcRenderer.invoke('reveal-root', dir),
  aiStatus: () => ipcRenderer.invoke('ai-status'),
  aiExtract: (opts) => ipcRenderer.invoke('ai-extract', opts),
  aiRewrite: (opts) => ipcRenderer.invoke('ai-rewrite', opts),
  aiApply: (opts) => ipcRenderer.invoke('ai-apply', opts),
  aiQa: (projectPath) => ipcRenderer.invoke('ai-qa', projectPath),
  aggregate: (opts) => ipcRenderer.invoke('aggregate', opts),
  health: () => ipcRenderer.invoke('health'),
  openManual: () => ipcRenderer.invoke('open-manual'),
  editorStatus: () => ipcRenderer.invoke('editor-status'),
  editorOpen: (opts) => ipcRenderer.invoke('editor-open', opts),
  editorSave: (opts) => ipcRenderer.invoke('editor-save', opts),
  editorClose: (id) => ipcRenderer.invoke('editor-close', id),
  onProgress: (cb) => {
    const fn = (_e, line) => cb(line);
    ipcRenderer.on('engine-progress', fn);
    return () => ipcRenderer.removeListener('engine-progress', fn);
  },
});
