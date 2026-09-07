import fs from 'node:fs'
import path from 'node:path'
import PizZip from 'pizzip'
import Docxtemplater from 'docxtemplater'
import type { CatalogItem, DailyLog, Project, WeeklyReportOptions } from '../shared/types'
import { fillDocxCellPatch } from './cell-patch'
import { aggregateLogs, logsToTemplateRows } from './logs'
import { loadTemplatesManifest, manifestEntryFor } from './template-manifest'

export function mark(checked: unknown): string {
  return checked === true || checked === 'true' || checked === '☑' || checked === '是' ? '☑' : '☐'
}

function asRecord(row: unknown): Record<string, unknown> {
  return row && typeof row === 'object' ? (row as Record<string, unknown>) : {}
}

function pickStr(row: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const v = row[key]
    if (v !== undefined && v !== null && String(v) !== '') return String(v)
  }
  return ''
}

function computedTotal(row: Record<string, unknown>): string {
  const existing = pickStr(row, 'total')
  if (existing) return existing
  const price = Number(pickStr(row, 'unit_price'))
  const qty = Number(pickStr(row, 'qty'))
  if (!Number.isNaN(price) && !Number.isNaN(qty) && pickStr(row, 'unit_price') && pickStr(row, 'qty')) {
    return String(price * qty)
  }
  return ''
}

export function mapHardwareRow(row: unknown, index: number): Record<string, string> {
  const r = asRecord(row)
  return {
    index: pickStr(r, 'index') || String(index + 1),
    name: pickStr(r, 'name'),
    spec: pickStr(r, 'spec'),
    brand: pickStr(r, 'brand'),
    deploy: pickStr(r, 'deploy', 'location'),
    unit_price: pickStr(r, 'unit_price'),
    qty: pickStr(r, 'qty'),
    total: computedTotal(r),
    note: pickStr(r, 'note', 'remark')
  }
}

export function mapSoftwareRow(row: unknown, index: number): Record<string, string> {
  const r = asRecord(row)
  return {
    index: pickStr(r, 'index') || String(index + 1),
    name: pickStr(r, 'name'),
    vendor: pickStr(r, 'vendor', 'version'),
    func: pickStr(r, 'func', 'license'),
    deploy: pickStr(r, 'deploy'),
    unit_price: pickStr(r, 'unit_price'),
    qty: pickStr(r, 'qty'),
    total: computedTotal(r),
    note: pickStr(r, 'note', 'remark')
  }
}

export function commonFields(project: Project): Record<string, string> {
  return {
    name: project.name,
    project_name: project.name,
    owner: project.owner,
    supervisor: project.supervisor,
    contractor: project.contractor,
    contract_no: project.contract_no,
    phase: project.phase,
    doc_no: project.doc_no,
    project_type: project.type
  }
}

function nullGetter(part: { module?: string; value?: string }): string {
  if (part.module === 'rawxml') return ''
  return ''
}

export function fillDocxTemplate(
  templatePath: string,
  data: Record<string, unknown>
): Buffer {
  if (!fs.existsSync(templatePath)) {
    throw new Error(`找不到模板文件：${templatePath}`)
  }
  const content = fs.readFileSync(templatePath)
  const zip = new PizZip(content)
  const doc = new Docxtemplater(zip, {
    paragraphLoop: true,
    linebreaks: true,
    nullGetter
  })
  doc.render(data)
  return doc.getZip().generate({ type: 'nodebuffer', compression: 'DEFLATE' }) as Buffer
}

export function fillDocx(
  templatePath: string,
  data: Record<string, unknown>,
  options?: { code?: string; templatesDir?: string }
): Buffer {
  const templatesDir = options?.templatesDir ?? path.dirname(templatePath)
  const manifest = loadTemplatesManifest(templatesDir)
  const entry = manifestEntryFor(manifest, {
    code: options?.code,
    fileName: path.basename(templatePath)
  })
  const mode = entry?.fillMode ?? (entry ? 'cell' : 'placeholder')
  if (mode === 'cell' && entry) {
    return fillDocxCellPatch(templatePath, data, entry)
  }
  return fillDocxTemplate(templatePath, data)
}

export function writeFilledDocx(
  templatePath: string,
  outputPath: string,
  data: Record<string, unknown>,
  options?: { code?: string; templatesDir?: string }
): string {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true })
  const buf = fillDocx(templatePath, data, options)
  fs.writeFileSync(outputPath, buf)
  return outputPath
}

export function buildTemplateData(
  item: CatalogItem,
  project: Project,
  payload: Record<string, unknown>,
  extra?: {
    logs?: DailyLog[]
    weekly?: WeeklyReportOptions
  }
): Record<string, unknown> {
  const base = {
    ...commonFields(project),
    ...payload,
    code: item.code,
    title: item.title
  }

  if (item.code === '2.10') {
    const logs = extra?.logs ?? []
    const one = logs[0]
    const row = one ? logsToTemplateRows([one])[0]! : {}
    return {
      ...base,
      ...row,
      date: row.date || payload.date || '',
      weather: row.weather || payload.weather || '',
      location: row.location || payload.location || '',
      work_done: row.work_done || payload.work_done || '',
      qs_check: row.qs_check || payload.qs_check || '',
      crew_count: row.crew_count || payload.crew_count || '',
      issues: row.issues || payload.issues || '',
      coordination: row.coordination || payload.coordination || '',
      logs: logsToTemplateRows(logs),
      log_count: String(logs.length)
    }
  }

  if (item.code === '2.11' || item.code === '2.12') {
    const weekly = extra?.weekly
    const logs = extra?.logs ?? []
    const agg = aggregateLogs(logs)
    return {
      ...base,
      period_start: weekly?.period_start ?? '',
      period_end: weekly?.period_end ?? '',
      done: weekly?.undone !== undefined ? agg.done : agg.done,
      undone: weekly?.undone || payload.undone || '（待补充未完事项）',
      issues: weekly?.issues || agg.issues,
      plan: weekly?.plan || payload.plan || '（待补充下期计划）'
    }
  }

  if (item.code === '2.7') {
    return {
      ...base,
      location: payload.location || project.phase || '',
      serial: payload.serial || '',
      device_name: payload.device_name || '',
      date: payload.date || '',
      packaging_ok: mark(payload.packaging_ok ?? true),
      appearance_ok: mark(payload.appearance_ok ?? true),
      accessories_ok: mark(payload.accessories_ok ?? true),
      docs_ok: mark(payload.docs_ok ?? true),
      model_ok: mark(payload.model_ok ?? true),
      remark: payload.remark || 'TODO：补充开箱检验备注'
    }
  }

  if (item.code === '2.8') {
    const rows = Array.isArray(payload.rows) && payload.rows.length > 0
      ? payload.rows
      : [
          {
            device_name: 'TODO 设备名称',
            location: payload.location || '',
            installer: payload.installer || '',
            date: payload.date || '',
            result: '合格'
          }
        ]
    return { ...base, rows }
  }

  if (item.code === '6.2') {
    return {
      ...base,
      basic_info:
        payload.basic_info ||
        `项目名称：${project.name}\n建设单位：${project.owner}\n监理单位：${project.supervisor}\n施工单位：${project.contractor}\n合同号：${project.contract_no}`,
      conclusion: payload.conclusion || 'TODO：填写竣工验收结论',
      warranty: payload.warranty || 'TODO：填写质保期与质保范围'
    }
  }

  if (item.code === '7.1') {
    return {
      ...base,
      overview: payload.overview || `本项目（${project.name}）按合同 ${project.contract_no} 组织实施。`,
      progress: payload.progress || 'TODO：建设过程概述',
      quality: payload.quality || 'TODO：质量与安全情况',
      issues: payload.issues || 'TODO：存在问题及整改',
      next: payload.next || 'TODO：运维移交安排'
    }
  }

  if (item.code === '7.2') {
    const hardwareRaw =
      Array.isArray(payload.hardware) && payload.hardware.length > 0
        ? (payload.hardware as Record<string, unknown>[])
        : [{ name: 'TODO 硬件名称', spec: '', qty: '1', unit: '台', remark: '' }]
    const softwareRaw =
      Array.isArray(payload.software) && payload.software.length > 0
        ? (payload.software as Record<string, unknown>[])
        : [{ name: 'TODO 软件名称', version: '', license: '', qty: '1', remark: '' }]
    return {
      ...base,
      approval_no: String(payload.approval_no || project.doc_no || ''),
      hardware: hardwareRaw.map((row, i) => mapHardwareRow(row, i)),
      software: softwareRaw.map((row, i) => mapSoftwareRow(row, i))
    }
  }

  return base
}

export function createStubDocx(title: string, note: string): Buffer {
  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:jc w:val="center"/></w:pPr>
      <w:r><w:rPr><w:b/><w:sz w:val="36"/><w:rFonts w:eastAsia="黑体"/></w:rPr>
        <w:t>${escapeXml(title)}</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r><w:rPr><w:sz w:val="24"/><w:rFonts w:eastAsia="宋体"/></w:rPr>
        <w:t>${escapeXml(note)}</w:t>
      </w:r>
    </w:p>
    <w:p>
      <w:r><w:t>本文件为 M1 占位稿，后续可由测评/等保模块自动生成。</w:t></w:r>
    </w:p>
  </w:body>
</w:document>`

  const zip = new PizZip()
  zip.file('[Content_Types].xml', CONTENT_TYPES)
  zip.file('_rels/.rels', RELS)
  zip.file('word/_rels/document.xml.rels', DOC_RELS)
  zip.file('word/document.xml', documentXml)
  zip.file('word/styles.xml', STYLES)
  zip.file('docProps/core.xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>${escapeXml(title)}</dc:title>
  <dc:creator>验收到手</dc:creator>
</cp:coreProperties>`)
  return zip.generate({ type: 'nodebuffer', compression: 'DEFLATE' }) as Buffer
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const CONTENT_TYPES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>`

const RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>`

const DOC_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="宋体" w:eastAsia="宋体"/><w:sz w:val="21"/></w:rPr>
  </w:style>
</w:styles>`
