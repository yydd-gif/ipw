import {
  FILL_STATUS_LABELS,
  IMPORTANCE_LABELS,
  PRINT_STATUS_LABELS,
  type CatalogVolumeState,
  type FillStatus,
  type PrintStatus
} from '@shared/types'
import { treeFillDot } from '@shared/catalog'

function PrintIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path d="M4.2 1.5h7.6v3.2H4.2V1.5zm-2.4 4h12.4v5.2h-2.2V8.2H4.2v2.5H1.8V5.5zm3.2 3.4h6.4v5.1H5V8.9z" />
    </svg>
  )
}

export default function CatalogTree(props: {
  catalog: CatalogVolumeState[]
  selectedCode: string | null
  onSelect: (code: string) => void
}) {
  return (
    <div className="editor-tree">
      {props.catalog.map((vol) => (
        <div className="volume" key={vol.volume.id}>
          <div className="volume-h">
            <span className="vol-index">{vol.volume.code}</span>
            {vol.volume.title}
            <span className="muted vol-count">{vol.items.length}</span>
          </div>
          {vol.items.map((entry) => {
            const fill = entry.record.editStatus
            const print = entry.record.printStatus
            const dot = treeFillDot(entry.item.importance, fill)
            return (
              <button
                type="button"
                key={entry.item.code}
                className={`tree-item ${props.selectedCode === entry.item.code ? 'sel' : ''}`}
                onClick={() => props.onSelect(entry.item.code)}
                data-code={entry.item.code}
                data-fill={fill}
                data-print={print}
                data-dot={dot}
              >
                <span className="tree-title">
                  {entry.item.code} {entry.item.title}
                </span>
                <span className={`imp imp-${entry.item.importance}`}>
                  {IMPORTANCE_LABELS[entry.item.importance]}
                </span>
                <span
                  className={`status-dot ${dot}`}
                  title={FILL_STATUS_LABELS[fill as FillStatus]}
                />
                <span
                  className={`print-ico ${print}`}
                  title={PRINT_STATUS_LABELS[print as PrintStatus]}
                  aria-label={PRINT_STATUS_LABELS[print as PrintStatus]}
                >
                  <PrintIcon />
                </span>
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
