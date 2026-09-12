import type { ItemEditorState } from '@shared/types'
import { FORM_MODE_BANNER } from '@shared/types'
import FormPane from './FormPane'
import PreviewPane from './PreviewPane'
import UploadPane from './UploadPane'

export default function FormPreviewHost(props: {
  editor: ItemEditorState
  draft: Record<string, string>
  previewHtml: string | null
  onDraft: (next: Record<string, string>) => void
  onUpload: () => void
  onReveal: (path: string) => void
}) {
  return (
    <div className="form-preview-host">
      <div className="mode-banner">{FORM_MODE_BANNER}</div>
      {props.editor.pane === 'form' ? (
        <>
          <FormPane editor={props.editor} draft={props.draft} onChange={props.onDraft} />
          <PreviewPane editor={props.editor} previewHtml={props.previewHtml} />
        </>
      ) : (
        <UploadPane editor={props.editor} onUpload={props.onUpload} onReveal={props.onReveal} />
      )}
    </div>
  )
}
