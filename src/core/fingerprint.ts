import { createHash } from 'node:crypto'
import type { UploadRecord } from '../shared/types'

export function contentFingerprint(
  mergedFields: Record<string, string>,
  uploads: UploadRecord[]
): string {
  const payload = {
    fields: Object.fromEntries(
      Object.entries(mergedFields)
        .map(([k, v]) => [k, (v ?? '').trim()] as const)
        .sort(([a], [b]) => a.localeCompare(b))
    ),
    uploads: uploads.map((u) => u.originalName).sort()
  }
  return createHash('sha256').update(JSON.stringify(payload)).digest('hex')
}
