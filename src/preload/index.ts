import { contextBridge, ipcRenderer } from 'electron'
import type { StudioAPI } from '../shared/api'

const api: StudioAPI = {
  dataDir: () => ipcRenderer.invoke('studio:dataDir'),
  listProjects: () => ipcRenderer.invoke('studio:listProjects'),
  getProject: (id) => ipcRenderer.invoke('studio:getProject', id),
  createProject: (input) => ipcRenderer.invoke('studio:createProject', input),
  updateProject: (id, patch) => ipcRenderer.invoke('studio:updateProject', id, patch),
  openProjectFile: () => ipcRenderer.invoke('studio:openProjectFile'),
  getCatalogState: (projectId) => ipcRenderer.invoke('studio:getCatalogState', projectId),
  getItemEditor: (projectId, itemCode) => ipcRenderer.invoke('studio:getItemEditor', projectId, itemCode),
  saveItemFields: (projectId, itemCode, fields, as) =>
    ipcRenderer.invoke('studio:saveItemFields', projectId, itemCode, fields, as),
  uploadFiles: (projectId, itemCode) => ipcRenderer.invoke('studio:uploadFiles', projectId, itemCode),
  fillItem: (projectId, itemCode) => ipcRenderer.invoke('studio:fillItem', projectId, itemCode),
  fillVolume: (projectId) => ipcRenderer.invoke('studio:fillVolume', projectId),
  checkExport: (projectId, itemCode) => ipcRenderer.invoke('studio:checkExport', projectId, itemCode),
  exportItem: (projectId, itemCode) => ipcRenderer.invoke('studio:exportItem', projectId, itemCode),
  printWarn: (projectId, itemCode) => ipcRenderer.invoke('studio:printWarn', projectId, itemCode),
  printPreview: (projectId, itemCode) => ipcRenderer.invoke('studio:printPreview', projectId, itemCode),
  printItem: (projectId, itemCode) => ipcRenderer.invoke('studio:printItem', projectId, itemCode),
  previewFile: (storedPath) => ipcRenderer.invoke('studio:previewFile', storedPath),
  revealInFolder: (filePath) => ipcRenderer.invoke('studio:revealInFolder', filePath),
  engineStatus: () => ipcRenderer.invoke('studio:engineStatus')
}

contextBridge.exposeInMainWorld('studio', api)
