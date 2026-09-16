#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4 V1–V4 fidelity gate. Writes src/fidelity-status.json and prints a markdown table.

  python tools/run_p4_gate.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import ENGINE, EXAMPLES, REPO, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO))
from _common import iter_templates  # noqa: E402

FIDELITY = REPO / 'src' / 'fidelity-status.json'
EVIDENCE = WORK / 'p4-evidence'
W_TBL = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl'
PART_DOC = 'word/document.xml'


def run(args, cwd=None, timeout=180, env=None) -> subprocess.CompletedProcess:
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
        vers = sorted(nvm.iterdir(), reverse=True)
        for v in vers:
            node = v / 'bin' / 'node'
            if node.is_file():
                return str(node), str(v / 'bin')
    return shutil.which('node') or 'node', ''


def v1_source_build() -> dict:
    """Product V1: pinned GenOffice source typecheck + embed bundle (not npm add)."""
    pin_path = REPO / 'vendor' / 'genoffice' / 'PIN.json'
    engine_src = REPO / 'vendor' / 'genoffice' / 'packages' / 'docx-engine' / 'src' / 'parse.ts'
    info = {'node': run([which_node()[0], '--version']).stdout.strip()}
    if not pin_path.is_file() or not engine_src.is_file():
        return {
            'status': 'BLOCKED',
            'reason': 'vendor/genoffice pin missing',
            **info,
        }
    pin = json.loads(pin_path.read_text(encoding='utf-8'))
    node, bindir = which_node()
    env = os.environ.copy()
    if bindir:
        env['PATH'] = bindir + os.pathsep + env.get('PATH', '')
    tsc = shutil.which('tsc')
    npm_bin = Path(bindir) / 'tsc' if bindir else None
    if not tsc and npm_bin and npm_bin.is_file():
        tsc = str(npm_bin)
    local_tsc = REPO / 'node_modules' / '.bin' / 'tsc'
    if local_tsc.is_file():
        tsc = str(local_tsc)
    if not tsc:
        return {'status': 'FAIL', 'reason': 'tsc not installed (npm install)', **info, 'pin': pin}
    checks = []
    for proj in (
        REPO / 'vendor' / 'genoffice' / 'packages' / 'pptx-engine',
        REPO / 'vendor' / 'genoffice' / 'packages' / 'docx-engine',
        REPO / 'packages' / 'docx-embed',
    ):
        proc = subprocess.run(
            [tsc, '--noEmit', '-p', str(proj)],
            cwd=str(REPO), env=env, capture_output=True, text=True, timeout=180,
        )
        checks.append({
            'project': str(proj.relative_to(REPO)),
            'exit': proc.returncode,
            'log': ((proc.stdout or '') + '\n' + (proc.stderr or ''))[-400:],
        })
        if proc.returncode != 0:
            return {
                'status': 'FAIL',
                'reason': 'typecheck failed: %s' % proj.name,
                'checks': checks,
                'pin': pin,
                **info,
            }
    build = subprocess.run(
        [node, str(REPO / 'packages' / 'docx-embed' / 'build.mjs')],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=120,
    )
    bundle = REPO / 'src' / 'editor' / 'bundle.cjs'
    if build.returncode != 0 or not bundle.is_file():
        return {
            'status': 'FAIL',
            'reason': 'embed bundle build failed',
            'log': ((build.stdout or '') + '\n' + (build.stderr or ''))[-800:],
            'pin': pin,
            **info,
        }
    return {
        'status': 'PASS',
        'reason': 'source pin %s typecheck+bundle' % pin.get('commit', '')[:12],
        'pin': pin,
        'checks': [{'project': c['project'], 'exit': c['exit']} for c in checks],
        **info,
    }


def v1_npm_add_historical() -> dict:
    """Record that the unpublished npm package still 404s (not the product V1)."""
    pnpm = shutil.which('pnpm')
    if not pnpm:
        return {'status': 'SKIPPED', 'reason': 'pnpm not on PATH (expected npm 404 anyway)'}
    tmp = Path(tempfile.mkdtemp(prefix='v1-genoffice-'))
    try:
        (tmp / 'package.json').write_text('{"name":"v1-probe","private":true}\n', encoding='utf-8')
        proc = subprocess.run(
            [pnpm, 'add', '@genoffice/docx-engine'],
            cwd=str(tmp), capture_output=True, text=True, timeout=90,
        )
        log = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
        blocked = proc.returncode != 0 or '404' in log
        return {
            'status': 'BLOCKED' if blocked else 'PASS',
            'reason': 'npm still unpublished (404 expected)' if blocked else 'unexpectedly installed',
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def v2_structural() -> dict:
    fails = []
    ok = 0
    details = []
    files = list(iter_templates(TEMPLATES))
    for p in files:
        rel = str(p.relative_to(TEMPLATES)).replace('\\', '/')
        rec = {'file': rel, 'tables': 0, 'headers': 0, 'footers': 0, 'ok': False}
        try:
            with zipfile.ZipFile(p) as z:
                names = z.namelist()
                if '[Content_Types].xml' not in names:
                    raise ValueError('missing [Content_Types].xml')
                if PART_DOC not in names:
                    raise ValueError('missing word/document.xml')
                raw = z.read(PART_DOC)
                root = ET.fromstring(raw)
                rec['tables'] = sum(1 for _ in root.iter(W_TBL))
                rec['headers'] = sum(1 for n in names if n.startswith('word/header'))
                rec['footers'] = sum(1 for n in names if n.startswith('word/footer'))
                rec['parts'] = len(names)
                rec['ok'] = True
                ok += 1
        except Exception as e:
            rec['error'] = str(e)
            fails.append(rec)
        details.append(rec)
    status = 'PASS' if ok == len(files) and files else 'FAIL'
    return {
        'status': status,
        'ok': ok,
        'total': len(files),
        'failures': fails,
        'note': 'headless zip+XML sanity; product V2 is the GenOffice Block renderer',
    }


def v23_embed() -> dict:
    """Product V2/V3: parse+render and saveDocx one-char via the bundled adapter."""
    node, bindir = which_node()
    env = os.environ.copy()
    if bindir:
        env['PATH'] = bindir + os.pathsep + env.get('PATH', '')
    bundle = REPO / 'src' / 'editor' / 'bundle.cjs'
    if not bundle.is_file():
        build = subprocess.run(
            [node, str(REPO / 'packages' / 'docx-embed' / 'build.mjs')],
            cwd=str(REPO), env=env, capture_output=True, text=True, timeout=120,
        )
        if build.returncode != 0 or not bundle.is_file():
            return {
                'v2': 'BLOCKED', 'v3': 'BLOCKED',
                'reason': 'embed bundle missing/failed',
                'log': ((build.stdout or '') + '\n' + (build.stderr or ''))[-800:],
            }
    proc = subprocess.run(
        [node, str(TOOLS / 'run_embed_gate.mjs')],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=420,
    )
    data = {}
    blob = (proc.stdout or '') + '\n' + (proc.stderr or '')
    for line in blob.splitlines():
        if line.startswith('EMBED_V23_JSON:'):
            data = json.loads(line[len('EMBED_V23_JSON:'):])
            break
    if not data:
        return {
            'v2': 'FAIL', 'v3': 'BLOCKED',
            'reason': 'embed gate produced no JSON',
            'exit': proc.returncode,
            'log': blob[-1200:],
        }
    return {
        'v2': data.get('v2', 'FAIL'),
        'v3': data.get('v3', 'FAIL'),
        'v2ok': data.get('v2ok'),
        'v2total': data.get('v2total'),
        'v2fail': data.get('v2fail') or [],
        'v3pass': data.get('v3pass'),
        'v3total': data.get('v3total'),
        'v3fail': data.get('v3fail') or [],
        'pin': data.get('pin'),
        'exit': proc.returncode,
        'path': 'saveDocx generated/xml + Block HTML renderer (not clone-only XML)',
    }


def v4_pdf() -> dict:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        pip = run([sys.executable, '-m', 'pip', 'install', 'pypdf', '-q'])
        if pip.returncode != 0:
            return {'status': 'FAIL', 'reason': 'cannot install pypdf: %s' % pip.stderr[-400:]}
    from lib.project_store import write_project

    root = WORK / 'p4-v4-proj'
    if root.exists():
        shutil.rmtree(root)
    (root / '_导出').mkdir(parents=True)
    (root / '二、过程分册' / '1、开工报审表').mkdir(parents=True)
    src = TEMPLATES / '二、过程分册' / '1、开工报审表.docx'
    dest = root / '二、过程分册' / '1、开工报审表' / 'YY123-KGBSB-01_开工报审表.docx'
    shutil.copy2(src, dest)
    demo = json.loads((EXAMPLES / 'demo_project.json').read_text(encoding='utf-8'))
    demo['_docs'] = {
        'D-KGBSB-01': {
            'itemId': '二-01',
            'relPath': '二、过程分册/1、开工报审表/YY123-KGBSB-01_开工报审表.docx',
            'docNo': 'YY123-KGBSB-01',
            'fillState': 'draft',
        }
    }
    write_project(root / 'project.json', demo, backup=False)
    out = root / '_导出' / '整册.pdf'
    proc = run([
        sys.executable, str(ENGINE / 'export_engine.py'),
        '--project', str(root / 'project.json'),
        '--mode', 'booklet', '--force', '--json',
        '--out', str(out),
    ], timeout=120)
    last = ''
    for line in (proc.stdout or '').splitlines():
        if line.strip():
            last = line.strip()
    payload = {}
    if last.startswith('{'):
        payload = json.loads(last)
    if proc.returncode != 0 or not out.is_file():
        return {
            'status': 'FAIL',
            'exit': proc.returncode,
            'reason': payload.get('summary') or (proc.stderr or proc.stdout or '')[-600:],
        }
    from pypdf import PdfReader
    reader = PdfReader(str(out))
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or '')
    blob = '\n'.join(texts)
    has_cn = any('\u4e00' <= ch <= '\u9fff' for ch in blob)
    has_page = '第' in blob and '页' in blob
    n = len(reader.pages)
    ok = has_cn and has_page and n >= 2
    return {
        'status': 'PASS' if ok else 'FAIL',
        'pages': n,
        'chineseOk': has_cn,
        'pageLabelOk': has_page,
        'sample': blob[:250].replace('\n', ' / '),
        'out': str(out),
        'stats': payload.get('stats') or {},
    }


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    print('P4 V1–V4 fidelity gate (source-integrated GenOffice)')
    print('=' * 68)

    v1 = v1_source_build()
    print('[V1 source] %s — %s (node %s)' % (v1['status'], v1.get('reason', ''), v1.get('node')))
    v1npm = v1_npm_add_historical()
    print('[V1 npm historical] %s — %s' % (v1npm.get('status'), v1npm.get('reason')))
    v2s = v2_structural()
    print('[V2 structural] %s — %d/%d zip+XML' % (v2s['status'], v2s['ok'], v2s['total']))
    if v2s['failures']:
        for f in v2s['failures']:
            print('    FAIL %s (%s)' % (f['file'], f.get('error')))
    v23 = v23_embed()
    print('[V2 renderer] %s  [V3 saveDocx] %s' % (v23.get('v2'), v23.get('v3')))
    if v23.get('v2fail'):
        for f in v23['v2fail'][:8]:
            print('    V2 fail %s: %s' % (f.get('file'), f.get('reason')))
    if v23.get('v3fail'):
        for f in v23['v3fail'][:8]:
            print('    V3 fail %s: %s' % (f.get('file'), str(f.get('reason'))[:160]))
    v4 = v4_pdf()
    print('[V4] %s — pages=%s chinese=%s labels=%s' % (
        v4.get('status'), v4.get('pages'), v4.get('chineseOk'), v4.get('pageLabelOk')))

    if v23.get('v2') == 'PASS' and v2s['status'] == 'PASS':
        v2_final = 'PASS'
        v2_note = 'structural + GenOffice Block HTML renderer %s/%s' % (
            v23.get('v2ok'), v23.get('v2total'))
    elif v23.get('v2') == 'PASS':
        v2_final = 'PARTIAL'
        v2_note = 'renderer PASS; zip+XML %s' % v2s['status']
    elif v2s['status'] == 'PASS':
        v2_final = 'PARTIAL'
        v2_note = 'zip+XML PASS; renderer %s (not product V2)' % v23.get('v2')
    else:
        v2_final = 'FAIL'
        v2_note = 'structural and renderer failed'

    v3_final = v23.get('v3') or 'BLOCKED'
    if v1['status'] != 'PASS':
        v3_product = 'BLOCKED' if v1['status'] == 'BLOCKED' else v3_final
        editor = 'E1'
        note = ('源码集成 V1=%s。壳走 E1 回退。embed V3=%s。' % (v1['status'], v3_final))
    elif v3_final == 'PASS':
        v3_product = 'PASS'
        editor = 'genoffice-embed'
        note = '源码集成 V3 保真写回通过（saveDocx generated/xml + diff_parts）。E1 表单仍可用。'
    else:
        v3_product = v3_final
        editor = 'E1'
        note = 'V3 未通过；壳走 E1 表单 + 只读预览。embed V3=%s。' % v3_final
    status = {
        'v1': v1['status'],
        'v2': v2_final,
        'v3': v3_product,
        'v4': v4.get('status') or 'FAIL',
        'editorMode': editor,
        'note': note,
        'v1_detail': {k: v1.get(k) for k in ('status', 'reason', 'node')},
        'v1_npm_historical': v1npm,
        'v2_structural': {'ok': v2s['ok'], 'total': v2s['total'], 'failures': v2s['failures']},
        'v2_note': v2_note,
        'v23_embed': {k: v23.get(k) for k in (
            'v2', 'v3', 'v2ok', 'v2total', 'v3pass', 'v3total', 'reason', 'path', 'pin')},
        'v3_fail_sample': (v23.get('v3fail') or [])[:5],
        'v2_fail_sample': (v23.get('v2fail') or [])[:5],
        'v4_detail': {k: v4.get(k) for k in (
            'status', 'pages', 'chineseOk', 'pageLabelOk', 'sample', 'out')},
    }
    FIDELITY.write_text(json.dumps({
        'v1': status['v1'],
        'v2': status['v2'],
        'v3': status['v3'],
        'v4': status['v4'],
        'editorMode': editor,
        'note': note,
        'pin': (v1.get('pin') or {}).get('commit') or v23.get('pin'),
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (EVIDENCE / 'gate.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print()
    print('| Gate | Result | Notes |')
    print('|------|--------|-------|')
    print('| V1 source pin typecheck+bundle | %s | %s |' % (
        v1['status'], (v1.get('reason') or '')[:80]))
    print('| V1 npm add (historical, unpublished) | %s | %s |' % (
        v1npm.get('status'), (v1npm.get('reason') or '')[:80]))
    print('| V2 Block HTML renderer 37 | %s | %s |' % (v2_final, v2_note[:80]))
    print('| V3 saveDocx + diff_parts | %s | %s/%s files |' % (
        v3_product, v23.get('v3pass'), v23.get('v3total')))
    print('| V4 booklet PDF page numbers / 中文 | %s | pages=%s chinese=%s |' % (
        v4.get('status'), v4.get('pages'), v4.get('chineseOk')))
    print('| editorMode | %s | %s |' % (editor, note[:80]))
    print('wrote', FIDELITY)
    ok = v2_final in ('PASS', 'PARTIAL') and v4.get('status') == 'PASS' and v1['status'] != 'FAIL'
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())


if __name__ == '__main__':
    sys.exit(main())
