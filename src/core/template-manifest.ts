import fs from 'node:fs'
import path from 'node:path'

export type CellFillMode =
  | 'replace'
  | 'replaceToken'
  | 'afterLabel'
  | 'appendAfterLabel'
  | 'checkbox'

export interface CellScalarSpec {
  table: number
  row: number
  col: number
  field: string
  mode?: CellFillMode
  token?: string
  label?: string
}

export interface ParagraphSpec {
  paraIndex: number
  field: string
  mode?: CellFillMode
  token?: string
  label?: string
  /** If the targeted paragraph has no token, scan all body paragraphs. */
  fallbackScan?: boolean
}

export interface TableColumnSpec {
  col: number
  field: string
}

export interface TableFillSpec {
  id?: string
  tableIndex: number
  headerRow?: number
  rowTemplateRow?: number
  /** Insert cloned rows after this index instead of replacing the …… row. */
  dataInsertAfterRow?: number
  /** If a row contains this text, insert data rows immediately under it (flat if not found). */
  categoryAnchor?: string
  columns?: TableColumnSpec[]
  scalars?: Omit<CellScalarSpec, 'table'>[]
}

export interface TemplateManifestEntry {
  code?: string
  file: string
  fillMode: 'cell' | 'placeholder'
  scalars?: CellScalarSpec[]
  tables?: TableFillSpec[]
  paragraphs?: ParagraphSpec[]
  /** Also patch word/header*.xml (7.1 cover/header risk). */
  patchHeaders?: boolean
  layoutRisk?: string
  notes?: string
}

export interface TemplatesManifest {
  version?: number
  fillDefault?: 'cell' | 'placeholder'
  templates: Record<string, TemplateManifestEntry>
}

interface RawScalar {
  key?: string
  field?: string
  table: number
  row: number
  col: number
  mode?: CellFillMode
  token?: string
  label?: string
}

interface RawParagraph {
  key?: string
  field?: string
  paraIndex: number
  mode?: CellFillMode
  token?: string
  label?: string
  replacePattern?: string
  fallbackScan?: boolean
}

interface RawTable {
  id?: string
  tableIndex: number
  headerRow?: number
  rowTemplateRow?: number
  dataInsertAfterRow?: number
  categoryAnchor?: string
  columns?: Array<string | TableColumnSpec>
  scalars?: RawScalar[]
}

interface RawEntry {
  code?: string
  file: string
  fillMode?: 'cell' | 'placeholder'
  scalars?: RawScalar[]
  tables?: RawTable[]
  paragraphs?: RawParagraph[]
  patchHeaders?: boolean
  layoutRisk?: string
  notes?: string
}

interface RawManifest {
  version?: number
  fillDefault?: 'cell' | 'placeholder'
  templates?: RawEntry[] | Record<string, RawEntry>
}

let cached: { dir: string; mtimeMs: number; manifest: TemplatesManifest } | null = null

function normalizeColumns(columns?: Array<string | TableColumnSpec>): TableColumnSpec[] {
  if (!columns?.length) return []
  return columns.map((col, i) =>
    typeof col === 'string' ? { col: i, field: col } : { col: col.col, field: col.field }
  )
}

function normalizeScalar(s: RawScalar, fallbackTable?: number): CellScalarSpec {
  return {
    table: s.table ?? fallbackTable ?? 0,
    row: s.row,
    col: s.col,
    field: s.key || s.field || '',
    mode: s.mode,
    token: s.token,
    label: s.label
  }
}

function normalizeParagraph(p: RawParagraph): ParagraphSpec {
  const token = p.replacePattern || p.token
  return {
    paraIndex: p.paraIndex,
    field: p.key || p.field || '',
    mode: p.mode || (token ? 'replaceToken' : 'replace'),
    token,
    label: p.label,
    fallbackScan: p.fallbackScan ?? Boolean(token)
  }
}

function normalizeEntry(raw: RawEntry, fillDefault: 'cell' | 'placeholder'): TemplateManifestEntry {
  return {
    code: raw.code,
    file: raw.file,
    fillMode: raw.fillMode || fillDefault,
    scalars: (raw.scalars ?? []).map((s) => normalizeScalar(s)),
    tables: (raw.tables ?? []).map((t) => ({
      id: t.id,
      tableIndex: t.tableIndex,
      headerRow: t.headerRow,
      rowTemplateRow: t.rowTemplateRow,
      dataInsertAfterRow: t.dataInsertAfterRow,
      categoryAnchor: t.categoryAnchor,
      columns: normalizeColumns(t.columns),
      scalars: (t.scalars ?? []).map((s) => normalizeScalar(s, t.tableIndex))
    })),
    paragraphs: (raw.paragraphs ?? []).map(normalizeParagraph),
    patchHeaders: raw.patchHeaders ?? raw.code === '7.1',
    layoutRisk: raw.layoutRisk || raw.notes,
    notes: raw.notes
  }
}

export function loadTemplatesManifest(templatesDir: string): TemplatesManifest {
  const file = path.join(templatesDir, 'manifest.json')
  if (!fs.existsSync(file)) {
    return { version: 1, fillDefault: 'cell', templates: {} }
  }
  const st = fs.statSync(file)
  if (cached && cached.dir === templatesDir && cached.mtimeMs === st.mtimeMs) {
    return cached.manifest
  }
  const raw = JSON.parse(fs.readFileSync(file, 'utf8')) as RawManifest
  if (!raw || typeof raw !== 'object' || !raw.templates) {
    throw new Error('templates/manifest.json 缺少 templates 字段')
  }
  const fillDefault = raw.fillDefault || 'cell'
  const templates: Record<string, TemplateManifestEntry> = {}
  if (Array.isArray(raw.templates)) {
    for (const entry of raw.templates) {
      if (!entry.code) throw new Error('templates/manifest.json 条目缺少 code')
      templates[entry.code] = normalizeEntry(entry, fillDefault)
    }
  } else {
    for (const [code, entry] of Object.entries(raw.templates)) {
      templates[code] = normalizeEntry({ ...entry, code: entry.code || code }, fillDefault)
    }
  }
  const manifest: TemplatesManifest = { version: raw.version ?? 1, fillDefault, templates }
  cached = { dir: templatesDir, mtimeMs: st.mtimeMs, manifest }
  return manifest
}

export function manifestEntryFor(
  manifest: TemplatesManifest,
  opts: { code?: string; fileName?: string }
): TemplateManifestEntry | undefined {
  if (opts.code && manifest.templates[opts.code]) return manifest.templates[opts.code]
  if (opts.fileName) {
    return Object.values(manifest.templates).find((e) => e.file === opts.fileName)
  }
  return undefined
}
