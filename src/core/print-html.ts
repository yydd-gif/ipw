import type { CatalogItem, Project, TableDocument, UploadRecord } from '../shared/types'

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function cellStyle(cell: { bold?: boolean; align?: string }): string {
  const parts = ['border:1px solid #333', 'padding:6px 8px', 'vertical-align:top']
  if (cell.bold) parts.push('font-weight:700')
  if (cell.align) parts.push(`text-align:${cell.align}`)
  return parts.join(';')
}

export function buildItemPrintHtml(args: {
  project: Project
  item: CatalogItem
  document: TableDocument | null
  uploads: UploadRecord[]
}): string {
  const { project, item, document, uploads } = args
  const blocks: string[] = []
  blocks.push(`<h1>${escapeHtml(`${item.code} ${item.title}`)}</h1>`)
  blocks.push(
    `<p class="meta">${escapeHtml(project.name)} · ${escapeHtml(project.owner || '建设单位未填')} · 合同 ${escapeHtml(project.contract_no || '未填')}</p>`
  )

  if (document) {
    for (const p of document.paragraphs) {
      const align = p.align ? ` style="text-align:${p.align};${p.bold ? 'font-weight:700;' : ''}"` : p.bold ? ' style="font-weight:700"' : ''
      blocks.push(`<p${align}>${escapeHtml(p.text)}</p>`)
    }
    for (const table of document.tables) {
      const rows = table.rows
        .map(
          (row) =>
            `<tr>${row
              .map((c) => `<td colspan="${c.colSpan ?? 1}" style="${cellStyle(c)}">${escapeHtml(c.text).replace(/\n/g, '<br/>')}</td>`)
              .join('')}</tr>`
        )
        .join('')
      blocks.push(`<table>${rows}</table>`)
    }
  }

  if (uploads.length) {
    blocks.push('<h2>归档原件</h2><ul>')
    for (const u of uploads) {
      blocks.push(`<li>${escapeHtml(u.original_name)}</li>`)
    }
    blocks.push('</ul>')
  }

  if (!document && uploads.length === 0) {
    blocks.push('<p>本条目尚无编辑内容或上传件。</p>')
  }

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>${escapeHtml(`${item.code} ${item.title}`)}</title>
  <style>
    @page { size: A4; margin: 16mm; }
    body { font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", "SimSun", serif; color: #1c140c; margin: 24px; }
    h1 { font-size: 20px; text-align: center; margin: 0 0 8px; }
    h2 { font-size: 16px; margin: 18px 0 8px; }
    .meta { color: #5a4634; font-size: 12px; text-align: center; margin-bottom: 18px; }
    table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13px; }
    p { line-height: 1.55; }
  </style>
</head>
<body>
${blocks.join('\n')}
</body>
</html>`
}
