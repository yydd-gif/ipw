import { createHash } from 'node:crypto'
import type { TableDocument, UploadRecord } from '../shared/types'

export function editorDocumentFromPayload(payload: Record<string, unknown>): TableDocument | null {
  const raw = payload.editorDocument
  if (!raw || typeof raw !== 'object') return null
  const doc = raw as TableDocument
  if (!Array.isArray(doc.paragraphs) || !Array.isArray(doc.tables)) return null
  return doc
}

export function computeContentFingerprint(input: {
  document?: TableDocument | null
  uploads?: Pick<UploadRecord, 'original_name' | 'stored_path'>[]
}): string {
  const payload = {
    document: input.document ?? null,
    uploads: (input.uploads ?? []).map((u) => `${u.original_name}|${u.stored_path}`)
  }
  return createHash('sha256').update(JSON.stringify(payload)).digest('hex').slice(0, 20)
}
