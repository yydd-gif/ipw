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
import { buildExportCheck } from '../shared/completeness'
import { packAcceptanceZip } from './exporter'
import { filterLogsByPeriod } from './logs'
import type {
  CatalogInstance,
  CatalogItemState,
  CatalogVolumeState,
  DailyLog,
  DailyLogInput,
  ExportCheck,
  GenerateResult,
  ItemStatus,
  Project,
  ProjectInput,
  UploadRecord,
  WeeklyReportOptions
} from '../shared/types'
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
import { buildTemplateData, createStubDocx, writeFilledDocx } from './template-engine'

interface InstanceRow {
  id: string
  project_id: string
  item_code: string
  status: string
  payload: string
  generated_path: string | null
  notes: string
  updated_at: string
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
  return {
    id: row.id,
    project_id: row.project_id,
    item_code: row.item_code,
    status: row.status as ItemStatus,
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
          `INSERT INTO catalog_instances (id, project_id, item_code, status, payload, generated_path, notes, updated_at)
           VALUES (?, ?, ?, 'empty', '{}', NULL, '', ?)`,
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
    this.store.exec(
      `UPDATE catalog_instances SET payload=?, status=CASE WHEN status='empty' THEN 'draft' ELSE status END, updated_at=?
       WHERE project_id=? AND item_code=?`,
      [JSON.stringify(merged), nowISO(), projectId, itemCode]
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
    this.store.exec(
      `UPDATE catalog_instances SET status=CASE WHEN status='empty' THEN 'draft' ELSE status END, updated_at=?
       WHERE project_id=? AND item_code=?`,
      [nowISO(), projectId, itemCode]
    )
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
      if (!item.templateFile) {
        throw new Error(`条目 ${itemCode} 没有关联 Word 模板`)
      }
      const templatePath = path.join(this.dirs.templatesDir, item.templateFile)
      const logs = this.listLogs(projectId)
      if ((itemCode === '2.12' || itemCode === '2.11') && !weekly) {
        weekly = {
          period_start: logs[0]?.date || todayISO(),
          period_end: todayISO()
        }
      }
      const filtered = filterLogsByPeriod(logs, weekly?.period_start, weekly?.period_end)
      const data = buildTemplateData(item, project, instance.payload, {
        logs: filtered,
        weekly
      })
      writeFilledDocx(templatePath, outPath, data)
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
      const detail = check.blockers.map((b) => `${b.code} ${b.title}（${b.reason}）`).join('；')
      throw new Error(`无法导出：仍有必填条目未完成。${detail}`)
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
        `INSERT INTO catalog_instances (id, project_id, item_code, status, payload, generated_path, notes, updated_at)
         VALUES (?, ?, ?, 'empty', '{}', NULL, '', ?)`,
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

function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00`)
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}
