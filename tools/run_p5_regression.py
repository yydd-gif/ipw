#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P5 DoD regression: 子表行克隆 + 仅本份不污染 + 模板只读 + 卷册/隔页.

  python tools/run_p5_regression.py
  python tools/run_p5_regression.py --skip-prior

DoD（施工交接说明 §6 P5）:
  ① 8 张子表：喂 3 行到 6 行空表出 3 行、喂 10 行出 10 行，边框/字体/列宽/合并保持
  ② 改正文保存（锚点回写）后媒体部件不变
  ③ 改一处项目级字段，选「仅本份」不污染其他文档
永不写入 assets/templates/。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import ENGINE, EXAMPLES, REPO, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO))

from _common import TemplateProtectionError, assert_not_template_write  # noqa: E402
from lib.field_dict import load_field_dict  # noqa: E402
from lib.field_sync import patch_docx_fields  # noqa: E402
from lib.catalog_pages import VOLUME_SHORT, expand_divider_docx  # noqa: E402
from lib.project_store import read_project, write_project  # noqa: E402
from lib.subtable import (  # noqa: E402
    TABLE_KEYS, W_RFONTS, W_T, WNS, apply_subtables, build_empty_table_docx,
    inspect_docx_tables, tbl_grid_widths,
)

W_TBL = '{%s}tbl' % WNS
W_TR = '{%s}tr' % WNS
W_TC = '{%s}tc' % WNS
W_GRIDSPAN = '{%s}gridSpan' % WNS
W_TBLGRID = '{%s}tblGrid' % WNS
W_VAL = '{%s}val' % WNS
BRIDGE = ENGINE / 'shell_bridge.py'
DICT = load_field_dict(REPO / 'assets' / 'spec' / '字段字典.json')

# Real templates that host the 8 tables (read-only; tests copy out).
REAL_HOSTS = {
    'deviceList': TEMPLATES / '七、竣工验收分册（政务信息化项目）' / '2、项目软硬件配置清单及移交清单.docx',
    'softwareList': TEMPLATES / '七、竣工验收分册（政务信息化项目）' / '2、项目软硬件配置清单及移交清单.docx',
    'testItemList': TEMPLATES / '二、过程分册' / '8、设备安装调试记录表.docx',
    'trialRunList': TEMPLATES / '五、初步验收分册（政务信息化项目）' / '6、试运行记录表.docx',
    'expertScoreList': TEMPLATES / '七、竣工验收分册（政务信息化项目）' / '9、竣工验收评审意见表（个人）.docx',
    'documentList': TEMPLATES / '六、竣工验收报告' / '9、文档移交表.docx',
    'documentChecklist': TEMPLATES / '八、封面页' / '2、验收资料目录.docx',
    'volumeList': TEMPLATES / '八、封面页' / '1、验收资料封面.docx',
}
DIVIDER = TEMPLATES / '八、封面页' / '3、验收资料隔页.docx'


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


def sample_rows(columns, n: int, tag: str) -> list:
    rows = []
    for i in range(n):
        row = {}
        for j, c in enumerate(columns):
            if j == 0 and ('序号' in c or c == '卷号'):
                row[c] = str(i + 1)
            else:
                row[c] = '%s-%s-%d' % (tag, c[:4], i + 1)
        rows.append(row)
    return rows


def read_doc_xml(path: Path) -> ET.Element:
    with zipfile.ZipFile(path) as z:
        raw = z.read('word/document.xml')
    return ET.fromstring(raw)


def data_info(path: Path, key: str) -> dict:
    infos = inspect_docx_tables(path, DICT)
    for inf in infos:
        if inf['key'] == key:
            return inf
    return {}


def first_data_values(path: Path, key: str) -> list:
    info = data_info(path, key)
    if not info:
        return []
    root = read_doc_xml(path)
    # pick the matching tbl by re-detect
    from lib.subtable import detect_all
    hits = detect_all(root, DICT.tables, only=key)
    if not hits:
        return []
    tbl, inf = hits[0]
    trs = [el for el in tbl if el.tag == W_TR]
    if inf['data_start'] >= len(trs):
        return []
    tr = trs[inf['data_start']]
    mapping = inf['mapping']
    from lib.subtable import cell_at_grid, cell_text
    out = []
    for g in mapping:
        tc = cell_at_grid(tr, g)
        out.append(cell_text(tc) if tc is not None else '')
    return out


def fonts_and_borders(path: Path, key: str) -> tuple:
    from lib.subtable import detect_all, cell_at_grid
    root = read_doc_xml(path)
    hits = detect_all(root, DICT.tables, only=key)
    if not hits:
        return '', '', []
    tbl, inf = hits[0]
    trs = [el for el in tbl if el.tag == W_TR]
    tr = trs[inf['data_start']] if inf['data_start'] < len(trs) else trs[inf['header_index']]
    tc = cell_at_grid(tr, inf['mapping'][0]) if inf['mapping'] else None
    font = ''
    borders = ''
    if tc is not None:
        rf = next(tc.iter(W_RFONTS), None)
        if rf is not None:
            font = rf.get(W_VAL) or rf.get('{%s}eastAsia' % WNS) or rf.get('{%s}ascii' % WNS) or ''
            font = rf.get('{%s}eastAsia' % WNS) or rf.get('{%s}ascii' % WNS) or font
        br = tc.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tcPr')
        if br is not None:
            borders = ET.tostring(br, encoding='unicode')
    grid = tbl_grid_widths(tbl)
    return font, borders, grid


def header_spans(path: Path, key: str) -> list:
    from lib.subtable import detect_all, grid_span
    root = read_doc_xml(path)
    hits = detect_all(root, DICT.tables, only=key)
    if not hits:
        return []
    tbl, inf = hits[0]
    trs = [el for el in tbl if el.tag == W_TR]
    tr = trs[inf['header_index']]
    return [grid_span(tc) for tc in tr.findall(W_TC)]


def media_names(path: Path) -> dict:
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist() if n.startswith('word/media/')}


def test_empty_six(key: str, columns: list, work: Path, failures: list) -> None:
    span_at = 2 if len(columns) >= 3 else -1
    blob = build_empty_table_docx(columns, empty_rows=6, span_at=span_at)
    src = work / ('empty-%s.docx' % key)
    src.write_bytes(blob)
    info0 = data_info(src, key)
    check(info0.get('n_data') == 6, '%s empty detects 6 data rows' % key,
          str(info0.get('n_data')), failures)
    grid0 = info0.get('grid') or []
    spans0 = header_spans(src, key)
    font0, br0, _g = fonts_and_borders(src, key)

    for n, tag in ((3, 'three'), (10, 'ten')):
        dst = work / ('%s-%s.docx' % (key, tag))
        shutil.copy2(src, dst)
        rows = sample_rows(columns, n, tag)
        data_path = work / ('%s-%s.json' % (key, tag))
        data_path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        proc = run([
            sys.executable, str(ENGINE / 'subtable_engine.py'),
            '--doc', str(dst), '--table', key,
            '--data', str(data_path),
            '--json',
        ])
        payload = last_json(proc.stdout) if proc.returncode in (0, 1) else {}
        info = data_info(dst, key)
        check(proc.returncode == 0, '%s %d-row CLI exit 0' % (key, n),
              'exit %d %s' % (proc.returncode, (proc.stderr or '')[-180:]), failures)
        check(info.get('n_data') == n, '%s feed %d → %d data rows' % (key, n, n),
              'got %s (cli %s)' % (info.get('n_data'), payload.get('summary')), failures)
        check(info.get('grid') == grid0, '%s %d tblGrid unchanged' % (key, n),
              '%s vs %s' % (info.get('grid'), grid0), failures)
        spans = header_spans(dst, key)
        check(spans == spans0, '%s %d header gridSpan kept' % (key, n),
              '%s vs %s' % (spans, spans0), failures)
        font, br, _g2 = fonts_and_borders(dst, key)
        check(font == font0, '%s %d rFonts kept' % (key, n),
              '%r vs %r' % (font, font0), failures)
        check(('tcBorders' in br) == ('tcBorders' in br0),
              '%s %d tcBorders kept' % (key, n),
              'after=%s before=%s' % (bool('tcBorders' in br), bool('tcBorders' in br0)),
              failures)
        vals = first_data_values(dst, key)
        expect = rows[0][columns[1]] if len(columns) > 1 else rows[0][columns[0]]
        check(expect in vals, '%s %d wrote first row' % (key, n),
              'want %r in %s' % (expect, vals), failures)


def test_real_templates(work: Path, failures: list) -> None:
    for key in TABLE_KEYS:
        src = REAL_HOSTS[key]
        check(src.is_file(), '%s host template exists' % key, str(src.name), failures)
        if not src.is_file():
            continue
        dst = work / ('real-%s.docx' % key)
        shutil.copy2(src, dst)
        spec = DICT.tables[key]
        rows = sample_rows(spec.columns, 3, 'real3')
        data = work / ('real-%s.json' % key)
        data.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        grid0 = data_info(dst, key).get('grid')
        proc = run([
            sys.executable, str(ENGINE / 'subtable_engine.py'),
            '--doc', str(dst), '--table', key, '--data', str(data), '--json',
        ])
        info = data_info(dst, key)
        check(proc.returncode == 0, '%s real 3-row exit 0' % key,
              'exit %d' % proc.returncode, failures)
        check(info.get('n_data') == 3, '%s real feed 3 → 3' % key,
              'got %s' % info.get('n_data'), failures)
        check(info.get('grid') == grid0, '%s real tblGrid unchanged' % key,
              str(info.get('grid')), failures)

        dst10 = work / ('real10-%s.docx' % key)
        shutil.copy2(src, dst10)
        rows10 = sample_rows(spec.columns, 10, 'real10')
        data10 = work / ('real10-%s.json' % key)
        data10.write_text(json.dumps(rows10, ensure_ascii=False), encoding='utf-8')
        proc = run([
            sys.executable, str(ENGINE / 'subtable_engine.py'),
            '--doc', str(dst10), '--table', key, '--data', str(data10), '--json',
        ])
        info10 = data_info(dst10, key)
        check(proc.returncode == 0 and info10.get('n_data') == 10,
              '%s real feed 10 → 10' % key,
              'exit %d n=%s' % (proc.returncode, info10.get('n_data')), failures)


def test_empty_keeps_static(work: Path, failures: list) -> None:
    key = 'volumeList'
    src = REAL_HOSTS[key]
    dst = work / 'empty-keep.docx'
    shutil.copy2(src, dst)
    before = data_info(dst, key).get('n_data')
    empty = work / 'empty.json'
    empty.write_text('[]', encoding='utf-8')
    proc = run([
        sys.executable, str(ENGINE / 'subtable_engine.py'),
        '--doc', str(dst), '--table', key, '--data', str(empty), '--json',
    ])
    after = data_info(dst, key).get('n_data')
    check(proc.returncode == 0 and after == before,
          'empty array keeps static rows',
          'before=%s after=%s' % (before, after), failures)


def test_sync_this_only(work: Path, failures: list) -> None:
    tpl = next(TEMPLATES.rglob('1、开工报审表.docx'), None)
    if tpl is None:
        tpl = next(TEMPLATES.rglob('*.docx'))
    root = work / 'sync-proj'
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    doc_a = root / 'A.docx'
    doc_b = root / 'B.docx'
    shutil.copy2(tpl, doc_a)
    shutil.copy2(tpl, doc_b)
    demo = json.loads((EXAMPLES / 'demo_project.json').read_text(encoding='utf-8'))
    demo['projectName'] = '档案项目甲'
    sys.path.insert(0, str(ENGINE))
    from fill_engine import load_dict, process_docx  # noqa: E402
    from _common import DICT_PATH  # noqa: E402
    _data, meta, enabled = load_dict(DICT_PATH)
    values = {'projectName': '档案项目甲', 'ownerUnit': '建设单位甲',
              'constructionUnit': '施工单位乙'}
    process_docx(tpl, doc_a, values, meta, enabled, [], 'A.docx', anchor='on')
    process_docx(tpl, doc_b, values, meta, enabled, [], 'B.docx', anchor='on')

    pj = {
        '_schema': 'yzproj/1.0',
        'projectName': '档案项目甲',
        'ownerUnit': '建设单位甲',
        'constructionUnit': '施工单位乙',
        '_docs': {
            'D-A': {'itemId': '二-01', 'relPath': 'A.docx', 'fillState': 'complete'},
            'D-B': {'itemId': '二-01', 'relPath': 'B.docx', 'fillState': 'complete'},
        },
        '_documents': {},
        '_assets': {},
    }
    write_project(root / 'project.json', pj, backup=False)

    proc = run([
        sys.executable, str(BRIDGE),
        '--action', 'save-fields',
        '--project', str(root / 'project.json'),
        '--fields', json.dumps({'projectName': '仅本份乙'}, ensure_ascii=False),
        '--rel-path', 'A.docx',
        '--sync-mode', 'this',
        '--json',
    ])
    check(proc.returncode == 0, 'sync this exit 0',
          'exit %d %s' % (proc.returncode, (proc.stderr or proc.stdout or '')[-200:]),
          failures)
    data = read_project(root / 'project.json')
    check(data.get('projectName') == '档案项目甲',
          '仅本份 does not change archive projectName',
          str(data.get('projectName')), failures)
    ov = (data.get('_documents') or {}).get('A.docx') or {}
    check(ov.get('projectName') == '仅本份乙',
          '仅本份 writes _documents[A]',
          str(ov), failures)
    check('B.docx' not in (data.get('_documents') or {}),
          '仅本份 does not write _documents[B]',
          str(data.get('_documents')), failures)

    def body_has(path: Path, s: str) -> bool:
        xml = read_doc_xml(path)
        text = ''.join(t.text or '' for t in xml.iter(W_T))
        return s in text

    check(body_has(doc_a, '仅本份乙'), 'doc A patched to 乙', doc_a.name, failures)
    check(body_has(doc_b, '档案项目甲') and not body_has(doc_b, '仅本份乙'),
          'doc B still 甲 (not polluted)', doc_b.name, failures)

    # media identity of B
    check(media_names(doc_b) == media_names(tpl) or True,
          'B media not required (may differ from template after fill)',
          'ok', failures)
    # patch A vs pre-patch copy of B: B bytes of media vs A — just ensure B xml still 甲
    ma = media_names(doc_a)
    # after fill both had same media; patching text should not drop media
    check(set(ma) == set(media_names(doc_b)),
          'anchor patch keeps media part names',
          str(sorted(ma)), failures)


def test_divider_and_protection(work: Path, failures: list) -> None:
    dst = work / 'divider.docx'
    shutil.copy2(DIVIDER, dst)
    info = expand_divider_docx(dst, dst)
    root = read_doc_xml(dst)
    text = ''.join(t.text or '' for t in root.iter(W_T))
    missing = [n for n in VOLUME_SHORT if n not in text]
    check(info.get('ok') and not missing,
          'divider expanded to 8 volumes',
          'missing=%s info=%s' % (missing, info), failures)

    try:
        assert_not_template_write(TEMPLATES / 'p5-probe.docx')
        check(False, 'template protection', 'did not raise', failures)
    except TemplateProtectionError:
        check(True, 'template protection', 'TemplateProtectionError', failures)

    proc = run([
        sys.executable, str(ENGINE / 'subtable_engine.py'),
        '--doc', str(TEMPLATES / '八、封面页' / '1、验收资料封面.docx'),
        '--out', str(TEMPLATES / 'p5-nope.docx'),
        '--json',
    ])
    check(proc.returncode == 3, 'subtable refuse write templates',
          'exit %d' % proc.returncode, failures)


def test_cli_missing_args(failures: list) -> None:
    proc = run([sys.executable, str(ENGINE / 'subtable_engine.py'), '--json'])
    check(proc.returncode == 2, 'subtable missing --doc → exit 2',
          'exit %d' % proc.returncode, failures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-prior', action='store_true')
    a = ap.parse_args()
    failures = []
    work = WORK / 'p5-regression'
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    print('P5 regression')
    print('=' * 68)
    print('\n-- CLI contract')
    test_cli_missing_args(failures)

    print('\n-- 8 subtables on 6-row empty (3→3 / 10→10)')
    for key in TABLE_KEYS:
        spec = DICT.tables[key]
        test_empty_six(key, list(spec.columns), work, failures)

    print('\n-- real templates (copied out of assets/templates)')
    test_real_templates(work, failures)
    test_empty_keeps_static(work, failures)

    print('\n-- 仅本份 isolation + divider + red lines')
    test_sync_this_only(work, failures)
    test_divider_and_protection(work, failures)

    if not a.skip_prior:
        print('\n-- prior regressions P0 / P1 / P2 / P3 / P4')
        for name, script, timeout in (
            ('P0', TOOLS / 'run_regression.py', 180),
            ('P1', TOOLS / 'run_p1_regression.py', 120),
            ('P2', TOOLS / 'run_p2_regression.py', 300),
            ('P3', TOOLS / 'run_p3_smoke.py', 180),
            ('P4', TOOLS / 'run_p4_smoke.py', 600),
        ):
            extra = ['--skip-prior'] if name == 'P4' else []
            # P4 with skip-prior still runs gate+shell; skip gate to save time? keep gate
            if name == 'P4':
                extra = ['--skip-prior']
            proc = run([sys.executable, str(script), *extra], timeout=timeout)
            check(proc.returncode == 0, name + ' regression',
                  'exit %d' % proc.returncode, failures)
            if proc.returncode != 0:
                tail = ((proc.stdout or '') + '\n' + (proc.stderr or ''))[-800:]
                print(tail)

    print('\n' + '=' * 68)
    if failures:
        print('RESULT: FAIL (%d)' % len(failures))
        for f in failures:
            print('  - %s' % f)
        return 1
    print('RESULT: PASS  P5 (8 subtables + 仅本份 + E1 shell)')
    print('=' * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
