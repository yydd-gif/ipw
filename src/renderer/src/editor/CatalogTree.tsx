import {
  EDIT_STATUS_LABELS,
  IMPORTANCE_LABELS,
  PRINT_STATUS_LABELS,
  type CatalogVolumeState,
  type EditStatus,
  type PrintStatus
} from '@shared/types'
import { treeAlertDot } from '@shared/catalog'

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
            const edit = entry.instance.editStatus
            const print = entry.instance.printStatus
            const alert = treeAlertDot(entry.item.importance, edit)
            return (
              <button
                type="button"
                key={entry.item.code}
                className={`tree-item ${props.selectedCode === entry.item.code ? 'sel' : ''}`}
                onClick={() => props.onSelect(entry.item.code)}
              >
                <span className={`status-dot ${alert ? 'alert' : edit}`} title={EDIT_STATUS_LABELS[edit as EditStatus]} />
                <span className="code">{entry.item.code}</span>
                <span className="tree-title">
                  {entry.item.title}
                  <span className={`imp imp-${entry.item.importance}`}>{IMPORTANCE_LABELS[entry.item.importance]}</span>
                </span>
                <span
                  className={`print-ico ${print}`}
                  title={PRINT_STATUS_LABELS[print as PrintStatus]}
                  aria-label={PRINT_STATUS_LABELS[print as PrintStatus]}
                >
                  {print === 'printed' ? '🖨✓' : '🖨'}
                </span>
              </button>
            )
          })}
        </div>
      ))}
    </div>
  )
}
