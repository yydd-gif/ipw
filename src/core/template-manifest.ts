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
  columns?: TableColumnSpec[]
  scalars?: Omit<CellScalarSpec, 'table'>[]
}

export interface TemplateManifestEntry {
  file: string
  fillMode: 'cell' | 'placeholder'
  scalars?: CellScalarSpec[]
  tables?: TableFillSpec[]
  paragraphs?: ParagraphSpec[]
  /** Also patch word/header*.xml (7.1 cover/header risk). */
  patchHeaders?: boolean
  layoutRisk?: string
}

export interface TemplatesManifest {
  version?: number
  templates: Record<string, TemplateManifestEntry>
}

let cached: { dir: string; mtimeMs: number; manifest: TemplatesManifest } | null = null

export function loadTemplatesManifest(templatesDir: string): TemplatesManifest {
  const file = path.join(templatesDir, 'manifest.json')
  if (!fs.existsSync(file)) {
    return { version: 1, templates: {} }
  }
  const st = fs.statSync(file)
  if (cached && cached.dir === templatesDir && cached.mtimeMs === st.mtimeMs) {
    return cached.manifest
  }
  const raw = JSON.parse(fs.readFileSync(file, 'utf8')) as TemplatesManifest
  if (!raw || typeof raw !== 'object' || !raw.templates) {
    throw new Error('templates/manifest.json 缺少 templates 字段')
  }
  cached = { dir: templatesDir, mtimeMs: st.mtimeMs, manifest: raw }
  return raw
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
