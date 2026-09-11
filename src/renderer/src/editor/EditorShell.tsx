import { useEffect, useMemo, useState } from 'react'
import type {
  CatalogVolumeState,
  EditorDocumentState,
  Project,
  TableDocument
} from '@shared/types'
import { EDIT_STATUS_LABELS, IMPORTANCE_LABELS, PRODUCE_TYPE_LABELS } from '@shared/types'
import CatalogTree from './CatalogTree'
import DocEditorPane from './DocEditorPane'
import UploadPane from './UploadPane'
import BottomBar from './BottomBar'

export default function EditorShell(props: {
  project: Project
  catalog: CatalogVolumeState[]
  onRefresh: () => Promise<void> | void
  notify: (msg: string) => void
}) {
  const [sel, setSel] = useState<string | null>(null)
  const [editor, setEditor] = useState<EditorDocumentState | null>(null)
  const [draft, setDraft] = useState<TableDocument | null>(null)
  const [busy, setBusy] = useState(false)

  const selectedCode = sel ?? props.catalog[0]?.items[0]?.item.code ?? null
  const stamp = useMemo(() => {
    for (const vol of props.catalog) {
      const found = vol.items.find((i) => i.item.code === selectedCode)
      if (found) return `${found.instance.updated_at}|${found.uploads.length}|${found.instance.printStatus}`
    }
    return ''
  }, [props.catalog, selectedCode])

  useEffect(() => {
    if (!selectedCode) {
      setEditor(null)
      setDraft(null)
      return
    }
    let cancelled = false
    void window.studio
      .getEditorDocument(props.project.id, selectedCode)
      .then((doc) => {
        if (cancelled) return
        setEditor(doc)
        setDraft(doc.document ? (JSON.parse(JSON.stringify(doc.document)) as TableDocument) : null)
      })
      .catch((err: unknown) => {
        props.notify(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [props.project.id, selectedCode, stamp])

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    try {
      const result = await fn()
      if (ok) props.notify(ok)
      await props.onRefresh()
      return result
    } catch (e) {
      props.notify(e instanceof Error ? e.message : String(e))
      return undefined
    } finally {
      setBusy(false)
    }
  }

  const currentDoc = draft
  const itemCode = editor?.item.code

  return (
    <div className="editor-shell">
      <aside className="editor-left card">
        <CatalogTree catalog={props.catalog} selectedCode={selectedCode} onSelect={setSel} />
      </aside>
      <section className="editor-right">
        <div className="card editor-pane">
          {editor ? (
            <>
              <div className="editor-head">
                <div>
                  <h3 className="sec">
                    {editor.item.code} {editor.item.title}
                  </h3>
                  <div className="row">
                    <span className="badge empty">{PRODUCE_TYPE_LABELS[editor.item.produceType]}</span>
                    <span
                      className={`badge ${editor.instance.editStatus === 'ready' ? 'confirmed' : editor.instance.editStatus}`}
                    >
                      {EDIT_STATUS_LABELS[editor.instance.editStatus]}
                    </span>
                    <span className={`imp imp-${editor.item.importance}`}>
                      {IMPORTANCE_LABELS[editor.item.importance]}
                    </span>
                    {editor.item.required ? <span className="badge req">必填</span> : <span className="badge opt">选填</span>}
                  </div>
                </div>
                <div className="actions" style={{ marginTop: 0 }}>
                  {editor.pane === 'doc' && currentDoc ? (
                    <>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () =>
                              window.studio.saveEditorDocument(
                                props.project.id,
                                editor.item.code,
                                currentDoc,
                                'draft'
                              ),
                            '已保存草稿'
                          )
                        }
                      >
                        保存草稿
                      </button>
                      <button
                        className="btn good"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () =>
                              window.studio.saveEditorDocument(
                                props.project.id,
                                editor.item.code,
                                currentDoc,
                                'ready'
                              ),
                            '已标记就绪'
                          )
                        }
                      >
                        标记就绪
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () => window.studio.setItemStatus(props.project.id, editor.item.code, 'draft'),
                            '已保存草稿'
                          )
                        }
                      >
                        保存草稿
                      </button>
                      <button
                        className="btn good"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () => window.studio.setItemStatus(props.project.id, editor.item.code, 'confirmed'),
                            '已标记就绪'
                          )
                        }
                      >
                        标记就绪
                      </button>
                    </>
                  )}
                </div>
              </div>

              {editor.pane === 'doc' && currentDoc ? (
                <DocEditorPane document={currentDoc} onChange={setDraft} />
              ) : (
                <UploadPane
                  editor={editor}
                  onUpload={() =>
                    run(() => window.studio.uploadFiles(props.project.id, editor.item.code), '已归档上传文件')
                  }
                  onReveal={(p) => window.studio.revealInFolder(p)}
                />
              )}
            </>
          ) : (
            <p className="muted">选择左侧目录条目开始编辑。</p>
          )}
        </div>
        <BottomBar
          instance={editor?.instance ?? null}
          busy={busy || !itemCode}
          onExportPdf={() => {
            if (!itemCode) return
            void run(async () => {
              const result = await window.studio.exportItemPdf(props.project.id, itemCode, currentDoc)
              if (result) props.notify(`已导出：${result.path}`)
              else props.notify('已取消导出')
            })
          }}
          onPreview={() => {
            if (!itemCode) return
            void run(
              () => window.studio.printPreview(props.project.id, itemCode, currentDoc),
              '已打开打印预览（预览不会标记已打印）'
            )
          }}
          onPrint={() => {
            if (!itemCode) return
            void run(async () => {
              const result = await window.studio.printItem(props.project.id, itemCode, currentDoc)
              if (!result.printed) throw new Error('打印未完成或已取消')
            }, '打印成功，已标记已打印')
          }}
        />
      </section>
    </div>
  )
}
