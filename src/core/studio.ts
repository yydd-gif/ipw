import { execFileSync } from 'node:child_process'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync
} from 'node:fs'
import { basename, extname, join } from 'node:path'
import { randomUUID } from 'node:crypto'
import { probeEngine, runFillEngine, scanMustaches } from './fill-bridge'
import { contentFingerprint } from './fingerprint'
import { buildSimplePdf } from './simple-pdf'
import { getCatalogItem, itemsForProjectType, volumesForProjectType } from '../shared/catalog'
import { fieldsForItem, inputToProjectFields } from '../shared/fields'
import type {
  CatalogItem,
  CatalogVolumeState,
  ExportCheck,
  ExportResult,
  FilePreview,
  FillResult,
  FillVolumeResult,
  FillStatus,
  ItemEditorState,
  ItemRecord,
  PrintWarn,
  Project,
  ProjectInput,
  ProjectSummary,
  UploadRecord
} from '../shared/types'

interface PersistedProject {
  schemaVersion: 1
  id: string
  name: string
  type: Project['type']
  owner: string
  supervisor: string
  contractor: string
  contract_no: string
  phase: string
  doc_no: string
  location: string
  date: string
  fields: Record<string, string>
  items: Record<string, ItemRecord>
  createdAt: string
  updatedAt: string
  openedAt: string
}

interface IndexFile {
  recents: ProjectSummary[]
}

export interface StudioOptions {
  dataDir: string
  templatesDir: string
  pythonBin?: string
  enginePath?: string
}

function nowIso(): string {
  return new Date().toISOString()
}

function emptyRecord(): ItemRecord {
  return {
    editStatus: 'empty',
    printStatus: 'unprinted',
    overrides: {},
    contentFingerprint: '',
    lastPrintedFingerprint: '',
    lastPrintedAt: null,
    residualKeys: [],
    fillError: null,
    filledPath: null,
    previewPath: null,
    uploads: [],
    notes: '',
    updatedAt: nowIso()
  }
}

function ensureDir(dir: string): void {
  mkdirSync(dir, { recursive: true })
}

function hasText(value: string | undefined): boolean {
  return Boolean(value && value.trim())
}

export class Studio {
  readonly dirs: { dataDir: string; projectsDir: string; templatesDir: string }
  private readonly pythonBin?: string
  private readonly enginePath?: string

  constructor(opts: StudioOptions) {
    this.dirs = {
      dataDir: opts.dataDir,
      projectsDir: join(opts.dataDir, 'projects'),
      templatesDir: opts.templatesDir
    }
    this.pythonBin = opts.pythonBin
    this.enginePath = opts.enginePath
    ensureDir(this.dirs.projectsDir)
  }

  engineStatus() {
    return probeEngine({ pythonBin: this.pythonBin, enginePath: this.enginePath })
  }

  private indexPath(): string {
    return join(this.dirs.dataDir, 'index.json')
  }

  private projectDir(id: string): string {
    return join(this.dirs.projectsDir, id)
  }

  private projectFile(id: string): string {
    return join(this.projectDir(id), 'project.json')
  }

  private itemDir(id: string, itemCode: string): string {
    return join(this.projectDir(id), 'items', itemCode)
  }

  private readIndex(): IndexFile {
    if (!existsSync(this.indexPath())) return { recents: [] }
    try {
      return JSON.parse(readFileSync(this.indexPath(), 'utf8')) as IndexFile
    } catch {
      return { recents: [] }
    }
  }

  private writeIndex(index: IndexFile): void {
    writeFileSync(this.indexPath(), JSON.stringify(index, null, 2), 'utf8')
  }

  private touchRecent(project: Project): void {
    const index = this.readIndex()
    const summary: ProjectSummary = {
      id: project.id,
      name: project.name,
      type: project.type,
      contract_no: project.contract_no,
      openedAt: project.openedAt,
      updatedAt: project.updatedAt,
      rootDir: project.rootDir
    }
    index.recents = [summary, ...index.recents.filter((r) => r.id !== project.id)].slice(0, 20)
    this.writeIndex(index)
  }

  private readPersisted(id: string): PersistedProject {
    const file = this.projectFile(id)
    if (!existsSync(file)) throw new Error(`项目不存在：${id}`)
    return JSON.parse(readFileSync(file, 'utf8')) as PersistedProject
  }

  private writePersisted(doc: PersistedProject): Project {
    ensureDir(this.projectDir(doc.id))
    writeFileSync(this.projectFile(doc.id), JSON.stringify(doc, null, 2), 'utf8')
    const project = this.toProject(doc)
    this.touchRecent(project)
    return project
  }

  private toProject(doc: PersistedProject): Project {
    return {
      id: doc.id,
      name: doc.name,
      type: doc.type,
      owner: doc.owner,
      supervisor: doc.supervisor,
      contractor: doc.contractor,
      contract_no: doc.contract_no,
      phase: doc.phase,
      doc_no: doc.doc_no,
      location: doc.location,
      date: doc.date,
      fields: { ...doc.fields },
      createdAt: doc.createdAt,
      updatedAt: doc.updatedAt,
      openedAt: doc.openedAt,
      rootDir: this.projectDir(doc.id)
    }
  }

  listProjects(): ProjectSummary[] {
    const fromIndex = this.readIndex().recents
    if (fromIndex.length) return fromIndex
    if (!existsSync(this.dirs.projectsDir)) return []
    const found: ProjectSummary[] = []
    for (const name of readdirSync(this.dirs.projectsDir)) {
      const file = this.projectFile(name)
      if (!existsSync(file)) continue
      const project = this.toProject(this.readPersisted(name))
      found.push({
        id: project.id,
        name: project.name,
        type: project.type,
        contract_no: project.contract_no,
        openedAt: project.openedAt,
        updatedAt: project.updatedAt,
        rootDir: project.rootDir
      })
    }
    return found.sort((a, b) => b.openedAt.localeCompare(a.openedAt))
  }

  getProject(id: string): Project {
    const doc = this.readPersisted(id)
    doc.openedAt = nowIso()
    return this.writePersisted(doc)
  }

  createProject(input: ProjectInput): Project {
    if (!input.name.trim()) throw new Error('请填写项目名称')
    const ts = nowIso()
    const id = randomUUID()
    const fields = inputToProjectFields(input)
    const doc: PersistedProject = {
      schemaVersion: 1,
      id,
      name: input.name.trim(),
      type: input.type,
      owner: input.owner,
      supervisor: input.supervisor,
      contractor: input.contractor,
      contract_no: input.contract_no,
      phase: input.phase,
      doc_no: input.doc_no,
      location: input.location ?? '',
      date: input.date ?? '',
      fields,
      items: {},
      createdAt: ts,
      updatedAt: ts,
      openedAt: ts
    }
    return this.writePersisted(doc)
  }

  updateProject(id: string, patch: Partial<ProjectInput>): Project {
    const doc = this.readPersisted(id)
    const next: ProjectInput = {
      name: patch.name ?? doc.name,
      type: patch.type ?? doc.type,
      owner: patch.owner ?? doc.owner,
      supervisor: patch.supervisor ?? doc.supervisor,
      contractor: patch.contractor ?? doc.contractor,
      contract_no: patch.contract_no ?? doc.contract_no,
      phase: patch.phase ?? doc.phase,
      doc_no: patch.doc_no ?? doc.doc_no,
      location: patch.location ?? doc.location,
      date: patch.date ?? doc.date
    }
    doc.name = next.name.trim() || doc.name
    doc.type = next.type
    doc.owner = next.owner
    doc.supervisor = next.supervisor
    doc.contractor = next.contractor
    doc.contract_no = next.contract_no
    doc.phase = next.phase
    doc.doc_no = next.doc_no
    doc.location = next.location ?? ''
    doc.date = next.date ?? ''
    doc.fields = { ...doc.fields, ...inputToProjectFields(next) }
    doc.updatedAt = nowIso()
    this.recomputeAllItems(doc)
    return this.writePersisted(doc)
  }

  openProjectFromPath(filePath: string): Project {
    const jsonPath = filePath.endsWith('project.json') ? filePath : join(filePath, 'project.json')
    if (!existsSync(jsonPath)) throw new Error('未找到 project.json')
    const doc = JSON.parse(readFileSync(jsonPath, 'utf8')) as PersistedProject
    if (!doc.id || !doc.name) throw new Error('project.json 格式无效')
    const dest = this.projectFile(doc.id)
    if (jsonPath !== dest) {
      ensureDir(this.projectDir(doc.id))
      copyFileSync(jsonPath, dest)
    }
    return this.getProject(doc.id)
  }

  private getOrCreateRecord(doc: PersistedProject, code: string): ItemRecord {
    if (!doc.items[code]) doc.items[code] = emptyRecord()
    return doc.items[code]!
  }

  private mergedFields(doc: PersistedProject, item: CatalogItem, record: ItemRecord): Record<string, string> {
    return { ...doc.fields, ...record.overrides, project_name: doc.fields.project_name || doc.name }
  }

  private computeFillStatus(item: CatalogItem, record: ItemRecord, merged: Record<string, string>): FillStatus {
    if (record.fillError) return 'error'
    if (record.residualKeys.length) return 'error'
    if (item.produceType === 'upload' || !item.fields?.length) {
      if (record.uploads.length === 0) return 'empty'
      return 'complete'
    }
    const required = item.fields.filter((f) => f.required)
    const filledReq = required.filter((f) => hasText(merged[f.key]))
    const anyFilled = item.fields.some((f) => hasText(merged[f.key]))
    if (required.length && filledReq.length === required.length) return 'complete'
    if (anyFilled || record.uploads.length) return 'draft'
    return 'empty'
  }

  private recomputeItem(doc: PersistedProject, item: CatalogItem): ItemRecord {
    const record = this.getOrCreateRecord(doc, item.code)
    const merged = this.mergedFields(doc, item, record)
    const fp = contentFingerprint(merged, record.uploads)
    if (record.contentFingerprint && record.contentFingerprint !== fp) {
      record.printStatus = 'unprinted'
    }
    record.contentFingerprint = fp
    record.editStatus = this.computeFillStatus(item, record, merged)
    record.updatedAt = nowIso()
    return record
  }

  private recomputeAllItems(doc: PersistedProject): void {
    for (const item of itemsForProjectType(doc.type)) {
      this.recomputeItem(doc, item)
    }
  }

  getCatalogState(projectId: string): CatalogVolumeState[] {
    const doc = this.readPersisted(projectId)
    return volumesForProjectType(doc.type).map((volume) => ({
      volume,
      items: itemsForProjectType(doc.type)
        .filter((item) => item.volumeId === volume.id)
        .map((item) => {
          const record = this.recomputeItem(doc, item)
          return { item, record: { ...record } }
        })
    }))
  }

  private templatePath(item: CatalogItem): string | null {
    if (!item.templateFile) return null
    const p = join(this.dirs.templatesDir, item.templateFile)
    return existsSync(p) ? p : null
  }

  getItemEditor(projectId: string, itemCode: string): ItemEditorState {
    const doc = this.readPersisted(projectId)
    const item = getCatalogItem(itemCode)
    if (!item) throw new Error(`未知目录条目：${itemCode}`)
    const record = this.recomputeItem(doc, item)
    this.writePersisted(doc)
    const templateMissing = item.produceType === 'template' && !this.templatePath(item)
    const hasForm = Boolean(item.fields?.length) && Boolean(this.templatePath(item))
    const engine = this.engineStatus()
    return {
      pane: hasForm ? 'form' : 'upload',
      templateMissing,
      item,
      record: { ...record, uploads: [...record.uploads] },
      mergedFields: this.mergedFields(doc, item, record),
      projectFields: { ...doc.fields },
      engineMessage: engine.python && engine.engine ? undefined : engine.message
    }
  }

  saveItemFields(
    projectId: string,
    itemCode: string,
    fields: Record<string, string>,
    as?: 'draft' | 'complete'
  ): ItemRecord {
    const doc = this.readPersisted(projectId)
    const item = getCatalogItem(itemCode)
    if (!item) throw new Error(`未知目录条目：${itemCode}`)
    const record = this.getOrCreateRecord(doc, item.code)
    const schema = fieldsForItem(item.code)
    const projectPatch: Record<string, string> = {}
    const overrides: Record<string, string> = { ...record.overrides }
    for (const [key, raw] of Object.entries(fields)) {
      const value = raw ?? ''
      const def = schema.find((f) => f.key === key)
      if (def?.scope === 'project' || key in doc.fields) {
        projectPatch[key] = value
      } else {
        overrides[key] = value
      }
    }
    doc.fields = { ...doc.fields, ...projectPatch }
    if (projectPatch.project_name) doc.name = projectPatch.project_name
    if (projectPatch.owner !== undefined) doc.owner = projectPatch.owner
    if (projectPatch.supervisor !== undefined) doc.supervisor = projectPatch.supervisor
    if (projectPatch.contractor !== undefined) doc.contractor = projectPatch.contractor
    if (projectPatch.contract_no !== undefined) doc.contract_no = projectPatch.contract_no
    if (projectPatch.phase !== undefined) doc.phase = projectPatch.phase
    if (projectPatch.doc_no !== undefined) doc.doc_no = projectPatch.doc_no
    if (projectPatch.location !== undefined) doc.location = projectPatch.location
    if (projectPatch.date !== undefined) doc.date = projectPatch.date
    record.overrides = overrides
    record.fillError = null
    const merged = this.mergedFields(doc, item, record)
    if (as === 'complete') {
      const missing = (item.fields ?? []).filter((f) => f.required && !hasText(merged[f.key]))
      if (missing.length) {
        throw new Error(`标记已齐失败，缺少：${missing.map((f) => f.label).join('、')}`)
      }
    }
    this.recomputeAllItems(doc)
    if (as === 'complete' && record.editStatus !== 'error') {
      record.editStatus = 'complete'
    }
    if (as === 'draft' && record.editStatus === 'empty') {
      record.editStatus = 'draft'
    }
    doc.updatedAt = nowIso()
    this.writePersisted(doc)
    return { ...record }
  }

  addUpload(projectId: string, itemCode: string, srcPath: string, originalName?: string): ItemRecord {
    const doc = this.readPersisted(projectId)
    const item = getCatalogItem(itemCode)
    if (!item) throw new Error(`未知目录条目：${itemCode}`)
    const record = this.getOrCreateRecord(doc, item.code)
    const dir = join(this.itemDir(projectId, itemCode), 'uploads')
    ensureDir(dir)
    const name = originalName || basename(srcPath)
    const stored = join(dir, `${Date.now()}_${name}`)
    copyFileSync(srcPath, stored)
    const upload: UploadRecord = {
      id: randomUUID(),
      originalName: name,
      storedPath: stored,
      createdAt: nowIso()
    }
    record.uploads = [...record.uploads, upload]
    this.recomputeItem(doc, item)
    doc.updatedAt = nowIso()
    this.writePersisted(doc)
    return { ...record }
  }

  fillItem(projectId: string, itemCode: string): FillResult {
    const doc = this.readPersisted(projectId)
    const item = getCatalogItem(itemCode)
    if (!item) throw new Error(`未知目录条目：${itemCode}`)
    const record = this.getOrCreateRecord(doc, item.code)
    const template = this.templatePath(item)
    if (!template) {
      const result: FillResult = {
        ok: false,
        itemCode,
        residualKeys: [],
        message: item.produceType === 'upload' ? '上传类条目无需填充，请使用上传区。' : '该条目尚无演示模板（待官方 37 套模板导入）。'
      }
      record.fillError = result.message
      this.recomputeItem(doc, item)
      this.writePersisted(doc)
      return result
    }
    const merged = this.mergedFields(doc, item, record)
    for (const field of item.fields ?? []) {
      if (!(field.key in merged)) merged[field.key] = ''
    }
    const work = this.itemDir(projectId, itemCode)
    ensureDir(work)
    const dataPath = join(work, 'fill-data.json')
    const outPath = join(work, `${item.code}_filled.docx`)
    const previewPath = join(work, 'preview.html')
    writeFileSync(dataPath, JSON.stringify(merged, null, 2), 'utf8')
    const report = runFillEngine({
      pythonBin: this.pythonBin,
      enginePath: this.enginePath,
      template,
      dataPath,
      outPath,
      previewPath
    })
    if (!report.ok) {
      record.fillError = report.message
      record.residualKeys = report.residual_keys ?? []
      record.filledPath = null
      record.previewPath = null
      this.recomputeItem(doc, item)
      this.writePersisted(doc)
      const engine = this.engineStatus()
      return {
        ok: false,
        itemCode,
        residualKeys: record.residualKeys,
        message: report.message,
        engineMissing: !engine.python || !engine.engine
      }
    }
    record.fillError = null
    record.residualKeys = report.residual_keys ?? []
    record.filledPath = report.filled_path || outPath
    record.previewPath = report.preview_path || previewPath
    this.recomputeItem(doc, item)
    this.writePersisted(doc)
    return {
      ok: record.residualKeys.length === 0,
      itemCode,
      filledPath: record.filledPath ?? undefined,
      previewPath: record.previewPath ?? undefined,
      residualKeys: record.residualKeys,
      message:
        record.residualKeys.length === 0
          ? '填充完成'
          : `填充完成，但仍有未替换占位符：${record.residualKeys.map((k) => `{{${k}}}`).join('、')}`
    }
  }

  fillVolume(projectId: string): FillVolumeResult {
    const doc = this.readPersisted(projectId)
    const results: FillResult[] = []
    let filled = 0
    let skipped = 0
    let failed = 0
    for (const item of itemsForProjectType(doc.type)) {
      if (!this.templatePath(item)) {
        skipped += 1
        continue
      }
      const result = this.fillItem(projectId, item.code)
      results.push(result)
      if (result.ok) filled += 1
      else failed += 1
    }
    return {
      ok: failed === 0 && filled > 0,
      filled,
      skipped,
      failed,
      results,
      message: `成册完成：成功 ${filled}，失败 ${failed}，跳过无模板 ${skipped}`
    }
  }

  checkExport(projectId: string, itemCode: string): ExportCheck {
    const editor = this.getItemEditor(projectId, itemCode)
    const blockers: ExportCheck['blockers'] = []
    let residual = [...editor.record.residualKeys]
    const missingReq = (editor.item.fields ?? []).filter(
      (f) => f.required && !String(editor.mergedFields[f.key] ?? '').trim()
    )
    if (missingReq.length) {
      blockers.push({
        code: itemCode,
        title: editor.item.title,
        reason: `导出硬阻断：必填未填 ${missingReq.map((f) => f.label).join('、')}`
      })
    }
    if (editor.pane === 'form') {
      if (!editor.record.filledPath || !existsSync(editor.record.filledPath)) {
        const filled = this.fillItem(projectId, itemCode)
        residual = filled.residualKeys
        if (filled.engineMissing) {
          blockers.push({ code: itemCode, title: editor.item.title, reason: filled.message })
        }
      } else if (editor.record.filledPath) {
        residual = this.scanFilledFile(editor.record.filledPath)
      }
    } else if (editor.record.uploads.length === 0) {
      blockers.push({ code: itemCode, title: editor.item.title, reason: '尚未上传文件' })
    }
    if (residual.length) {
      blockers.push({
        code: itemCode,
        title: editor.item.title,
        reason: `导出硬阻断：残留占位符 ${residual.map((k) => `{{${k}}}`).join('、')}`
      })
    }
    return { ok: blockers.length === 0, blockers, residualKeys: residual }
  }

  private scanFilledFile(filePath: string): string[] {
    try {
      const buf = readFileSync(filePath)
      return scanMustaches(buf.toString('utf8'))
    } catch {
      return []
    }
  }

  exportItemFile(projectId: string, itemCode: string, destPath: string): ExportResult {
    const check = this.checkExport(projectId, itemCode)
    if (!check.ok) {
      throw new Error(check.blockers.map((b) => b.reason).join('；'))
    }
    const editor = this.getItemEditor(projectId, itemCode)
    const item = editor.item
    const source =
      editor.record.filledPath && existsSync(editor.record.filledPath)
        ? editor.record.filledPath
        : editor.record.uploads[0]?.storedPath
    if (!source) throw new Error('没有可导出的文件')

    if (destPath.toLowerCase().endsWith('.pdf')) {
      const converted = this.tryLibreOfficePdf(source, destPath)
      if (converted) return { path: destPath, format: 'pdf' }
      writeFileSync(
        destPath,
        buildSimplePdf({
          title: `${item.code} ${item.title}`,
          note: 'TODO: install LibreOffice/soffice for real DOCX→PDF. This is a valid PDF stub.'
        })
      )
      return {
        path: destPath,
        format: 'pdf',
        fallbackNote: '未检测到 LibreOffice/soffice，已写入占位 PDF。正式版请用 soffice 转 PDF。'
      }
    }
    copyFileSync(source, destPath)
    return { path: destPath, format: destPath.toLowerCase().endsWith('.pdf') ? 'pdf' : 'docx' }
  }

  private tryLibreOfficePdf(source: string, destPath: string): boolean {
    const bins = ['soffice', 'libreoffice']
    for (const bin of bins) {
      try {
        const outDir = destPath.replace(/[/\\][^/\\]+$/, '')
        execFileSync(bin, ['--headless', '--convert-to', 'pdf', '--outdir', outDir, source], {
          stdio: 'ignore'
        })
        const guessed = join(outDir, basename(source, extname(source)) + '.pdf')
        if (existsSync(guessed) && guessed !== destPath) copyFileSync(guessed, destPath)
        if (existsSync(destPath)) return true
      } catch {
        /* try next */
      }
    }
    return false
  }

  printWarn(projectId: string, itemCode: string): PrintWarn {
    const editor = this.getItemEditor(projectId, itemCode)
    const incomplete = editor.record.editStatus !== 'complete'
    return {
      incomplete,
      message: incomplete ? '当前条目尚未齐套。打印仅软提示，仍可继续。' : undefined
    }
  }

  writePrintHtml(projectId: string, itemCode: string): string {
    const editor = this.getItemEditor(projectId, itemCode)
    if (editor.pane === 'form' && (!editor.record.previewPath || !existsSync(editor.record.previewPath))) {
      this.fillItem(projectId, itemCode)
    }
    const again = this.getItemEditor(projectId, itemCode)
    if (again.record.previewPath && existsSync(again.record.previewPath)) {
      return again.record.previewPath
    }
    const work = this.itemDir(projectId, itemCode)
    ensureDir(work)
    const htmlPath = join(work, 'print.html')
    const uploads = again.record.uploads.map((u) => `<li>${escapeHtml(u.originalName)}</li>`).join('')
    writeFileSync(
      htmlPath,
      `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(itemCode)}</title></head><body><h1>${escapeHtml(again.item.code)} ${escapeHtml(again.item.title)}</h1><p>上传文件</p><ul>${uploads || '<li>无</li>'}</ul></body></html>`,
      'utf8'
    )
    return htmlPath
  }

  markPrinted(projectId: string, itemCode: string): ItemRecord {
    const doc = this.readPersisted(projectId)
    const item = getCatalogItem(itemCode)
    if (!item) throw new Error(`未知目录条目：${itemCode}`)
    const record = this.recomputeItem(doc, item)
    record.printStatus = 'printed'
    record.lastPrintedAt = nowIso()
    record.lastPrintedFingerprint = record.contentFingerprint
    doc.updatedAt = nowIso()
    this.writePersisted(doc)
    return { ...record }
  }

  previewUpload(storedPath: string): FilePreview {
    const name = basename(storedPath)
    const ext = extname(storedPath).toLowerCase()
    if (['.png', '.jpg', '.jpeg', '.gif', '.webp'].includes(ext)) {
      const buf = readFileSync(storedPath)
      const mime = ext === '.png' ? 'image/png' : ext === '.gif' ? 'image/gif' : ext === '.webp' ? 'image/webp' : 'image/jpeg'
      return { kind: 'image', name, dataUrl: `data:${mime};base64,${buf.toString('base64')}` }
    }
    if (ext === '.pdf') {
      const buf = readFileSync(storedPath)
      return { kind: 'pdf', name, dataUrl: `data:application/pdf;base64,${buf.toString('base64')}` }
    }
    if (['.txt', '.md', '.json', '.csv', '.log', '.html', '.htm'].includes(ext)) {
      return { kind: 'text', name, text: readFileSync(storedPath, 'utf8').slice(0, 200_000) }
    }
    return { kind: 'other', name }
  }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]!)
}
