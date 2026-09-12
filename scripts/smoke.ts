/**
 * 黑寡妇过关 / 绿巨人冒烟（备胎首版）。
 * npm test 必须按下面 7 条全过。下一轮（OnlyOffice 真内嵌 / Win 便携包 / dsh）不在本脚本。
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { treeFillDot } from '../src/shared/catalog'
import { ACTIVE_EDITOR_KERNEL, FORM_MODE_BANNER } from '../src/shared/types'
import { Studio } from '../src/core/studio'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'acceptance-fallback-'))
const templatesDir = path.join(root, 'templates')
const engine = path.join(root, 'engine', 'fill_engine.py')

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(`ASSERT: ${msg}`)
}

function pass(id: number, msg: string): void {
  console.log(`PASS ${id}  ${msg}`)
}

async function main(): Promise<void> {
  execFileSync('python3', [engine, 'make-demo', '--out', templatesDir], { stdio: 'inherit' })

  const studio = new Studio({ dataDir: tmp, templatesDir, enginePath: engine, pythonBin: 'python3' })
  const project = studio.createProject({
    name: '备胎线演示项目',
    type: 'hybrid',
    owner: '建设单位',
    supervisor: '监理',
    contractor: '施工',
    contract_no: 'HT-FB-1',
    phase: '验收',
    doc_no: 'YS-F1'
  })
  const projectJson = path.join(project.rootDir, 'project.json')
  assert(fs.existsSync(projectJson), 'project.json created')

  // --- 1 色点与打印标拆开，空和草稿分得开 ---
  const catalog = studio.getCatalogState(project.id)
  assert(catalog.length === 8, 'eight volumes')
  const byCode = new Map(catalog.flatMap((v) => v.items).map((e) => [e.item.code, e]))

  const emptyNormal = byCode.get('1.1')
  assert(emptyNormal, '1.1 exists')
  assert(emptyNormal.record.editStatus === 'empty', '1.1 starts empty')
  assert(treeFillDot(emptyNormal.item.importance, 'empty') === 'empty', '普通空 → 灰')
  assert(emptyNormal.record.printStatus === 'unprinted', 'print icon is separate and starts 未打印')

  const importantEmpty = byCode.get('1.2')
  assert(importantEmpty, '1.2 exists')
  assert(treeFillDot(importantEmpty.item.importance, importantEmpty.record.editStatus) === 'error', '重要且空 → 红')

  const draftRec = studio.saveItemFields(project.id, '8.1', { volume_title: '验收资料' }, 'draft')
  assert(draftRec.editStatus === 'draft', '8.1 partial → 草稿')
  assert(treeFillDot('normal', 'draft') === 'draft', '草稿 → 琥珀')
  assert(treeFillDot('normal', 'empty') !== treeFillDot('normal', 'draft'), '空灰 ≠ 琥珀草稿')
  assert(draftRec.printStatus === 'unprinted', 'draft does not light print icon')

  const ready = studio.saveItemFields(
    project.id,
    '2.7',
    {
      project_name: '备胎线演示项目',
      owner: '建设单位',
      device_name: '配电柜',
      device_model: 'XL-21',
      inspect_date: '2026-09-12',
      inspect_result: '外观完好，资料齐全'
    },
    'complete'
  )
  assert(ready.editStatus === 'complete', '2.7 已齐')
  assert(treeFillDot('important', 'complete') === 'complete', '已齐 → 绿')
  pass(1, '色点灰/琥珀/绿/红与打印标拆开，空和草稿分得开')

  // --- 2 上表单写 project.json，下只读预览引擎稿，顶条不是内嵌编辑 ---
  assert(FORM_MODE_BANNER.includes('不是内嵌编辑'), 'banner copy locked')
  assert(ACTIVE_EDITOR_KERNEL === 'form-preview', 'kernel is form-preview, not onlyoffice')
  const persisted = JSON.parse(fs.readFileSync(projectJson, 'utf8')) as {
    fields: Record<string, string>
    items: Record<string, { overrides: Record<string, string> }>
  }
  assert(persisted.fields.project_name === '备胎线演示项目', 'form writes project.json fields')
  assert(persisted.items['2.7']?.overrides.device_name === '配电柜', 'per-doc overrides in project.json')

  const formPane = studio.getItemEditor(project.id, '2.7')
  assert(formPane.pane === 'form', 'template item is form, not a fake WYSIWYG table')
  const filled = studio.fillItem(project.id, '2.7')
  assert(filled.ok && filled.filledPath && fs.existsSync(filled.filledPath), 'engine wrote filled docx')
  assert(filled.previewPath && fs.existsSync(filled.previewPath), 'engine wrote read-only preview')
  assert(fs.readFileSync(filled.previewPath, 'utf8').includes('配电柜'), 'preview shows form value')
  pass(2, '表单写入 project.json，只读预览引擎 docx，顶条「不是内嵌编辑」')

  // --- 3 没模板走上传区 ---
  const upload = studio.getItemEditor(project.id, '1.2')
  assert(upload.pane === 'upload' && !upload.item.fields?.length, '1.2 upload-only, no fake table')
  const dummy = path.join(tmp, 'contract.txt')
  fs.writeFileSync(dummy, '合同扫描件占位\n')
  studio.addUpload(project.id, '1.2', dummy, '合同.pdf.txt')
  const missingTpl = studio.getItemEditor(project.id, '2.1')
  assert(missingTpl.pane === 'upload' && missingTpl.templateMissing, 'no demo template → upload zone')
  pass(3, '没模板走上传区')

  // --- 4 导出残留硬拦；打印缺字段软提示可继续 ---
  const incomplete = studio.saveItemFields(project.id, '6.2', { summary: '未齐' }, 'draft')
  assert(incomplete.editStatus === 'draft', '6.2 still draft')
  const blockedReq = studio.checkExport(project.id, '6.2')
  assert(!blockedReq.ok, 'missing required fields hard-block export')

  fs.appendFileSync(filled.filledPath!, '{{ghost_key}}')
  const blockedResidual = studio.checkExport(project.id, '2.7')
  assert(!blockedResidual.ok, 'residual {{}} hard-blocks export')
  assert(
    blockedResidual.residualKeys.includes('ghost_key') ||
      blockedResidual.blockers.some((b) => b.reason.includes('ghost_key')),
    'export blocker names leftover {{ghost_key}}'
  )
  let threw = false
  try {
    studio.exportItemFile(project.id, '2.7', path.join(tmp, 'should-not.pdf'))
  } catch (err) {
    threw = String(err).includes('ghost_key') || String(err).includes('残留')
  }
  assert(threw, 'exportItemFile throws on residual {{}}')
  studio.fillItem(project.id, '2.7')

  const warn = studio.printWarn(project.id, '6.2')
  assert(warn.incomplete, 'print soft-warns when fields missing')
  const printedAnyway = studio.markPrinted(project.id, '6.2')
  assert(printedAnyway.printStatus === 'printed', 'soft-warn still allows continue → 已打印')
  pass(4, '导出残留硬拦；打印缺字段软提示可继续')

  // --- 5 真打成功才亮已打印，改过打回未打印 ---
  const again = studio.fillItem(project.id, '2.7')
  const exported = studio.exportItemFile(project.id, '2.7', path.join(tmp, '2.7-current.pdf'))
  assert(fs.readFileSync(exported.path).subarray(0, 5).toString('utf8') === '%PDF-', 'export PDF')
  assert(studio.getItemEditor(project.id, '2.7').record.printStatus !== 'printed', 'export ≠ printed')
  studio.writePrintHtml(project.id, '2.7')
  assert(studio.getItemEditor(project.id, '2.7').record.printStatus !== 'printed', 'preview ≠ printed')
  const printed = studio.markPrinted(project.id, '2.7')
  assert(printed.printStatus === 'printed', 'real print success → 已打印')
  assert(printed.lastPrintedFingerprint === printed.contentFingerprint, 'print stores fingerprint')
  const afterEdit = studio.saveItemFields(project.id, '2.7', { inspect_result: '改过内容应打回未打印' }, 'complete')
  assert(afterEdit.printStatus === 'unprinted', 'content change resets print icon')
  assert(afterEdit.editStatus === 'complete', 'fill stays 绿, print goes 灰')
  pass(5, '真打成功才亮已打印；改内容打回未打印')

  // --- 6 一键成册离线调 Python ---
  const book = studio.fillVolume(project.id)
  assert(book.filled >= 1, `fillVolume used python engine, filled ${book.filled}`)
  const nopy = new Studio({
    dataDir: path.join(tmp, 'nopy'),
    templatesDir,
    pythonBin: '/nonexistent/python-missing',
    enginePath: engine
  })
  const orphan = nopy.createProject({
    name: '缺 Python',
    type: 'hybrid',
    owner: 'A',
    supervisor: '',
    contractor: '',
    contract_no: '',
    phase: '',
    doc_no: ''
  })
  const fail = nopy.fillItem(orphan.id, '2.7')
  assert(!fail.ok && (fail.engineMissing || /python/i.test(fail.message)), 'offline python missing is graceful')
  pass(6, '一键成册离线调 Python')

  // --- 7 不宣称所见即所得 ---
  const kernel: string = ACTIVE_EDITOR_KERNEL
  assert(kernel === 'form-preview', 'v1 kernel is form-preview, not onlyoffice')
  assert(!FORM_MODE_BANNER.includes('所见即所得'), 'banner does not claim WYSIWYG')
  assert(FORM_MODE_BANNER.includes('不是内嵌编辑'), 'banner states 不是内嵌编辑')
  pass(7, '不宣称所见即所得')

  console.log('Fallback DoD smoke OK')
  console.log('dataDir', tmp)
  console.log('fillVolume', book.message)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
