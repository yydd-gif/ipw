import type { ItemRecord, PrintStatus } from '@shared/types'

export default function BottomBar(props: {
  record: ItemRecord | null
  busy: boolean
  onExport: () => void
  onPreview: () => void
  onPrint: () => void
}) {
  const print: PrintStatus = props.record?.printStatus ?? 'unprinted'
  return (
    <footer className="editor-bottom">
      <div className={`print-state ${print}`}>{print === 'printed' ? '已打印' : '未打印'}</div>
      <div className="bottom-btns">
        <button className="btn" disabled={props.busy} onClick={props.onExport}>
          导出
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
