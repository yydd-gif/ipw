import { useEffect, useMemo, useState } from 'react'
import type { CatalogVolumeState, ItemEditorState, Project } from '@shared/types'
import { FILL_STATUS_LABELS, IMPORTANCE_LABELS, PRODUCE_TYPE_LABELS } from '@shared/types'
import CatalogTree from './CatalogTree'
import EditorHost from './EditorHost'
import BottomBar from './BottomBar'
import AiRibbon from './AiRibbon'

export default function EditorShell(props: {
  project: Project
  catalog: CatalogVolumeState[]
  onRefresh: () => Promise<void> | void
  notify: (msg: string) => void
}) {
  const [sel, setSel] = useState<string | null>(null)
  const [editor, setEditor] = useState<ItemEditorState | null>(null)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [previewHtml, setPreviewHtml] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const selectedCode = sel ?? props.catalog[0]?.items[0]?.item.code ?? null
  const stamp = useMemo(() => {
    for (const vol of props.catalog) {
      const found = vol.items.find((i) => i.item.code === selectedCode)
      if (found) {
        return `${found.record.updatedAt}|${found.record.uploads.length}|${found.record.printStatus}|${found.record.editStatus}`
      }
    }
    return ''
  }, [props.catalog, selectedCode])

  useEffect(() => {
    if (!selectedCode) {
      setEditor(null)
      setDraft({})
      setPreviewHtml(null)
      return
    }
    let cancelled = false
    void window.studio
      .getItemEditor(props.project.id, selectedCode)
      .then(async (doc) => {
        if (cancelled) return
        setEditor(doc)
        setDraft({ ...doc.mergedFields })
        if (doc.record.previewPath) {
          const pv = await window.studio.previewFile(doc.record.previewPath)
          if (!cancelled && pv.text) setPreviewHtml(pv.text)
          else if (!cancelled && pv.kind === 'other') setPreviewHtml(null)
        } else {
          setPreviewHtml(null)
        }
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

  const itemCode = editor?.item.code

  const loadPreview = async (path?: string | null) => {
    if (!path) return
    const pv = await window.studio.previewFile(path)
    if (pv.text) setPreviewHtml(pv.text)
  }

  return (
    <div className="editor-shell">
      <aside className="editor-left card">
        <CatalogTree catalog={props.catalog} selectedCode={selectedCode} onSelect={setSel} />
      </aside>
      <section className="editor-right">
        <div className="editor-toolbar">
          <AiRibbon />
          <button
            className="btn good"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const result = await window.studio.fillVolume(props.project.id)
                props.notify(result.message)
              })
            }
          >
            一键成册
          </button>
        </div>
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
                    <span className={`badge ${editor.record.editStatus}`}>
                      {FILL_STATUS_LABELS[editor.record.editStatus]}
                    </span>
                    <span className={`imp imp-${editor.item.importance}`}>
                      {IMPORTANCE_LABELS[editor.item.importance]}
                    </span>
                    {editor.item.required ? (
                      <span className="badge req">必填</span>
                    ) : (
                      <span className="badge opt">选填</span>
                    )}
                  </div>
                </div>
                <div className="actions" style={{ marginTop: 0 }}>
                  {editor.pane === 'form' ? (
                    <>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          run(
                            () => window.studio.saveItemFields(props.project.id, editor.item.code, draft, 'draft'),
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
                            () => window.studio.saveItemFields(props.project.id, editor.item.code, draft, 'complete'),
                            '已标记已齐'
                          )
                        }
                      >
                        标记已齐
                      </button>
                      <button
                        className="btn"
                        disabled={busy}
                        onClick={() =>
                          run(async () => {
                            await window.studio.saveItemFields(props.project.id, editor.item.code, draft, 'draft')
                            const filled = await window.studio.fillItem(props.project.id, editor.item.code)
                            await loadPreview(filled.previewPath)
                            if (filled.engineMissing) throw new Error(filled.message)
                            return filled
                          }, '已生成预览')
                        }
                      >
                        生成预览
                      </button>
                    </>
                  ) : null}
                </div>
              </div>
              {editor.engineMessage ? <div className="notice">{editor.engineMessage}</div> : null}
              <EditorHost
                editor={editor}
                draft={draft}
                previewHtml={previewHtml}
                onDraft={setDraft}
                onUpload={() =>
                  void run(() => window.studio.uploadFiles(props.project.id, editor.item.code), '已归档上传文件')
                }
                onReveal={(p) => void window.studio.revealInFolder(p)}
              />
            </>
          ) : (
            <p className="muted">选择左侧目录条目开始填报。</p>
          )}
        </div>
        <BottomBar
          record={editor?.record ?? null}
          busy={busy || !itemCode}
          onExport={() => {
            if (!itemCode) return
            void run(async () => {
              if (editor?.pane === 'form') {
                await window.studio.saveItemFields(props.project.id, itemCode, draft, 'draft')
              }
              const check = await window.studio.checkExport(props.project.id, itemCode)
              if (!check.ok) throw new Error(check.blockers.map((b) => b.reason).join('；'))
              const result = await window.studio.exportItem(props.project.id, itemCode)
              if (result) props.notify(result.fallbackNote ? `${result.path}（${result.fallbackNote}）` : `已导出：${result.path}`)
              else props.notify('已取消导出')
            })
          }}
          onPreview={() => {
            if (!itemCode) return
            void window.studio
              .printPreview(props.project.id, itemCode)
              .then(() => props.notify('已打开打印预览（预览不算已打印）'))
              .catch((e: unknown) => props.notify(e instanceof Error ? e.message : String(e)))
          }}
          onPrint={() => {
            if (!itemCode) return
            void run(async () => {
              const warn = await window.studio.printWarn(props.project.id, itemCode)
              if (warn.incomplete) {
                const go = window.confirm(`${warn.message}\n\n仍要继续打印？`)
                if (!go) return { printed: false }
              }
              const result = await window.studio.printItem(props.project.id, itemCode)
              if (!result.printed) throw new Error(result.reason || '打印未完成或已取消')
            }, '打印成功，已标记已打印')
          }}
        />
      </section>
    </div>
  )
}
