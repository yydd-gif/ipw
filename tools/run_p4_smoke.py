#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4 smoke: fidelity gate + shell_bridge + print-state persist + prior regressions.

  python tools/run_p4_smoke.py
  python tools/run_p4_smoke.py --skip-prior
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
from _paths import ENGINE, EXAMPLES, REPO, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO))
from _common import TemplateProtectionError, assert_not_template_write  # noqa: E402
from lib.project_store import read_project  # noqa: E402

BRIDGE = ENGINE / 'shell_bridge.py'


def check(ok: bool, name: str, detail: str, failures: list) -> None:
    mark = 'PASS' if ok else 'FAIL'
    print('  [%s] %s — %s' % (mark, name, detail))
    if not ok:
        failures.append('%s: %s' % (name, detail))


def run(args, cwd=None, timeout=300) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')
    return subprocess.run(
        args, cwd=cwd or str(REPO), env=env, timeout=timeout,
        capture_output=True, text=True, encoding='utf-8',
    )


def last_json(text: str) -> dict:
    lines = [ln for ln in (text or '').splitlines() if ln.strip()]
    if not lines:
        raise ValueError('empty output')
    return json.loads(lines[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-prior', action='store_true',
                    help='do not re-run P0/P1/P2/P3 scripts')
    ap.add_argument('--skip-gate', action='store_true',
                    help='skip V1–V4 gate (use existing fidelity-status.json)')
    a = ap.parse_args()
    failures = []
    print('P4 smoke')
    print('=' * 68)

    if not a.skip_gate:
        print('\n-- V1–V4 gate')
        g = run([sys.executable, str(TOOLS / 'run_p4_gate.py')], timeout=600)
        print(g.stdout)
        if g.stderr:
            print(g.stderr[-400:])
        fid = REPO / 'src' / 'fidelity-status.json'
        data = json.loads(fid.read_text(encoding='utf-8')) if fid.exists() else {}
        check(data.get('v2') in ('PASS', 'PARTIAL'), 'V2 recorded',
              str(data.get('v2')), failures)
        check(data.get('v3') in ('PASS', 'BLOCKED', 'FAIL', 'PARTIAL'), 'V3 recorded honestly',
              str(data.get('v3')), failures)
        check(data.get('editorMode') in ('E1', 'genoffice-embed', 'genoffice'),
              'editorMode recorded',
              '%s / V3=%s' % (data.get('editorMode'), data.get('v3')),
              failures)
        check(data.get('v4') == 'PASS', 'V4 PDF', str(data.get('v4')), failures)
        if data.get('v3') == 'PASS':
            check(data.get('editorMode') in ('genoffice-embed', 'genoffice'),
                  'V3 PASS → embedded editor mode',
                  str(data.get('editorMode')), failures)
        else:
            check(data.get('editorMode') == 'E1',
                  'V3 not PASS → E1 fallback',
                  '%s / V3=%s' % (data.get('editorMode'), data.get('v3')),
                  failures)
        if data.get('v1') == 'BLOCKED':
            check(data.get('editorMode') == 'E1', 'V1 blocked → E1 shell',
                  str(data.get('editorMode')), failures)
            check(data.get('v3') != 'PASS',
                  'do not claim V3 PASS when source V1 blocked',
                  str(data.get('v3')), failures)

    print('\n-- shell_bridge create / save / print persist')
    root = WORK / 'p4-smoke-proj'
    if root.exists():
        shutil.rmtree(root)
    fields = {
        'projectName': 'P4冒烟工程',
        'ownerUnit': '建设单位甲',
        'constructionUnit': '施工单位乙',
        'contractNo': 'YY-P4',
    }
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'create',
        '--dir', str(root), '--fields', json.dumps(fields, ensure_ascii=False), '--json',
    ])
    check(proc.returncode == 0, 'create exit 0', 'exit %d %s' % (
        proc.returncode, (proc.stderr or '')[-200:]), failures)
    created = last_json(proc.stdout) if proc.returncode == 0 else {}
    st = created.get('stats') or {}
    check(st.get('projectPath'), 'create projectPath', str(st.get('projectPath')), failures)
    check(len(st.get('items') or []) >= 50, 'catalog items',
          str(len(st.get('items') or [])), failures)
    dots = {it.get('dot') for it in st.get('items') or []}
    check(dots <= {'gray', 'blue', 'green', 'red'} and 'gray' in dots,
          'fill dots gray/blue/green/red only', str(dots), failures)
    by_id = {it.get('itemId'): it for it in st.get('items') or []}
    check(by_id.get('二-05', {}).get('required') is False,
          '工程开工令 optional in snapshot',
          str((by_id.get('二-05') or {}).get('required')), failures)
    check(by_id.get('六-01', {}).get('required') is True,
          '验收报告封面 required in snapshot',
          str((by_id.get('六-01') or {}).get('required')), failures)
    check((by_id.get('二-05') or {}).get('dot') == 'gray'
          and not (by_id.get('二-05') or {}).get('docs'),
          'optional empty row has no instance',
          str(by_id.get('二-05')), failures)

    # save a field
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'save-fields',
        '--project', str(root / 'project.json'),
        '--fields', json.dumps({'buildSite': '岳阳市测试地点'}, ensure_ascii=False),
        '--json',
    ])
    check(proc.returncode == 0, 'save-fields', 'exit %d' % proc.returncode, failures)
    data = read_project(root / 'project.json')
    check(data.get('buildSite') == '岳阳市测试地点', 'field persisted',
          str(data.get('buildSite')), failures)

    print('\n-- on-demand create-item (GUI 新建表格)')
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'create-item',
        '--project', str(root / 'project.json'), '--item', '二-05', '--json',
    ])
    check(proc.returncode == 0, 'create-item exit',
          'exit %d %s' % (proc.returncode, (proc.stderr or '')[-200:]), failures)
    created_item = last_json(proc.stdout) if proc.returncode == 0 else {}
    st2 = created_item.get('stats') or {}
    kgl = next((it for it in (st2.get('items') or []) if it.get('itemId') == '二-05'), None)
    kgb = next((it for it in (st2.get('items') or []) if it.get('itemId') == '二-01'), None)
    kgl_docs = [d for d in ((kgl or {}).get('docs') or []) if d.get('exists')]
    check(kgl and kgl_docs and (root / kgl_docs[0]['relPath']).is_file(),
          '新建表格 adds one 工程开工令 instance',
          str(kgl_docs[:1]), failures)
    check(not [d for d in ((kgb or {}).get('docs') or []) if d.get('exists')],
          'create-item does not invent other optionals',
          str((kgb or {}).get('docs')), failures)
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'booklet',
        '--project', str(root / 'project.json'), '--json',
    ], timeout=180)
    check(proc.returncode == 0, 'booklet after optional create',
          'exit %d' % proc.returncode, failures)
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'open',
        '--project', str(root / 'project.json'), '--json',
    ])
    after = last_json(proc.stdout) if proc.returncode == 0 else {}
    st3 = after.get('stats') or {}
    kgl2 = next((it for it in (st3.get('items') or []) if it.get('itemId') == '二-05'), None)
    check(len([d for d in ((kgl2 or {}).get('docs') or []) if d.get('exists')]) == 1,
          'booklet does not mass-create extra 开工令',
          str((kgl2 or {}).get('docs')), failures)
    n_req = sum(1 for it in (st3.get('items') or []) if it.get('required'))
    n_with = sum(1 for it in (st3.get('items') or [])
                 if any(d.get('exists') for d in (it.get('docs') or [])))
    check(n_with == n_req + 1,
          'booklet instances = required + preselected optional',
          'with=%d required=%d' % (n_with, n_req), failures)

    # print state: need a docId — register a fake one then mark
    data = read_project(root / 'project.json')
    data['_docs']['D-SMOKE-01'] = {
        'itemId': '二-01',
        'relPath': 'missing.docx',
        'docNo': '',
        'fillState': 'empty',
    }
    from lib.project_store import write_project
    write_project(root / 'project.json', data, backup=False)
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'mark-printed',
        '--project', str(root / 'project.json'),
        '--doc-id', 'D-SMOKE-01', '--json',
    ])
    check(proc.returncode == 0, 'mark-printed', 'exit %d' % proc.returncode, failures)
    # reopen
    proc = run([
        sys.executable, str(BRIDGE), '--action', 'open',
        '--project', str(root / 'project.json'), '--json',
    ])
    opened = last_json(proc.stdout)
    ps = (opened.get('stats') or {}).get('printStates') or {}
    check(ps.get('D-SMOKE-01', {}).get('printed') is True, 'print state survives reopen',
          str(ps.get('D-SMOKE-01')), failures)
    # printed is NOT a fill dot colour
    items = (opened.get('stats') or {}).get('items') or []
    item = next((it for it in items if it.get('itemId') == '二-01'), None)
    if item:
        check(item.get('printed') is True, 'printed is a separate badge flag',
              str(item.get('printed')), failures)
        check(item.get('dot') in ('gray', 'blue', 'green', 'red'),
              'dot unchanged by print', str(item.get('dot')), failures)

    print('\n-- red lines')
    try:
        assert_not_template_write(TEMPLATES / 'p4-probe.txt')
        check(False, 'template protection', 'did not raise', failures)
    except TemplateProtectionError:
        check(True, 'template protection', 'TemplateProtectionError', failures)

    proc = run([
        sys.executable, str(ENGINE / 'export_engine.py'),
        '--project', str(root / 'project.json'),
        '--out', str(TEMPLATES / 'no.pdf'), '--force', '--json',
    ])
    check(proc.returncode == 3, 'export refuse templates',
          'exit %d' % proc.returncode, failures)

    if not a.skip_prior:
        print('\n-- prior regressions P0 / P1 / P2 / P3')
        for name, script, timeout in (
            ('P0', TOOLS / 'run_regression.py', 180),
            ('P1', TOOLS / 'run_p1_regression.py', 120),
            ('P2', TOOLS / 'run_p2_regression.py', 300),
            ('P3', TOOLS / 'run_p3_smoke.py', 180),
        ):
            proc = run([sys.executable, str(script)], timeout=timeout)
            check(proc.returncode == 0, name + ' regression',
                  'exit %d' % proc.returncode, failures)
            if proc.returncode != 0:
                tail = ((proc.stdout or '') + '\n' + (proc.stderr or ''))[-500:]
                print(tail)

    print('\n' + '=' * 68)
    if failures:
        print('RESULT: FAIL (%d)' % len(failures))
        for f in failures:
            print('  - %s' % f)
        return 1
    print('RESULT: PASS  P4 smoke (E1 shell + V1–V4 recorded)')
    print('=' * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
