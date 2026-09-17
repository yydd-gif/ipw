#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 DoD regression: 生成与校验闭环（施工交接说明 §6 P2）.

  python tools/run_p2_regression.py

Does not replace P0 `tools/run_regression.py` (37/171/0) or P1.
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
from _paths import ENGINE, EXAMPLES, REPO, SPEC, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ENGINE))

from lib.catalog_build import find_template, item_folder, numbered_filename  # noqa: E402
from lib.inclusion import (  # noqa: E402
    FIRST_CUT_OPTIONAL_COUNT, FIRST_CUT_OPTIONAL_TEMPLATE_IDS,
    FIRST_CUT_REQUIRED_COUNT, booklet_items, is_required, parse_inclusion,
)
from lib.numbering import (  # noqa: E402
    allocate_one, apply_action, empty_pool, ensure_pool, make_prefix,
    release_one, restore_one,
)
from lib.project_store import read_project, write_project  # noqa: E402
from lib.rule_engine import load_catalog  # noqa: E402
from _common import TemplateProtectionError, assert_not_template_write, iter_templates  # noqa: E402

W_T = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'
W_BS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bookmarkStart'
W_BE = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bookmarkEnd'
MEDIA_RE = __import__('re').compile(r'^word/media/')

DEMO = EXAMPLES / 'demo_project.json'
ABBR = SPEC / '表名缩写字典.csv'
ALIAS = SPEC / '分册别名表.csv'
EXPECT_CATALOG = 56
EXPECT_TPL = 37
EXPECT_UPLOAD = 19
EXPECT_REQUIRED = FIRST_CUT_REQUIRED_COUNT  # 32 = 37 templates − 二-01～05
EXPECT_OPTIONAL = FIRST_CUT_OPTIONAL_COUNT  # 24 = 19 upload + 5 optional templates
WNS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'


def check(ok: bool, name: str, detail: str, failures: list) -> None:
    mark = 'PASS' if ok else 'FAIL'
    print('  [%s] %s — %s' % (mark, name, detail))
    if not ok:
        failures.append('%s: %s' % (name, detail))


def run_cmd(args, cwd=None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')
    return subprocess.run(
        args, cwd=cwd or str(REPO), env=env,
        capture_output=True, text=True, encoding='utf-8',
    )


def last_json_line(text: str) -> dict:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return json.loads(lines[-1])


def copy_demo(dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    pj = dest_dir / 'project.json'
    shutil.copy2(DEMO, pj)
    return pj


def xml_parts_ok(docx: Path) -> tuple:
    """Return (ok, detail) for zip+xml+bookmark pairing — stand-in for Word open."""
    try:
        with zipfile.ZipFile(docx) as z:
            names = set(z.namelist())
            if '[Content_Types].xml' not in names:
                return False, 'missing [Content_Types].xml'
            for n in z.namelist():
                if n.endswith('/') or n.startswith('word/media/'):
                    continue
                if n.endswith('.xml') or n.endswith('.rels'):
                    raw = z.read(n)
                    try:
                        ET.fromstring(raw)
                    except ET.ParseError as e:
                        return False, '%s parse: %s' % (n, e)
            # bookmark pairing in document
            if 'word/document.xml' in names:
                root = ET.fromstring(z.read('word/document.xml'))
                starts, ends = {}, {}
                for el in root.iter(W_BS):
                    i = el.get('{%s}id' % WNS) or el.get('id')
                    starts[i] = el.get('{%s}name' % WNS) or el.get('name')
                for el in root.iter(W_BE):
                    i = el.get('{%s}id' % WNS) or el.get('id')
                    ends[i] = True
                yz = {i: n for i, n in starts.items() if (n or '').startswith('yz_')}
                missing = [i for i in yz if i not in ends]
                if missing:
                    return False, 'unpaired yz_ bookmarks %s' % missing[:3]
    except zipfile.BadZipFile as e:
        return False, 'bad zip: %s' % e
    return True, 'ok'


def media_map(docx: Path) -> dict:
    out = {}
    with zipfile.ZipFile(docx) as z:
        for info in z.infolist():
            if MEDIA_RE.match(info.filename) or '/media/' in info.filename:
                import hashlib
                out[info.filename] = hashlib.sha256(z.read(info.filename)).hexdigest()
    return out


def part_names(docx: Path) -> list:
    with zipfile.ZipFile(docx) as z:
        return [i.filename for i in z.infolist()]


def count_yz_bookmarks(docx: Path) -> int:
    n = 0
    with zipfile.ZipFile(docx) as z:
        for name in z.namelist():
            if not name.endswith('.xml') or not name.startswith('word/'):
                continue
            if 'customXml' in name:
                continue
            try:
                root = ET.fromstring(z.read(name))
            except ET.ParseError:
                continue
            for el in root.iter(W_BS):
                nm = el.get('{%s}name' % WNS) or el.get('name') or ''
                if nm.startswith('yz_'):
                    n += 1
    return n


def numbering_five_cases(failures: list) -> None:
    print('\n-- numbering 5 cases')
    catalog = load_catalog(ABBR, ALIAS)
    item = catalog.by_id['二-01']
    project = json.loads(DEMO.read_text(encoding='utf-8'))
    prefix = make_prefix(project.get('contractNo') or '', item.abbr)
    pool = empty_pool(prefix, item.digits)

    a1 = allocate_one(pool, item.abbr)
    a2 = allocate_one(pool, item.abbr)
    a3 = allocate_one(pool, item.abbr)
    check(a1['no'] == 'YY123-KGBSB-01' and a2['no'] == 'YY123-KGBSB-02'
          and a3['no'] == 'YY123-KGBSB-03' and pool['max'] == 3,
          'case1 allocate 01/02/03',
          '%s %s %s max=%s' % (a1['no'], a2['no'], a3['no'], pool['max']),
          failures)

    rel = release_one(pool, no='YY123-KGBSB-02')
    still_03 = any(r.get('no') == 'YY123-KGBSB-03' for r in pool['allocated'])
    check(still_03 and pool['max'] == 3 and 'YY123-KGBSB-02' in pool['released']
          and not any(r.get('no') == 'YY123-KGBSB-02' for r in pool['allocated']),
          'case2 delete 02, 03 stays 03',
          'max=%s released=%s allocated=%s' % (
              pool['max'], pool['released'],
              [r['no'] for r in pool['allocated']]),
          failures)

    a4 = allocate_one(pool, item.abbr)
    check(a4['no'] == 'YY123-KGBSB-02' and a4.get('reused') is True,
          'case3 allocate reuses smallest released (02)',
          a4['no'], failures)

    # reset to 01,02,03 then release tail 03
    release_one(pool, no='YY123-KGBSB-03')
    check(pool['max'] == 2 and 'YY123-KGBSB-03' not in (pool['released'] or []),
          'case4 release tail 03 shrinks max',
          'max=%s released=%s' % (pool['max'], pool['released']),
          failures)
    a5 = allocate_one(pool, item.abbr)
    check(a5['no'] == 'YY123-KGBSB-03',
          'case4 next allocate is 03 again', a5['no'], failures)

    # case5: release 02 (middle), restore original 02/docId without reallocation
    rec02 = next(r for r in pool['allocated'] if r['no'].endswith('-02'))
    doc_id_02, no_02 = rec02['docId'], rec02['no']
    release_one(pool, doc_id=doc_id_02)
    nos_after = [r['no'] for r in pool['allocated']]
    check('YY123-KGBSB-03' in nos_after and no_02 not in nos_after,
          'case5 after release 02, 03 still 03',
          nos_after, failures)
    restore_one(pool, doc_id_02, no_02)
    nos_restored = [r['no'] for r in pool['allocated']]
    check(no_02 in nos_restored and 'YY123-KGBSB-03' in nos_restored
          and pool['max'] == 3,
          'case5 restore takes original 02, does not reshuffle',
          nos_restored, failures)


def main() -> int:
    failures = []
    print('=' * 68)
    print('P2 regression · 生成与校验闭环')
    print('=' * 68)

    catalog = load_catalog(ABBR, ALIAS)
    tpls = list(iter_templates(TEMPLATES))
    n_tpl = sum(1 for it in catalog.items if find_template(TEMPLATES, it))
    n_up = len(catalog.items) - n_tpl
    check(len(catalog.items) == EXPECT_CATALOG, 'catalog size',
          '%d (expect %d)' % (len(catalog.items), EXPECT_CATALOG), failures)
    check(len(tpls) == EXPECT_TPL and n_tpl == EXPECT_TPL, 'template items',
          'files=%d catalog-hasTemplate=%d' % (len(tpls), n_tpl), failures)
    check(n_up == EXPECT_UPLOAD, 'upload items',
          '%d (expect %d)' % (n_up, EXPECT_UPLOAD), failures)
    n_req = sum(1 for it in catalog.items if is_required(it))
    check(n_req == EXPECT_REQUIRED, 'required inclusion count',
          '%d (expect %d) %s' % (n_req, EXPECT_REQUIRED,
                                 [it.item_id for it in catalog.items if is_required(it)]),
          failures)
    req_ids = tuple(it.item_id for it in booklet_items(catalog.items))
    check(len(req_ids) == EXPECT_REQUIRED, 'first-cut required count',
          '%d ids' % len(req_ids), failures)
    check(all(i not in req_ids for i in FIRST_CUT_OPTIONAL_TEMPLATE_IDS),
          '二-01～05 not in booklet',
          [i for i in FIRST_CUT_OPTIONAL_TEMPLATE_IDS if i in req_ids], failures)
    check('二-10' in req_ids and '二-07' in req_ids,
          'templated items other than 二-01～05 are required',
          '二-10/二-07 in required', failures)
    upload_req = [it.item_id for it in catalog.items
                  if not find_template(TEMPLATES, it) and is_required(it)]
    check(not upload_req, 'upload items must be optional',
          str(upload_req) or 'none required', failures)
    opt_tpl = [it.item_id for it in catalog.items
               if find_template(TEMPLATES, it) and not is_required(it)]
    check(set(opt_tpl) == set(FIRST_CUT_OPTIONAL_TEMPLATE_IDS),
          'only 二-01～05 templated items are optional',
          'optional-tpl=%s' % opt_tpl, failures)
    check(n_req + len([it for it in catalog.items if not is_required(it)]) == EXPECT_CATALOG
          and EXPECT_OPTIONAL == EXPECT_CATALOG - EXPECT_REQUIRED,
          '32 required + 24 optional = 56',
          'req=%d opt=%d' % (n_req, EXPECT_OPTIONAL), failures)
    check(parse_inclusion('重要', '二-01', '有模板') == 'optional'
          and parse_inclusion('普通', '二-10', '有模板') == 'required',
          '软件目录 重要/普通 must not drive 收录',
          '重要→%s 普通→%s' % (
              parse_inclusion('重要', '二-01', '有模板'),
              parse_inclusion('普通', '二-10', '有模板')),
          failures)

    numbering_five_cases(failures)

    print('\n-- numbering CLI')
    td = Path(tempfile.mkdtemp(prefix='yz-p2-num-'))
    try:
        pj = copy_demo(td)
        proc = run_cmd([
            sys.executable, str(ENGINE / 'numbering_engine.py'),
            '--project', str(pj), '--item', '二-01', '--count', '3', '--json',
        ])
        payload = last_json_line(proc.stdout) if proc.stdout.strip() else {}
        check(proc.returncode == 0, 'allocate CLI exit',
              'exit %d %s' % (proc.returncode, payload.get('summary')), failures)
        nos = [it['no'] for it in (payload.get('items') or [])]
        check(nos == ['YY123-KGBSB-01', 'YY123-KGBSB-02', 'YY123-KGBSB-03'],
              'allocate CLI 01/02/03', nos, failures)
        # release 02 via CLI
        proc = run_cmd([
            sys.executable, str(ENGINE / 'numbering_engine.py'),
            '--project', str(pj), '--item', '开工报审表',
            '--action', 'release', '--no', 'YY123-KGBSB-02', '--json',
        ])
        data = read_project(pj)
        pool = (data.get('_numbering') or {}).get('二-01') or {}
        allocated = [r['no'] for r in pool.get('allocated') or []]
        check(proc.returncode == 0 and 'YY123-KGBSB-03' in allocated
              and 'YY123-KGBSB-02' not in allocated
              and 'YY123-KGBSB-02' in (pool.get('released') or []),
              'CLI release 02 keeps 03', allocated, failures)
        missing = run_cmd([sys.executable, str(ENGINE / 'numbering_engine.py'),
                           '--json'])
        check(missing.returncode == 2, 'numbering missing args exit 2',
              'exit %d' % missing.returncode, failures)
        try:
            last_json_line(missing.stdout)
            check(True, 'numbering missing --json', 'last line JSON', failures)
        except Exception as e:
            check(False, 'numbering missing --json', str(e), failures)
    finally:
        shutil.rmtree(td, ignore_errors=True)

    print('\n-- no-template triad (blank / upload / skip)')
    triad = Path(tempfile.mkdtemp(prefix='yz-p2-triad-'))
    try:
        pj = copy_demo(triad)
        for item, mode, expect_file, expect_action in (
            ('一-01', 'upload', '一、依据分册/1、中标通知书/中标通知书.upload.json', 'created'),
            ('一-02', 'skip', None, 'skipped'),
            ('一-03', 'blank', '一、依据分册/3、项目招标控制价评审报告及评审清单/项目招标控制价评审报告及评审清单.docx', 'created'),
        ):
            proc = run_cmd([
                sys.executable, str(ENGINE / 'docgen_engine.py'),
                '--project', str(pj), '--item', item, '--mode', mode,
                '--out', str(triad), '--json',
            ])
            payload = last_json_line(proc.stdout) if proc.stdout.strip() else {}
            act = ((payload.get('items') or [{}])[0]).get('action')
            check(proc.returncode == 0 and act == expect_action,
                  'triad %s %s' % (item, mode),
                  'exit %d action=%s' % (proc.returncode, act), failures)
            if expect_file:
                check((triad / expect_file).exists(), 'triad file %s' % mode,
                      expect_file, failures)
            else:
                recs = [r for r in (read_project(pj).get('_docs') or {}).values()
                        if r.get('itemId') == item]
                check(recs and recs[0].get('skipped') is True,
                      'triad skip marker', str(recs[:1]), failures)
    finally:
        shutil.rmtree(triad, ignore_errors=True)

    print('\n-- docgen booklet (ADR-21: required only)')
    book = WORK / 'p2-booklet'
    if book.exists():
        shutil.rmtree(book)
    pj = copy_demo(book)
    proc = run_cmd([
        sys.executable, str(ENGINE / 'docgen_engine.py'),
        '--project', str(pj), '--item', 'all', '--out', str(book), '--json',
    ])
    if proc.returncode != 0:
        print(proc.stdout[-2000:] if proc.stdout else '')
        print(proc.stderr[-2000:] if proc.stderr else '')
    payload = last_json_line(proc.stdout) if proc.stdout.strip() else {}
    check(proc.returncode == 0, 'docgen all exit',
          'exit %d %s' % (proc.returncode, payload.get('summary')), failures)
    data = read_project(pj)
    n_docs = len(data.get('_docs') or {})
    created_ids = [r.get('itemId') for r in (payload.get('items') or [])]
    optional_in_all = [i for i in created_ids if i in FIRST_CUT_OPTIONAL_TEMPLATE_IDS
                       or i not in req_ids]
    check(not optional_in_all, 'all must not create optionals (DoD ⑤ FAIL if leak)',
          optional_in_all[:8], failures)
    check(n_docs == EXPECT_REQUIRED, '_docs count required-only',
          '%d (expect %d; generating optionals into booklet must fail)' % (
              n_docs, EXPECT_REQUIRED), failures)
    check((payload.get('stats') or {}).get('selected') == EXPECT_REQUIRED,
          'all selected == required',
          str((payload.get('stats') or {}).get('selected')), failures)
    snap = (data.get('_catalogSnapshot') or {}).get('items') or []
    check(len(snap) == EXPECT_CATALOG, 'catalog snapshot still lists all rows',
          '%d items' % len(snap), failures)
    snap_inc = {it.get('itemId'): it.get('inclusion') for it in snap}
    check(snap_inc.get('二-07') == 'required' and snap_inc.get('二-01') == 'optional'
          and snap_inc.get('一-01') == 'optional',
          'snapshot inclusion column (dictionary 收录 only)',
          '二-07=%s 二-01=%s 一-01=%s' % (
              snap_inc.get('二-07'), snap_inc.get('二-01'), snap_inc.get('一-01')),
          failures)

    # paths — required numbered 设备开箱验收记录 / 施工日志 in booklet; 二-01 optional not
    kg = '二、过程分册/1、开工报审表/YY123-KGBSB-01_开工报审表.docx'
    sb = '二、过程分册/7、设备开箱验收记录/YY123-SBKXYSJL-01_设备开箱验收记录.docx'
    log = '二、过程分册/10、施工日志/YY123-SGRZ-001_施工日志.docx'
    blank = '一、依据分册/1、中标通知书/中标通知书.docx'
    check((book / sb).is_file(), 'numbered path (required 二-07)', sb, failures)
    check((book / log).is_file(), 'numbered path (required 施工日志)', log, failures)
    check(not (book / kg).exists(), 'optional 开工报审表 not in booklet', kg, failures)
    check(not (book / blank).exists(), 'optional upload not in booklet', blank, failures)
    gen_docx = [p for p in book.rglob('*.docx') if not p.name.startswith('~$')]
    check(len(gen_docx) == EXPECT_REQUIRED, 'generated docx count required-only',
          '%d (expect %d required; 56 would mean optionals bulk-generated)' % (
              len(gen_docx), EXPECT_REQUIRED),
          failures)

    # repeat generate-all: skip required that exist; still no optionals
    proc2 = run_cmd([
        sys.executable, str(ENGINE / 'docgen_engine.py'),
        '--project', str(pj), '--item', 'all', '--out', str(book), '--json',
    ])
    payload2 = last_json_line(proc2.stdout) if proc2.stdout.strip() else {}
    data2 = read_project(pj)
    gen_docx2 = [p for p in book.rglob('*.docx') if not p.name.startswith('~$')]
    check(proc2.returncode == 0 and payload2.get('stats', {}).get('skipped') == EXPECT_REQUIRED,
          'repeat generate-all skips required only',
          'skipped=%s created=%s' % (
              (payload2.get('stats') or {}).get('skipped'),
              (payload2.get('stats') or {}).get('created')),
          failures)
    check(len(data2.get('_docs') or {}) == EXPECT_REQUIRED
          and len(gen_docx2) == len(gen_docx),
          'repeat generate-all no duplicate / no optional leak',
          'docs=%d files=%d' % (len(data2.get('_docs') or {}), len(gen_docx2)),
          failures)

    # 新建表格：显式 --item 创建可选 开工报审表 → 01，再追加 02
    proc_opt_kg = run_cmd([
        sys.executable, str(ENGINE / 'docgen_engine.py'),
        '--project', str(pj), '--item', '二-01', '--count', '1',
        '--out', str(book), '--json',
    ])
    pok = last_json_line(proc_opt_kg.stdout) if proc_opt_kg.stdout.strip() else {}
    kg1 = book / kg
    check(proc_opt_kg.returncode == 0 and kg1.is_file(),
          '新建表格 creates numbered optional 二-01',
          str(pok.get('summary')), failures)
    proc3 = run_cmd([
        sys.executable, str(ENGINE / 'docgen_engine.py'),
        '--project', str(pj), '--item', '二-01', '--count', '1',
        '--out', str(book), '--json',
    ])
    p3 = last_json_line(proc3.stdout) if proc3.stdout.strip() else {}
    kg2 = book / '二、过程分册/1、开工报审表/YY123-KGBSB-02_开工报审表.docx'
    check(proc3.returncode == 0 and kg2.is_file(),
          'append second numbered optional',
          str(p3.get('summary')), failures)

    proc_opt = run_cmd([
        sys.executable, str(ENGINE / 'docgen_engine.py'),
        '--project', str(pj), '--item', '一-01', '--out', str(book), '--json',
    ])
    po = last_json_line(proc_opt.stdout) if proc_opt.stdout.strip() else {}
    check(proc_opt.returncode == 0 and (book / blank).is_file(),
          'explicit item creates optional upload (新建表格)',
          str(po.get('summary')), failures)

    # verify after booklet+optional: optional never-created must not be a deficiency
    proc_v0 = run_cmd([
        sys.executable, str(ENGINE / 'verify_engine.py'),
        '--dir', str(book), '--project', str(pj), '--level', 'all', '--json',
    ])
    pv0 = last_json_line(proc_v0.stdout) if proc_v0.stdout.strip() else {}
    inc0 = [e for e in (pv0.get('errors') or []) if e.get('loc') == 'inclusion']
    opt_inc = [e for e in inc0 if (e.get('file') or e.get('key') or '') in (
        '一-02', '二-02', '二-03', '二-04', '二-05')]
    check(not any(e.get('level') == 'block' for e in inc0) and not opt_inc,
          'verify does not hard-block optional not-created',
          'inc=%s' % inc0[:3], failures)

    print('\n-- anchors + diff_parts (media / no lost parts)')
    kg_doc = book / kg
    if kg_doc.is_file():
        ok_xml, detail = xml_parts_ok(kg_doc)
        check(ok_xml, 'Word-open stand-in (xml/zip/bookmarks)', detail, failures)
        n_yz = count_yz_bookmarks(kg_doc)
        check(n_yz >= 1, 'yz_ bookmarks written', '%d' % n_yz, failures)
        with zipfile.ZipFile(kg_doc) as z:
            check('customXml/item1.xml' in z.namelist(),
                  'customXml ledger', 'item1.xml', failures)
            ledger = z.read('customXml/item1.xml').decode('utf-8', 'ignore')
            check('yz_projectName' in ledger or 'projectName' in ledger,
                  'ledger mentions projectName', 'ok' if 'projectName' in ledger else ledger[:80],
                  failures)
        tpl = TEMPLATES / '二、过程分册/1、开工报审表.docx'
        lost = set(part_names(tpl)) - set(part_names(kg_doc))
        # directory entries may drop; only care about files
        lost_files = {n for n in lost if not n.endswith('/')}
        check(not lost_files, 'no lost parts vs template',
              'ok' if not lost_files else str(sorted(lost_files)[:6]), failures)
        sm, dm = media_map(tpl), media_map(kg_doc)
        mismatch = [k for k, hv in sm.items() if dm.get(k) != hv]
        check(not mismatch, 'media byte-identical',
              'ok' if not mismatch else str(mismatch[:4]), failures)

    log_doc = book / log
    if log_doc.is_file():
        with zipfile.ZipFile(log_doc) as z:
            xml = z.read('word/document.xml').decode('utf-8', 'ignore')
        check('{{weather}}' not in xml and '晴' in xml,
              'cross-run weather still filled', '施工日志', failures)

    print('\n-- verify leftover gate + location')
    proc_v = run_cmd([
        sys.executable, str(ENGINE / 'verify_engine.py'),
        '--dir', str(book), '--project', str(pj), '--json',
    ])
    pv = last_json_line(proc_v.stdout) if proc_v.stdout.strip() else {}
    # booklet includes blanks with no leftovers; template docs filled from demo
    check(proc_v.returncode == 0, 'verify booklet exit',
          'exit %d %s' % (proc_v.returncode, pv.get('summary')), failures)

    # plant a leftover and require loc
    planted = WORK / 'p2-leftover'
    if planted.exists():
        shutil.rmtree(planted)
    planted.mkdir(parents=True)
    sample = planted / 'leak.docx'
    shutil.copy2(kg_doc if kg_doc.is_file() else tpls[0], sample)
    # inject {{projectName}} into document.xml
    with zipfile.ZipFile(sample, 'r') as zin:
        items = zin.infolist()
        contents = {it.filename: zin.read(it.filename) for it in items}
    doc_xml = contents['word/document.xml'].decode('utf-8')
    # append a paragraph with leftover before </w:body>
    inject = (
        '<w:p><w:r><w:t>{{projectName}}</w:t></w:r></w:p>'
    )
    if '</w:body>' in doc_xml:
        doc_xml = doc_xml.replace('</w:body>', inject + '</w:body>', 1)
        contents['word/document.xml'] = doc_xml.encode('utf-8')
        with zipfile.ZipFile(sample, 'w', zipfile.ZIP_DEFLATED) as zout:
            for it in items:
                zout.writestr(it, contents[it.filename])
    proc_bad = run_cmd([
        sys.executable, str(ENGINE / 'verify_engine.py'),
        '--dir', str(planted), '--json',
    ])
    pb = last_json_line(proc_bad.stdout) if proc_bad.stdout.strip() else {}
    check(proc_bad.returncode == 1, 'verify leftover exit 1',
          'exit %d' % proc_bad.returncode, failures)
    errs = pb.get('errors') or []
    hit = [e for e in errs if e.get('key') == 'projectName']
    check(bool(hit), 'verify reports leftover key',
          'errors=%d' % len(errs), failures)
    if hit:
        loc = hit[0].get('loc') or ''
        reason = hit[0].get('reason') or ''
        check(('段' in loc or '表' in loc) and 'projectName' in reason,
              'verify precise location',
              'loc=%s reason=%s' % (loc, reason[:80]), failures)

    print('\n-- fill v1.0 anchors on demo (keep 37/171/0)')
    proc_f = run_cmd([
        sys.executable, str(ENGINE / 'fill_engine.py'), '--demo', '--json',
        '--anchor', 'on',
    ])
    pf = last_json_line(proc_f.stdout) if proc_f.stdout.strip() else {}
    st = pf.get('stats') or {}
    check(proc_f.returncode == 0, 'fill --demo exit',
          'exit %d' % proc_f.returncode, failures)
    check(st.get('docs') == 37 and st.get('filled') == 171 and st.get('residual') == 0,
          'fill 37/171/0 with anchors',
          '%s/%s/%s' % (st.get('docs'), st.get('filled'), st.get('residual')),
          failures)
    demo_one = WORK / 'demo-fill' / '二、过程分册' / '1、开工报审表.docx'
    if demo_one.is_file():
        ok_xml, detail = xml_parts_ok(demo_one)
        check(ok_xml, 'demo-fill Word-open stand-in', detail, failures)
        check(count_yz_bookmarks(demo_one) >= 1, 'demo-fill yz_ bookmarks',
              str(count_yz_bookmarks(demo_one)), failures)

    print('\n-- red lines')
    try:
        assert_not_template_write(TEMPLATES / 'probe.txt')
        check(False, 'template protection', 'did not raise', failures)
    except TemplateProtectionError:
        check(True, 'template protection', 'TemplateProtectionError', failures)
    proc_tpl = run_cmd([
        sys.executable, str(ENGINE / 'docgen_engine.py'),
        '--project', str(pj), '--item', 'all',
        '--out', str(TEMPLATES), '--json',
    ])
    check(proc_tpl.returncode == 3, 'docgen refuse templates out',
          'exit %d' % proc_tpl.returncode, failures)

    print('\n' + '=' * 68)
    if failures:
        print('RESULT: FAIL (%d)' % len(failures))
        for f in failures:
            print('  - %s' % f)
        return 1
    print('RESULT: PASS  P2 DoD  必选成册 / 可选新建表格 / 编号 5 用例 / 校验定位 / 锚点')
    print('=' * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
