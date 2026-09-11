import type { CatalogInstance, PrintStatus } from '@shared/types'

export default function BottomBar(props: {
  instance: CatalogInstance | null
  busy: boolean
  onExportPdf: () => void
  onPreview: () => void
  onPrint: () => void
}) {
  const print: PrintStatus = props.instance?.printStatus ?? 'unprinted'
  return (
    <footer className="editor-bottom">
      <div className={`print-state ${print}`}>{print === 'printed' ? '已打印' : '未打印'}</div>
      <div className="bottom-btns">
        <button className="btn" disabled={props.busy} onClick={props.onExportPdf}>
          导出 PDF
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
