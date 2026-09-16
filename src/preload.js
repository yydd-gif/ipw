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
  preview: (opts) => ipcRenderer.invoke('preview', opts),
  markPrinted: (opts) => ipcRenderer.invoke('mark-printed', opts),
  exportPdf: (opts) => ipcRenderer.invoke('export-pdf', opts),
  trashPut: (opts) => ipcRenderer.invoke('trash-put', opts),
  trashList: (dir) => ipcRenderer.invoke('trash-list', dir),
  showItem: (p) => ipcRenderer.invoke('show-item', p),
  revealRoot: (dir) => ipcRenderer.invoke('reveal-root', dir),
  onProgress: (cb) => {
    const fn = (_e, line) => cb(line);
    ipcRenderer.on('engine-progress', fn);
    return () => ipcRenderer.removeListener('engine-progress', fn);
  },
});
