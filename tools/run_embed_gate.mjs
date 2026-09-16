#!/usr/bin/env node
/**
 * Product V2/V3 gate against the source-integrated GenOffice adapter.
 *
 * V2: parseDocx + Block HTML renderer for every template (not zip/XML-only).
 * V3: edit one character via saveDocx (generated / patchTableCellTexts),
 *     write a work copy, diff_parts vs original. Never writes assets/templates.
 *
 *   node tools/run_embed_gate.mjs
 */
import { createRequire } from 'node:module';
import {
  readdirSync, readFileSync, mkdirSync, writeFileSync, existsSync, copyFileSync,
} from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));
const REPO = join(here, '..');
const TEMPLATES = join(REPO, 'assets', 'templates');
const OUT = join(REPO, 'work', 'embed-v23');
const BUNDLE = join(REPO, 'src', 'editor', 'bundle.cjs');
const ALLOWED = new Set([
  'word/document.xml',
  'docProps/core.xml',
  'docProps/app.xml',
]);

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

if (!existsSync(BUNDLE)) {
  const report = {
    ok: false, v2: 'BLOCKED', v3: 'BLOCKED',
    reason: 'src/editor/bundle.cjs missing; run npm run embed:build',
  };
  mkdirSync(OUT, { recursive: true });
  writeFileSync(join(OUT, 'report.json'), JSON.stringify(report, null, 2));
  console.log('EMBED_V23_JSON:' + JSON.stringify(report));
  process.exit(0);
}

const embed = require(BUNDLE);
const files = listDocx(TEMPLATES);
if (files.length === 0) {
  console.error('no templates under assets/templates');
  process.exit(2);
}

const v2 = { total: files.length, ok: 0, fail: [] };
const v3 = { total: 0, pass: 0, fail: [] };

mkdirSync(join(OUT, 'edited'), { recursive: true });
mkdirSync(join(OUT, 'original'), { recursive: true });

for (const file of files) {
  const rel = relative(TEMPLATES, file).replace(/\\/g, '/');
  const bytes = new Uint8Array(readFileSync(file));
  let opened;
  try {
    opened = await embed.openBytes(bytes);
    if (!opened.render || !opened.render.html || opened.render.stats.visible < 1) {
      throw new Error('renderer empty');
    }
    v2.ok += 1;
  } catch (err) {
    v2.fail.push({ file: rel, reason: String(err && err.message || err).slice(0, 300) });
    continue;
  }

  v3.total += 1;
  try {
    const plan = embed.planOneCharEdit(opened.parsed);
    if (!plan) throw new Error('no editable paragraph or table cell');
    const outBytes = await embed.saveWithEdits(opened.parsed, embed.editsFromPlan(plan));
    const dest = join(OUT, 'edited', rel);
    mkdirSync(dirname(dest), { recursive: true });
    writeFileSync(dest, Buffer.from(outBytes));
    const origCopy = join(OUT, 'original', rel);
    mkdirSync(dirname(origCopy), { recursive: true });
    copyFileSync(file, origCopy);
    const diff = spawnSync(
      process.env.PYTHON || 'python3',
      [join(REPO, 'tools', 'diff_parts.py'), origCopy, dest],
      { encoding: 'utf8', cwd: REPO },
    );
    const text = (diff.stdout || '') + '\n' + (diff.stderr || '');
    const changed = [...text.matchAll(/~\s+(\S+)/g)].map((m) => m[1]);
    const mediaHit = changed.some((n) => /media\//.test(n));
    const extra = changed.filter((n) => !ALLOWED.has(n) && !n.endsWith('/'));
    const hasDoc = changed.includes('word/document.xml');
    const looksOk = !mediaHit && hasDoc && extra.length === 0 && /判定：实质差异/.test(text);
    if (!looksOk) {
      v3.fail.push({
        file: rel,
        plan: { kind: plan.kind, docxIndex: plan.docxIndex },
        changed,
        extra,
        mediaHit,
        reason: text.split('\n').filter(Boolean).slice(0, 16).join(' | ').slice(0, 700),
      });
    } else {
      v3.pass += 1;
    }
  } catch (err) {
    v3.fail.push({ file: rel, reason: String(err && err.message || err).slice(0, 400) });
  }
}

const report = {
  ok: v2.fail.length === 0 && v3.fail.length === 0 && v3.pass === files.length,
  engine: 'genoffice-embed',
  pin: embed.sourcePin ? embed.sourcePin() : null,
  v2: v2.fail.length === 0 ? 'PASS' : 'FAIL',
  v2ok: v2.ok,
  v2total: v2.total,
  v2fail: v2.fail,
  v3: v3.fail.length === 0 && v3.pass > 0 ? 'PASS' : (v3.pass > 0 ? 'PARTIAL' : 'FAIL'),
  v3pass: v3.pass,
  v3total: v3.total,
  v3fail: v3.fail,
  note: 'V2 = parseDocx + Block HTML renderer; V3 = saveDocx generated/xml path + diff_parts. Not clone-only XML patching.',
};
mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, 'report.json'), JSON.stringify(report, null, 2));
console.log('EMBED_V23_JSON:' + JSON.stringify({
  ok: report.ok, v2: report.v2, v3: report.v3,
  v2ok: report.v2ok, v2total: report.v2total,
  v3pass: report.v3pass, v3total: report.v3total,
  v2fail: report.v2fail, v3fail: (report.v3fail || []).slice(0, 8),
  pin: report.pin && report.pin.commit,
}));
if (v2.fail.length) {
  console.error('V2 failures:');
  for (const f of v2.fail) console.error(' ', f.file, f.reason);
}
if (v3.fail.length) {
  console.error('V3 failures:');
  for (const f of v3.fail.slice(0, 12)) console.error(' ', f.file, (f.reason || '').slice(0, 200));
}
