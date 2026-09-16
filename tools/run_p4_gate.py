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


def v1_npm_add() -> dict:
    """Try `pnpm add @genoffice/docx-engine` in a throwaway dir."""
    pnpm = shutil.which('pnpm')
    node, bindir = which_node()
    info = {
        'node': run([node, '--version']).stdout.strip() if node else 'missing',
        'pnpm': pnpm or 'missing',
    }
    if not pnpm:
        return {'status': 'BLOCKED', 'reason': 'pnpm not on PATH', **info}
    tmp = Path(tempfile.mkdtemp(prefix='v1-genoffice-'))
    try:
        (tmp / 'package.json').write_text(
            '{"name":"v1-probe","private":true}\n', encoding='utf-8')
        env = os.environ.copy()
        if bindir:
            env['PATH'] = bindir + os.pathsep + env.get('PATH', '')
        proc = subprocess.run(
            [pnpm, 'add', '@genoffice/docx-engine'],
            cwd=str(tmp), env=env, capture_output=True, text=True, timeout=90,
        )
        log = ((proc.stdout or '') + '\n' + (proc.stderr or '')).strip()
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / 'v1_pnpm_add.log').write_text(log[-8000:], encoding='utf-8')
        blocked = proc.returncode != 0 or 'ERR_PNPM_FETCH_404' in log or '404' in log
        return {
            'status': 'BLOCKED' if blocked else 'PASS',
            'exit': proc.returncode,
            'reason': 'npm 404: @genoffice/docx-engine is private in genspark-ai/genoffice (not published)'
            if blocked else 'installed',
            'log_tail': log[-600:],
            **info,
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
        'note': 'headless zip+XML open/parse (no visual renderer available without genoffice npm)',
    }


def v23_genoffice() -> dict:
    src = Path(os.environ.get('GENOFFICE_SRC', '/tmp/genoffice'))
    parse_ts = src / 'packages' / 'docx-engine' / 'src' / 'parse.ts'
    if not parse_ts.is_file():
        return {
            'v2': 'SKIPPED', 'v3': 'BLOCKED',
            'reason': 'no local genoffice checkout at %s' % src,
        }
    probe_dir = WORK / 'p4-probe'
    probe_dir.mkdir(parents=True, exist_ok=True)
    pkg = {
        'name': 'p4-genoffice-probe',
        'private': True,
        'type': 'module',
        'dependencies': {
            '@genoffice/docx-engine': 'file:%s' % (src / 'packages' / 'docx-engine'),
            '@genoffice/pptx-engine': 'file:%s' % (src / 'packages' / 'pptx-engine'),
            'fast-xml-parser': '^5.3.4',
            'jszip': '^3.10.1',
            'utif2': '^4.1.0',
            'tsx': '^4.21.0',
        },
        'pnpm': {
            'overrides': {
                '@genoffice/pptx-engine': 'file:%s' % (src / 'packages' / 'pptx-engine'),
            }
        },
    }
    (probe_dir / 'package.json').write_text(json.dumps(pkg, indent=2), encoding='utf-8')
    pnpm = shutil.which('pnpm') or 'pnpm'
    node, bindir = which_node()
    env = os.environ.copy()
    if bindir:
        env['PATH'] = bindir + os.pathsep + env.get('PATH', '')
    env['GENOFFICE_SRC'] = str(src)
    inst = subprocess.run(
        [pnpm, 'install'], cwd=str(probe_dir), env=env,
        capture_output=True, text=True, timeout=180,
    )
    if inst.returncode != 0:
        return {
            'v2': 'FAIL', 'v3': 'BLOCKED',
            'reason': 'pnpm install of file:genoffice packages failed',
            'log': ((inst.stdout or '') + inst.stderr)[-800:],
        }
    probe_js = probe_dir / 'probe.mjs'
    shutil.copy2(TOOLS / 'v23_genoffice_probe.mjs', probe_js)
    proc = subprocess.run(
        [pnpm, 'exec', 'tsx', str(probe_js)],
        cwd=str(probe_dir), env=env,
        capture_output=True, text=True, timeout=300,
    )
    data = {}
    for line in (proc.stdout or '').splitlines():
        if line.startswith('P4_V23_JSON:'):
            data = json.loads(line[len('P4_V23_JSON:'):])
            break
    if not data:
        return {
            'v2': 'FAIL', 'v3': 'BLOCKED',
            'reason': 'probe produced no JSON',
            'exit': proc.returncode,
            'log': ((proc.stdout or '') + '\n' + (proc.stderr or ''))[-1200:],
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
        'exit': proc.returncode,
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
    print('P4 V1–V4 fidelity gate')
    print('=' * 68)

    v1 = v1_npm_add()
    print('[V1] %s — %s (node %s)' % (v1['status'], v1.get('reason', ''), v1.get('node')))
    v2s = v2_structural()
    print('[V2 structural] %s — %d/%d zip+XML' % (v2s['status'], v2s['ok'], v2s['total']))
    if v2s['failures']:
        for f in v2s['failures']:
            print('    FAIL %s (%s)' % (f['file'], f.get('error')))
    v23 = v23_genoffice()
    print('[V2 genoffice] %s  [V3] %s' % (v23.get('v2'), v23.get('v3')))
    if v23.get('v2fail'):
        for f in v23['v2fail'][:8]:
            print('    V2 fail %s: %s' % (f.get('file'), f.get('reason')))
    if v23.get('v3fail'):
        for f in v23['v3fail'][:8]:
            print('    V3 fail %s: %s' % (f.get('file'), str(f.get('reason'))[:160]))
    v4 = v4_pdf()
    print('[V4] %s — pages=%s chinese=%s labels=%s' % (
        v4.get('status'), v4.get('pages'), v4.get('chineseOk'), v4.get('pageLabelOk')))

    v2_final = 'PASS' if v2s['status'] == 'PASS' else 'FAIL'
    if v23.get('v2') == 'FAIL':
        v2_note = 'structural PASS; genoffice parse FAIL'
        v2_final = 'PARTIAL'
    elif v23.get('v2') == 'PASS':
        v2_note = 'structural + genoffice parse PASS (headless; no screenshot compare)'
    else:
        v2_note = 'structural PASS; genoffice parse %s' % v23.get('v2')

    v3_final = v23.get('v3') or 'BLOCKED'
    # Product editor follows V1: unpublished package → E1, do not claim V3 PASS.
    if v1['status'] == 'BLOCKED':
        v3_product = 'BLOCKED'
        editor = 'E1'
        note = ('@genoffice/docx-engine 未发布到 npm（private:true / 404）。'
                '壳走 E1 表单 + 只读预览。clone 探针 V3=%s（不作为产品放行）。' % v3_final)
    elif v3_final == 'PASS':
        v3_product = 'PASS'
        editor = 'genoffice'
        note = 'V3 保真写回通过，可接编辑内核。'
    else:
        v3_product = v3_final
        editor = 'E1'
        note = 'V3 未通过；壳走 E1 表单 + 只读预览。'
    status = {
        'v1': v1['status'],
        'v2': v2_final,
        'v3': v3_product,
        'v4': v4.get('status') or 'FAIL',
        'editorMode': editor,
        'note': note,
        'v1_detail': v1,
        'v2_structural': {'ok': v2s['ok'], 'total': v2s['total'], 'failures': v2s['failures']},
        'v2_note': v2_note,
        'v23_genoffice': {k: v23.get(k) for k in (
            'v2', 'v3', 'v2ok', 'v2total', 'v3pass', 'v3total', 'reason') if k in v23 or True},
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
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (EVIDENCE / 'gate.json').write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print()
    print('| Gate | Result | Notes |')
    print('|------|--------|-------|')
    print('| V1 npm add `@genoffice/docx-engine` | %s | %s |' % (
        v1['status'], (v1.get('reason') or '')[:80]))
    print('| V2 headless open/render 37 | %s | %s |' % (v2_final, v2_note[:80]))
    print('| V3 clone probe (git file: + diff_parts) | %s | %s/%s files |' % (
        v3_final, v23.get('v3pass'), v23.get('v3total')))
    print('| V3 product (pnpm add from registry) | %s | E1 fallback; do not vendor private source |' % v3_product)
    print('| V4 booklet PDF page numbers / 中文 | %s | pages=%s chinese=%s |' % (
        v4.get('status'), v4.get('pages'), v4.get('chineseOk')))
    print('| editorMode | %s | %s |' % (editor, note[:80]))
    print('wrote', FIDELITY)
    return 0 if v2s['status'] == 'PASS' and v4.get('status') == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
