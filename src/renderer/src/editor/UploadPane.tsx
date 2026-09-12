import { useEffect, useState } from 'react'
import type { FilePreview, ItemEditorState } from '@shared/types'

export default function UploadPane(props: {
  editor: ItemEditorState
  onUpload: () => void
  onReveal: (path: string) => void
}) {
  const [previews, setPreviews] = useState<Record<string, FilePreview>>({})

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const next: Record<string, FilePreview> = {}
      for (const u of props.editor.record.uploads) {
        next[u.id] = await window.studio.previewFile(u.storedPath)
      }
      if (!cancelled) setPreviews(next)
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [props.editor.record.uploads])

  return (
    <div className="upload-pane">
      {props.editor.templateMissing ? (
        <div className="notice">该条目尚无演示模板（待官方 37 套模板导入）。此处只提供上传区，不造假表。</div>
      ) : (
        <div className="notice">无模板条目：仅上传归档，不生成可编辑表格。</div>
      )}
      <div className="actions">
        <button className="btn primary" onClick={props.onUpload}>
          上传文件
        </button>
      </div>
      <ul className="upload-list">
        {props.editor.record.uploads.map((u) => {
          const pv = previews[u.id]
          return (
            <li className="upload-card" key={u.id}>
              <strong>{u.originalName}</strong>
              <div className="actions">
                <button className="btn ghost" onClick={() => props.onReveal(u.storedPath)}>
                  打开所在文件夹
                </button>
              </div>
              {pv?.kind === 'image' && pv.dataUrl ? (
                <img className="upload-preview" src={pv.dataUrl} alt={pv.name} />
              ) : null}
              {pv?.kind === 'pdf' && pv.dataUrl ? (
                <iframe className="upload-preview pdf" title={pv.name} src={pv.dataUrl} />
              ) : null}
              {pv?.kind === 'text' ? <pre className="upload-text">{pv.text}</pre> : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
