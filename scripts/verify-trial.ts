/**
 * Trial DoD (黑寡妇 must-pass / 绿巨人 smoke):
 * left catalog + right table or upload; draft yellow / ready green persist;
 * current-item PDF; preview does not mark printed; real print success does;
 * edit resets unprinted; important+empty red dot.
 * Zip / weekly-monthly / book-6 full split are next round — not required here.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { treeAlertDot } from '../src/shared/catalog'
import { Studio } from '../src/core/studio'
import type { TableDocument } from '../src/shared/types'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'acceptance-studio-trial-'))
const templatesDir = path.join(root, 'templates')

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(`ASSERT: ${msg}`)
}

function cloneDoc(doc: TableDocument): TableDocument {
  return JSON.parse(JSON.stringify(doc)) as TableDocument
}

async function main(): Promise<void> {
  if (!fs.existsSync(path.join(templatesDir, '2.7_设备开箱检验记录.docx'))) {
    throw new Error('templates missing; run npm run generate:templates')
  }

  const studio = new Studio({ dataDir: tmp, templatesDir })
  await studio.init()

  const project = studio.createProject({
    name: '试用编辑项目',
    type: 'hybrid',
    owner: '建设单位',
    supervisor: '监理',
    contractor: '施工',
    contract_no: 'HT-TRIAL-1',
    phase: '验收',
    doc_no: 'YS-T1'
  })

  const catalog = studio.getCatalogState(project.id)
  assert(catalog.length === 8, 'left tree has eight books')
  const byCode = new Map(catalog.flatMap((v) => v.items).map((e) => [e.item.code, e]))

  const contract = byCode.get('1.2')
  assert(contract, 'can open 1.2 from catalog')
  assert(contract.item.importance === 'important', '1.2 is 重要')
  assert(contract.instance.editStatus === 'empty', '1.2 starts empty')
  assert(treeAlertDot(contract.item.importance, contract.instance.editStatus), '重要且空 → 红点')

  const open27 = studio.getEditorDocument(project.id, '2.7')
  assert(open27.pane === 'doc', 'template item opens table/doc pane')
  assert((open27.document?.tables[0]?.rows.length ?? 0) >= 2, 'parsed table rows')
  const doc = cloneDoc(open27.document!)
  const table = doc.tables[0]!
  const beforeRows = table.rows.length
  table.rows[0]![0]!.text = '试用改格子'
  table.rows.push(table.rows[0]!.map((c) => ({ ...c, text: '增行' })))
  assert(table.rows.length === beforeRows + 1, 'can add row')
  table.rows.splice(table.rows.length - 1, 1)
  assert(table.rows.length === beforeRows, 'can remove row')
  table.rows.push(table.rows[0]!.map((c) => ({ ...c, text: '增行保留' })))

  const draft = studio.saveEditorDocument(project.id, '2.7', doc, 'draft')
  assert(draft.editStatus === 'draft', 'draft persists as 草稿')
  assert(draft.printStatus === 'unprinted', 'draft is unprinted')

  const reopened = studio.getEditorDocument(project.id, '2.7')
  assert(reopened.document?.tables[0]?.rows[0]?.[0]?.text === '试用改格子', 'edited cell saved')
  assert(reopened.instance.editStatus === 'draft', 'yellow/draft survives reopen')
  assert((reopened.document?.tables[0]?.rows.length ?? 0) === beforeRows + 1, 'added row saved')

  const ready = studio.saveEditorDocument(project.id, '2.7', reopened.document!, 'ready')
  assert(ready.editStatus === 'ready', 'ready persists as 已齐')
  const readyAgain = studio.getEditorDocument(project.id, '2.7')
  assert(readyAgain.instance.editStatus === 'ready', 'green/已齐 survives reopen')

  const pdfDest = path.join(tmp, '2.7-current.pdf')
  const exported = studio.exportItemPdfFile(project.id, '2.7', pdfDest, reopened.document)
  assert(fs.existsSync(exported.path), 'current-item PDF path exists')
  const pdfHead = fs.readFileSync(exported.path).subarray(0, 5).toString('utf8')
  assert(pdfHead === '%PDF-', `current-item export is PDF, got ${pdfHead}`)
  const previewHtml = fs.readFileSync(exported.htmlPath!, 'utf8')
  assert(previewHtml.includes('试用改格子'), 'print preview HTML shows edited cell')

  const afterExport = studio.getEditorDocument(project.id, '2.7').instance
  assert(afterExport.printStatus !== 'printed', 'PDF export does not mark printed')

  const printed = studio.markItemPrinted(project.id, '2.7')
  assert(printed.printStatus === 'printed', 'real print success → 已打印')
  assert(printed.lastPrintedFingerprint === printed.contentFingerprint, 'print stores fingerprint')

  const htmlAfterPrint = studio.writeItemPrintHtml(project.id, '2.7', reopened.document)
  assert(fs.existsSync(htmlAfterPrint), 'preview can open HTML')
  const stillPrinted = studio.getEditorDocument(project.id, '2.7').instance
  assert(stillPrinted.printStatus === 'printed', 'preview does not mark / unmark printed')

  const edited = cloneDoc(reopened.document!)
  edited.tables[0]!.rows[0]![0]!.text = '改过内容应打回未打印'
  const afterEdit = studio.saveEditorDocument(project.id, '2.7', edited, 'ready')
  assert(afterEdit.printStatus === 'unprinted', 'content change resets to unprinted')
  assert(afterEdit.editStatus === 'ready', 'edit keeps 已齐 but print goes gray')

  const uploadPane = studio.getEditorDocument(project.id, '1.2')
  assert(uploadPane.pane === 'upload', 'no-template item is upload, not a fake table')
  assert(uploadPane.document === null, 'upload pane has no fake table')
  const dummy = path.join(tmp, 'contract.txt')
  fs.writeFileSync(dummy, '合同扫描件占位\n')
  studio.addUpload(project.id, '1.2', dummy, '合同.pdf.txt')
  const afterUpload = studio.getEditorDocument(project.id, '1.2')
  assert(afterUpload.uploads.length >= 1, 'upload preview has files')
  assert(afterUpload.instance.editStatus === 'draft', 'upload turns empty into draft')

  const missing = studio.getEditorDocument(project.id, '2.1')
  assert(missing.pane === 'upload' && missing.templateMissing, 'no template → 待补模版 upload')

  console.log('Trial verify OK')
  console.log('dataDir', tmp)
  console.log('pdf', exported.path)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
