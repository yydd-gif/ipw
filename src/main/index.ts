import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron'
import { join } from 'node:path'
import { existsSync, writeFileSync } from 'node:fs'
import { Studio } from '../core/studio'
import { withExportSavePath } from '../shared/completeness'
import type { DailyLogInput, ItemStatus, ProjectInput, TableDocument, WeeklyReportOptions } from '../shared/types'

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
    width: 1440,
    height: 900,
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
  const check = s.checkExport(projectId)
  const win = BrowserWindow.fromWebContents(e.sender)
  const result = await withExportSavePath(
    check,
    async () => {
      const pick = await dialog.showSaveDialog(win ?? undefined!, {
        title: '导出验收资料包',
        defaultPath: `${project.name}_验收资料包.zip`,
        filters: [{ name: 'Zip', extensions: ['zip'] }]
      })
      if (pick.canceled || !pick.filePath) return null
      return pick.filePath
    },
    (dest) => s.exportZip(projectId, dest)
  )
  if (result) shell.showItemInFolder(result.path)
  return result
})

ipcMain.handle('studio:openPath', async (_e, filePath: string) => {
  await openGeneratedDocument(filePath)
})

ipcMain.handle('studio:revealInFolder', async (_e, filePath: string) => {
  shell.showItemInFolder(filePath)
})

ipcMain.handle('studio:getEditorDocument', async (_e, projectId: string, itemCode: string) =>
  (await getStudio()).getEditorDocument(projectId, itemCode)
)

ipcMain.handle(
  'studio:saveEditorDocument',
  async (_e, projectId: string, itemCode: string, document: TableDocument, as?: 'draft' | 'ready') =>
    (await getStudio()).saveEditorDocument(projectId, itemCode, document, as)
)

ipcMain.handle(
  'studio:markItemPrinted',
  async (_e, projectId: string, itemCode: string, fingerprint?: string) =>
    (await getStudio()).markItemPrinted(projectId, itemCode, fingerprint)
)

ipcMain.handle('studio:previewUpload', async (_e, storedPath: string) =>
  (await getStudio()).previewUpload(storedPath)
)

ipcMain.handle(
  'studio:exportItemPdf',
  async (e, projectId: string, itemCode: string, document?: TableDocument | null) => {
    const s = await getStudio()
    if (document) s.saveEditorDocument(projectId, itemCode, document, 'draft')
    const htmlPath = s.writeItemPrintHtml(projectId, itemCode, document)
    const project = s.getProject(projectId)
    const item = (await s.getEditorDocument(projectId, itemCode)).item
    const win = BrowserWindow.fromWebContents(e.sender)
    const pick = await dialog.showSaveDialog(win ?? undefined!, {
      title: '导出当前条目 PDF',
      defaultPath: `${item.code}_${item.title}_${project.name}.pdf`,
      filters: [{ name: 'PDF', extensions: ['pdf'] }]
    })
    if (pick.canceled || !pick.filePath) return null
    try {
      const pdf = await htmlToPdf(htmlPath)
      s.writeItemPdfBytes(projectId, itemCode, pdf)
      writeFileSync(pick.filePath, pdf)
      return { path: pick.filePath, htmlPath }
    } catch (err) {
      const htmlDest = pick.filePath.replace(/\.pdf$/i, '') + '.html'
      const html = (await getStudio()).itemPrintHtml(projectId, itemCode, document)
      writeFileSync(htmlDest, html, 'utf8')
      console.warn('printToPDF failed, wrote HTML instead:', err)
      return { path: htmlDest, htmlPath }
    }
  }
)

ipcMain.handle(
  'studio:printPreview',
  async (_e, projectId: string, itemCode: string, document?: TableDocument | null) => {
    const s = await getStudio()
    if (document) s.saveEditorDocument(projectId, itemCode, document, 'draft')
    const htmlPath = s.writeItemPrintHtml(projectId, itemCode, document)
    const preview = new BrowserWindow({
      width: 900,
      height: 1100,
      title: '打印预览',
      backgroundColor: '#ffffff',
      webPreferences: { sandbox: false }
    })
    previewWindows.add(preview)
    preview.on('closed', () => previewWindows.delete(preview))
    await preview.loadFile(htmlPath)
    preview.show()
  }
)

ipcMain.handle(
  'studio:printItem',
  async (e, projectId: string, itemCode: string, document?: TableDocument | null) => {
    const s = await getStudio()
    if (document) s.saveEditorDocument(projectId, itemCode, document, 'draft')
    const instance = s.getEditorDocument(projectId, itemCode).instance
    const htmlPath = s.writeItemPrintHtml(projectId, itemCode, document)
    const owner = BrowserWindow.fromWebContents(e.sender)
    const printWin = new BrowserWindow({
      width: 800,
      height: 1000,
      show: false,
      parent: owner ?? undefined,
      webPreferences: { sandbox: false }
    })
    previewWindows.add(printWin)
    await printWin.loadFile(htmlPath)
    const printed = await new Promise<boolean>((resolve) => {
      printWin.webContents.print({ printBackground: true }, (success) => {
        resolve(Boolean(success))
      })
    })
    previewWindows.delete(printWin)
    if (!printWin.isDestroyed()) printWin.close()
    if (printed) {
      s.markItemPrinted(projectId, itemCode, instance.contentFingerprint)
      return { printed: true }
    }
    return { printed: false, reason: 'cancelled' }
  }
)

const previewWindows = new Set<BrowserWindow>()

async function htmlToPdf(htmlPath: string): Promise<Buffer> {
  const hidden = new BrowserWindow({
    show: false,
    width: 794,
    height: 1123,
    webPreferences: { sandbox: false }
  })
  try {
    await hidden.loadFile(htmlPath)
    const data = await hidden.webContents.printToPDF({
      printBackground: true,
      pageSize: 'A4',
      margins: { marginType: 'default' }
    })
    return Buffer.from(data)
  } finally {
    if (!hidden.isDestroyed()) hidden.close()
  }
}
