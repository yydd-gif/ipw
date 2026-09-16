import {
  patchTableCellTexts,
  saveDocx,
  type ParsedDocFull,
  type Run,
  type SaveBlock,
} from '@genoffice/docx-engine';

export type ParagraphEdit = { kind: 'paragraph'; docxIndex: number; text: string };
export type TableCellEdit = {
  kind: 'table-cell';
  docxIndex: number;
  row: number;
  col: number;
  text: string;
};
export type TextEdit = ParagraphEdit | TableCellEdit;

export type OneCharPlan = {
  kind: 'paragraph' | 'table-cell';
  docxIndex: number;
  row?: number;
  col?: number;
  before: string;
  after: string;
};

function visible(parsed: ParsedDocFull) {
  return (parsed.blocks || []).filter((b) => !b.hidden);
}

function concatRuns(runs: Run[] | undefined): string {
  return (runs || []).map((r) => r.text || '').join('');
}

function flipChar(ch: string): string {
  if (!ch) return '△';
  return (ch[0] === '△' ? '▲' : '△') + ch.slice(1);
}

function applyPlainTextToRuns(runs: Run[] | undefined, newText: string): Run[] {
  const list = (runs || []).map((r) => ({ ...r }));
  const idx = list.findIndex((r) => r.text && r.text.length > 0);
  if (idx < 0) {
    list.push({ text: newText });
    return list;
  }
  let first = true;
  return list.map((r) => {
    if (r.text && r.text.length) {
      if (first) {
        first = false;
        return { ...r, text: newText };
      }
      return { ...r, text: '' };
    }
    return r;
  });
}

/** Pick one body paragraph or table cell and change its first character. */
export function planOneCharEdit(parsed: ParsedDocFull): OneCharPlan | null {
  for (const b of visible(parsed)) {
    if ((b.type === 'paragraph' || b.type === 'heading' || b.type === 'listItem')
      && b.docxIndex != null
      && (b.runs || []).some((r) => r && r.text && r.text.length > 0)) {
      const before = concatRuns(b.runs);
      const after = flipChar(before);
      return { kind: 'paragraph', docxIndex: b.docxIndex, before, after };
    }
  }
  for (const b of visible(parsed)) {
    if (b.type !== 'table' || b.docxIndex == null || !b.table) continue;
    const rows = b.table.rows || [];
    for (let r = 0; r < rows.length; r++) {
      const row = rows[r] || [];
      for (let c = 0; c < row.length; c++) {
        const cell = row[c];
        if (!cell) continue;
        const before = (cell.paras && cell.paras.join('\n'))
          || (cell.richParas || []).map((p) => concatRuns(p.runs)).join('\n');
        if (!before) continue;
        return {
          kind: 'table-cell',
          docxIndex: b.docxIndex,
          row: r,
          col: c,
          before,
          after: flipChar(before),
        };
      }
    }
  }
  return null;
}

export function editsFromPlan(plan: OneCharPlan): TextEdit[] {
  if (plan.kind === 'paragraph') {
    return [{ kind: 'paragraph', docxIndex: plan.docxIndex, text: plan.after }];
  }
  return [{
    kind: 'table-cell',
    docxIndex: plan.docxIndex,
    row: plan.row ?? 0,
    col: plan.col ?? 0,
    text: plan.after,
  }];
}

function originalSavePlan(parsed: ParsedDocFull): SaveBlock[] {
  return visible(parsed)
    .filter((b) => b.docxIndex != null)
    .map((b) => ({ kind: 'original' as const, docxIndex: b.docxIndex as number }));
}

/**
 * Apply body/table text edits through saveDocx (generated paragraphs /
 * patchTableCellTexts xml), matching the official docs convert.ts table path.
 */
export async function saveWithEdits(
  parsed: ParsedDocFull,
  edits: TextEdit[],
): Promise<Uint8Array> {
  const paraEdits = new Map<number, string>();
  const tableEdits = new Map<number, TableCellEdit[]>();
  for (const e of edits) {
    if (e.kind === 'paragraph') paraEdits.set(e.docxIndex, e.text);
    else {
      const list = tableEdits.get(e.docxIndex) || [];
      list.push(e);
      tableEdits.set(e.docxIndex, list);
    }
  }
  if (!paraEdits.size && !tableEdits.size) {
    return saveDocx(parsed, originalSavePlan(parsed));
  }

  const blocks: SaveBlock[] = [];
  for (const b of visible(parsed)) {
    if (b.docxIndex == null) continue;
    const idx = b.docxIndex;
    if (paraEdits.has(idx)
      && (b.type === 'paragraph' || b.type === 'heading' || b.type === 'listItem')) {
      const text = paraEdits.get(idx) as string;
      const orig = concatRuns(b.runs);
      if (text === orig) {
        blocks.push({ kind: 'original', docxIndex: idx });
        continue;
      }
      blocks.push({
        kind: 'generated',
        block: {
          type: b.type === 'heading' ? 'heading' : b.type === 'listItem' ? 'listItem' : 'paragraph',
          level: b.level,
          styleId: b.styleId,
          list: b.list,
          format: b.format,
          rawPPr: b.rawPPr,
          bookmarks: b.bookmarks,
          hiddenBookmarks: b.hiddenBookmarks,
          commentStarts: b.commentStarts,
          commentEnds: b.commentEnds,
          sdtShell: b.sdtShell,
          runs: applyPlainTextToRuns(b.runs, text),
        },
      });
      continue;
    }
    if (tableEdits.has(idx) && b.type === 'table' && b.originalXml) {
      const changes = tableEdits.get(idx) as TableCellEdit[];
      const rows = b.table?.rows || [];
      const grid: Array<Array<string[] | null>> = rows.map((row) => row.map(() => null));
      let dirty = false;
      for (const ch of changes) {
        const cell = rows[ch.row] && rows[ch.row][ch.col];
        if (!cell) continue;
        const before = (cell.paras && cell.paras.join('\n'))
          || (cell.richParas || []).map((p) => concatRuns(p.runs)).join('\n');
        if (ch.text === before) continue;
        const paras = ch.text.split('\n');
        if (!grid[ch.row]) continue;
        grid[ch.row][ch.col] = paras;
        dirty = true;
      }
      if (!dirty) {
        blocks.push({ kind: 'original', docxIndex: idx });
        continue;
      }
      const xml = patchTableCellTexts(b.originalXml, grid);
      blocks.push({ kind: 'xml', xml, docxIndex: idx });
      continue;
    }
    blocks.push({ kind: 'original', docxIndex: idx });
  }
  return saveDocx(parsed, blocks);
}
