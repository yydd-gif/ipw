/**
 * Headless M1 acceptance path:
 * hybrid project → ≥3 daily logs → 2.12 weekly docx → 2.10 log docx
 * → dummy uploads for remaining required items → zip export.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import PizZip from 'pizzip'
import { itemsForProjectType } from '../src/shared/catalog'
import {
  canOpenExportSaveDialog,
  formatConfirmReadyToast,
  withExportSavePath
} from '../src/shared/completeness'
import { Studio } from '../src/core/studio'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'acceptance-studio-m1-'))
const templatesDir = path.join(root, 'templates')

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(`ASSERT: ${msg}`)
}

async function main(): Promise<void> {
  if (!fs.existsSync(path.join(templatesDir, '2.12_项目周报.docx'))) {
    throw new Error('templates missing; run npm run generate:templates')
  }

  const studio = new Studio({ dataDir: tmp, templatesDir })
  await studio.init()

  const project = studio.createProject({
    name: '演示混合验收项目',
    type: 'hybrid',
    owner: '某市大数据局',
    supervisor: '某监理公司',
    contractor: '某集成公司',
    contract_no: 'HT-2026-001',
    phase: '施工',
    doc_no: 'YS-001'
  })

  const logs = [
    {
      date: '2026-09-01',
      weather: '晴',
      location: '主机房',
      work_done: '完成机柜就位与接地检查。',
      qs_check: '接地电阻合格。',
      crew_count: 8,
      issues: '桥架到货延迟半天。',
      coordination: '与业主确认机柜编号。'
    },
    {
      date: '2026-09-02',
      weather: '多云',
      location: '主机房',
      work_done: '完成核心交换机上架及线缆敷设。',
      qs_check: '标签与图纸一致。',
      crew_count: 10,
      issues: '',
      coordination: '监理旁站。'
    },
    {
      date: '2026-09-03',
      weather: '阴',
      location: '配线间',
      work_done: '完成配线架打线和通断测试。',
      qs_check: '抽测 20 点全部通过。',
      crew_count: 6,
      issues: '两根尾纤需更换。',
      coordination: '通知供货商更换。'
    }
  ]

  for (const log of logs) {
    studio.saveLog({ ...log, project_id: project.id })
  }
  assert(studio.listLogs(project.id).length >= 3, 'need ≥3 daily logs')

  assert(
    formatConfirmReadyToast(0, {
      ok: false,
      blockers: [],
      confirmed: 0,
      required: 23,
      waived: 0
    }) === '没有可确认的资料（请先上传或生成文件）',
    'n=0 toast copy'
  )
  assert(
    formatConfirmReadyToast(3, {
      ok: false,
      blockers: [{ code: '1.2', title: '合同', reason: '尚未提供资料' }],
      confirmed: 1,
      required: 23,
      waived: 0
    }) === '本批已确认 3 条资料。必填进度 1/23，尚不能出包',
    'n>0 incomplete toast copy uses 本批已确认 and ExportCheck progress'
  )
  assert(
    formatConfirmReadyToast(5, {
      ok: true,
      blockers: [],
      confirmed: 23,
      required: 23,
      waived: 0
    }) === '本批已确认 5 条资料。必填已齐，可以出包',
    'n>0 complete toast copy'
  )

  const earlyCheck = studio.checkExport(project.id)
  assert(!earlyCheck.ok, 'export check fails while required items are incomplete')
  assert(
    !canOpenExportSaveDialog(earlyCheck),
    'save dialog must stay closed while required items are incomplete'
  )
  const none = studio.confirmItemsWithArtifacts(project.id)
  assert(none === 0, 'batch confirm is 0 before any artifacts')
  assert(
    formatConfirmReadyToast(none, earlyCheck) === '没有可确认的资料（请先上传或生成文件）',
    'empty batch uses n=0 copy, not header confirmed count'
  )

  let saveDialogOpened = false
  let blockedBeforeDialog = false
  try {
    await withExportSavePath(
      earlyCheck,
      async () => {
        saveDialogOpened = true
        return path.join(tmp, 'too-early.zip')
      },
      (dest) => studio.exportZip(project.id, dest)
    )
  } catch {
    blockedBeforeDialog = true
  }
  assert(blockedBeforeDialog, 'export must block while required items are incomplete')
  assert(!saveDialogOpened, 'save dialog must not open before completeness passes')

  let blocked = false
  try {
    studio.exportZip(project.id, path.join(tmp, 'too-early.zip'))
  } catch {
    blocked = true
  }
  assert(blocked, 'exportZip must still throw while required items are incomplete')

  const weekly = studio.generateWeeklyReport(project.id, {
    period_start: '2026-09-01',
    period_end: '2026-09-03',
    undone: '机房精密空调调试未完成。',
    plan: '下周完成空调调试并开始试运行准备。'
  })
  const weeklyBuf = fs.readFileSync(weekly.path)
  const weeklyZip = new PizZip(weeklyBuf)
  const weeklyXml = weeklyZip.file('word/document.xml')?.asText() ?? ''
  assert(weeklyXml.includes('完成机柜就位') || weeklyXml.includes('核心交换机'), 'weekly docx aggregates log text')
  assert(weeklyXml.includes('施工单位') || weeklyXml.includes('项目周报'), '2.12 retains week-report structure')

  const logDoc = studio.generateDocument(project.id, '2.10')
  assert(fs.existsSync(logDoc.path), '2.10 docx exists')
  assert((logDoc.paths?.length ?? 1) >= 3, '2.10 one log → one file')
  const logXml = new PizZip(fs.readFileSync(logDoc.path)).file('word/document.xml')?.asText() ?? ''
  assert(logXml.includes('施工单位'), '2.10 retains 施工单位 header')
  assert(logXml.includes('施工日志'), '2.10 retains 施工日志 header structure')
  assert(
    logXml.includes('完成机柜就位') || logXml.includes('核心交换机') || logXml.includes('配线架'),
    '2.10 filled with a daily log'
  )
  assert(logXml.includes('某集成公司'), '2.10 contractor filled')

  const optionalBatch = studio.confirmItemsWithArtifacts(project.id)
  const afterOptional = studio.checkExport(project.id)
  assert(optionalBatch > 0, 'optional weekly/log artifacts are in the batch count')
  assert(!afterOptional.ok, 'optional confirms do not make export ready')
  assert(
    afterOptional.confirmed === 0,
    'header ExportCheck.confirmed stays required-only after optional batch'
  )
  assert(
    formatConfirmReadyToast(optionalBatch, afterOptional) ===
      `本批已确认 ${optionalBatch} 条资料。必填进度 ${afterOptional.confirmed}/${afterOptional.required}，尚不能出包`,
    'incomplete toast reports batch n and required progress separately'
  )

  for (const item of itemsForProjectType('hybrid')) {
    if (item.produceType === 'template' || item.produceType === 'derived') {
      if (item.code === '2.10' || item.code === '2.12') continue
      studio.generateDocument(project.id, item.code)
    }
    if (item.required && item.produceType === 'upload') {
      const dummy = path.join(tmp, `dummy-${item.code}.txt`)
      fs.writeFileSync(dummy, `占位资料 ${item.code} ${item.title}\n`)
      studio.addUpload(project.id, item.code, dummy, `${item.code}_${item.title}.txt`)
    }
  }

  const hwPath = path.join(tmp, 'projects', project.id, 'generated', '7.2_软硬件清单.docx')
  assert(fs.existsSync(hwPath), '7.2 docx generated')
  const hwXml = new PizZip(fs.readFileSync(hwPath)).file('word/document.xml')?.asText() ?? ''
  const tmpl72 = new PizZip(fs.readFileSync(path.join(templatesDir, '7.2_软硬件清单.docx'))).file(
    'word/document.xml'
  )!.asText()
  assert(hwXml.includes('硬件配置清单'), '7.2 real-template fingerprint 硬件配置清单')
  assert(hwXml.includes('TODO 硬件名称'), '7.2 fills cloned hardware row')
  const totTmpl = (tmpl72.match(/总计/g) || []).length
  const totGen = (hwXml.match(/总计/g) || []).length
  assert(totGen === totTmpl, `7.2 must not clone 总计 rows (template=${totTmpl} generated=${totGen})`)

  const confirmed = studio.confirmItemsWithArtifacts(project.id)
  assert(confirmed > 0, 'confirmed some items')
  const check = studio.checkExport(project.id)
  assert(check.ok, `export should be allowed, blockers=${JSON.stringify(check.blockers)}`)
  assert(canOpenExportSaveDialog(check), 'save dialog may open only after completeness passes')
  assert(
    confirmed !== check.confirmed,
    'batch n includes optional artifacts; header ExportCheck.confirmed is required-only'
  )
  assert(
    formatConfirmReadyToast(confirmed, check) ===
      `本批已确认 ${confirmed} 条资料。必填已齐，可以出包`,
    'ready toast reports batch n and does not reuse header confirmed count'
  )
  assert(
    !formatConfirmReadyToast(confirmed, check).includes(`已确认 ${check.confirmed} 条已有资料`),
    'must not pretend batch n is the header confirmed count'
  )

  const catalogState = studio.getCatalogState(project.id)
  const byCode = new Map(
    catalogState.flatMap((v) => v.items).map((entry) => [entry.item.code, entry.item.title])
  )
  assert(byCode.get('2.1') === '开工报审表', '2.1 is 开工报审表')
  assert(
    byCode.get('2.2') === '项目经理授权书及法定代表人授权书',
    '2.2 is authorization letters'
  )
  assert(byCode.get('2.3') === '施工组织方案报审表', '2.3 is 施工组织方案报审表')
  assert(byCode.get('2.4') === '施工组织方案', '2.4 is 施工组织方案')
  assert(byCode.get('2.5') === '工程开工令', '2.5 is 工程开工令')
  assert(byCode.get('2.11') === '项目月报', '2.11 is 项目月报')
  assert(byCode.get('2.12') === '项目周报', '2.12 is 项目周报')
  assert(
    catalogState.some((v) => v.volume.id === '5' && v.items.some((i) => i.item.code === '5.1')),
    'gov-IT items enabled in hybrid'
  )

  const dummy21 = path.join(tmp, 'dummy-2.1.txt')
  fs.writeFileSync(dummy21, '占位 开工报审表\n')
  studio.addUpload(project.id, '2.1', dummy21, '2.1_开工报审表.txt')
  studio.setItemStatus(project.id, '2.1', 'confirmed')

  const zipPath = path.join(tmp, 'out.zip')
  let allowedDialogOpened = false
  const exported = await withExportSavePath(
    studio.checkExport(project.id),
    async () => {
      allowedDialogOpened = true
      return zipPath
    },
    (dest) => studio.exportZip(project.id, dest)
  )
  assert(allowedDialogOpened, 'save dialog opens when export is allowed')
  assert(exported && fs.existsSync(exported.path), 'zip exists')

  const zip = new PizZip(fs.readFileSync(zipPath))
  const names = Object.keys(zip.files)
  const joined = names.join('\n')
  assert(names.some((n) => n.endsWith('00_目录与校验报告.md')), 'index markdown in zip')
  assert(joined.includes('2.12_项目周报'), 'weekly folder/file in zip')
  assert(joined.includes('2.11_项目月报'), 'monthly folder/file in zip')
  assert(joined.includes('2.10_施工日志'), 'log folder in zip')
  const logZipDocs = names.filter((n) => n.includes('2.10_施工日志') && n.endsWith('.docx'))
  assert(logZipDocs.length >= 3, 'zip packs one 2.10 file per daily log')
  assert(joined.includes('2.1_开工报审表'), '2.1 zip folder uses 开工报审表')
  assert(!joined.includes('检验批'), 'zip must not use 检验批 folder names')
  assert(joined.includes('1.2_合同'), 'contract folder in zip')
  assert(joined.includes('02_过程分册'), 'volume 2 folder')
  assert(joined.includes('07_竣工验收_政务信息化'), 'gov volume present for hybrid')
  assert(joined.includes('2.7_设备开箱'), 'template item folder uses catalog code')

  const indexFile = names.find((n) => n.endsWith('00_目录与校验报告.md'))!
  const indexText = zip.file(indexFile)!.asText()
  assert(indexText.includes('演示混合验收项目'), 'index contains project name')
  assert(indexText.includes('2.12'), 'index lists weekly report')
  assert(indexText.includes('2.11 项目月报') || indexText.includes('| 2.11 |'), 'index lists monthly report')
  assert(indexText.includes('开工报审表'), 'index lists 2.1 as 开工报审表')
  assert(!indexText.includes('检验批'), 'index must not mention 检验批')

  console.log('M1 verify OK')
  console.log('dataDir', tmp)
  console.log('zip entries', names.length)
  console.log(names.slice(0, 12).join('\n'))
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
