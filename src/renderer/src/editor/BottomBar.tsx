import type { CatalogInstance, PrintStatus } from '@shared/types'

export default function BottomBar(props: {
  instance: CatalogInstance | null
  busy: boolean
  onExportPdf: () => void
  onPreview: () => void
  onPrint: () => void
}) {
  const print: PrintStatus = props.instance?.printStatus ?? 'unprinted'
  const fp = props.instance?.contentFingerprint
  return (
    <footer className="editor-bottom">
      <div className="muted">
        打印状态：{print === 'printed' ? '已打印' : '未打印'}
        {fp ? ` · 指纹 ${fp.slice(0, 8)}` : ''}
        {props.instance?.lastPrintedAt ? ` · 上次打印 ${props.instance.lastPrintedAt.slice(0, 19).replace('T', ' ')}` : ''}
      </div>
      <div className="actions" style={{ marginTop: 0 }}>
        <button className="btn" disabled={props.busy} onClick={props.onExportPdf}>
          导出当前条目 PDF
        </button>
        <button className="btn" disabled={props.busy} onClick={props.onPreview}>
          打印预览
        </button>
        <button className="btn primary" disabled={props.busy} onClick={props.onPrint}>
          打印
        </button>
      </div>
    </footer>
  )
}
