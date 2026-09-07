import { contextBridge, ipcRenderer } from 'electron'
import type { StudioAPI } from '../shared/api'

const api: StudioAPI = {
  dataDir: () => ipcRenderer.invoke('studio:dataDir'),
  listProjects: () => ipcRenderer.invoke('studio:listProjects'),
  getProject: (id) => ipcRenderer.invoke('studio:getProject', id),
  createProject: (input) => ipcRenderer.invoke('studio:createProject', input),
  updateProject: (id, patch) => ipcRenderer.invoke('studio:updateProject', id, patch),
  listLogs: (projectId) => ipcRenderer.invoke('studio:listLogs', projectId),
  saveLog: (input) => ipcRenderer.invoke('studio:saveLog', input),
  deleteLog: (id) => ipcRenderer.invoke('studio:deleteLog', id),
  getCatalogState: (projectId) => ipcRenderer.invoke('studio:getCatalogState', projectId),
  setItemStatus: (projectId, itemCode, status, notes) =>
    ipcRenderer.invoke('studio:setItemStatus', projectId, itemCode, status, notes),
  updateItemPayload: (projectId, itemCode, payload) =>
    ipcRenderer.invoke('studio:updateItemPayload', projectId, itemCode, payload),
  uploadFiles: (projectId, itemCode) => ipcRenderer.invoke('studio:uploadFiles', projectId, itemCode),
  generateDocument: (projectId, itemCode, extra) =>
    ipcRenderer.invoke('studio:generateDocument', projectId, itemCode, extra),
  generateWeeklyReport: (projectId, options) =>
    ipcRenderer.invoke('studio:generateWeeklyReport', projectId, options),
  generateMonthlyReport: (projectId, options) =>
    ipcRenderer.invoke('studio:generateMonthlyReport', projectId, options),
  checkExport: (projectId) => ipcRenderer.invoke('studio:checkExport', projectId),
  confirmReady: (projectId) => ipcRenderer.invoke('studio:confirmReady', projectId),
  exportZip: (projectId) => ipcRenderer.invoke('studio:exportZip', projectId),
  openPath: (filePath) => ipcRenderer.invoke('studio:openPath', filePath),
  revealInFolder: (filePath) => ipcRenderer.invoke('studio:revealInFolder', filePath)
}

contextBridge.exposeInMainWorld('studio', api)
