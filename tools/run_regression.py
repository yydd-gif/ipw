#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 regression: demo fill must report 37 docs / 171 filled / 0 leftovers.

Also checks:
  - templates were not written
  - media parts of output match templates byte-for-byte
  - cross-run placeholders in 施工日志 were actually filled
  - writing into assets/templates raises TemplateProtectionError
  - backup SHA256 verify is fail-loud on the two known drifted templates

Usage (repo root):
  python tools/run_regression.py
  python tools/run_regression.py --skip-backup
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import (  # noqa: E402
    ENGINE, EXAMPLES, REPO, TEMPLATES, TEMPLATES_BACKUP, WORK,
)

sys.path.insert(0, str(ENGINE))
from _common import TemplateProtectionError, assert_not_template_write, iter_templates  # noqa: E402

import xml.etree.ElementTree as ET  # noqa: E402

W_T = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'
W_P = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'
PART_RE = __import__('re').compile(
    r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')
PH_RE = __import__('re').compile(r'\{\{[^{}]+\}\}')
MEDIA_RE = __import__('re').compile(r'^word/media/')

EXPECT_DOCS = 37
EXPECT_FILLED = 171
EXPECT_RESIDUAL = 0

# Known fail-loud SHA256 drift (内容零丢失, 故意不覆盖冻结备份)
KNOWN_DRIFT = {
    '七、竣工验收分册（政务信息化项目）/1、项目情况简介.docx',
    '二、过程分册/4、施工组织方案.docx',
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def para_placeholders(docx: Path) -> list:
    hits = []
    with zipfile.ZipFile(docx) as z:
        for name in z.namelist():
            if not PART_RE.match(name):
                continue
            try:
                root = ET.fromstring(z.read(name))
            except ET.ParseError:
                continue
            for p in root.iter(W_P):
                full = ''.join(t.text or '' for t in p.iter(W_T))
                hits.extend(PH_RE.findall(full))
    return hits


def media_map(docx: Path) -> dict:
    out = {}
    with zipfile.ZipFile(docx) as z:
        for info in z.infolist():
            if MEDIA_RE.match(info.filename):
                out[info.filename] = hashlib.sha256(z.read(info.filename)).hexdigest()
            elif info.filename.startswith('word/') and not info.filename.endswith('.xml'):
                if '/media/' in info.filename:
                    out[info.filename] = hashlib.sha256(z.read(info.filename)).hexdigest()
    return out


def part_names(docx: Path) -> list:
    with zipfile.ZipFile(docx) as z:
        return [i.filename for i in z.infolist()]


def last_json_line(text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError('engine produced no stdout')
    return json.loads(lines[-1])


def run_cmd(args, cwd=None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')
    return subprocess.run(
        args, cwd=cwd or str(REPO), env=env,
        capture_output=True, text=True, encoding='utf-8',
    )


def check(ok: bool, name: str, detail: str, failures: list) -> None:
    mark = 'PASS' if ok else 'FAIL'
    print('  [%s] %s — %s' % (mark, name, detail))
    if not ok:
        failures.append('%s: %s' % (name, detail))


def main() -> int:
    ap = argparse.ArgumentParser(description='P0 fill regression')
    ap.add_argument('--skip-backup', action='store_true',
                    help='skip SHA256 backup verify (known fail-loud)')
    a = ap.parse_args()

    failures = []
    print('=' * 68)
    print('P0 regression · 验收资料编辑软件')
    print('=' * 68)

    templates = list(iter_templates(TEMPLATES))
    check(len(templates) == EXPECT_DOCS, 'template count',
          '%d (expect %d)' % (len(templates), EXPECT_DOCS), failures)

    before_hash = {str(p.relative_to(TEMPLATES)): sha256_file(p) for p in templates}
    ph_in_tpl = 0
    for p in templates:
        ph_in_tpl += len(para_placeholders(p))
    check(ph_in_tpl == EXPECT_FILLED, 'template placeholders',
          '%d (expect %d)' % (ph_in_tpl, EXPECT_FILLED), failures)

    fill_py = ENGINE / 'fill_engine.py'
    print('\n-- fill_engine --demo --json')
    proc = run_cmd([sys.executable, str(fill_py), '--demo', '--json'])
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        check(False, 'fill exit', 'code %d' % proc.returncode, failures)
        print('\n'.join(failures))
        return 1
    try:
        payload = last_json_line(proc.stdout)
    except Exception as e:
        check(False, 'fill json', str(e), failures)
        print(proc.stdout[-2000:])
        return 1

    stats = payload.get('stats') or {}
    check(payload.get('engine') == 'fill', 'engine id', str(payload.get('engine')), failures)
    check(stats.get('docs') == EXPECT_DOCS, 'json docs',
          '%s (expect %d)' % (stats.get('docs'), EXPECT_DOCS), failures)
    check(stats.get('filled') == EXPECT_FILLED, 'json filled',
          '%s (expect %d)' % (stats.get('filled'), EXPECT_FILLED), failures)
    check(stats.get('residual') == EXPECT_RESIDUAL, 'json residual',
          '%s (expect %d)' % (stats.get('residual'), EXPECT_RESIDUAL), failures)
    print('  summary: %s' % payload.get('summary'))

    out_dir = WORK / 'demo-fill'
    out_docs = list(iter_templates(out_dir))
    check(len(out_docs) == EXPECT_DOCS, 'output docs',
          '%d' % len(out_docs), failures)

    leftover = 0
    for p in out_docs:
        leftover += len(para_placeholders(p))
    check(leftover == EXPECT_RESIDUAL, 'independent leftover scan',
          '%d (expect %d)' % (leftover, EXPECT_RESIDUAL), failures)

    # media + part-list integrity vs frozen templates
    media_mismatch = []
    missing_parts = []
    for src in templates:
        rel = src.relative_to(TEMPLATES)
        dst = out_dir / rel
        if not dst.exists():
            missing_parts.append('%s (missing output)' % rel)
            continue
        src_parts = part_names(src)
        dst_parts = part_names(dst)
        if set(src_parts) - set(dst_parts):
            missing_parts.append('%s lost %s' % (
                rel, sorted(set(src_parts) - set(dst_parts))[:4]))
        sm, dm = media_map(src), media_map(dst)
        for k, hv in sm.items():
            if dm.get(k) != hv:
                media_mismatch.append('%s %s' % (rel, k))
    check(not missing_parts, 'part inventory',
          'ok' if not missing_parts else '; '.join(missing_parts[:5]), failures)
    check(not media_mismatch, 'media byte-identical',
          'ok' if not media_mismatch else '; '.join(media_mismatch[:5]), failures)

    after_hash = {str(p.relative_to(TEMPLATES)): sha256_file(p) for p in templates}
    mutated = [k for k in before_hash if before_hash[k] != after_hash.get(k)]
    check(not mutated, 'templates frozen',
          'ok' if not mutated else 'mutated: %s' % mutated[:3], failures)

    # cross-run merge: 施工日志 weather/todayWork were split across w:t
    log_rel = Path('二、过程分册') / '10、施工日志.docx'
    log_out = out_dir / log_rel
    if log_out.exists():
        with zipfile.ZipFile(log_out) as z:
            xml = z.read('word/document.xml').decode('utf-8', 'ignore')
        check('{{weather}}' not in xml and '晴' in xml,
              'cross-run weather', '施工日志 filled weather', failures)
        check('{{todayWork}}' not in xml,
              'cross-run todayWork', '施工日志 filled todayWork', failures)
    else:
        check(False, 'cross-run weather', 'output log missing', failures)

    # TemplateProtectionError
    try:
        assert_not_template_write(TEMPLATES / 'probe.txt')
        check(False, 'template protection', 'did not raise', failures)
    except TemplateProtectionError:
        check(True, 'template protection', 'TemplateProtectionError', failures)

    # CLI skeletons: --json last line + missing-arg exit 2
    print('\n-- engine skeletons')
    demo = EXAMPLES / 'demo_project.json'
    skeleton_cmds = [
        (['datafill_engine.py', '--project', str(demo), '--out', str(WORK / 'fillplan.json'), '--json'], 0),
        (['docgen_engine.py', '--project', str(demo), '--item', 'all', '--json'], 0),
        (['numbering_engine.py', '--project', str(demo), '--item', '二-01', '--json'], 0),
        (['aggregate_engine.py', '--period', 'week', '--project', str(demo), '--json'], 0),
        (['subtable_engine.py', '--doc', str(templates[0]), '--json'], 0),
        (['verify_engine.py', '--dir', str(out_dir), '--json'], 0),
        (['datafill_engine.py', '--json'], 2),
    ]
    for args, expect in skeleton_cmds:
        proc = run_cmd([sys.executable, str(ENGINE / args[0]), *args[1:]])
        name = args[0].replace('_engine.py', '') + ' ' + args[1] if len(args) > 1 else args[0]
        ok = proc.returncode == expect
        if '--json' in args and proc.returncode in (0, 1, 2, 3):
            try:
                last_json_line(proc.stdout)
            except Exception:
                ok = False
        check(ok, 'cli %s' % args[0],
              'exit %d (expect %d)' % (proc.returncode, expect), failures)

    if not a.skip_backup:
        print('\n-- backup SHA256 (known fail-loud)')
        bak = run_cmd([sys.executable, str(TOOLS / 'backup_templates.py'),
                       '--verify-only', '--brief'])
        # exit 1 is expected while the two drifted templates remain fail-loud
        detail = (bak.stdout or bak.stderr).strip().splitlines()
        last = detail[-1] if detail else '(no output)'
        if bak.returncode == 0:
            check(True, 'backup verify', 'unexpectedly clean: %s' % last, failures)
        else:
            check(True, 'backup verify fail-loud',
                  'exit %d (expected while drifted templates stay uncovered) · %s'
                  % (bak.returncode, last[:120]), failures)
            print('    known drift (do not "fix" by overwriting backups):')
            for rel in sorted(KNOWN_DRIFT):
                print('      - %s' % rel)

    print('\n' + '=' * 68)
    if failures:
        print('RESULT: FAIL (%d)' % len(failures))
        for f in failures:
            print('  - %s' % f)
        return 1
    print('RESULT: PASS  %d 份 / %d 处已填充 / %d 处残留' % (
        EXPECT_DOCS, EXPECT_FILLED, EXPECT_RESIDUAL))
    print('=' * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
