#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验闸门 · 残留占位符精确定位 + §7 全量口径.

规格：数据与规则规格.md §3.7 / §7
  python assets/engine/verify_engine.py --dir work/booklet --project work/booklet/project.json --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# Windows embeddable CPython (python._pth) omits the script dir from sys.path.
_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent.parent, _HERE):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from _common import (
    BASE, DICT_PATH, emit_progress, emit_result, exit_env, exit_param,
    result_payload, wns_tag,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.numbering import parse_seq  # noqa: E402
from lib.project_store import ProjectStoreError, read_project  # noqa: E402

W_T = wns_tag('t')
W_P = wns_tag('p')
W_TBL = wns_tag('tbl')
W_TR = wns_tag('tr')
W_TC = wns_tag('tc')
W_SDT = wns_tag('sdt')
W_SDT_CONTENT = wns_tag('sdtContent')
W_BODY = wns_tag('body')
PART_RE = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')
PH_RE = re.compile(r'\{\{([^{}]+)\}\}')
DATE_PREFIX = 'date:'
PLACEHOLDER_HINTS = ('#rows', '/rows', 'image:', 'upload:')

# 日期留白豁免：年　　月　　日 / 日　期：
DATE_BLANK_RE = re.compile(r'年[\s\u3000]*月[\s\u3000]*日|日[\s\u3000]*期[：:]')
# 自动生成后日期误填：年+数字+月
DATE_FILLED_RE = re.compile(r'年\s*\d{1,4}\s*月')


def load_dict_sets(dict_path: Path):
    enabled, known = set(), set()
    if not dict_path.exists():
        return enabled, known
    data = json.loads(dict_path.read_text(encoding='utf-8'))
    for g in data.get('groups', []):
        for f in g.get('fields', []):
            enabled.add(f['key'])
            known.add(f['key'])
    for f in data.get('disabledFields', []):
        known.add(f.get('key'))
    for f in data.get('removedFields', {}).get('fields', []):
        known.add(f.get('key'))
    known.discard(None)
    return enabled, known


def _para_text(p) -> str:
    return ''.join(t.text or '' for t in p.iter(W_T))


def locate_hits(root, part: str, file_rel: str) -> list:
    """Return leftover {{key}} hits with 段N / 表M行R列C."""
    hits = []
    body = root.find(W_BODY)
    nodes = list(body) if body is not None else list(root)

    pno, tno = 0, 0

    def feed(child, loc_prefix=''):
        nonlocal pno, tno
        if child.tag == W_P:
            pno += 1
            loc = '%s段%d' % (loc_prefix, pno)
            text = _para_text(child)
            for m in PH_RE.finditer(text):
                hits.append({
                    'file': file_rel, 'part': part, 'key': m.group(1).strip(),
                    'loc': loc, 'reason': '残留占位符 {{%s}}' % m.group(1).strip(),
                    'level': 'block', 'text': text[:80],
                })
        elif child.tag == W_TBL:
            tno += 1
            for r, tr in enumerate([x for x in child if x.tag == W_TR], 1):
                for c, tc in enumerate([x for x in tr if x.tag == W_TC], 1):
                    loc = '%s表%d行%d列%d' % (loc_prefix, tno, r, c)
                    text = _para_text(tc)
                    for m in PH_RE.finditer(text):
                        hits.append({
                            'file': file_rel, 'part': part,
                            'key': m.group(1).strip(),
                            'loc': loc,
                            'reason': '残留占位符 {{%s}}' % m.group(1).strip(),
                            'level': 'block', 'text': text[:80],
                        })
        elif child.tag == W_SDT:
            for sub in child:
                if sub.tag == W_SDT_CONTENT:
                    for x in sub:
                        feed(x, loc_prefix)

    for child in nodes:
        feed(child)
    # header/footer have no body — still walked via nodes=list(root)
    if body is None and not hits:
        pno = 0
        for p in root.iter(W_P):
            pno += 1
            text = _para_text(p)
            for m in PH_RE.finditer(text):
                hits.append({
                    'file': file_rel, 'part': part, 'key': m.group(1).strip(),
                    'loc': '段%d' % pno,
                    'reason': '残留占位符 {{%s}}' % m.group(1).strip(),
                    'level': 'block', 'text': text[:80],
                })
    return hits


def scan_file(path: Path, root_dir: Path) -> tuple:
    hits = []
    date_warns = []
    try:
        rel = str(path.relative_to(root_dir)).replace('\\', '/')
    except ValueError:
        rel = str(path)
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not PART_RE.match(name):
                    continue
                try:
                    root = ET.fromstring(z.read(name))
                except ET.ParseError:
                    hits.append({
                        'file': rel, 'part': name, 'key': '',
                        'loc': '-', 'reason': 'XML 无法解析', 'level': 'block',
                    })
                    continue
                part_short = name.replace('word/', '').replace('.xml', '')
                hits.extend(locate_hits(root, part_short, rel))
                full = ''.join(t.text or '' for t in root.iter(W_T))
                if DATE_FILLED_RE.search(full) and not DATE_BLANK_RE.search(full):
                    # only warn when a 年N月 pattern appears (auto-fill smell)
                    date_warns.append({
                        'file': rel, 'part': part_short, 'key': '',
                        'loc': '-', 'reason': '日期被误填', 'level': 'warn',
                    })
    except zipfile.BadZipFile:
        hits.append({
            'file': rel, 'part': '-', 'key': '',
            'loc': '-', 'reason': '文件损坏', 'level': 'block',
        })
    return hits, date_warns


def classify_ph(hit: dict, enabled: set, known: set) -> dict:
    key = hit.get('key') or ''
    if not key:
        return hit
    if key.startswith(DATE_PREFIX) or any(h in key for h in PLACEHOLDER_HINTS):
        hit['level'] = 'warn'
        hit['reason'] = '特殊占位符 {{%s}}（豁免阻断）' % key
        return hit
    if key in enabled:
        hit['level'] = 'block'
        hit['reason'] = '残留占位符 {{%s}} @ %s' % (key, hit.get('loc') or '-')
        return hit
    if key in known:
        hit['level'] = 'warn'
        hit['reason'] = '停用/归档字段残留 {{%s}} @ %s' % (key, hit.get('loc') or '-')
        return hit
    hit['level'] = 'block'
    hit['reason'] = '未定义 key {{%s}} @ %s' % (key, hit.get('loc') or '-')
    return hit


def _is_empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def check_required(project: dict) -> list:
    errors = []
    for key, label in (
        ('projectName', '项目名称'),
        ('ownerUnit', '建设单位'),
        ('constructionUnit', '承建单位'),
    ):
        if _is_empty(project.get(key)):
            errors.append({
                'file': 'project.json', 'part': '-', 'key': key, 'loc': key,
                'reason': '必填缺失：%s' % label, 'level': 'block',
            })
    # contractNo 有条件必填：其它字段暗示有合同时
    if project.get('_fieldSources', {}).get('contractNo') and _is_empty(project.get('contractNo')):
        errors.append({
            'file': 'project.json', 'part': '-', 'key': 'contractNo', 'loc': 'contractNo',
            'reason': '必填缺失：合同编号（有条件）', 'level': 'block',
        })
    # 规格：contractNo 有条件但为空 → block。若项目已填了大量合同相关字段也算条件触发
    if _is_empty(project.get('contractNo')) and not _is_empty(project.get('contractAmount')):
        errors.append({
            'file': 'project.json', 'part': '-', 'key': 'contractNo', 'loc': 'contractNo',
            'reason': '必填缺失：合同编号（有条件）', 'level': 'block',
        })
    return errors


def check_missing_files(project: dict, root: Path) -> list:
    errors = []
    for did, rec in (project.get('_docs') or {}).items():
        if not isinstance(rec, dict):
            continue
        if rec.get('skipped'):
            continue
        rel = rec.get('relPath') or ''
        if not rel or rel.endswith('/') or Path(rel).suffix == '':
            # skip-mode 目录占位
            continue
        dest = root / rel
        if not dest.exists():
            errors.append({
                'file': rel, 'part': '-', 'key': did, 'loc': '-',
                'reason': '文档缺失：_docs[%s] 指向的文件不存在' % did,
                'level': 'block',
            })
    return errors


def check_numbering(project: dict) -> list:
    errors = []
    seen_no = {}  # (itemId, no) -> docId
    seen_id = {}
    for item_id, pool in (project.get('_numbering') or {}).items():
        if not isinstance(pool, dict):
            continue
        allocated = pool.get('allocated') or []
        released = set(pool.get('released') or [])
        seqs = []
        for rec in allocated:
            if not isinstance(rec, dict):
                continue
            did, no = rec.get('docId'), rec.get('no')
            if did and did in seen_id:
                errors.append({
                    'file': item_id, 'part': '-', 'key': did, 'loc': '-',
                    'reason': '编号重复：同一 docId 对应多个编号', 'level': 'block',
                })
            if did:
                seen_id[did] = no
            if no:
                key = (item_id, no)
                if key in seen_no and seen_no[key] != did:
                    errors.append({
                        'file': item_id, 'part': '-', 'key': no, 'loc': '-',
                        'reason': '编号重复：同目录项两个 docId 同号 %s' % no,
                        'level': 'block',
                    })
                seen_no[key] = did
                try:
                    seqs.append(parse_seq(no))
                except Exception:
                    pass
        if seqs:
            seqs_sorted = sorted(set(seqs))
            holes = []
            for a, b in zip(seqs_sorted, seqs_sorted[1:]):
                for h in range(a + 1, b):
                    # 允许中间留坑（released 含该号）
                    hole_in_released = any(
                        True for n in released
                        if _seq_or_none(n) == h)
                    if not hole_in_released:
                        # 非 tail：max 以内的空洞且不在 released → warn
                        holes.append(h)
            if holes:
                errors.append({
                    'file': item_id, 'part': '-', 'key': '', 'loc': '-',
                    'reason': '编号断号：缺 %s（非 released 留坑）' % holes,
                    'level': 'warn',
                })
    return errors


def _seq_or_none(no):
    try:
        return parse_seq(no)
    except Exception:
        return None


def extract_field_values(docx: Path, keys: set) -> dict:
    """Best-effort: yz_ bookmark inner text, else skip."""
    found = {k: [] for k in keys}
    W_BS = wns_tag('bookmarkStart')
    W_BE = wns_tag('bookmarkEnd')
    try:
        with zipfile.ZipFile(docx) as z:
            raw = z.read('word/document.xml')
    except (KeyError, zipfile.BadZipFile, OSError):
        return found
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return found
    # walk document in order, track open yz_ bookmarks
    open_ids = {}  # id -> key

    def local(el, name):
        v = el.get(wns_tag(name))
        return v if v is not None else el.get(name)

    # flatten
    for el in root.iter():
        if el.tag == W_BS:
            name = local(el, 'name') or ''
            bid = local(el, 'id')
            if name.startswith('yz_'):
                key = name[3:]
                if '_' in key and key.rsplit('_', 1)[-1].isdigit():
                    key = key.rsplit('_', 1)[0]
                if key in keys:
                    open_ids[bid] = (key, [])
        elif el.tag == W_T:
            for bid, (key, buf) in list(open_ids.items()):
                buf.append(el.text or '')
        elif el.tag == W_BE:
            bid = local(el, 'id')
            if bid in open_ids:
                key, buf = open_ids.pop(bid)
                found[key].append(''.join(buf))
    return found


def check_unit_consistency(root: Path, keys=('constructionUnit', 'ownerUnit',
                                             'supervisionUnit')) -> list:
    errors = []
    collected = {k: {} for k in keys}  # key -> {value: [files]}
    docs = sorted(p for p in root.rglob('*.docx') if not p.name.startswith('~$'))
    for p in docs:
        vals = extract_field_values(p, set(keys))
        try:
            rel = str(p.relative_to(root)).replace('\\', '/')
        except ValueError:
            rel = str(p)
        for k in keys:
            for v in vals.get(k) or []:
                if not v.strip():
                    continue
                collected[k].setdefault(v, []).append(rel)
    for k, by_val in collected.items():
        if len(by_val) > 1:
            sample = '；'.join('%s×%d' % (v[:20], len(fs))
                              for v, fs in list(by_val.items())[:4])
            errors.append({
                'file': '-', 'part': '-', 'key': k, 'loc': '-',
                'reason': '单位名不一致：%s 出现 %d 种写法（%s）' % (
                    k, len(by_val), sample),
                'level': 'warn',
            })
    return errors


def check_amount(project: dict) -> list:
    errors = []
    raw = project.get('contractAmount')
    try:
        contract = float(str(raw).replace(',', '').replace('万元', '').strip())
    except (TypeError, ValueError):
        return errors
    devices = (project.get('_assets') or {}).get('devices') or []
    if not devices:
        return errors
    total = 0.0
    n = 0
    for row in devices:
        if not isinstance(row, dict):
            continue
        for k in ('total', 'amount', 'price', '总价', '合价'):
            if k in row:
                try:
                    total += float(str(row[k]).replace(',', ''))
                    n += 1
                    break
                except ValueError:
                    pass
    if n == 0:
        return errors
    # contractAmount 单位：万元；devices 可能是元或万元。只在同量级时比。
    if total > 1000 and contract < 1000:
        total = total / 10000.0
    if contract == 0:
        return errors
    dev = abs(total - contract) / abs(contract)
    if dev > 0.01:
        errors.append({
            'file': 'project.json', 'part': '-', 'key': 'contractAmount',
            'loc': '_assets.devices',
            'reason': '金额不符：合同额 %s 与设备清单合计 %s 偏差 %.1f%%' % (
                contract, total, dev * 100),
            'level': 'warn',
        })
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description='verify_engine · 校验闸门')
    ap.add_argument('--dir', type=Path, help='待校验目录')
    ap.add_argument('--dict', type=Path, default=DICT_PATH)
    ap.add_argument('--project', type=Path, help='给了才能做一致性校验（§7）')
    ap.add_argument('--level', choices=('block', 'all'), default='block')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.dir:
        return exit_param('需要 --dir', a.as_json, 'verify')
    if not a.dir.exists():
        return exit_param('校验目录不存在：%s' % a.dir, a.as_json, 'verify')

    docs = sorted(p for p in a.dir.rglob('*.docx') if not p.name.startswith('~$'))
    if not docs:
        return exit_env('校验目录里没找到 docx：%s' % a.dir, a.as_json, 'verify')

    enabled, known = load_dict_sets(a.dict)
    errors = []
    date_warns = []
    for i, doc in enumerate(docs, 1):
        emit_progress(i, len(docs), str(doc.name))
        hits, dw = scan_file(doc, a.dir)
        for h in hits:
            errors.append(classify_ph(h, enabled, known))
        date_warns.extend(dw)

    project = None
    if a.project:
        if not a.project.exists():
            return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'verify')
        try:
            project = read_project(a.project, apply_migration=False)
        except ProjectStoreError as e:
            return exit_env(str(e), a.as_json, 'verify')
        errors.extend(check_required(project))
        errors.extend(check_missing_files(project, a.dir))
        errors.extend(check_numbering(project))
        errors.extend(check_unit_consistency(a.dir))
        errors.extend(check_amount(project))
        errors.extend(date_warns)

    residual_enabled = [
        e for e in errors
        if e.get('key') in enabled and str(e.get('reason', '')).startswith('残留')
    ]
    unknown = [
        e for e in errors
        if e.get('key') and e.get('key') not in known
        and '未定义' in str(e.get('reason', ''))
    ]
    broken = [e for e in errors if e.get('reason') in ('文件损坏', 'XML 无法解析')]
    blocks = [e for e in errors if e.get('level') == 'block']
    shown = blocks if a.level == 'block' else errors

    ok = len(blocks) == 0
    summary = '%d 份 / 阻断 %d 处（启用残留 %d / 未定义 %d / 损坏 %d）' % (
        len(docs), len(blocks), len(residual_enabled), len(unknown), len(broken))
    payload = result_payload(
        ok, 'verify', summary,
        stats={
            'docs': len(docs),
            'filled': 0,
            'missing': len(residual_enabled),
            'residual': len(residual_enabled) + len(unknown),
            'block': len(blocks),
            'warn': sum(1 for e in errors if e.get('level') == 'warn'),
        },
        errors=shown,
    )
    if not a.as_json:
        print(summary)
        for e in shown[:30]:
            print('  [%s] %s %s %s' % (
                e.get('level'), e.get('file'), e.get('loc') or '', e.get('reason')))
    emit_result(payload, a.as_json)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
