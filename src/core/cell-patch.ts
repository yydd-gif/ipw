import fs from 'node:fs'
import PizZip from 'pizzip'
import type {
  CellFillMode,
  CellScalarSpec,
  ParagraphSpec,
  TableFillSpec,
  TemplateManifestEntry
} from './template-manifest'
import {
  escapeXml,
  extractDirectChildren,
  extractElements,
  firstChild,
  getText,
  type XmlElement
} from './xml-parts'
const ELLIPSIS = '……'
const TOTAL_LABEL = '总计'

function fieldValue(data: Record<string, unknown>, field: string): unknown {
  if (field in data) return data[field]
  return undefined
}

function stringifyValue(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return String(value)
}

function applyMode(
  original: string,
  value: string,
  mode: CellFillMode | undefined,
  spec: { token?: string; label?: string }
): string {
  const m = mode || 'replace'
  if (m === 'checkbox') {
    return value === 'true' || value === '☑' || value === '是' ? '☑' : '☐'
  }
  if (m === 'replace') return value
  if (m === 'replaceToken') {
    const token = spec.token || '×××'
    if (original.includes(token)) return original.split(token).join(value)
    return original
  }
  const label = spec.label || ''
  if (!label) return value
  if (m === 'appendAfterLabel') {
    const idx = original.indexOf(label)
    if (idx < 0) return original.includes(value) ? original : original + value
    const at = idx + label.length
    return original.slice(0, at) + value + original.slice(at)
  }
  // afterLabel: keep label, replace the span until the next CJK/ascii label or EOL
  let idx = original.indexOf(label)
  if (idx < 0) {
    const stripped = label.replace(/[：:]\s*$/, '')
    idx = stripped ? original.indexOf(stripped) : -1
    if (idx < 0) return original
    const usedLabel = original.slice(idx).match(new RegExp(escapeRegExp(stripped) + '[：:]?'))?.[0] ?? stripped
    return spliceAfterLabel(original, idx, usedLabel, value)
  }
  return spliceAfterLabel(original, idx, label, value)
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function spliceAfterLabel(original: string, idx: number, label: string, value: string): string {
  const afterStart = idx + label.length
  const rest = original.slice(afterStart)
  const next = rest.search(/[^\s][\u4e00-\u9fffA-Za-z0-9]{0,24}[：:]/)
  if (next >= 0) return original.slice(0, afterStart) + value + rest.slice(next)
  return original.slice(0, afterStart) + value
}

function asElement(full: string, name: string): XmlElement {
  const el = extractElements(full, name)[0]
  if (!el) throw new Error(`CellPatch: expected <${name}>`)
  return el
}

function writeRuns(containerFull: string, containerName: 'w:tc' | 'w:p', text: string): string {
  const el = asElement(containerFull, containerName)
  const lines = text.split(/\r?\n/)
  if (containerName === 'w:p') {
    const pPr = firstChild(el, 'w:pPr')?.full ?? ''
    const firstR = firstChild(el, 'w:r')
    const rPr = firstR ? (firstChild(firstR, 'w:rPr')?.full ?? '') : ''
    return `${containerFull.slice(el.start, el.openEnd)}${pPr}${runXml(lines[0] ?? '', rPr)}</w:p>`
  }
  const tcPr = firstChild(el, 'w:tcPr')?.full ?? ''
  const firstP = firstChild(el, 'w:p')
  const pPr = firstP ? (firstChild(firstP, 'w:pPr')?.full ?? '') : ''
  const firstR = firstP ? firstChild(firstP, 'w:r') : undefined
  const rPr = firstR ? (firstChild(firstR, 'w:rPr')?.full ?? '') : ''
  const paragraphs = (lines.length ? lines : ['']).map((line) => `<w:p>${pPr}${runXml(line, rPr)}</w:p>`).join('')
  return `${containerFull.slice(el.start, el.openEnd)}${tcPr}${paragraphs}</w:tc>`
}

function runXml(text: string, rPr: string): string {
  const space = text.startsWith(' ') || text.endsWith(' ') || text === '' ? ' xml:space="preserve"' : ''
  return `<w:r>${rPr}<w:t${space}>${escapeXml(text)}</w:t></w:r>`
}

function replaceSlice(xml: string, start: number, end: number, next: string): string {
  return xml.slice(0, start) + next + xml.slice(end)
}

function getTables(xml: string): XmlElement[] {
  return extractElements(xml, 'w:tbl')
}

function getRows(tableFull: string): XmlElement[] {
  return extractDirectChildren(asElement(tableFull, 'w:tbl'), 'w:tr')
}

function getCells(rowFull: string): XmlElement[] {
  return extractDirectChildren(asElement(rowFull, 'w:tr'), 'w:tc')
}

function getBodyParagraphs(xml: string): XmlElement[] {
  const body = extractElements(xml, 'w:body')[0]
  if (!body) return []
  return extractDirectChildren(body, 'w:p')
}

function applyGroupedCellScalars(tableFull: string, specs: CellScalarSpec[], data: Record<string, unknown>): string {
  const groups = new Map<string, CellScalarSpec[]>()
  for (const spec of specs) {
    const key = `${spec.row}:${spec.col}`
    const list = groups.get(key) ?? []
    list.push(spec)
    groups.set(key, list)
  }
  let xml = tableFull
  for (const group of groups.values()) {
    const { row, col } = group[0]!
    const rows = getRows(xml)
    const rowEl = rows[row]
    if (!rowEl) continue
    const cells = getCells(rowEl.full)
    const cell = cells[col]
    if (!cell) continue
    let text = getText(cell.full)
    let wrote = false
    for (const spec of group) {
      const raw = fieldValue(data, spec.field)
      if (raw === undefined) continue
      text = applyMode(text, stringifyValue(raw), spec.mode, spec)
      wrote = true
    }
    if (!wrote) continue
    const newCell = writeRuns(cell.full, 'w:tc', text)
    const newRow = replaceSlice(rowEl.full, cell.start, cell.end, newCell)
    xml = replaceSlice(xml, rowEl.start, rowEl.end, newRow)
  }
  return xml
}

function resolveTemplateRowIndex(rows: XmlElement[], requested: number): number {
  const row = rows[requested]
  if (!row) return requested
  const text = getText(row.full)
  if (text.includes(TOTAL_LABEL) && !text.includes(ELLIPSIS)) {
    const found = rows.findIndex((r, i) => i > requested && getText(r.full).includes(ELLIPSIS))
    return found >= 0 ? found : -1
  }
  return requested
}

function fillTemplateRow(rowFull: string, columns: TableFillSpec['columns'], item: Record<string, unknown>): string {
  const cols = [...(columns ?? [])].sort((a, b) => b.col - a.col)
  let xml = rowFull
  for (const col of cols) {
    const cells = getCells(xml)
    const cell = cells[col.col]
    if (!cell) continue
    const raw = fieldValue(item, col.field)
    const newCell = writeRuns(cell.full, 'w:tc', stringifyValue(raw ?? ''))
    xml = replaceSlice(xml, cell.start, cell.end, newCell)
  }
  return xml
}

function cloneDataRows(tableFull: string, spec: TableFillSpec, data: Record<string, unknown>): string {
  if (spec.rowTemplateRow == null || !spec.id) return tableFull
  const rowsPayload = data[spec.id]
  const items = Array.isArray(rowsPayload) ? (rowsPayload as Record<string, unknown>[]) : []
  if (items.length === 0) return tableFull

  const tbl = asElement(tableFull, 'w:tbl')
  const rows = extractDirectChildren(tbl, 'w:tr')
  const idx = resolveTemplateRowIndex(rows, spec.rowTemplateRow)
  if (idx < 0 || !rows[idx]) {
    console.warn(`CellPatch: skip clone for ${spec.id}, refusing 总计 row and no ${ELLIPSIS} row`)
    return tableFull
  }
  const template = rows[idx]!.full
  const filled = items.map((item) => fillTemplateRow(template, spec.columns, item))
  const newRows = [...rows.slice(0, idx).map((r) => r.full), ...filled, ...rows.slice(idx + 1).map((r) => r.full)]
  const first = rows[0]!
  const last = rows[rows.length - 1]!
  return replaceSlice(tableFull, first.start, last.end, newRows.join(''))
}

function applyParagraphs(xml: string, specs: ParagraphSpec[], data: Record<string, unknown>): string {
  if (!specs.length) return xml
  const sorted = [...specs].sort((a, b) => b.paraIndex - a.paraIndex)
  let out = xml
  for (const spec of sorted) {
    const raw = fieldValue(data, spec.field)
    if (raw === undefined) continue
    const value = stringifyValue(raw)
    const paras = getBodyParagraphs(out)
    let target: XmlElement | undefined = paras[spec.paraIndex]
    if (spec.mode === 'replaceToken' || spec.fallbackScan) {
      const token = spec.token || '×××'
      const hasToken = target ? getText(target.full).includes(token) : false
      if (!hasToken && spec.fallbackScan) {
        target = paras.find((p) => getText(p.full).includes(token))
      }
    }
    if (!target) continue
    const original = getText(target.full)
    const next = applyMode(original, value, spec.mode || 'replaceToken', spec)
    if (next === original) continue
    const newP = writeRuns(target.full, 'w:p', next)
    out = replaceSlice(out, target.start, target.end, newP)
  }
  return out
}

function applyEntryToDocumentXml(xml: string, entry: TemplateManifestEntry, data: Record<string, unknown>): string {
  let out = applyParagraphs(xml, entry.paragraphs ?? [], data)
  const tables = getTables(out)
  const tableSpecs = entry.tables ?? []
  const topScalars = entry.scalars ?? []

  const indices = new Set<number>()
  for (const t of tableSpecs) indices.add(t.tableIndex)
  for (const s of topScalars) indices.add(s.table)

  const sortedIdx = [...indices].sort((a, b) => b - a)
  for (const tableIndex of sortedIdx) {
    const currentTables = getTables(out)
    const tableEl = currentTables[tableIndex]
    if (!tableEl) continue
    let tableXml = tableEl.full
    const localSpecs = tableSpecs.filter((t) => t.tableIndex === tableIndex)
    const scalars: CellScalarSpec[] = [
      ...topScalars.filter((s) => s.table === tableIndex),
      ...localSpecs.flatMap((t) =>
        (t.scalars ?? []).map((s) => ({ ...s, table: tableIndex }))
      )
    ]
    if (scalars.length) tableXml = applyGroupedCellScalars(tableXml, scalars, data)
    for (const spec of localSpecs) {
      tableXml = cloneDataRows(tableXml, spec, data)
    }
    out = replaceSlice(out, tableEl.start, tableEl.end, tableXml)
  }
  return out
}

export function fillDocxCellPatch(
  templatePath: string,
  data: Record<string, unknown>,
  entry: TemplateManifestEntry
): Buffer {
  if (!fs.existsSync(templatePath)) {
    throw new Error(`找不到模板文件：${templatePath}`)
  }
  const zip = new PizZip(fs.readFileSync(templatePath))
  const docFile = zip.file('word/document.xml')
  if (!docFile) throw new Error(`模板缺少 word/document.xml：${templatePath}`)
  const nextDoc = applyEntryToDocumentXml(docFile.asText(), entry, data)
  zip.file('word/document.xml', nextDoc)

  if (entry.patchHeaders) {
    for (const name of Object.keys(zip.files)) {
      if (!/^word\/header\d*\.xml$/.test(name)) continue
      const part = zip.file(name)
      if (!part) continue
      zip.file(name, applyEntryToDocumentXml(part.asText(), entry, data))
    }
  }

  return zip.generate({ type: 'nodebuffer', compression: 'DEFLATE' }) as Buffer
}
