#!/usr/bin/env node
/**
 * Generate placeholder .docx templates with docxtemplater tags kept in a
 * single <w:t> run so Chinese Word tables fill reliably.
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

function tc(inner, width = 2400) {
  return `<w:tc>
    <w:tcPr><w:tcW w:w="${width}" w:type="dxa"/><w:tcBorders>
      <w:top w:val="single" w:sz="4" w:color="8A6A3A"/>
      <w:left w:val="single" w:sz="4" w:color="8A6A3A"/>
      <w:bottom w:val="single" w:sz="4" w:color="8A6A3A"/>
      <w:right w:val="single" w:sz="4" w:color="8A6A3A"/>
    </w:tcBorders><w:shd w:val="clear" w:color="auto" w:fill="FFF8EE"/>
    </w:tcPr>
    <w:p><w:pPr><w:spacing w:before="40" w:after="40"/></w:pPr>${inner}</w:p>
  </w:tc>`
}

function headerTc(text, width = 2400) {
  return `<w:tc>
    <w:tcPr><w:tcW w:w="${width}" w:type="dxa"/><w:shd w:val="clear" w:color="auto" w:fill="6B3A2A"/>
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
  const zip = new PizZip()
  zip.file('[Content_Types].xml', CONTENT_TYPES)
  zip.file('_rels/.rels', RELS)
  zip.file('word/_rels/document.xml.rels', DOC_RELS)
  zip.file('word/document.xml', doc(bodyInner, titleText))
  zip.file('word/styles.xml', STYLES)
  zip.file('docProps/core.xml', core(titleText))
  zip.file('docProps/app.xml', APP)
  fs.mkdirSync(OUT, { recursive: true })
  const buf = zip.generate({ type: 'nodebuffer', compression: 'DEFLATE' })
  fs.writeFileSync(path.join(OUT, filename), buf)
  console.log('wrote', filename)
}

const headerBlock = [
  kvTable([
    ['项目名称', '{project_name}'],
    ['建设单位', '{owner}'],
    ['监理单位', '{supervisor}'],
    ['施工单位', '{contractor}'],
    ['合同号', '{contract_no}'],
    ['阶段', '{phase}'],
    ['文号', '{doc_no}']
  ])
].join('')

function save210() {
  const logRow = `<w:tr>
    ${tc(t('{#logs}{date}'), 1400)}
    ${tc(t('{weather}'), 1200)}
    ${tc(t('{location}'), 1600)}
    ${tc(t('{work_done}'), 2400)}
    ${tc(t('{qs_check}'), 1600)}
    ${tc(t('{crew_count}'), 800)}
    ${tc(t('{issues}{/logs}'), 1600)}
  </w:tr>`
  const body = [
    title('2.10 施工日志'),
    headerBlock,
    heading('日志明细'),
    p(t('共 {log_count} 条。'), null),
    table(
      [
        `<w:tr>${['日期', '天气', '地点', '完成工作', '质检情况', '人数', '问题'].map((h, i) => headerTc(h, [1400, 1200, 1600, 2400, 1600, 800, 1600][i])).join('')}</w:tr>`,
        logRow
      ],
      [1400, 1200, 1600, 2400, 1600, 800, 1600]
    ),
    heading('协调事项（末条展开）'),
    p(t('{#logs}{date}：{coordination}{/logs}'), null)
  ].join('')
  saveDocx('2.10_施工日志.docx', '2.10 施工日志', body)
}

function savePeriod(code, name, file) {
  const body = [
    title(`${code} ${name}`),
    headerBlock,
    heading('报告周期'),
    kvTable([
      ['起始日期', '{period_start}'],
      ['截止日期', '{period_end}'],
      ['当前阶段', '{phase}']
    ]),
    heading('本期完成工作（由施工日志汇总）'),
    p(t('{done}'), null),
    heading('未完事项'),
    p(t('{undone}'), null),
    heading('存在问题'),
    p(t('{issues}'), null),
    heading('下期计划'),
    p(t('{plan}'), null)
  ].join('')
  saveDocx(file, `${code} ${name}`, body)
}

function save27() {
  const body = [
    title('2.7 设备开箱检验记录'),
    headerBlock,
    heading('设备信息'),
    kvTable([
      ['安装地点', '{location}'],
      ['出厂编号 / 序列号', '{serial}'],
      ['设备名称', '{device_name}']
    ]),
    heading('检验项目'),
    table(
      [
        `<w:tr>${headerTc('检验项', 4000)}${headerTc('结果', 2000)}${headerTc('勾选', 2500)}</w:tr>`,
        `<w:tr>${tc(t('包装完好'), 4000)}${tc(t('包装完好'), 2000)}${tc(t('{packaging_ok}'), 2500)}</w:tr>`,
        `<w:tr>${tc(t('外观无损'), 4000)}${tc(t('外观无损'), 2000)}${tc(t('{appearance_ok}'), 2500)}</w:tr>`,
        `<w:tr>${tc(t('配件齐全'), 4000)}${tc(t('配件齐全'), 2000)}${tc(t('{accessories_ok}'), 2500)}</w:tr>`,
        `<w:tr>${tc(t('随机资料齐全'), 4000)}${tc(t('资料齐全'), 2000)}${tc(t('{docs_ok}'), 2500)}</w:tr>`,
        `<w:tr>${tc(t('型号规格与合同相符'), 4000)}${tc(t('型号相符'), 2000)}${tc(t('{model_ok}'), 2500)}</w:tr>`
      ],
      [4000, 2000, 2500]
    ),
    heading('备注'),
    p(t('{remark}'), null)
  ].join('')
  saveDocx('2.7_设备开箱检验记录.docx', '2.7 设备开箱检验记录', body)
}

function save28() {
  const dataRow = `<w:tr>
    ${tc(t('{#rows}{device_name}'), 2200)}
    ${tc(t('{location}'), 2000)}
    ${tc(t('{installer}'), 1800)}
    ${tc(t('{date}'), 1600)}
    ${tc(t('{result}{/rows}'), 1600)}
  </w:tr>`
  const body = [
    title('2.8 设备安装记录'),
    headerBlock,
    heading('安装明细'),
    table(
      [
        `<w:tr>${['设备名称', '安装地点', '安装人', '日期', '结果'].map((h, i) => headerTc(h, [2200, 2000, 1800, 1600, 1600][i])).join('')}</w:tr>`,
        dataRow
      ],
      [2200, 2000, 1800, 1600, 1600]
    ),
    p(t('TODO：可在资料目录中补充安装照片等附件。'), null)
  ].join('')
  saveDocx('2.8_设备安装记录.docx', '2.8 设备安装记录', body)
}

function save62() {
  const body = [
    title('6.2 竣工验收报告'),
    heading('一、基本信息'),
    p(t('{basic_info}'), null),
    heading('二、验收结论'),
    p(t('{conclusion}'), null),
    heading('三、质保条款'),
    p(t('{warranty}'), null),
    p(t('建设单位：{owner}    施工单位：{contractor}    监理单位：{supervisor}'), null)
  ].join('')
  saveDocx('6.2_竣工验收报告.docx', '6.2 竣工验收报告', body)
}

function save71() {
  const body = [
    title('7.1 项目建设总结'),
    headerBlock,
    heading('一、项目概况'),
    p(t('{overview}'), null),
    heading('二、建设过程'),
    p(t('{progress}'), null),
    heading('三、质量与安全'),
    p(t('{quality}'), null),
    heading('四、问题与整改'),
    p(t('{issues}'), null),
    heading('五、运维与移交'),
    p(t('{next}'), null)
  ].join('')
  saveDocx('7.1_项目建设总结.docx', '7.1 项目建设总结', body)
}

function save72() {
  const hw = `<w:tr>
    ${tc(t('{#hardware}{name}'), 2200)}
    ${tc(t('{spec}'), 2200)}
    ${tc(t('{qty}'), 1000)}
    ${tc(t('{unit}'), 1000)}
    ${tc(t('{remark}{/hardware}'), 2200)}
  </w:tr>`
  const sw = `<w:tr>
    ${tc(t('{#software}{name}'), 2200)}
    ${tc(t('{version}'), 1600)}
    ${tc(t('{license}'), 1800)}
    ${tc(t('{qty}'), 1000)}
    ${tc(t('{remark}{/software}'), 2600)}
  </w:tr>`
  const body = [
    title('7.2 软硬件清单'),
    headerBlock,
    heading('硬件清单'),
    table(
      [
        `<w:tr>${['名称', '规格型号', '数量', '单位', '备注'].map((h, i) => headerTc(h, [2200, 2200, 1000, 1000, 2200][i])).join('')}</w:tr>`,
        hw
      ],
      [2200, 2200, 1000, 1000, 2200]
    ),
    heading('软件清单'),
    table(
      [
        `<w:tr>${['名称', '版本', '授权', '数量', '备注'].map((h, i) => headerTc(h, [2200, 1600, 1800, 1000, 2600][i])).join('')}</w:tr>`,
        sw
      ],
      [2200, 1600, 1800, 1000, 2600]
    )
  ].join('')
  saveDocx('7.2_软硬件清单.docx', '7.2 软硬件清单', body)
}

save210()
savePeriod('2.11', '项目月报', '2.11_项目月报.docx')
savePeriod('2.12', '项目周报', '2.12_项目周报.docx')
save27()
save28()
save62()
save71()
save72()
console.log('templates dir:', OUT)
