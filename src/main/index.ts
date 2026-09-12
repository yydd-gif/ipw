import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { Studio } from '../core/studio'
import type { ProjectInput } from '../shared/types'

if (process.platform === 'linux') {
  app.disableHardwareAcceleration()
  app.commandLine.appendSwitch('no-sandbox')
  app.commandLine.appendSwitch('disable-gpu')
}

function resolveTemplatesDir(): string {
  const packaged = join(process.resourcesPath || '', 'templates')
  const dev = join(app.getAppPath(), 'templates')
  const cwd = join(process.cwd(), 'templates')
  if (app.isPackaged && existsSync(packaged)) return packaged
  if (existsSync(dev)) return dev
  return cwd
}

function resolveEnginePath(): string {
  const packaged = join(process.resourcesPath || '', 'engine', 'fill_engine.py')
  const dev = join(app.getAppPath(), 'engine', 'fill_engine.py')
  const cwd = join(process.cwd(), 'engine', 'fill_engine.py')
  if (app.isPackaged && existsSync(packaged)) return packaged
  if (existsSync(dev)) return dev
  return cwd
}

function resolveDataDir(): string {
  if (process.env.ACCEPTANCE_STUDIO_HOME) return process.env.ACCEPTANCE_STUDIO_HOME
  return join(app.getPath('userData'), 'acceptance-studio')
}

let studio: Studio

function getStudio(): Studio {
  if (!studio) {
    studio = new Studio({
      dataDir: resolveDataDir(),
      templatesDir: resolveTemplatesDir(),
      enginePath: resolveEnginePath()
    })
  }
  return studio
}

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1480,
    height: 920,
    minWidth: 1024,
    minHeight: 700,
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
  return win
}

app.whenReady().then(() => {
  getStudio()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

ipcMain.handle('studio:dataDir', () => getStudio().dirs.dataDir)
ipcMain.handle('studio:listProjects', () => getStudio().listProjects())
ipcMain.handle('studio:getProject', (_e, id: string) => getStudio().getProject(id))
ipcMain.handle('studio:createProject', (_e, input: ProjectInput) => getStudio().createProject(input))
ipcMain.handle('studio:updateProject', (_e, id: string, patch: Partial<ProjectInput>) =>
  getStudio().updateProject(id, patch)
)
ipcMain.handle('studio:engineStatus', () => getStudio().engineStatus())
ipcMain.handle('studio:getCatalogState', (_e, projectId: string) => getStudio().getCatalogState(projectId))
ipcMain.handle('studio:getItemEditor', (_e, projectId: string, itemCode: string) =>
  getStudio().getItemEditor(projectId, itemCode)
)
ipcMain.handle(
  'studio:saveItemFields',
  (_e, projectId: string, itemCode: string, fields: Record<string, string>, as?: 'draft' | 'complete') =>
    getStudio().saveItemFields(projectId, itemCode, fields, as)
)
ipcMain.handle('studio:fillItem', (_e, projectId: string, itemCode: string) =>
  getStudio().fillItem(projectId, itemCode)
)
ipcMain.handle('studio:fillVolume', (_e, projectId: string) => getStudio().fillVolume(projectId))
ipcMain.handle('studio:checkExport', (_e, projectId: string, itemCode: string) =>
  getStudio().checkExport(projectId, itemCode)
)
ipcMain.handle('studio:printWarn', (_e, projectId: string, itemCode: string) =>
  getStudio().printWarn(projectId, itemCode)
)
ipcMain.handle('studio:previewFile', (_e, storedPath: string) => getStudio().previewUpload(storedPath))
ipcMain.handle('studio:revealInFolder', async (_e, filePath: string) => {
  shell.showItemInFolder(filePath)
})

ipcMain.handle('studio:openProjectFile', async (e) => {
  const win = BrowserWindow.fromWebContents(e.sender)
  const result = await dialog.showOpenDialog(win ?? undefined!, {
    title: '打开项目（project.json）',
    properties: ['openFile'],
    filters: [{ name: '项目', extensions: ['json'] }]
  })
  if (result.canceled || !result.filePaths[0]) return null
  return getStudio().openProjectFromPath(result.filePaths[0])
})

ipcMain.handle('studio:uploadFiles', async (e, projectId: string, itemCode: string) => {
  const win = BrowserWindow.fromWebContents(e.sender)
  const result = await dialog.showOpenDialog(win ?? undefined!, {
    title: '选择要归档的资料文件',
    properties: ['openFile', 'multiSelections']
  })
  if (result.canceled) return getStudio().getItemEditor(projectId, itemCode).record
  let last = getStudio().getItemEditor(projectId, itemCode).record
  for (const p of result.filePaths) {
    last = getStudio().addUpload(projectId, itemCode, p)
  }
  return last
})

ipcMain.handle('studio:exportItem', async (e, projectId: string, itemCode: string) => {
  const check = getStudio().checkExport(projectId, itemCode)
  if (!check.ok) {
    throw new Error(check.blockers.map((b) => b.reason).join('；'))
  }
  const win = BrowserWindow.fromWebContents(e.sender)
  const result = await dialog.showSaveDialog(win ?? undefined!, {
    title: '导出当前条目',
    defaultPath: `${itemCode}.pdf`,
    filters: [
      { name: 'PDF', extensions: ['pdf'] },
      { name: 'Word', extensions: ['docx'] }
    ]
  })
  if (result.canceled || !result.filePath) return null
  return getStudio().exportItemFile(projectId, itemCode, result.filePath)
})

async function openPrintWindow(htmlPath: string, print: boolean): Promise<boolean> {
  return await new Promise((resolve) => {
    const win = new BrowserWindow({
      width: 900,
      height: 1100,
      show: !print,
      title: print ? '打印' : '打印预览',
      webPreferences: { sandbox: true }
    })
    void win.loadFile(htmlPath)
    win.webContents.on('did-finish-load', () => {
      if (!print) {
        resolve(true)
        return
      }
      win.webContents.print({ silent: false, printBackground: true }, (success) => {
        win.close()
        resolve(Boolean(success))
      })
    })
    win.on('closed', () => resolve(false))
  })
}

ipcMain.handle('studio:printPreview', async (_e, projectId: string, itemCode: string) => {
  const htmlPath = getStudio().writePrintHtml(projectId, itemCode)
  await openPrintWindow(htmlPath, false)
})

ipcMain.handle('studio:printItem', async (_e, projectId: string, itemCode: string) => {
  const htmlPath = getStudio().writePrintHtml(projectId, itemCode)
  const printed = await openPrintWindow(htmlPath, true)
  if (!printed) return { printed: false, reason: '打印未完成或已取消' }
  getStudio().markPrinted(projectId, itemCode)
  return { printed: true }
})
