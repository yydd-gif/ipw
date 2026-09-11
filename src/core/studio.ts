import fs from 'node:fs'
import path from 'node:path'
import { randomUUID } from 'node:crypto'
import {
  CATALOG_VOLUMES,
  getCatalogItem,
  itemApplies,
  itemsForProjectType,
  volumeApplies
} from '../shared/catalog'
import { buildExportCheck, exportBlockedMessage } from '../shared/completeness'
import { packAcceptanceZip } from './exporter'
import { filterLogsByPeriod } from './logs'
import type {
  CatalogInstance,
  CatalogItemState,
  CatalogVolumeState,
  DailyLog,
  DailyLogInput,
  EditorDocumentState,
  ExportCheck,
  FilePreview,
  GenerateResult,
  ItemStatus,
  PrintStatus,
  Project,
  ProjectInput,
  TableDocument,
  UploadRecord,
  WeeklyReportOptions
} from '../shared/types'
import { editStatusFrom } from '../shared/types'
import { SqliteStore } from './db'
import {
  ensureDir,
  generatedDir,
  projectDir,
  sanitizeFilePart,
  todayISO,
  uploadsDir,
  type StudioDirs
} from './paths'
import { parseDocxBuffer, tableDocumentToDocx } from './docx-table'
import { computeContentFingerprint, editorDocumentFromPayload } from './fingerprint'
import { buildItemPrintHtml } from './print-html'
import { buildTemplateData, createStubDocx, fillDocx, writeFilledDocx } from './template-engine'

interface InstanceRow {
  id: string
  project_id: string
  item_code: string
  status: string
  payload: string
  generated_path: string | null
  notes: string
  updated_at: string
  print_status?: string
  content_fingerprint?: string
  last_printed_at?: string | null
  last_printed_fingerprint?: string
}

interface UploadRow {
  id: string
  project_id: string
  item_code: string
  original_name: string
  stored_path: string
  created_at: string
}

function nowISO(): string {
  return new Date().toISOString()
}

function parseInstance(row: InstanceRow): CatalogInstance {
  let payload: Record<string, unknown> = {}
  try {
    payload = JSON.parse(row.payload || '{}') as Record<string, unknown>
  } catch {
    payload = {}
  }
  const status = row.status as ItemStatus
  return {
    id: row.id,
    project_id: row.project_id,
    item_code: row.item_code,
    status,
    editStatus: editStatusFrom(status),
    printStatus: (row.print_status === 'printed' ? 'printed' : 'unprinted') as PrintStatus,
    contentFingerprint: row.content_fingerprint || '',
    lastPrintedAt: row.last_printed_at || null,
    lastPrintedFingerprint: row.last_printed_fingerprint || '',
    payload,
    generated_path: row.generated_path,
    notes: row.notes || '',
    updated_at: row.updated_at
  }
}

export class Studio {
  readonly dirs: StudioDirs
  private store!: SqliteStore

  constructor(dirs: StudioDirs) {
    this.dirs = dirs
  }

  async init(): Promise<void> {
    ensureDir(this.dirs.dataDir)
    ensureDir(this.dirs.templatesDir)
    this.store = new SqliteStore(path.join(this.dirs.dataDir, 'studio.sqlite'))
    await this.store.init()
  }

  listProjects(): Project[] {
    return this.store.all<Project>('SELECT * FROM projects ORDER BY updated_at DESC')
  }

  getProject(id: string): Project {
    const project = this.store.get<Project>('SELECT * FROM projects WHERE id = ?', [id])
    if (!project) throw new Error(`项目不存在：${id}`)
    return project
  }

  createProject(input: ProjectInput): Project {
    const id = randomUUID()
    const ts = nowISO()
    const project: Project = {
      id,
      name: input.name.trim(),
      type: input.type || 'hybrid',
      owner: input.owner?.trim() || '',
      supervisor: input.supervisor?.trim() || '',
      contractor: input.contractor?.trim() || '',
      contract_no: input.contract_no?.trim() || '',
      phase: input.phase?.trim() || '',
      doc_no: input.doc_no?.trim() || '',
      created_at: ts,
      updated_at: ts
    }
    if (!project.name) throw new Error('项目名称不能为空')
    this.store.exec(
      `INSERT INTO projects (id, name, type, owner, supervisor, contractor, contract_no, phase, doc_no, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        project.id,
        project.name,
        project.type,
        project.owner,
        project.supervisor,
        project.contractor,
        project.contract_no,
        project.phase,
        project.doc_no,
        project.created_at,
        project.updated_at
      ]
    )
    ensureDir(projectDir(this.dirs.dataDir, id))
    ensureDir(generatedDir(this.dirs.dataDir, id))
    this.syncCatalogInstances(project)
    return project
  }

  updateProject(id: string, patch: Partial<ProjectInput>): Project {
    const current = this.getProject(id)
    const next: Project = {
      ...current,
      ...patch,
      id,
      name: (patch.name ?? current.name).trim(),
      updated_at: nowISO()
    }
    this.store.exec(
      `UPDATE projects SET name=?, type=?, owner=?, supervisor=?, contractor=?, contract_no=?, phase=?, doc_no=?, updated_at=? WHERE id=?`,
      [
        next.name,
        next.type,
        next.owner,
        next.supervisor,
        next.contractor,
        next.contract_no,
        next.phase,
        next.doc_no,
        next.updated_at,
        id
      ]
    )
    this.syncCatalogInstances(next)
    return this.getProject(id)
  }

  private syncCatalogInstances(project: Project): void {
    const items = itemsForProjectType(project.type)
    const ts = nowISO()
    for (const item of items) {
      const existing = this.store.get<{ id: string }>(
        'SELECT id FROM catalog_instances WHERE project_id=? AND item_code=?',
        [project.id, item.code]
      )
      if (!existing) {
        this.store.exec(
          `INSERT INTO catalog_instances (id, project_id, item_code, status, payload, generated_path, notes, updated_at, print_status, content_fingerprint, last_printed_at, last_printed_fingerprint)
           VALUES (?, ?, ?, 'empty', '{}', NULL, '', ?, 'unprinted', '', NULL, '')`,
          [randomUUID(), project.id, item.code, ts]
        )
      }
    }
  }

  listLogs(projectId: string): DailyLog[] {
    this.getProject(projectId)
    return this.store.all<DailyLog>(
      'SELECT * FROM daily_logs WHERE project_id=? ORDER BY date ASC, created_at ASC',
      [projectId]
    )
  }

  saveLog(input: DailyLogInput & { id?: string }): DailyLog {
    this.getProject(input.project_id)
    const ts = nowISO()
    if (input.id) {
      this.store.exec(
        `UPDATE daily_logs SET date=?, weather=?, location=?, work_done=?, qs_check=?, crew_count=?, issues=?, coordination=?
         WHERE id=? AND project_id=?`,
        [
          input.date,
          input.weather || '',
          input.location || '',
          input.work_done || '',
          input.qs_check || '',
          Number(input.crew_count) || 0,
          input.issues || '',
          input.coordination || '',
          input.id,
          input.project_id
        ]
      )
      const row = this.store.get<DailyLog>('SELECT * FROM daily_logs WHERE id=?', [input.id])
      if (!row) throw new Error('日志不存在')
      this.touchProject(input.project_id)
      return row
    }
    const log: DailyLog = {
      id: randomUUID(),
      project_id: input.project_id,
      date: input.date,
      weather: input.weather || '',
      location: input.location || '',
      work_done: input.work_done || '',
      qs_check: input.qs_check || '',
      crew_count: Number(input.crew_count) || 0,
      issues: input.issues || '',
      coordination: input.coordination || '',
      created_at: ts
    }
    this.store.exec(
      `INSERT INTO daily_logs (id, project_id, date, weather, location, work_done, qs_check, crew_count, issues, coordination, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        log.id,
        log.project_id,
        log.date,
        log.weather,
        log.location,
        log.work_done,
        log.qs_check,
        log.crew_count,
        log.issues,
        log.coordination,
        log.created_at
      ]
    )
    this.touchProject(input.project_id)
    return log
  }

  deleteLog(id: string): void {
    this.store.exec('DELETE FROM daily_logs WHERE id=?', [id])
  }

  getCatalogState(projectId: string): CatalogVolumeState[] {
    const project = this.getProject(projectId)
    const instances = this.store
      .all<InstanceRow>('SELECT * FROM catalog_instances WHERE project_id=?', [projectId])
      .map(parseInstance)
    const uploads = this.store.all<UploadRow>('SELECT * FROM uploads WHERE project_id=?', [projectId])
    const instanceByCode = new Map(instances.map((i) => [i.item_code, i]))
    const uploadsByCode = new Map<string, UploadRecord[]>()
    for (const u of uploads) {
      const list = uploadsByCode.get(u.item_code) ?? []
      list.push(u)
      uploadsByCode.set(u.item_code, list)
    }

    return CATALOG_VOLUMES.filter((v) => volumeApplies(v, project.type)).map((volume) => {
      const items: CatalogItemState[] = itemsForProjectType(project.type)
        .filter((item) => item.volumeId === volume.id)
        .map((item) => {
          const instance =
            instanceByCode.get(item.code) ??
            ({
              id: '',
              project_id: projectId,
              item_code: item.code,
              status: 'empty',
              editStatus: 'empty',
              printStatus: 'unprinted',
              contentFingerprint: '',
              lastPrintedAt: null,
              lastPrintedFingerprint: '',
              payload: {},
              generated_path: null,
              notes: '',
              updated_at: ''
            } satisfies CatalogInstance)
          const itemUploads = uploadsByCode.get(item.code) ?? []
          const complete =
            instance.status === 'confirmed' ||
            instance.status === 'waived' ||
            (!item.required && instance.status !== 'empty')
          return { item, instance, uploads: itemUploads, complete }
        })
      return { volume, items }
    })
  }

  setItemStatus(projectId: string, itemCode: string, status: ItemStatus, notes?: string): CatalogInstance {
    this.ensureInstance(projectId, itemCode)
    const ts = nowISO()
    this.store.exec(
      `UPDATE catalog_instances SET status=?, notes=COALESCE(?, notes), updated_at=? WHERE project_id=? AND item_code=?`,
      [status, notes ?? null, ts, projectId, itemCode]
    )
    this.touchProject(projectId)
    return this.getInstance(projectId, itemCode)
  }

  updateItemPayload(projectId: string, itemCode: string, payload: Record<string, unknown>): CatalogInstance {
    this.ensureInstance(projectId, itemCode)
    const current = this.getInstance(projectId, itemCode)
    const merged = { ...current.payload, ...payload }
    const uploads = this.uploadsFor(projectId, itemCode)
    const fingerprint = computeContentFingerprint({
      document: editorDocumentFromPayload(merged),
      uploads
    })
    const printReset = fingerprint !== current.lastPrintedFingerprint
    this.store.exec(
      `UPDATE catalog_instances SET payload=?, status=CASE WHEN status='empty' THEN 'draft' ELSE status END,
       content_fingerprint=?, print_status=CASE WHEN ? = 1 THEN 'unprinted' ELSE print_status END, updated_at=?
       WHERE project_id=? AND item_code=?`,
      [JSON.stringify(merged), fingerprint, printReset ? 1 : 0, nowISO(), projectId, itemCode]
    )
    return this.getInstance(projectId, itemCode)
  }

  addUpload(
    projectId: string,
    itemCode: string,
    sourcePath: string,
    originalName?: string
  ): UploadRecord {
    const item = getCatalogItem(itemCode)
    if (!item) throw new Error(`未知目录条目：${itemCode}`)
    if (!itemApplies(item, this.getProject(projectId).type)) {
      throw new Error(`条目 ${itemCode} 不适用于当前项目类型`)
    }
    const destDir = ensureDir(uploadsDir(this.dirs.dataDir, projectId, item))
    const name = originalName || path.basename(sourcePath)
    const dest = uniquePath(path.join(destDir, sanitizeFilePart(name)))
    fs.copyFileSync(sourcePath, dest)
    const rec: UploadRecord = {
      id: randomUUID(),
      project_id: projectId,
      item_code: itemCode,
      original_name: name,
      stored_path: dest,
      created_at: nowISO()
    }
    this.store.exec(
      `INSERT INTO uploads (id, project_id, item_code, original_name, stored_path, created_at) VALUES (?, ?, ?, ?, ?, ?)`,
      [rec.id, rec.project_id, rec.item_code, rec.original_name, rec.stored_path, rec.created_at]
    )
    this.refreshFingerprint(projectId, itemCode, { bumpDraft: true })
    this.touchProject(projectId)
    return rec
  }

  addUploadBuffer(
    projectId: string,
    itemCode: string,
    buffer: Buffer,
    originalName: string
  ): UploadRecord {
    const tmp = path.join(this.dirs.dataDir, '.tmp', `${randomUUID()}-${originalName}`)
    ensureDir(path.dirname(tmp))
    fs.writeFileSync(tmp, buffer)
    try {
      return this.addUpload(projectId, itemCode, tmp, originalName)
    } finally {
      fs.rmSync(tmp, { force: true })
    }
  }

  generateDocument(
    projectId: string,
    itemCode: string,
    extra?: { weekly?: WeeklyReportOptions }
  ): GenerateResult {
    const project = this.getProject(projectId)
    const item = getCatalogItem(itemCode)
    if (!item) throw new Error(`未知目录条目：${itemCode}`)
    this.ensureInstance(projectId, itemCode)
    const instance = this.getInstance(projectId, itemCode)
    const outDir = ensureDir(generatedDir(this.dirs.dataDir, projectId))
    const outPath = path.join(outDir, `${sanitizeFilePart(item.code + '_' + item.title)}.docx`)
    let weekly = extra?.weekly

    if (item.stubNote) {
      const buf = createStubDocx(`${item.code} ${item.title}`, item.stubNote)
      fs.writeFileSync(outPath, buf)
    } else {
      const savedDoc = editorDocumentFromPayload(instance.payload)
      const templatePath = item.templateFile
        ? path.join(this.dirs.templatesDir, item.templateFile)
        : ''
      const hasTemplate = Boolean(templatePath && fs.existsSync(templatePath))
      if (savedDoc && (savedDoc.tables.length > 0 || savedDoc.paragraphs.length > 0)) {
        fs.writeFileSync(outPath, tableDocumentToDocx(savedDoc))
      } else if (!hasTemplate) {
        const buf = createStubDocx(
          `${item.code} ${item.title}`,
          item.produceType === 'template'
            ? '待补模版。试用版可上传原件或等待模板补齐。'
            : '本条目尚无关联 Word 模板。'
        )
        fs.writeFileSync(outPath, buf)
      } else {
        const logs = this.listLogs(projectId)
        if ((itemCode === '2.12' || itemCode === '2.11') && !weekly) {
          weekly = {
            period_start: logs[0]?.date || todayISO(),
            period_end: todayISO()
          }
        }
        const filtered = filterLogsByPeriod(logs, weekly?.period_start, weekly?.period_end)
        const fillOpts = { code: item.code, templatesDir: this.dirs.templatesDir }
        if (itemCode === '2.10') {
          const prefix = sanitizeFilePart(`${item.code}_${item.title}`)
          clearGeneratedPrefix(outDir, prefix)
          const targets = filtered.length > 0 ? filtered : [null]
          const paths: string[] = []
          for (const log of targets) {
            const data = buildTemplateData(item, project, instance.payload, {
              logs: log ? [log] : [],
              weekly
            })
            const suffix = log ? `_${sanitizeFilePart(log.date)}` : ''
            const outFile = uniquePath(path.join(outDir, `${prefix}${suffix}.docx`))
            writeFilledDocx(templatePath, outFile, data, fillOpts)
            paths.push(outFile)
          }
          const primary = paths[paths.length - 1]!
          this.store.exec(
            `UPDATE catalog_instances SET generated_path=?, status=CASE WHEN status='confirmed' THEN 'confirmed' ELSE 'draft' END,
             payload=?, updated_at=? WHERE project_id=? AND item_code=?`,
            [primary, JSON.stringify({ ...instance.payload, generated_paths: paths }), nowISO(), projectId, itemCode]
          )
          this.touchProject(projectId)
          return { path: primary, itemCode, paths }
        }
        const data = buildTemplateData(item, project, instance.payload, {
          logs: filtered,
          weekly
        })
        writeFilledDocx(templatePath, outPath, data, fillOpts)
      }
    }

    this.store.exec(
      `UPDATE catalog_instances SET generated_path=?, status=CASE WHEN status='confirmed' THEN 'confirmed' ELSE 'draft' END,
       payload=?, updated_at=? WHERE project_id=? AND item_code=?`,
      [
        outPath,
        JSON.stringify({
          ...instance.payload,
          ...(weekly ?? extra?.weekly ?? {})
        }),
        nowISO(),
        projectId,
        itemCode
      ]
    )
    this.touchProject(projectId)
    return { path: outPath, itemCode }
  }

  generateWeeklyReport(projectId: string, options?: Partial<WeeklyReportOptions>): GenerateResult {
    const logs = this.listLogs(projectId)
    const end = options?.period_end || todayISO()
    const start =
      options?.period_start ||
      (logs.length ? logs[Math.max(0, logs.length - 7)]!.date : addDays(end, -6))
    return this.generateDocument(projectId, '2.12', {
      weekly: {
        period_start: start,
        period_end: end,
        undone: options?.undone,
        issues: options?.issues,
        plan: options?.plan
      }
    })
  }

  generateMonthlyReport(projectId: string, options?: Partial<WeeklyReportOptions>): GenerateResult {
    const end = options?.period_end || todayISO()
    const start = options?.period_start || `${end.slice(0, 7)}-01`
    return this.generateDocument(projectId, '2.11', {
      weekly: {
        period_start: start,
        period_end: end,
        undone: options?.undone,
        issues: options?.issues,
        plan: options?.plan
      }
    })
  }

  confirmItemsWithArtifacts(projectId: string): number {
    const state = this.getCatalogState(projectId)
    let n = 0
    for (const vol of state) {
      for (const item of vol.items) {
        const hasFile = Boolean(item.instance.generated_path) || item.uploads.length > 0
        if (hasFile && item.instance.status !== 'confirmed' && item.instance.status !== 'waived') {
          this.setItemStatus(projectId, item.item.code, 'confirmed')
          n += 1
        }
      }
    }
    return n
  }

  checkExport(projectId: string): ExportCheck {
    const project = this.getProject(projectId)
    const flat = this.getCatalogState(projectId).flatMap((v) => v.items)
    return buildExportCheck(project.type, flat)
  }

  exportZip(projectId: string, destPath?: string): { path: string; check: ExportCheck } {
    const project = this.getProject(projectId)
    const check = this.checkExport(projectId)
    if (!check.ok) {
      throw new Error(exportBlockedMessage(check))
    }

    const out = packAcceptanceZip({
      project,
      check,
      state: this.getCatalogState(projectId),
      dataDir: this.dirs.dataDir,
      destPath
    })
    this.touchProject(projectId)
    return { path: out, check }
  }

  getEditorDocument(projectId: string, itemCode: string): EditorDocumentState {
    const project = this.getProject(projectId)
    const item = getCatalogItem(itemCode)
    if (!item || !itemApplies(item, project.type)) {
      throw new Error(`条目 ${itemCode} 不适用于当前项目`)
    }
    this.ensureInstance(projectId, itemCode)
    const instance = this.getInstance(projectId, itemCode)
    const uploads = this.uploadsFor(projectId, itemCode)
    const saved = editorDocumentFromPayload(instance.payload)
    const templatePath = item.templateFile
      ? path.join(this.dirs.templatesDir, item.templateFile)
      : ''
    const hasTemplate = Boolean(templatePath && fs.existsSync(templatePath))

    if (saved) {
      return {
        pane: 'doc',
        templateMissing: !hasTemplate,
        document: saved,
        item,
        instance,
        uploads,
        message: hasTemplate ? undefined : '已保存草稿。关联模板尚未入库。'
      }
    }

    if (hasTemplate) {
      const logs = this.listLogs(projectId)
      const data = buildTemplateData(item, project, instance.payload, { logs })
      const buf = fillDocx(templatePath, data, { code: item.code, templatesDir: this.dirs.templatesDir })
      return {
        pane: 'doc',
        templateMissing: false,
        document: parseDocxBuffer(buf),
        item,
        instance,
        uploads
      }
    }

    if (item.produceType === 'template' || item.produceType === 'derived') {
      return {
        pane: 'upload',
        templateMissing: true,
        document: null,
        item,
        instance,
        uploads,
        message: '待补模版。本条目可先上传原件，或等待 Word 模板入库后再在表格中编辑。'
      }
    }

    return {
      pane: 'upload',
      templateMissing: false,
      document: null,
      item,
      instance,
      uploads,
      message: item.stubNote
    }
  }

  saveEditorDocument(
    projectId: string,
    itemCode: string,
    document: TableDocument,
    as: 'draft' | 'ready' = 'draft'
  ): CatalogInstance {
    this.ensureInstance(projectId, itemCode)
    const current = this.getInstance(projectId, itemCode)
    const merged = { ...current.payload, editorDocument: document }
    const uploads = this.uploadsFor(projectId, itemCode)
    const fingerprint = computeContentFingerprint({ document, uploads })
    const printReset = fingerprint !== current.lastPrintedFingerprint
    const status: ItemStatus =
      as === 'ready' ? 'confirmed' : current.status === 'confirmed' ? 'confirmed' : 'draft'
    const outDir = ensureDir(generatedDir(this.dirs.dataDir, projectId))
    const item = getCatalogItem(itemCode)!
    const titled = document.title ? document : { ...document, title: `${item.code} ${item.title}` }
    const outPath = path.join(outDir, `${sanitizeFilePart(item.code + '_' + item.title)}.docx`)
    fs.writeFileSync(outPath, tableDocumentToDocx(titled))
    this.store.exec(
      `UPDATE catalog_instances SET payload=?, status=?, content_fingerprint=?,
       print_status=CASE WHEN ? = 1 THEN 'unprinted' ELSE print_status END,
       generated_path=?, updated_at=? WHERE project_id=? AND item_code=?`,
      [JSON.stringify(merged), status, fingerprint, printReset ? 1 : 0, outPath, nowISO(), projectId, itemCode]
    )
    this.touchProject(projectId)
    return this.getInstance(projectId, itemCode)
  }

  markItemPrinted(projectId: string, itemCode: string, fingerprint?: string): CatalogInstance {
    this.ensureInstance(projectId, itemCode)
    const current = this.getInstance(projectId, itemCode)
    const fp = fingerprint || current.contentFingerprint
    this.store.exec(
      `UPDATE catalog_instances SET print_status='printed', last_printed_at=?, last_printed_fingerprint=?, updated_at=?
       WHERE project_id=? AND item_code=?`,
      [nowISO(), fp, nowISO(), projectId, itemCode]
    )
    this.touchProject(projectId)
    return this.getInstance(projectId, itemCode)
  }

  itemPrintHtml(projectId: string, itemCode: string, document?: TableDocument | null): string {
    const project = this.getProject(projectId)
    const editor = this.getEditorDocument(projectId, itemCode)
    return buildItemPrintHtml({
      project,
      item: editor.item,
      document: document ?? editor.document,
      uploads: editor.uploads
    })
  }

  writeItemPrintHtml(projectId: string, itemCode: string, document?: TableDocument | null): string {
    const html = this.itemPrintHtml(projectId, itemCode, document)
    const item = getCatalogItem(itemCode)!
    const outDir = ensureDir(generatedDir(this.dirs.dataDir, projectId))
    const htmlPath = path.join(outDir, `${sanitizeFilePart(item.code + '_' + item.title)}.html`)
    fs.writeFileSync(htmlPath, html, 'utf8')
    return htmlPath
  }

  writeItemPdfBytes(projectId: string, itemCode: string, pdfBytes: Buffer): string {
    const item = getCatalogItem(itemCode)!
    const outDir = ensureDir(generatedDir(this.dirs.dataDir, projectId))
    const pdfPath = path.join(outDir, `${sanitizeFilePart(item.code + '_' + item.title)}.pdf`)
    fs.writeFileSync(pdfPath, pdfBytes)
    return pdfPath
  }

  previewUpload(storedPath: string): FilePreview {
    const name = path.basename(storedPath)
    if (!fs.existsSync(storedPath)) {
      return { kind: 'other', name }
    }
    const dataDir = path.resolve(this.dirs.dataDir)
    const resolved = path.resolve(storedPath)
    if (!resolved.startsWith(dataDir)) {
      throw new Error('预览路径不在数据目录内')
    }
    const ext = path.extname(storedPath).toLowerCase()
    const buf = fs.readFileSync(storedPath)
    if (['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'].includes(ext)) {
      const mime =
        ext === '.png' ? 'image/png' : ext === '.gif' ? 'image/gif' : ext === '.webp' ? 'image/webp' : 'image/jpeg'
      return { kind: 'image', name, dataUrl: `data:${mime};base64,${buf.toString('base64')}` }
    }
    if (ext === '.pdf') {
      return { kind: 'pdf', name, dataUrl: `data:application/pdf;base64,${buf.toString('base64')}` }
    }
    if (['.txt', '.md', '.csv', '.json', '.xml', '.log'].includes(ext) && buf.length < 200_000) {
      return { kind: 'text', name, text: buf.toString('utf8') }
    }
    return { kind: 'other', name }
  }

  private uploadsFor(projectId: string, itemCode: string): UploadRecord[] {
    return this.store.all<UploadRow>(
      'SELECT * FROM uploads WHERE project_id=? AND item_code=? ORDER BY created_at ASC',
      [projectId, itemCode]
    )
  }

  private refreshFingerprint(projectId: string, itemCode: string, opts?: { bumpDraft?: boolean }): void {
    const current = this.getInstance(projectId, itemCode)
    const uploads = this.uploadsFor(projectId, itemCode)
    const fingerprint = computeContentFingerprint({
      document: editorDocumentFromPayload(current.payload),
      uploads
    })
    const printReset = fingerprint !== current.lastPrintedFingerprint
    this.store.exec(
      `UPDATE catalog_instances SET content_fingerprint=?,
       print_status=CASE WHEN ? = 1 THEN 'unprinted' ELSE print_status END,
       status=CASE WHEN ? = 1 AND status='empty' THEN 'draft' ELSE status END,
       updated_at=? WHERE project_id=? AND item_code=?`,
      [fingerprint, printReset ? 1 : 0, opts?.bumpDraft ? 1 : 0, nowISO(), projectId, itemCode]
    )
  }

  private ensureInstance(projectId: string, itemCode: string): void {
    const project = this.getProject(projectId)
    const item = getCatalogItem(itemCode)
    if (!item || !itemApplies(item, project.type)) {
      throw new Error(`条目 ${itemCode} 不适用于当前项目`)
    }
    const existing = this.store.get<{ id: string }>(
      'SELECT id FROM catalog_instances WHERE project_id=? AND item_code=?',
      [projectId, itemCode]
    )
    if (!existing) {
      this.store.exec(
        `INSERT INTO catalog_instances (id, project_id, item_code, status, payload, generated_path, notes, updated_at, print_status, content_fingerprint, last_printed_at, last_printed_fingerprint)
         VALUES (?, ?, ?, 'empty', '{}', NULL, '', ?, 'unprinted', '', NULL, '')`,
        [randomUUID(), projectId, itemCode, nowISO()]
      )
    }
  }

  private getInstance(projectId: string, itemCode: string): CatalogInstance {
    const row = this.store.get<InstanceRow>(
      'SELECT * FROM catalog_instances WHERE project_id=? AND item_code=?',
      [projectId, itemCode]
    )
    if (!row) throw new Error(`目录实例不存在：${itemCode}`)
    return parseInstance(row)
  }

  private touchProject(id: string): void {
    this.store.exec('UPDATE projects SET updated_at=? WHERE id=?', [nowISO(), id])
  }
}

function uniquePath(filePath: string): string {
  if (!fs.existsSync(filePath)) return filePath
  const ext = path.extname(filePath)
  const base = filePath.slice(0, -ext.length)
  let i = 1
  while (fs.existsSync(`${base}_${i}${ext}`)) i += 1
  return `${base}_${i}${ext}`
}

function clearGeneratedPrefix(dir: string, prefix: string): void {
  if (!fs.existsSync(dir)) return
  for (const name of fs.readdirSync(dir)) {
    if (name.startsWith(prefix) && name.endsWith('.docx')) {
      fs.unlinkSync(path.join(dir, name))
    }
  }
}

function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}
