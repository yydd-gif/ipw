import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { join } from 'node:path'
import { existsSync } from 'node:fs'
import { Studio } from '../core/studio'
import type { DailyLogInput, ItemStatus, ProjectInput, WeeklyReportOptions } from '../shared/types'

if (process.platform === 'linux') {
  app.disableHardwareAcceleration()
  app.commandLine.appendSwitch('no-sandbox')
  app.commandLine.appendSwitch('disable-gpu')
}

// GENOFFICE_EXTENSION_POINT: later, open generated docx via GenOffice instead of OS default.
async function openGeneratedDocument(filePath: string): Promise<void> {
  const err = await shell.openPath(filePath)
  if (err) {
    console.warn('openPath failed:', err)
  }
}

function resolveTemplatesDir(): string {
  const packaged = join(process.resourcesPath || '', 'templates')
  const dev = join(app.getAppPath(), 'templates')
  const cwd = join(process.cwd(), 'templates')
  if (app.isPackaged && existsSync(packaged)) return packaged
  if (existsSync(dev)) return dev
  return cwd
}

function resolveDataDir(): string {
  if (process.env.ACCEPTANCE_STUDIO_HOME) return process.env.ACCEPTANCE_STUDIO_HOME
  return join(app.getPath('userData'), 'acceptance-studio')
}

let studio: Studio

async function getStudio(): Promise<Studio> {
  if (!studio) {
    studio = new Studio({
      dataDir: resolveDataDir(),
      templatesDir: resolveTemplatesDir()
    })
    await studio.init()
  }
  return studio
}

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    title: '验收到手',
    backgroundColor: '#f4efe6',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  if (process.env.ELECTRON_RENDERER_URL) {
    win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

app.whenReady().then(async () => {
  await getStudio()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

ipcMain.handle('studio:dataDir', async () => (await getStudio()).dirs.dataDir)

ipcMain.handle('studio:listProjects', async () => (await getStudio()).listProjects())

ipcMain.handle('studio:getProject', async (_e, id: string) => (await getStudio()).getProject(id))

ipcMain.handle('studio:createProject', async (_e, input: ProjectInput) =>
  (await getStudio()).createProject(input)
)

ipcMain.handle('studio:updateProject', async (_e, id: string, patch: Partial<ProjectInput>) =>
  (await getStudio()).updateProject(id, patch)
)

ipcMain.handle('studio:listLogs', async (_e, projectId: string) => (await getStudio()).listLogs(projectId))

ipcMain.handle('studio:saveLog', async (_e, input: DailyLogInput & { id?: string }) =>
  (await getStudio()).saveLog(input)
)

ipcMain.handle('studio:deleteLog', async (_e, id: string) => {
  ;(await getStudio()).deleteLog(id)
})

ipcMain.handle('studio:getCatalogState', async (_e, projectId: string) =>
  (await getStudio()).getCatalogState(projectId)
)

ipcMain.handle(
  'studio:setItemStatus',
  async (_e, projectId: string, itemCode: string, status: ItemStatus, notes?: string) =>
    (await getStudio()).setItemStatus(projectId, itemCode, status, notes)
)

ipcMain.handle(
  'studio:updateItemPayload',
  async (_e, projectId: string, itemCode: string, payload: Record<string, unknown>) =>
    (await getStudio()).updateItemPayload(projectId, itemCode, payload)
)

ipcMain.handle('studio:uploadFiles', async (e, projectId: string, itemCode: string) => {
  const win = BrowserWindow.fromWebContents(e.sender)
  const result = await dialog.showOpenDialog(win ?? undefined!, {
    title: '选择要归档的资料文件',
    properties: ['openFile', 'multiSelections']
  })
  if (result.canceled) return []
  const s = await getStudio()
  return result.filePaths.map((p) => s.addUpload(projectId, itemCode, p))
})

ipcMain.handle(
  'studio:generateDocument',
  async (_e, projectId: string, itemCode: string, extra?: { weekly?: WeeklyReportOptions }) => {
    const s = await getStudio()
    const result = s.generateDocument(projectId, itemCode, extra)
    await openGeneratedDocument(result.path)
    return { ...result, opened: true }
  }
)

ipcMain.handle(
  'studio:generateWeeklyReport',
  async (_e, projectId: string, options?: Partial<WeeklyReportOptions>) => {
    const s = await getStudio()
    const result = s.generateWeeklyReport(projectId, options)
    await openGeneratedDocument(result.path)
    return { ...result, opened: true }
  }
)

ipcMain.handle(
  'studio:generateMonthlyReport',
  async (_e, projectId: string, options?: Partial<WeeklyReportOptions>) => {
    const s = await getStudio()
    const result = s.generateMonthlyReport(projectId, options)
    await openGeneratedDocument(result.path)
    return { ...result, opened: true }
  }
)

ipcMain.handle('studio:checkExport', async (_e, projectId: string) => (await getStudio()).checkExport(projectId))

ipcMain.handle('studio:confirmReady', async (_e, projectId: string) =>
  (await getStudio()).confirmItemsWithArtifacts(projectId)
)

ipcMain.handle('studio:exportZip', async (e, projectId: string) => {
  const s = await getStudio()
  const project = s.getProject(projectId)
  const win = BrowserWindow.fromWebContents(e.sender)
  const suggested = `${project.name}_验收资料包.zip`
  const pick = await dialog.showSaveDialog(win ?? undefined!, {
    title: '导出验收资料包',
    defaultPath: suggested,
    filters: [{ name: 'Zip', extensions: ['zip'] }]
  })
  if (pick.canceled || !pick.filePath) return null
  const result = s.exportZip(projectId, pick.filePath)
  shell.showItemInFolder(result.path)
  return result
})

ipcMain.handle('studio:openPath', async (_e, filePath: string) => {
  await openGeneratedDocument(filePath)
})

ipcMain.handle('studio:revealInFolder', async (_e, filePath: string) => {
  shell.showItemInFolder(filePath)
})
