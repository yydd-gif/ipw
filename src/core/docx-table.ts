import PizZip from 'pizzip'
import { extractDirectChildren, extractElements, getText } from './xml-parts'
import type { DocCell, DocParagraph, TableDocument } from '../shared/types'

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function hasBold(xml: string): boolean {
  return /<w:b(?:\s[^>]*)?\/>/.test(xml) || /<w:b\s[^>]*w:val="(true|1)"/.test(xml)
}

function readAlign(xml: string): DocCell['align'] {
  const m = xml.match(/<w:jc\s+w:val="([^"]+)"/)
  if (!m) return undefined
  if (m[1] === 'center') return 'center'
  if (m[1] === 'right' || m[1] === 'end') return 'right'
  return 'left'
}

function readColSpan(tcXml: string): number | undefined {
  const m = tcXml.match(/<w:gridSpan\s+w:val="(\d+)"/)
  const n = m ? Number(m[1]) : 1
  return n > 1 ? n : undefined
}

function parseParagraph(pXml: string): DocParagraph {
  return {
    text: getText(pXml).replace(/\s+/g, ' ').trim(),
    bold: hasBold(pXml),
    align: readAlign(pXml)
  }
}

function parseCell(tcXml: string): DocCell {
  return {
    text: getText(tcXml),
    bold: hasBold(tcXml),
    align: readAlign(tcXml),
    colSpan: readColSpan(tcXml)
  }
}

export function parseDocumentXml(xml: string): TableDocument {
  const body = extractElements(xml, 'w:body')[0]
  if (!body) return { paragraphs: [], tables: [] }
  const paras = extractDirectChildren(body, 'w:p').map((el) => ({ kind: 'p' as const, el }))
  const tables = extractDirectChildren(body, 'w:tbl').map((el) => ({ kind: 'tbl' as const, el }))
  const blocks = [...paras, ...tables].sort((a, b) => a.el.start - b.el.start)

  const paragraphs: DocParagraph[] = []
  const parsedTables: TableDocument['tables'] = []
  for (const block of blocks) {
    if (block.kind === 'p') {
      const para = parseParagraph(block.el.full)
      if (para.text) paragraphs.push(para)
    } else {
      const rows = extractDirectChildren(block.el, 'w:tr').map((tr) =>
        extractDirectChildren(tr, 'w:tc').map((tc) => parseCell(tc.full))
      )
      if (rows.length) parsedTables.push({ rows })
    }
  }
  return {
    title: paragraphs[0]?.text,
    paragraphs,
    tables: parsedTables
  }
}

export function parseDocxBuffer(buf: Buffer): TableDocument {
  const zip = new PizZip(buf)
  const xml = zip.file('word/document.xml')?.asText() ?? ''
  return parseDocumentXml(xml)
}

function cellXml(cell: DocCell, width: number): string {
  const span = cell.colSpan && cell.colSpan > 1 ? `<w:gridSpan w:val="${cell.colSpan}"/>` : ''
  const jc = cell.align ? `<w:jc w:val="${cell.align}"/>` : ''
  const bold = cell.bold ? '<w:b/>' : ''
  return `<w:tc>
    <w:tcPr><w:tcW w:w="${width}" w:type="dxa"/>${span}<w:tcBorders>
      <w:top w:val="single" w:sz="4" w:color="333333"/>
      <w:left w:val="single" w:sz="4" w:color="333333"/>
      <w:bottom w:val="single" w:sz="4" w:color="333333"/>
      <w:right w:val="single" w:sz="4" w:color="333333"/>
    </w:tcBorders></w:tcPr>
    <w:p><w:pPr>${jc}</w:pPr><w:r><w:rPr>${bold}<w:rFonts w:eastAsia="宋体"/><w:sz w:val="21"/></w:rPr>
      <w:t xml:space="preserve">${escapeXml(cell.text)}</w:t>
    </w:r></w:p>
  </w:tc>`
}

function paraXml(p: DocParagraph): string {
  const jc = p.align ? `<w:jc w:val="${p.align}"/>` : ''
  const bold = p.bold ? '<w:b/>' : ''
  return `<w:p><w:pPr>${jc}</w:pPr><w:r><w:rPr>${bold}<w:rFonts w:eastAsia="宋体"/><w:sz w:val="24"/></w:rPr>
    <w:t xml:space="preserve">${escapeXml(p.text)}</w:t></w:r></w:p>`
}

export function tableDocumentToDocx(doc: TableDocument): Buffer {
  const parts: string[] = []
  if (doc.title) {
    parts.push(
      `<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="36"/><w:rFonts w:eastAsia="黑体"/></w:rPr><w:t>${escapeXml(doc.title)}</w:t></w:r></w:p>`
    )
  }
  for (const p of doc.paragraphs) {
    if (doc.title && p.text === doc.title) continue
    parts.push(paraXml(p))
  }
  for (const table of doc.tables) {
    const colCount = Math.max(1, ...table.rows.map((r) => r.reduce((n, c) => n + (c.colSpan ?? 1), 0)))
    const width = Math.floor(9000 / colCount)
    const grid = `<w:tblGrid>${Array.from({ length: colCount }, () => `<w:gridCol w:w="${width}"/>`).join('')}</w:tblGrid>`
    const rows = table.rows
      .map((row) => `<w:tr>${row.map((c) => cellXml(c, width)).join('')}</w:tr>`)
      .join('')
    parts.push(
      `<w:tbl><w:tblPr><w:tblW w:w="${width * colCount}" w:type="dxa"/></w:tblPr>${grid}${rows}</w:tbl>`
    )
  }
  const documentXml = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${parts.join('\n')}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>`

  const zip = new PizZip()
  zip.file(
    '[Content_Types].xml',
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>`
  )
  zip.file(
    '_rels/.rels',
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>`
  )
  zip.file(
    'word/_rels/document.xml.rels',
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>`
  )
  zip.file('word/document.xml', documentXml)
  zip.file(
    'docProps/core.xml',
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>${escapeXml(doc.title || '验收资料')}</dc:title>
  <dc:creator>验收到手</dc:creator>
</cp:coreProperties>`
  )
  return zip.generate({ type: 'nodebuffer', compression: 'DEFLATE' }) as Buffer
}

export function emptyDocument(title: string): TableDocument {
  return {
    title,
    paragraphs: [{ text: title, bold: true, align: 'center' }],
    tables: []
  }
}
