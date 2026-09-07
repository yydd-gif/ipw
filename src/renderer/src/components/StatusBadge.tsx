import { STATUS_LABELS, type ItemStatus } from '@shared/types'

const LABELS: Record<ItemStatus, string> = STATUS_LABELS

export function StatusBadge({ status }: { status: ItemStatus }) {
  return <span className={`badge ${status}`}>{LABELS[status]}</span>
}

export function ProduceBadge({ type }: { type: 'upload' | 'template' | 'derived' }) {
  const map = { upload: '上传', template: '模板填报', derived: '由日志派生' }
  return <span className="badge empty">{map[type]}</span>
}
