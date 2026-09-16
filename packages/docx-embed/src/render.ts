/** Escape text for HTML text nodes / attributes. */
export function esc(s: unknown): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string
  ));
}

function runStyle(run: { bold?: boolean; italic?: boolean; underline?: boolean; strike?: boolean; color?: string; font?: string; sizeHalfPoints?: number }): string {
  const css: string[] = [];
  if (run.bold) css.push('font-weight:700');
  if (run.italic) css.push('font-style:italic');
  if (run.underline) css.push('text-decoration:underline');
  if (run.strike) css.push('text-decoration:line-through');
  if (run.color && run.color !== 'auto') css.push('color:#' + run.color.replace(/^#/, ''));
  if (run.font) css.push('font-family:' + JSON.stringify(run.font));
  if (run.sizeHalfPoints) css.push('font-size:' + (run.sizeHalfPoints / 2) + 'pt');
  return css.join(';');
}

function runsHtml(runs: Array<{ text?: string; vanish?: boolean }> | undefined): string {
  if (!runs || !runs.length) return '&nbsp;';
  const parts: string[] = [];
  for (const r of runs) {
    if (r.vanish) continue;
    const t = r.text || '';
    if (!t) continue;
    const st = runStyle(r as never);
    parts.push(st ? `<span style="${esc(st)}">${esc(t)}</span>` : esc(t));
  }
  return parts.join('') || '&nbsp;';
}

export type RenderStats = {
  blocks: number;
  visible: number;
  paragraphs: number;
  tables: number;
  images: number;
  htmlChars: number;
};

export type RenderResult = {
  html: string;
  stats: RenderStats;
};

type AnyBlock = {
  type?: string;
  hidden?: boolean;
  docxIndex?: number | null;
  runs?: Array<{ text?: string }>;
  table?: {
    rows?: Array<Array<{
      paras?: string[];
      richParas?: Array<{ runs?: Array<{ text?: string }> }>;
      nestedTables?: unknown[];
      gridSpan?: number;
    } | null>>;
    colWidthsPct?: number[];
  };
  imageDataUrl?: string;
  imageWidthPx?: number;
  imageHeightPx?: number;
  label?: string;
  previewText?: string;
  fieldDisplay?: { text?: string };
};

function cellText(cell: { paras?: string[]; richParas?: Array<{ runs?: Array<{ text?: string }> }> } | null | undefined): string {
  if (!cell) return '';
  if (cell.richParas && cell.richParas.length) {
    return cell.richParas.map((p) => (p.runs || []).map((r) => r.text || '').join('')).join('\n');
  }
  return (cell.paras || []).join('\n');
}

function renderTable(block: AnyBlock): string {
  const idx = block.docxIndex;
  const rows = block.table?.rows || [];
  const cols = block.table?.colWidthsPct;
  let html = `<table class="go-tbl" data-go-kind="table" data-go-idx="${idx}">`;
  if (cols && cols.length) {
    html += '<colgroup>' + cols.map((w) => `<col style="width:${Number(w) || 0}%">`).join('') + '</colgroup>';
  }
  for (let r = 0; r < rows.length; r++) {
    const row = rows[r] || [];
    html += '<tr>';
    for (let c = 0; c < row.length; c++) {
      const cell = row[c];
      if (!cell) {
        html += '<td></td>';
        continue;
      }
      const span = cell.gridSpan && cell.gridSpan > 1 ? ` colspan="${cell.gridSpan}"` : '';
      const nested = cell.nestedTables && cell.nestedTables.length
        ? '<div class="go-nested">(嵌套表 · 只读)</div>'
        : '';
      const text = cellText(cell);
      html += `<td${span} class="go-td"><div contenteditable="true" data-go-edit="table-cell" data-go-idx="${idx}" data-go-row="${r}" data-go-col="${c}">${esc(text)}</div>${nested}</td>`;
    }
    html += '</tr>';
  }
  html += '</table>';
  return html;
}

/** Render a parsed GenOffice Block tree to editable HTML (actual renderer, not zip/XML dump). */
export function renderBlocks(blocks: AnyBlock[]): RenderResult {
  const stats: RenderStats = {
    blocks: blocks.length,
    visible: 0,
    paragraphs: 0,
    tables: 0,
    images: 0,
    htmlChars: 0,
  };
  const parts: string[] = ['<div class="go-doc">'];
  for (const b of blocks) {
    if (b.hidden) continue;
    stats.visible += 1;
    const idx = b.docxIndex;
    if (b.type === 'table' && b.table) {
      stats.tables += 1;
      parts.push(renderTable(b));
      continue;
    }
    if (b.type === 'image' || b.imageDataUrl) {
      stats.images += 1;
      const w = b.imageWidthPx ? ` width="${Math.round(b.imageWidthPx)}"` : '';
      const img = b.imageDataUrl
        ? `<img class="go-img" alt="${esc(b.label || 'image')}" src="${esc(b.imageDataUrl)}"${w}>`
        : `<div class="go-img-ph">${esc(b.label || b.previewText || '图片')}</div>`;
      parts.push(`<div class="go-fig" data-go-kind="image" data-go-idx="${idx}">${img}</div>`);
      continue;
    }
    if (b.type === 'passthrough') {
      const t = b.previewText || b.fieldDisplay?.text || b.label || '';
      parts.push(`<div class="go-pass" data-go-kind="passthrough" data-go-idx="${idx}">${esc(t) || '&nbsp;'}</div>`);
      continue;
    }
    stats.paragraphs += 1;
    const tag = b.type === 'heading' ? 'h3' : 'p';
    const cls = b.type === 'heading' ? 'go-h' : (b.type === 'listItem' ? 'go-li' : 'go-p');
    parts.push(
      `<${tag} class="${cls}" contenteditable="true" data-go-edit="paragraph" data-go-kind="${esc(b.type || 'paragraph')}" data-go-idx="${idx}">${runsHtml(b.runs)}</${tag}>`,
    );
  }
  parts.push('</div>');
  const html = parts.join('\n');
  stats.htmlChars = html.length;
  return { html, stats };
}
