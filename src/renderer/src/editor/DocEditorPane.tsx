import { useMemo, useState } from 'react'
import type { DocCell, TableDocument } from '@shared/types'

function cloneDoc(doc: TableDocument): TableDocument {
  return JSON.parse(JSON.stringify(doc)) as TableDocument
}

function colCount(doc: TableDocument, tableIndex: number): number {
  const rows = doc.tables[tableIndex]?.rows ?? []
  return Math.max(1, ...rows.map((r) => r.reduce((n, c) => n + (c.colSpan ?? 1), 0)), 1)
}

function emptyCell(): DocCell {
  return { text: '' }
}

export default function DocEditorPane(props: {
  document: TableDocument
  onChange: (next: TableDocument) => void
}) {
  const [sel, setSel] = useState<{ t: number; r: number; c: number } | null>(null)
  const selected = useMemo(() => {
    if (!sel) return null
    return props.document.tables[sel.t]?.rows[sel.r]?.[sel.c] ?? null
  }, [props.document, sel])

  const patch = (mut: (next: TableDocument) => void) => {
    const next = cloneDoc(props.document)
    mut(next)
    props.onChange(next)
  }

  const applyCell = (partial: Partial<DocCell>) => {
    if (!sel) return
    patch((d) => {
      const cell = d.tables[sel.t]?.rows[sel.r]?.[sel.c]
      if (cell) Object.assign(cell, partial)
    })
  }

  const addRow = () => {
    const t = sel?.t ?? 0
    if (!props.document.tables[t]) return
    patch((d) => {
      const cols = colCount(d, t)
      d.tables[t]!.rows.push(Array.from({ length: cols }, emptyCell))
    })
  }

  const removeRow = () => {
    const t = sel?.t ?? 0
    const r = sel?.r ?? (props.document.tables[t]?.rows.length ?? 1) - 1
    patch((d) => {
      if ((d.tables[t]?.rows.length ?? 0) <= 1) return
      d.tables[t]!.rows.splice(r, 1)
    })
    setSel(null)
  }

  const addCol = () => {
    const t = sel?.t ?? 0
    if (!props.document.tables[t]) return
    patch((d) => {
      for (const row of d.tables[t]!.rows) row.push(emptyCell())
    })
  }

  const removeCol = () => {
    const t = sel?.t ?? 0
    const c = sel?.c ?? colCount(props.document, t) - 1
    patch((d) => {
      for (const row of d.tables[t]!.rows) {
        if (row.length <= 1) continue
        row.splice(Math.min(c, row.length - 1), 1)
      }
    })
    setSel(null)
  }

  const addTable = () => {
    patch((d) => {
      d.tables.push({
        rows: [
          [emptyCell(), emptyCell(), emptyCell()],
          [emptyCell(), emptyCell(), emptyCell()]
        ]
      })
    })
  }

  return (
    <div className="doc-editor">
      <div className="doc-toolbar">
        <button className="btn" onClick={() => applyCell({ bold: !selected?.bold })} disabled={!sel}>
          粗体
        </button>
        <button className="btn" onClick={() => applyCell({ align: 'left' })} disabled={!sel}>
          左齐
        </button>
        <button className="btn" onClick={() => applyCell({ align: 'center' })} disabled={!sel}>
          居中
        </button>
        <button className="btn" onClick={() => applyCell({ align: 'right' })} disabled={!sel}>
          右齐
        </button>
        <span className="toolbar-sep" />
        <button className="btn" onClick={addRow}>
          增行
        </button>
        <button className="btn" onClick={removeRow}>
          删行
        </button>
        <button className="btn" onClick={addCol}>
          增列
        </button>
        <button className="btn" onClick={removeCol}>
          删列
        </button>
        <button className="btn" onClick={addTable}>
          加表
        </button>
      </div>

      <label className="field">
        标题
        <input
          value={props.document.title || ''}
          onChange={(e) => patch((d) => { d.title = e.target.value })}
        />
      </label>

      {props.document.paragraphs.map((p, i) => (
        <textarea
          key={`p-${i}`}
          className="doc-para"
          style={{ fontWeight: p.bold ? 700 : 400, textAlign: p.align || 'left' }}
          value={p.text}
          onChange={(e) =>
            patch((d) => {
              if (d.paragraphs[i]) d.paragraphs[i]!.text = e.target.value
            })
          }
        />
      ))}
      <button
        className="btn ghost"
        onClick={() => patch((d) => { d.paragraphs.push({ text: '' }) })}
      >
        增加段落
      </button>

      {props.document.tables.length === 0 ? (
        <p className="muted">模板未解析到表格。可用「加表」新建，或编辑上方段落。</p>
      ) : null}

      {props.document.tables.map((table, ti) => (
        <div className="table-wrap" key={`t-${ti}`}>
          <table className="edit-table">
            <tbody>
              {table.rows.map((row, ri) => (
                <tr key={ri}>
                  {row.map((cell, ci) => (
                    <td
                      key={ci}
                      colSpan={cell.colSpan ?? 1}
                      className={sel?.t === ti && sel.r === ri && sel.c === ci ? 'cell-sel' : ''}
                      onClick={() => setSel({ t: ti, r: ri, c: ci })}
                    >
                      <textarea
                        style={{
                          fontWeight: cell.bold ? 700 : 400,
                          textAlign: cell.align || 'left'
                        }}
                        value={cell.text}
                        onFocus={() => setSel({ t: ti, r: ri, c: ci })}
                        onChange={(e) =>
                          patch((d) => {
                            const c = d.tables[ti]?.rows[ri]?.[ci]
                            if (c) c.text = e.target.value
                          })
                        }
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
