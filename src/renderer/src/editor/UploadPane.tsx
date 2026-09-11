import { useEffect, useState } from 'react'
import type { EditorDocumentState, FilePreview } from '@shared/types'

export default function UploadPane(props: {
  editor: EditorDocumentState
  onUpload: () => void
  onReveal: (path: string) => void
}) {
  const [previews, setPreviews] = useState<Record<string, FilePreview>>({})

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const next: Record<string, FilePreview> = {}
      for (const u of props.editor.uploads) {
        try {
          next[u.id] = await window.studio.previewUpload(u.stored_path)
        } catch {
          next[u.id] = { kind: 'other', name: u.original_name }
        }
      }
      if (!cancelled) setPreviews(next)
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [props.editor.uploads])

  return (
    <div className="upload-pane">
      {props.editor.templateMissing ? (
        <div className="notice">待补模版。当前没有可打开的 Word 表格，请上传原件 / 扫描件，不要使用空表充数。</div>
      ) : (
        <p className="muted">本条目以上传归档为主，不生成假表格。</p>
      )}
      {props.editor.message ? <p className="muted">{props.editor.message}</p> : null}

      <div className="actions">
        <button className="btn primary" onClick={props.onUpload}>
          上传资料
        </button>
      </div>

      {props.editor.uploads.length === 0 ? (
        <p className="muted" style={{ marginTop: 16 }}>
          尚未归档文件。
        </p>
      ) : (
        <ul className="upload-list">
          {props.editor.uploads.map((u) => {
            const preview = previews[u.id]
            return (
              <li key={u.id} className="upload-card">
                <div className="row">
                  <strong>{u.original_name}</strong>
                  <button className="btn ghost" onClick={() => props.onReveal(u.stored_path)}>
                    打开所在文件夹
                  </button>
                </div>
                {preview?.kind === 'image' && preview.dataUrl ? (
                  <img className="upload-preview" src={preview.dataUrl} alt={u.original_name} />
                ) : null}
                {preview?.kind === 'pdf' && preview.dataUrl ? (
                  <iframe className="upload-preview pdf" title={u.original_name} src={preview.dataUrl} />
                ) : null}
                {preview?.kind === 'text' && preview.text ? (
                  <pre className="upload-text">{preview.text.slice(0, 4000)}</pre>
                ) : null}
                {preview?.kind === 'other' ? <p className="muted">该类型试用版仅归档，请用系统程序打开。</p> : null}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
