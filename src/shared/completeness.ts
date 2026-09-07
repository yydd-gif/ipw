import type { CatalogItemState, ExportBlocker, ExportCheck, ItemStatus, ProjectType } from './types'
import { isRequiredComplete, itemsForProjectType } from './catalog'

export function buildExportCheck(
  projectType: ProjectType,
  states: CatalogItemState[]
): ExportCheck {
  const applicable = itemsForProjectType(projectType)
  const byCode = new Map(states.map((s) => [s.item.code, s]))
  const blockers: ExportBlocker[] = []
  let confirmed = 0
  let required = 0
  let waived = 0

  for (const item of applicable) {
    if (!item.required) continue
    required += 1
    const state = byCode.get(item.code)
    const status = (state?.instance.status ?? 'empty') as ItemStatus
    if (status === 'confirmed') confirmed += 1
    if (status === 'waived') waived += 1
    if (
      !isRequiredComplete({
        required: true,
        status,
        generatedPath: state?.instance.generated_path,
        uploadCount: state?.uploads.length ?? 0
      })
    ) {
      blockers.push({
        code: item.code,
        title: item.title,
        reason:
          status === 'empty'
            ? '尚未提供资料'
            : status === 'draft'
              ? '已有草稿，待确认'
              : '未完成'
      })
    }
  }

  return {
    ok: blockers.length === 0,
    blockers,
    confirmed,
    required,
    waived
  }
}
