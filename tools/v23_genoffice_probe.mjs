#!/usr/bin/env node
/**
 * Headless V2/V3 probe against a local checkout of genspark-ai/genoffice
 * packages/docx-engine. Not a product dependency (the npm package is private).
 *
 *   GENOFFICE_SRC=/tmp/genoffice node --import tsx tools/v23_genoffice_probe.mjs
 */
import { readdirSync, readFileSync, mkdirSync, writeFileSync, existsSync } from 'node:fs';
import { join, relative } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url));
// When copied to work/p4-probe/, repo is two levels up; when run from tools/, one.
const REPO = existsSync(join(here, '..', '..', 'assets', 'templates'))
  ? join(here, '..', '..')
  : join(here, '..');
const TEMPLATES = join(REPO, 'assets', 'templates');
const OUT = join(REPO, 'work', 'p4-v23');

function listDocx(root) {
  const out = [];
  const walk = (d) => {
    for (const name of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, name.name);
      if (name.isDirectory()) walk(p);
      else if (name.name.endsWith('.docx') && !name.name.startsWith('~$')) out.push(p);
    }
  };
  walk(root);
  return out.sort();
}

function fail(msg) {
  console.error(msg);
  process.exit(2);
}

let parseDocx, saveDocx;
try {
  const mod = await import('@genoffice/docx-engine');
  parseDocx = mod.parseDocx;
  saveDocx = mod.saveDocx;
} catch (err) {
  const report = {
    ok: false,
    v2: 'FAIL',
    v3: 'BLOCKED',
    reason: 'import @genoffice/docx-engine failed: ' + String(err && err.message || err),
  };
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, 'report.json'), JSON.stringify(report, null, 2));
  console.log('P4_V23_JSON:' + JSON.stringify(report));
  process.exit(0);
}

const files = listDocx(TEMPLATES);
if (files.length === 0) fail('no templates under assets/templates');

const v2 = { total: files.length, ok: 0, fail: [] };
const v3 = { total: 0, pass: 0, fail: [] };

mkdirSync(join(OUT, 'edited'), { recursive: true });

for (const file of files) {
  const rel = relative(TEMPLATES, file);
  const bytes = new Uint8Array(readFileSync(file));
  try {
    const parsed = await parseDocx(bytes);
    const nBlocks = (parsed.blocks || []).length;
    const nVisible = (parsed.blocks || []).filter((b) => !b.hidden).length;
    if (!nBlocks) throw new Error('0 blocks');
    v2.ok += 1;
    // V3: mutate one character in the first paragraph-like block with text
    const visible = (parsed.blocks || []).filter((b) => !b.hidden);
    const idx = visible.findIndex((b) =>
      (b.type === 'paragraph' || b.type === 'heading' || b.type === 'listItem') &&
      (b.runs || []).some((r) => r && r.text && r.text.length > 0) &&
      b.docxIndex != null
    );
    if (idx < 0) {
      v3.fail.push({ file: rel, reason: 'no editable paragraph run' });
      continue;
    }
    v3.total += 1;
    const target = visible[idx];
    const runs = (target.runs || []).map((r) => ({ ...r }));
    const ri = runs.findIndex((r) => r.text && r.text.length > 0);
    const ch = runs[ri].text;
    const next = (ch[0] === '△' ? '▲' : '△') + ch.slice(1);
    runs[ri] = { ...runs[ri], text: next };
    const finalBlocks = visible.map((b, i) => {
      if (i !== idx) return { kind: 'original', docxIndex: b.docxIndex };
      return {
        kind: 'generated',
        block: {
          type: target.type === 'heading' ? 'heading' : target.type === 'listItem' ? 'listItem' : 'paragraph',
          level: target.level,
          styleId: target.styleId,
          list: target.list,
          format: target.format,
          rawPPr: target.rawPPr,
          bookmarks: target.bookmarks,
          hiddenBookmarks: target.hiddenBookmarks,
          runs,
        },
      };
    });
    const outBytes = await saveDocx(parsed, finalBlocks);
    const dest = join(OUT, 'edited', rel);
    mkdirSync(join(dest, '..'), { recursive: true });
    writeFileSync(dest, Buffer.from(outBytes));
    const diff = spawnSync(
      process.env.PYTHON || 'python3',
      [join(REPO, 'tools', 'diff_parts.py'), file, dest],
      { encoding: 'utf8', cwd: REPO },
    );
    const text = (diff.stdout || '') + '\n' + (diff.stderr || '');
    const changed = [...text.matchAll(/~\s+(\S+)/g)].map((m) => m[1]);
    const mediaHit = changed.some((n) => /\/media\//.test(n) || /^word\/media/.test(n));
    const hasDoc = changed.includes('word/document.xml') || /word\/document\.xml/.test(text);
    const extra = changed.filter((n) =>
      n !== 'word/document.xml' &&
      n !== 'docProps/core.xml' &&
      n !== 'docProps/app.xml' &&
      !n.endsWith('/')
    );
    const looksOk = !mediaHit && hasDoc && extra.length === 0 && /判定：实质差异/.test(text);
    if (looksOk) v3.pass += 1;
    else v3.fail.push({
      file: rel,
      exit: diff.status,
      changed,
      reason: text.split('\n').filter(Boolean).slice(0, 14).join(' | ').slice(0, 500),
    });
  } catch (err) {
    v2.fail.push({ file: rel, reason: String(err && err.message || err).slice(0, 300) });
  }
}

const report = {
  ok: v2.fail.length === 0,
  v2: v2.fail.length === 0 ? 'PASS' : 'FAIL',
  v2ok: v2.ok,
  v2total: v2.total,
  v2fail: v2.fail,
  v3: v3.fail.length === 0 && v3.pass > 0 ? 'PASS' : (v3.pass > 0 ? 'PARTIAL' : 'FAIL'),
  v3pass: v3.pass,
  v3total: v3.total,
  v3fail: v3.fail.slice(0, 20),
};
mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, 'report.json'), JSON.stringify(report, null, 2));
console.log('P4_V23_JSON:' + JSON.stringify(report));
