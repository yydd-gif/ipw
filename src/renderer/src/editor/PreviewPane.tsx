import type { ItemEditorState } from '@shared/types'

export default function PreviewPane(props: { editor: ItemEditorState; previewHtml: string | null }) {
  const residual = props.editor.record.residualKeys
  return (
    <div className="preview-pane">
      <div className="preview-head">只读预览 · 填充结果（预览不等于已打印）</div>
      {props.editor.record.fillError ? (
        <div className="notice">{props.editor.record.fillError}</div>
      ) : null}
      {residual.length ? (
        <div className="notice danger">残留 {residual.map((k) => `{{${k}}}`).join('、')}，导出将被硬阻断。</div>
      ) : null}
      {props.previewHtml ? (
        <iframe className="preview-frame" title="文档预览" srcDoc={props.previewHtml} />
      ) : (
        <p className="muted">保存表单后点「生成预览 / 成册」，预览区显示 fill_engine 产出的只读稿。</p>
      )}
    </div>
  )
}
