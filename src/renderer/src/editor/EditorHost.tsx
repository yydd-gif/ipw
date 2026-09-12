import { ACTIVE_EDITOR_KERNEL, type ItemEditorState } from '@shared/types'
import FormPreviewHost from './FormPreviewHost'
import OnlyOfficeHost from './OnlyOfficeHost'

/**
 * EditorHost is the only UI seam for swapping the document kernel.
 * v1: FormPreviewHost (form fill + read-only preview).
 * Later: OnlyOfficeHost (WYSIWYG). Catalog / fill_engine / print stay outside.
 */
export default function EditorHost(props: {
  editor: ItemEditorState
  draft: Record<string, string>
  previewHtml: string | null
  onDraft: (next: Record<string, string>) => void
  onUpload: () => void
  onReveal: (path: string) => void
}) {
  if (ACTIVE_EDITOR_KERNEL === 'onlyoffice') {
    return <OnlyOfficeHost />
  }
  return <FormPreviewHost {...props} />
}
