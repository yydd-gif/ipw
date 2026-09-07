#!/usr/bin/env node
/**
 * Generate .docx templates used by CellPatch (no docxtemplater tags).
 *
 * Never overwrites an existing file — real user templates and a dropped
 * core-templates.zip must not be clobbered by postinstall.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const PizZip = require('pizzip')

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT = path.resolve(__dirname, '../templates')

function escapeXml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function t(text, extraRPr = '') {
  return `<w:r><w:rPr><w:rFonts w:ascii="宋体" w:hAnsi="宋体" w:eastAsia="宋体"/><w:sz w:val="21"/>${extraRPr}</w:rPr><w:t xml:space="preserve">${escapeXml(text)}</w:t></w:r>`
}

function p(inner, jc) {
  const pr = jc ? `<w:pPr><w:jc w:val="${jc}"/><w:spacing w:after="120"/></w:pPr>` : `<w:pPr><w:spacing w:after="80"/></w:pPr>`
  return `<w:p>${pr}${inner}</w:p>`
}

function title(text) {
  return `<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="240"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="36"/><w:rFonts w:eastAsia="黑体" w:ascii="SimHei"/></w:rPr><w:t>${escapeXml(text)}</w:t></w:r></w:p>`
}

function heading(text) {
  return `<w:p><w:pPr><w:spacing w:before="200" w:after="120"/></w:pPr><w:r><w:rPr><w:b/><w:sz w:val="28"/><w:rFonts w:eastAsia="黑体"/></w:rPr><w:t>${escapeXml(text)}</w:t></w:r></w:p>`
}

function tc(inner, width = 2400, span) {
  const spanXml = span && span > 1 ? `<w:gridSpan w:val="${span}"/>` : ''
  return `<w:tc>
    <w:tcPr><w:tcW w:w="${width}" w:type="dxa"/>${spanXml}<w:tcBorders>
      <w:top w:val="single" w:sz="4" w:color="8A6A3A"/>
      <w:left w:val="single" w:sz="4" w:color="8A6A3A"/>
      <w:bottom w:val="single" w:sz="4" w:color="8A6A3A"/>
      <w:right w:val="single" w:sz="4" w:color="8A6A3A"/>
    </w:tcBorders><w:shd w:val="clear" w:color="auto" w:fill="FFF8EE"/>
    </w:tcPr>
    <w:p><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr>${inner}</w:p>
  </w:tc>`
}

function headerTc(text, width = 2400, span) {
  const spanXml = span && span > 1 ? `<w:gridSpan w:val="${span}"/>` : ''
  return `<w:tc>
    <w:tcPr><w:tcW w:w="${width}" w:type="dxa"/>${spanXml}<w:shd w:val="clear" w:color="auto" w:fill="6B3A2A"/>
      <w:tcBorders>
        <w:top w:val="single" w:sz="4" w:color="6B3A2A"/>
        <w:left w:val="single" w:sz="4" w:color="6B3A2A"/>
        <w:bottom w:val="single" w:sz="4" w:color="6B3A2A"/>
        <w:right w:val="single" w:sz="4" w:color="6B3A2A"/>
      </w:tcBorders>
    </w:tcPr>
    <w:p><w:r><w:rPr><w:b/><w:color w:val="FFFFFF"/><w:rFonts w:eastAsia="黑体"/><w:sz w:val="20"/></w:rPr><w:t>${escapeXml(text)}</w:t></w:r></w:p>
  </w:tc>`
}

function table(rows, widths) {
  const grid = `<w:tblGrid>${widths.map((w) => `<w:gridCol w:w="${w}"/>`).join('')}</w:tblGrid>`
  return `<w:tbl>
    <w:tblPr>
      <w:tblW w:w="${widths.reduce((a, b) => a + b, 0)}" w:type="dxa"/>
      <w:tblBorders>
        <w:top w:val="single" w:sz="4" w:color="8A6A3A"/>
        <w:left w:val="single" w:sz="4" w:color="8A6A3A"/>
        <w:bottom w:val="single" w:sz="4" w:color="8A6A3A"/>
        <w:right w:val="single" w:sz="4" w:color="8A6A3A"/>
        <w:insideH w:val="single" w:sz="4" w:color="8A6A3A"/>
        <w:insideV w:val="single" w:sz="4" w:color="8A6A3A"/>
      </w:tblBorders>
    </w:tblPr>
    ${grid}
    ${rows.join('')}
  </w:tbl>`
}

function kvTable(pairs) {
  const rows = pairs.map(
    ([k, v]) => `<w:tr>${tc(t(k), 2800)}${tc(t(v), 6500)}</w:tr>`
  )
  return table(rows, [2800, 6500])
}

function doc(bodyInner, titleText) {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${bodyInner}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>
    </w:sectPr>
  </w:body>
</w:document>`
}

const CONTENT_TYPES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>`

const RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`

const DOC_RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/><w:sz w:val="21"/></w:rPr></w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
</w:styles>`

function core(name) {
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>${escapeXml(name)}</dc:title>
  <dc:creator>验收到手 Acceptance Studio</dc:creator>
  <cp:lastModifiedBy>验收到手</cp:lastModifiedBy>
</cp:coreProperties>`
}

const APP = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>验收到手</Application>
</Properties>`

function saveDocx(filename, titleText, bodyInner) {
  fs.mkdirSync(OUT, { recursive: true })
  const dest = path.join(OUT, filename)
  // Never clobber real user templates (postinstall / generate:templates).
  // Set GENERATE_TEMPLATES_OVERWRITE=1 only for an explicit local rebuild.
  if (fs.existsSync(dest) && process.env.GENERATE_TEMPLATES_OVERWRITE !== '1') {
    console.log('skip existing', filename)
    return false
  }
  const zip = new PizZip()
  zip.file('[Content_Types].xml', CONTENT_TYPES)
  zip.file('_rels/.rels', RELS)
  zip.file('word/_rels/document.xml.rels', DOC_RELS)
  zip.file('word/document.xml', doc(bodyInner, titleText))
  zip.file('word/styles.xml', STYLES)
  zip.file('docProps/core.xml', core(titleText))
  zip.file('docProps/app.xml', APP)
  const buf = zip.generate({ type: 'nodebuffer', compression: 'DEFLATE' })
  fs.writeFileSync(dest, buf)
  console.log('wrote', filename)
  return true
}

function para(text, opts = {}) {
  const extraRPr = opts.bold ? '<w:b/>' : ''
  const sz = opts.sz ? `<w:sz w:val="${opts.sz}"/>` : '<w:sz w:val="21"/>'
  const jc = opts.jc ? `<w:jc w:val="${opts.jc}"/>` : ''
  return `<w:p><w:pPr>${jc}<w:spacing w:after="120"/></w:pPr>${t(text, extraRPr + sz)}</w:p>`
}

function emptyTc(width = 2400, span) {
  return tc(t(''), width, span)
}

function tr(cells) {
  return `<w:tr>${cells.join('')}</w:tr>`
}

function ellipsisRow(widths) {
  return tr(widths.map((w) => tc(t('……'), w)))
}

function emptyRow(widths) {
  return tr(widths.map((w) => emptyTc(w)))
}

function save210() {
  const w = [2200, 2500, 1800, 2800]
  const span = w[0] + w[1] + w[2] + w[3]
  const body = [
    title('施工日志'),
    para('工程名称：×××工程'),
    para('编号：项目编号-A25-流水号'),
    table(
      [
        tr([tc(t('施工单位'), w[0]), emptyTc(w[1]), tc(t('日期'), w[2]), emptyTc(w[3])]),
        tr([tc(t('天气'), w[0]), emptyTc(w[1] + w[2] + w[3], 3)]),
        tr([tc(t('施工地点'), w[0]), emptyTc(w[1] + w[2] + w[3], 3)]),
        tr([tc(t('今日完成工作：'), span, 4)]),
        tr([emptyTc(span, 4)]),
        tr([tc(t('施工人数：  个    现场问题：    需协调事项：'), span, 4)])
      ],
      w
    )
  ].join('')
  saveDocx('2.10_施工日志.docx', '施工日志', body)
}

function savePeriod(code, name, file, docNoToken) {
  const w = [2200, 2500, 1800, 2800]
  const body = [
    title(name),
    para('工程名称：×××工程'),
    para(`编号：${docNoToken}`),
    table(
      [
        tr([tc(t('施工单位'), w[0]), emptyTc(w[1]), tc(t('截止日期'), w[2]), emptyTc(w[3])]),
        tr([tc(t('当前阶段'), w[0]), emptyTc(w[1] + w[2] + w[3], 3)]),
        tr([tc(t('本期完成工作'), w[0]), emptyTc(w[1] + w[2] + w[3], 3)]),
        tr([tc(t('未完事项'), w[0]), emptyTc(w[1] + w[2] + w[3], 3)]),
        tr([tc(t('存在问题'), w[0]), emptyTc(w[1] + w[2] + w[3], 3)]),
        tr([tc(t('下期计划'), w[0]), emptyTc(w[1] + w[2] + w[3], 3)])
      ],
      w
    )
  ].join('')
  saveDocx(file, `${code} ${name}`, body)
}

function save27() {
  const w = [2800, 2200, 2200, 2100]
  const body = [
    title('设备开箱检验记录'),
    para('工程名称：×××工程'),
    para('编号：项目编号-A12-流水号'),
    table(
      [
        tr([tc(t('建设单位'), w[0]), emptyTc(w[1]), tc(t('监理单位'), w[2]), emptyTc(w[3])]),
        tr([tc(t('施工单位'), w[0]), emptyTc(w[1]), tc(t('安装地点'), w[2]), emptyTc(w[3])]),
        tr([tc(t('出厂编号'), w[0]), emptyTc(w[1]), tc(t('设备名称'), w[2]), emptyTc(w[3])])
      ],
      w
    )
  ].join('')
  saveDocx('2.7_设备开箱检验记录.docx', '设备开箱检验记录', body)
}

function save28() {
  const w = [1600, 1600, 1600, 1600, 1400, 1400]
  const body = [
    title('设备安装记录'),
    para('工程名称：×××工程'),
    para('编号：项目编号-A13-流水号'),
    table(
      [
        tr([tc(t('安装地点'), w[0]), emptyTc(w[1] + w[2], 2), tc(t('日期'), w[3]), emptyTc(w[4] + w[5], 2)]),
        tr([tc(t('安装人'), w[0]), emptyTc(w[1] + w[2], 2), tc(t('监理人员'), w[3]), emptyTc(w[4] + w[5], 2)]),
        tr(['设备名称', '配件', '安装地点', '工艺', '供电', '记录'].map((h, i) => headerTc(h, w[i]))),
        ellipsisRow(w)
      ],
      w
    )
  ].join('')
  saveDocx('2.8_设备安装记录.docx', '设备安装记录', body)
}

function save62() {
  const coverW = [2800, 6500]
  const checkW = [4000, 2000]
  const infoW = [2800, 6500]
  const body = [
    title('竣工验收报告'),
    heading('封面信息'),
    table(
      [
        tr([headerTc('验收单位', coverW[0] + coverW[1], 2)]),
        tr([tc(t('建设单位'), coverW[0]), emptyTc(coverW[1])]),
        tr([tc(t('监理单位'), coverW[0]), emptyTc(coverW[1])]),
        tr([tc(t('施工单位'), coverW[0]), emptyTc(coverW[1])])
      ],
      coverW
    ),
    heading('验收检查项（勾选写入主单元格）'),
    table(
      [
        tr([tc(t('资料齐全'), checkW[0]), tc(t('☐'), checkW[1])]),
        tr([tc(t('质量合格'), checkW[0]), tc(t('☐'), checkW[1])]),
        tr([tc(t('安全文明'), checkW[0]), tc(t('☐'), checkW[1])])
      ],
      checkW
    ),
    heading('验收正文'),
    table(
      [
        tr([tc(t('项目名称'), infoW[0]), emptyTc(infoW[1])]),
        tr([tc(t('合同号'), infoW[0]), emptyTc(infoW[1])]),
        tr([tc(t('建设单位'), infoW[0]), emptyTc(infoW[1])]),
        tr([tc(t('监理单位'), infoW[0]), emptyTc(infoW[1])]),
        tr([tc(t('施工单位'), infoW[0]), emptyTc(infoW[1])]),
        tr([tc(t('验收结论'), infoW[0]), emptyTc(infoW[1])]),
        tr([tc(t('质保条款'), infoW[0]), emptyTc(infoW[1])])
      ],
      infoW
    )
  ].join('')
  saveDocx('6.2_竣工验收报告.docx', '竣工验收报告', body)
}

function save71() {
  const body = [
    title('项目建设总结'),
    para('XXX项目情况简介'),
    para('本合同段建设总结稿排版较密，CellPatch 仅替换文首项目名称，其余章节留待人工校核。'),
    heading('一、项目概况'),
    para('（模板原文：请结合合同与批复填写项目概况。勿在程序中强行灌入长文以免打乱样式。）'),
    heading('二、建设过程'),
    para('（模板原文：建设过程概述。）'),
    heading('三、质量与安全'),
    para('（模板原文：质量与安全情况。）'),
    heading('四、问题与整改'),
    para('（模板原文：存在问题及整改。）'),
    heading('五、运维与移交'),
    para('（模板原文：运维移交安排。）')
  ].join('')
  saveDocx('7.1_项目建设总结.docx', '项目建设总结', body)
}

function inventoryTable(titleText, padEmptyBeforeEllipsis) {
  const cols = [800, 1400, 1400, 1000, 1200, 900, 700, 900, 1200]
  const header = ['序号', '名称', '规格型号', '品牌', '部署位置', '单价', '数量', '合计', '备注']
  const swHeader = ['序号', '名称', '厂商', '功能', '部署位置', '单价', '数量', '合计', '备注']
  const heads = titleText.includes('软件') ? swHeader : header
  const sum = cols.reduce((a, b) => a + b, 0)
  const rows = [
    tr([headerTc(titleText, sum, 9)]),
    tr([
      tc(t('项目名称'), cols[0]),
      emptyTc(cols[1] + cols[2] + cols[3], 3),
      tc(t('批复文号'), cols[4]),
      emptyTc(cols[5] + cols[6] + cols[7] + cols[8], 4)
    ]),
    tr(heads.map((h, i) => headerTc(h, cols[i]))),
    tr([tc(t('总计'), cols[0]), ...cols.slice(1).map((w) => emptyTc(w))]),
    ...Array.from({ length: padEmptyBeforeEllipsis }, () => emptyRow(cols)),
    ellipsisRow(cols)
  ]
  return table(rows, cols)
}

function save72() {
  const body = [
    title('软硬件清单'),
    para('XXX'),
    inventoryTable('硬件配置清单', 2),
    inventoryTable('软件配置清单', 5)
  ].join('')
  saveDocx('7.2_软硬件清单.docx', '软硬件清单', body)
}

save210()
savePeriod('2.11', '项目月报', '2.11_项目月报.docx', '项目编号-A26-流水号')
savePeriod('2.12', '项目周报', '2.12_项目周报.docx', '项目编号-A25-流水号')
save27()
save28()
save62()
save71()
save72()
console.log('templates dir:', OUT)
