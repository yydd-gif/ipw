import type { CatalogItemState, ExportBlocker, ExportCheck, ItemStatus, ProjectType } from './types'
import { isRequiredComplete, itemsForProjectType } from './catalog'

/** Native save dialog may open only after completeness has already passed. */
export function canOpenExportSaveDialog(check: ExportCheck): boolean {
  return check.ok
}

export function exportBlockedMessage(check: ExportCheck): string {
  const detail = check.blockers.map((b) => `${b.code} ${b.title}（${b.reason}）`).join('；')
  return `无法导出：仍有必填条目未完成。${detail}`
}

/**
 * Gate export behind completeness: `pickSavePath` (the save dialog) is not
 * called unless the package is allowed to export.
 */
export async function withExportSavePath<T>(
  check: ExportCheck,
  pickSavePath: () => Promise<string | null | undefined>,
  exportTo: (destPath: string) => T | Promise<T>
): Promise<T | null> {
  if (!canOpenExportSaveDialog(check)) {
    throw new Error(exportBlockedMessage(check))
  }
  const dest = await pickSavePath()
  if (!dest) return null
  return exportTo(dest)
}

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
