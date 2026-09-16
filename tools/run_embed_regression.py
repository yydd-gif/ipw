#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Source-integrated GenOffice embed: typecheck, bundle, V2/V3, template protect.

  python tools/run_embed_regression.py
  python tools/run_embed_regression.py --skip-prior
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import REPO, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(REPO / 'assets' / 'engine'))
sys.path.insert(0, str(REPO))
from _common import TemplateProtectionError, assert_not_template_write  # noqa: E402


def check(ok: bool, name: str, detail: str, failures: list) -> None:
    mark = 'PASS' if ok else 'FAIL'
    print('  [%s] %s — %s' % (mark, name, detail))
    if not ok:
        failures.append('%s: %s' % (name, detail))


def run(args, cwd=None, timeout=300, env=None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault('PYTHONUTF8', '1')
    return subprocess.run(
        args, cwd=cwd or str(REPO), env=e, timeout=timeout,
        capture_output=True, text=True, encoding='utf-8',
    )


def which_node():
    nvm = Path.home() / '.nvm' / 'versions' / 'node'
    if nvm.is_dir():
        for v in sorted(nvm.iterdir(), reverse=True):
            node = v / 'bin' / 'node'
            if node.is_file():
                return str(node), str(v / 'bin')
    return shutil.which('node') or 'node', ''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-prior', action='store_true')
    a = ap.parse_args()
    failures: list = []
    print('GenOffice source embed regression')
    print('=' * 68)

    pin = REPO / 'vendor' / 'genoffice' / 'PIN.json'
    lic = REPO / 'vendor' / 'genoffice' / 'LICENSE'
    notice = REPO / 'vendor' / 'genoffice' / 'NOTICE'
    parse_ts = REPO / 'vendor' / 'genoffice' / 'packages' / 'docx-engine' / 'src' / 'parse.ts'
    check(pin.is_file(), 'PIN.json', str(pin), failures)
    check(lic.is_file() and 'Apache' in lic.read_text(encoding='utf-8'),
          'Apache-2.0 LICENSE', str(lic), failures)
    check(notice.is_file(), 'NOTICE', str(notice), failures)
    check(parse_ts.is_file(), 'docx-engine parse.ts', str(parse_ts), failures)
    if pin.is_file():
        data = json.loads(pin.read_text(encoding='utf-8'))
        check(data.get('commit'), 'pinned commit', str(data.get('commit')), failures)
        check(data.get('license') == 'Apache-2.0', 'pin license', str(data.get('license')), failures)

    node, bindir = which_node()
    env = os.environ.copy()
    if bindir:
        env['PATH'] = bindir + os.pathsep + env.get('PATH', '')
    tsc = REPO / 'node_modules' / '.bin' / 'tsc'
    esbuild = REPO / 'node_modules' / 'esbuild'
    check(tsc.is_file() or shutil.which('tsc'), 'typescript installed',
          str(tsc if tsc.is_file() else shutil.which('tsc')), failures)
    check(esbuild.is_dir() or shutil.which('esbuild'), 'esbuild installed',
          'node_modules/esbuild', failures)

    if tsc.is_file():
        for proj in (
            'vendor/genoffice/packages/pptx-engine',
            'vendor/genoffice/packages/docx-engine',
            'packages/docx-embed',
        ):
            proc = run([str(tsc), '--noEmit', '-p', proj], env=env, timeout=180)
            check(proc.returncode == 0, 'typecheck ' + proj,
                  (proc.stderr or proc.stdout or 'ok')[-200:], failures)

    build = run([node, str(REPO / 'packages' / 'docx-embed' / 'build.mjs')], env=env)
    bundle = REPO / 'src' / 'editor' / 'bundle.cjs'
    check(build.returncode == 0 and bundle.is_file(), 'embed bundle',
          (build.stderr or build.stdout or str(bundle))[-200:], failures)

    print('\n-- template freeze (Node + Python)')
    probe = TEMPLATES / 'embed-must-not-exist.docx'
    try:
        assert_not_template_write(probe)
        check(False, 'python protect raises', 'did not raise', failures)
    except TemplateProtectionError:
        check(True, 'python protect raises', 'TemplateProtectionError', failures)
    script = r"""
const { assertNotTemplateWrite } = require('./src/editor/protect');
const path = require('path');
try {
  assertNotTemplateWrite(path.resolve('assets/templates/x.docx'), process.cwd());
  console.log('NO_THROW');
  process.exit(2);
} catch (e) {
  console.log(e.code || e.message);
  process.exit(0);
}
"""
    prot = run([node, '-e', script], env=env)
    check(prot.returncode == 0 and 'TEMPLATE_PROTECTED' in (prot.stdout or ''),
          'node protect refuses templates',
          (prot.stdout or prot.stderr or '')[-120:], failures)
    check(not probe.exists(), 'no stray template file', str(probe), failures)

    print('\n-- V2/V3 embed gate (all templates)')
    gate = run([node, str(TOOLS / 'run_embed_gate.mjs')], env=env, timeout=420)
    print(gate.stdout[-1500:] if gate.stdout else '')
    if gate.stderr:
        print(gate.stderr[-400:])
    payload = {}
    for line in (gate.stdout or '').splitlines():
        if line.startswith('EMBED_V23_JSON:'):
            payload = json.loads(line[len('EMBED_V23_JSON:'):])
    check(payload.get('v2') == 'PASS', 'V2 renderer 37/37',
          '%s %s/%s' % (payload.get('v2'), payload.get('v2ok'), payload.get('v2total')),
          failures)
    check(payload.get('v3') in ('PASS', 'PARTIAL', 'FAIL', 'BLOCKED'),
          'V3 recorded honestly', str(payload.get('v3')), failures)
    if payload.get('v3') != 'PASS':
        print('  [INFO] V3 not PASS — do not label product V3 green')
        for f in (payload.get('v3fail') or [])[:8]:
            print('    ', f.get('file'), str(f.get('reason', ''))[:160])
    else:
        check(payload.get('v3pass') == payload.get('v3total'),
              'V3 all files',
              '%s/%s' % (payload.get('v3pass'), payload.get('v3total')),
              failures)

    host = REPO / 'src' / 'main.js'
    text = host.read_text(encoding='utf-8')
    check('editor-open' in text and 'editor-save' in text, 'Electron editor IPC',
          'editor-open/save', failures)
    check('editorHost' in text, 'main loads editor host', 'require editor/host', failures)
    html = (REPO / 'src' / 'renderer' / 'index.html').read_text(encoding='utf-8')
    check('data-view="edit"' in html, '正文 tab', 'index.html', failures)
    check('不是 Office 替代品' in html or '不是 Office' in html,
          'About does not claim Word replacement', 'index.html', failures)

    if not a.skip_prior:
        print('\n-- prior P0')
        p0 = run([sys.executable, str(TOOLS / 'run_regression.py')], timeout=240)
        print(p0.stdout[-400:] if p0.stdout else '')
        check(p0.returncode == 0, 'P0 regression', 'exit %s' % p0.returncode, failures)

    print()
    print('=' * 68)
    if failures:
        print('FAIL %d' % len(failures))
        for f in failures:
            print('  -', f)
        return 1
    print('RESULT: PASS  GenOffice source embed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
