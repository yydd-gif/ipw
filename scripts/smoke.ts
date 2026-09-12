/**
 * Fallback-line smoke: project.json persist, eight-book tree,
 * form fields → python fill_engine, residual {{}} hard-block,
 * print status machine (preview ≠ printed; edit resets print),
 * no-template item is upload-only, important+empty → red error dot.
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { treeFillDot } from '../src/shared/catalog'
import { Studio } from '../src/core/studio'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'acceptance-fallback-'))
const templatesDir = path.join(root, 'templates')
const engine = path.join(root, 'engine', 'fill_engine.py')

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(`ASSERT: ${msg}`)
}

async function main(): Promise<void> {
  execFileSync('python3', [engine, 'make-demo', '--out', templatesDir], { stdio: 'inherit' })
  assert(fs.existsSync(path.join(templatesDir, '2.7_设备开箱检验记录.docx')), 'demo 2.7 template')
  assert(fs.existsSync(path.join(templatesDir, '6.2_竣工验收报告.docx')), 'demo 6.2 template')
  assert(fs.existsSync(path.join(templatesDir, '8.1_总封面.docx')), 'demo 8.1 template')

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
  assert(fs.existsSync(path.join(project.rootDir, 'project.json')), 'persists project.json under data dir')

  const catalog = studio.getCatalogState(project.id)
  assert(catalog.length === 8, 'left tree has eight books')
  const byCode = new Map(catalog.flatMap((v) => v.items).map((e) => [e.item.code, e]))

  const contract = byCode.get('1.2')
  assert(contract, 'can open 1.2 from catalog')
  assert(contract.item.importance === 'important', '1.2 is 重要')
  assert(contract.record.editStatus === 'empty', '1.2 starts empty')
  assert(treeFillDot(contract.item.importance, contract.record.editStatus) === 'error', '重要且空 → 红点')

  const open27 = studio.getItemEditor(project.id, '2.7')
  assert(open27.pane === 'form', 'template item opens form pane, not a fake table')
  assert((open27.item.fields?.length ?? 0) >= 4, '2.7 has form fields')

  const draft = studio.saveItemFields(
    project.id,
    '2.7',
    { device_name: '配电柜', device_model: '' },
    'draft'
  )
  assert(draft.editStatus === 'draft', 'partial form is 草稿 / amber')
  assert(draft.printStatus === 'unprinted', 'draft is unprinted')

  const reopened = studio.getItemEditor(project.id, '2.7')
  assert(reopened.mergedFields.device_name === '配电柜', 'field persists in project.json')
  assert(reopened.record.editStatus === 'draft', 'amber survives reopen')

  const incompleteExport = studio.checkExport(project.id, '2.7')
  assert(!incompleteExport.ok, 'incomplete required fields hard-block export')

  const ghostTpl = path.join(tmp, 'ghost.docx')
  execFileSync('python3', [engine, 'make-demo', '--out', tmp])
  const demo27 = path.join(templatesDir, '2.7_设备开箱检验记录.docx')
  fs.copyFileSync(demo27, ghostTpl)
  const ghostData = path.join(tmp, 'ghost.json')
  fs.writeFileSync(ghostData, JSON.stringify({ project_name: 'X' }), 'utf8')
  const ghostOut = path.join(tmp, 'ghost-filled.docx')
  const ghostPrev = path.join(tmp, 'ghost.html')
  const ghostReport = JSON.parse(
    execFileSync(
      'python3',
      [engine, 'fill', '--template', ghostTpl, '--data', ghostData, '--out', ghostOut, '--preview', ghostPrev],
      { encoding: 'utf8' }
    )
  ) as { residual_keys: string[] }
  assert(ghostReport.residual_keys.includes('device_name'), 'empty/missing keys remain as {{device_name}}')
  assert(fs.readFileSync(ghostOut).toString('utf8').includes('{{device_name}}'), 'filled docx still has mustache')

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
  assert(ready.editStatus === 'complete', 'complete persists as 已齐')

  const filled = studio.fillItem(project.id, '2.7')
  assert(filled.ok, `fill_engine ok: ${filled.message}`)
  assert(filled.filledPath && fs.existsSync(filled.filledPath), 'filled docx exists')
  assert(filled.previewPath && fs.existsSync(filled.previewPath), 'preview html exists')
  assert(filled.residualKeys.length === 0, 'no residual {{}} after full fill')
  const preview = fs.readFileSync(filled.previewPath!, 'utf8')
  assert(preview.includes('配电柜'), 'preview shows form value')

  const pdfDest = path.join(tmp, '2.7-current.pdf')
  const exported = studio.exportItemFile(project.id, '2.7', pdfDest)
  assert(fs.existsSync(exported.path), 'export path exists')
  const pdfHead = fs.readFileSync(exported.path).subarray(0, 5).toString('utf8')
  assert(pdfHead === '%PDF-', `export is PDF, got ${pdfHead}`)

  const afterExport = studio.getItemEditor(project.id, '2.7').record
  assert(afterExport.printStatus !== 'printed', 'export does not mark printed')

  const htmlAfter = studio.writePrintHtml(project.id, '2.7')
  assert(fs.existsSync(htmlAfter), 'print preview writes HTML')
  const stillUnprinted = studio.getItemEditor(project.id, '2.7').record
  assert(stillUnprinted.printStatus === 'unprinted', 'preview does not mark printed')

  const printed = studio.markPrinted(project.id, '2.7')
  assert(printed.printStatus === 'printed', 'real print success → 已打印')
  assert(printed.lastPrintedFingerprint === printed.contentFingerprint, 'print stores fingerprint')

  const afterEdit = studio.saveItemFields(project.id, '2.7', { inspect_result: '改过内容应打回未打印' }, 'complete')
  assert(afterEdit.printStatus === 'unprinted', 'content change resets to unprinted')
  assert(afterEdit.editStatus === 'complete', 'edit keeps 已齐 but print goes gray')

  const uploadPane = studio.getItemEditor(project.id, '1.2')
  assert(uploadPane.pane === 'upload', 'no-template item is upload, not a fake table')
  assert(!uploadPane.item.fields?.length, 'upload pane has no form schema / fake table')
  const dummy = path.join(tmp, 'contract.txt')
  fs.writeFileSync(dummy, '合同扫描件占位\n')
  studio.addUpload(project.id, '1.2', dummy, '合同.pdf.txt')
  const afterUpload = studio.getItemEditor(project.id, '1.2')
  assert(afterUpload.record.uploads.length >= 1, 'upload has files')
  assert(afterUpload.record.editStatus === 'complete', 'upload turns empty into complete')

  const missing = studio.getItemEditor(project.id, '2.1')
  assert(missing.pane === 'upload' && missing.templateMissing, 'no demo template → upload zone only')

  const book = studio.fillVolume(project.id)
  assert(book.filled >= 1, '一键成册 fills available demo templates')

  const missingPy = new Studio({
    dataDir: path.join(tmp, 'nopy'),
    templatesDir,
    pythonBin: '/nonexistent/python-missing',
    enginePath: engine
  })
  missingPy.createProject({
    name: '缺 Python',
    type: 'hybrid',
    owner: 'A',
    supervisor: '',
    contractor: '',
    contract_no: '',
    phase: '',
    doc_no: ''
  })
  const listed = missingPy.listProjects()
  const fail = missingPy.fillItem(listed[0]!.id, '2.7')
  assert(fail.engineMissing || !fail.ok, 'graceful message when python missing')
  assert(fail.message.includes('Python') || fail.message.includes('python'), `mentions python: ${fail.message}`)

  const warn = studio.printWarn(project.id, '2.1')
  assert(warn.incomplete, 'print soft-warns when item is incomplete')

  console.log('Fallback smoke OK')
  console.log('dataDir', tmp)
  console.log('pdf', exported.path)
  console.log('fillVolume', book.message)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
