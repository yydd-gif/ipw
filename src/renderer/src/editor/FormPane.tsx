import type { FieldDef, ItemEditorState } from '@shared/types'

export default function FormPane(props: {
  editor: ItemEditorState
  draft: Record<string, string>
  onChange: (next: Record<string, string>) => void
}) {
  const fields = props.editor.item.fields ?? []
  const set = (key: string, value: string) => props.onChange({ ...props.draft, [key]: value })

  return (
    <div className="form-pane">
      <div className="form-grid">
        {fields.map((field: FieldDef) => (
          <label className={`field ${field.multiline ? 'field-wide' : ''}`} key={field.key}>
            {field.label}
            {field.required ? <span className="req-star">*</span> : null}
            {field.scope === 'project' ? <span className="scope-tag">项目</span> : <span className="scope-tag">本项</span>}
            {field.multiline ? (
              <textarea
                value={props.draft[field.key] ?? ''}
                placeholder={field.placeholder}
                onChange={(e) => set(field.key, e.target.value)}
              />
            ) : (
              <input
                value={props.draft[field.key] ?? ''}
                placeholder={field.placeholder}
                onChange={(e) => set(field.key, e.target.value)}
              />
            )}
          </label>
        ))}
      </div>
    </div>
  )
}
