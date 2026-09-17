#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档生成引擎 · 一键成册 / 单份 / 追加 / 无模板三选一 / 编号绑定.

规格：数据与规则规格.md §2.7–2.8 / §3.2
  python assets/engine/docgen_engine.py --project work/proj/project.json --item all --json
  python assets/engine/docgen_engine.py --project work/proj/project.json --item 二-01 --count 2 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Windows embeddable CPython (python._pth) omits the script dir from sys.path.
_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent.parent, _HERE):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from _common import (
    ABBR_PATH, BASE, CATALOG_DOCX, DICT_PATH, SPEC, TEMPLATES,
    TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.blank_docx import build_blank_docx  # noqa: E402
from lib.catalog_build import (  # noqa: E402
    build_catalog_snapshot, find_template, item_folder, numbered_filename,
    plain_filename, upload_filename,
)
from lib.catalog_flags import item_required  # noqa: E402
from lib.numbering import NumberingError, apply_action, make_doc_id  # noqa: E402
from lib.project_store import ProjectStoreError, read_project, write_project  # noqa: E402
from lib.rule_engine import load_catalog, normalize_item_id  # noqa: E402

from fill_engine import (  # noqa: E402
    build_values, compute_fillplan, load_dict, process_docx, values_from_plan,
)

ALIAS_PATH = SPEC / '分册别名表.csv'


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _today() -> str:
    return datetime.now().date().isoformat()


def live_docs(project: dict, item_id: str) -> list:
    trash = set()
    for t in project.get('_trash') or []:
        if isinstance(t, dict) and t.get('docId'):
            trash.add(t['docId'])
        for d in t.get('documents') or []:
            if isinstance(d, dict) and d.get('docId'):
                trash.add(d['docId'])
    out = []
    for did, rec in (project.get('_docs') or {}).items():
        if not isinstance(rec, dict):
            continue
        if rec.get('itemId') == item_id and did not in trash:
            out.append((did, rec))
    return out


def unique_doc_id(project: dict, item, seq: int) -> str:
    taken = set(project.get('_docs') or {})
    primary = make_doc_id(item.abbr, seq, item.digits)
    if primary not in taken:
        return primary
    alt = 'D-%s-%s-%0*d' % (item.abbr, item.item_id, item.digits, seq)
    n = seq
    cand = alt
    while cand in taken:
        n += 1
        cand = 'D-%s-%s-%0*d' % (item.abbr, item.item_id, item.digits, n)
    return cand


def next_plain_seq(project: dict, item) -> int:
    n = 1
    for _did, rec in live_docs(project, item.item_id):
        rel = rec.get('relPath') or ''
        n = max(n, 1)
        # count existing
        n += 1
    return n if live_docs(project, item.item_id) else 1


def register_doc(project: dict, doc_id: str, item, rel_path: str, doc_no: str,
                 fill_state: str, anchors: list, skipped: bool = False) -> None:
    docs = project.setdefault('_docs', {})
    now = _now()
    rec = {
        'itemId': item.item_id,
        'relPath': rel_path,
        'docNo': doc_no or '',
        'fillState': fill_state,
        'createdAt': now,
        'updatedAt': now,
        'anchors': anchors,
    }
    if skipped:
        rec['skipped'] = True
    if doc_id in docs and docs[doc_id].get('createdAt'):
        rec['createdAt'] = docs[doc_id]['createdAt']
    docs[doc_id] = rec
    if doc_no:
        ov = project.setdefault('_documents', {}).setdefault(rel_path, {})
        ov['docNo'] = doc_no


def fill_from_template(tpl: Path, dest: Path, project: dict, plan, meta, enabled,
                       item, rel_path: str, tpl_rel: str, doc_no: str,
                       records: list, anchor: str) -> list:
    values = build_values(project, enabled, tpl_rel)
    extra = build_values(project, enabled, rel_path)
    values.update(extra)
    if plan is not None:
        values = values_from_plan(plan, tpl_rel, values)
        values = values_from_plan(plan, rel_path, values)
    if doc_no:
        values['docNo'] = doc_no
    process_docx(tpl, dest, values, meta, enabled, records, rel_path,
                 anchor=anchor, plan=plan)
    try:
        from lib.catalog_pages import apply_structure_to_docx
        apply_structure_to_docx(dest, project)
    except Exception:
        # structure pass must not abort 成册; P5 regression covers it
        pass
    return sorted({r['key'] for r in records if r['状态'] == '已填充'
                   and r['文件'] == rel_path})


def write_upload_stub(dest: Path, item) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({
        'itemId': item.item_id,
        'name': item.name,
        'mode': 'upload',
        'note': '请将现成文件放到本目录（docx / PDF / 图片）',
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_blank(dest: Path, item, project: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = build_blank_docx(
        item.name,
        project_name=str(project.get('projectName') or ''),
        hint='（无模板项 · 空白文档）',
    )
    dest.write_bytes(data)


def generate_one(item, project, catalog, templates, out_dir, mode, overwrite,
                 plan, meta, enabled, records, anchor: str) -> dict:
    """Create or skip one document instance. Returns action dict."""
    folder = item_folder(item)
    tpl = find_template(templates, item)
    has_tpl = tpl is not None
    existing = live_docs(project, item.item_id)

    if existing and not overwrite:
        return {
            'itemId': item.item_id, 'action': 'skipped',
            'docId': existing[0][0],
            'relPath': existing[0][1].get('relPath', ''),
            'reason': 'already exists',
        }

    if overwrite and existing:
        actions = []
        for doc_id, rec in existing:
            rel_path = rec.get('relPath') or ''
            dest = out_dir / rel_path
            doc_no = rec.get('docNo') or ''
            anchors = []
            fill_state = rec.get('fillState') or 'draft'
            if has_tpl and rel_path.endswith('.docx'):
                tpl_rel = str(tpl.relative_to(templates)).replace('\\', '/')
                before = len(records)
                anchors = fill_from_template(
                    tpl, dest, project, plan, meta, enabled, item,
                    rel_path, tpl_rel, doc_no, records, anchor)
                missing = any(r['状态'] == '缺值·保留' for r in records[before:]
                              if r['文件'] == rel_path)
                fill_state = 'draft' if missing else 'complete'
            elif dest.suffix == '.docx' and not has_tpl:
                write_blank(dest, item, project)
                fill_state = 'draft'
            register_doc(project, doc_id, item, rel_path, doc_no, fill_state,
                         anchors)
            actions.append({
                'itemId': item.item_id, 'action': 'overwritten',
                'docId': doc_id, 'relPath': rel_path, 'docNo': doc_no,
            })
        return actions[0] if len(actions) == 1 else {
            'itemId': item.item_id, 'action': 'overwritten',
            'docs': len(actions),
        }

    # --- create new ---
    item_mode = mode
    if has_tpl:
        item_mode = 'template'
    elif mode == 'template':
        item_mode = 'blank'  # 无模板默认建空白（仅对本次要生成的项）

    doc_no = ''
    doc_id = ''
    if item.numbered and item_mode != 'skip':
        _pool, results = apply_action(project, catalog, item.item_id, 'allocate',
                                      count=1)
        doc_id = results[0]['docId']
        doc_no = results[0]['no']
        fname = numbered_filename(doc_no, item.name)
    elif item_mode == 'skip':
        seq = next_plain_seq(project, item)
        doc_id = unique_doc_id(project, item, seq)
        rel_path = folder
        register_doc(project, doc_id, item, rel_path, '', 'empty', [],
                     skipped=True)
        return {
            'itemId': item.item_id, 'action': 'skipped',
            'docId': doc_id, 'relPath': rel_path, 'reason': 'mode=skip',
        }
    elif item_mode == 'upload':
        seq = next_plain_seq(project, item)
        doc_id = unique_doc_id(project, item, seq)
        fname = upload_filename(item.name)
    else:
        seq = next_plain_seq(project, item)
        doc_id = unique_doc_id(project, item, seq)
        fname = plain_filename(item.name)
        if seq > 1:
            fname = '%s-%02d.docx' % (item.name, seq)

    rel_path = '%s/%s' % (folder, fname)
    dest = out_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    anchors: list = []
    fill_state = 'draft'

    if item_mode == 'template' and has_tpl:
        tpl_rel = str(tpl.relative_to(templates)).replace('\\', '/')
        before = len(records)
        anchors = fill_from_template(
            tpl, dest, project, plan, meta, enabled, item,
            rel_path, tpl_rel, doc_no, records, anchor)
        missing = any(r['状态'] == '缺值·保留' for r in records[before:]
                      if r['文件'] == rel_path)
        fill_state = 'draft' if missing else 'complete'
    elif item_mode == 'upload':
        write_upload_stub(dest, item)
        fill_state = 'empty'
    else:
        write_blank(dest, item, project)
        fill_state = 'draft'

    register_doc(project, doc_id, item, rel_path, doc_no, fill_state, anchors)
    return {
        'itemId': item.item_id, 'action': 'created',
        'docId': doc_id, 'relPath': rel_path, 'docNo': doc_no,
        'mode': item_mode,
    }


def select_items(catalog, token: str) -> list:
    if token == 'all':
        return list(catalog.items)
    nid = normalize_item_id(token)
    if nid in catalog.by_id:
        return [catalog.by_id[nid]]
    hits = [it for it in catalog.items if it.name == token or it.abbr == token
            or it.item_id == token]
    if len(hits) == 1:
        return hits
    if not hits:
        raise ValueError('未知目录项：%s' % token)
    raise ValueError('目录项不唯一：%s' % token)


def booklet_jobs(catalog, project, token: str, count: int) -> tuple:
    """--item all: required + already-instanced. Specific item: --count copies.

    Optional catalog rows with no live instance are skipped (not created).
    """
    items = select_items(catalog, token)
    jobs = []
    skipped_optional = []
    if token == 'all':
        for it in items:
            existing = live_docs(project, it.item_id)
            if item_required(it) or existing:
                jobs.append((it, 1))
            else:
                skipped_optional.append({
                    'itemId': it.item_id, 'action': 'skipped',
                    'reason': 'optional not selected',
                })
    else:
        jobs = [(items[0], int(count or 1))]
    return jobs, skipped_optional


def main() -> int:
    ap = argparse.ArgumentParser(description='docgen_engine · 一键成册 / 单份 / 追加')
    ap.add_argument('--project', type=Path)
    ap.add_argument('--item', default='', help='all 或具体 itemId')
    ap.add_argument('--count', type=int, default=1)
    ap.add_argument('--mode', choices=('template', 'blank', 'upload', 'skip'),
                    default='template')
    ap.add_argument('--templates', type=Path, default=TEMPLATES)
    ap.add_argument('--out', type=Path, help='输出根目录（默认从 --project 推断）')
    ap.add_argument('--overwrite', action='store_true')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.project or not a.item:
        return exit_param('需要 --project / --item', a.as_json, 'docgen')
    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'docgen')
    if int(a.count or 1) < 1:
        return exit_param('--count 必须 ≥ 1', a.as_json, 'docgen')

    out_dir = a.out or a.project.parent
    try:
        assert_not_template_write(out_dir)
        assert_not_template_write(a.project)
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'docgen')
    if not a.templates.exists():
        return exit_env('模板目录不存在：%s' % a.templates, a.as_json, 'docgen')

    try:
        project = read_project(a.project, apply_migration=False)
        catalog = load_catalog(ABBR_PATH, ALIAS_PATH)
        items = select_items(catalog, a.item)
    except ValueError as e:
        return exit_param(str(e), a.as_json, 'docgen')
    except ProjectStoreError as e:
        return exit_env(str(e), a.as_json, 'docgen')

    snap = project.get('_catalogSnapshot') or {}
    if not snap.get('items'):
        project['_catalogSnapshot'] = build_catalog_snapshot(
            catalog, a.templates,
            [ABBR_PATH, ALIAS_PATH, CATALOG_DOCX],
            snap.get('parsedAt') or _today())
    else:
        # keep parsedAt; refresh items so hasTemplate / required are accurate
        project['_catalogSnapshot'] = build_catalog_snapshot(
            catalog, a.templates,
            [ABBR_PATH, ALIAS_PATH, CATALOG_DOCX],
            snap.get('parsedAt') or _today())

    _data, meta, enabled = load_dict(DICT_PATH)
    plan = compute_fillplan(project)
    records: list = []
    created = skipped = overwritten = 0
    errors = []

    # --item all → 必填 + 已建表；指定 item → --count 份（追加，含可选表）
    jobs, skipped_optional = booklet_jobs(catalog, project, a.item, a.count)
    results = list(skipped_optional)
    skipped = len(skipped_optional)

    total = sum(n for _it, n in jobs)
    done = 0
    try:
        for it, n in jobs:
            for _i in range(n):
                done += 1
                emit_progress(done, total, '%s %s' % (it.item_id, it.name))
                try:
                    # append: force create even if one exists, unless --item all
                    ow = a.overwrite
                    if a.item != 'all' and not ow:
                        # generate_one skips when live docs exist — temporarily
                        # bypass by not treating as skip: use a local copy flag
                        action = _generate_append_or_first(
                            it, project, catalog, a.templates, out_dir, a.mode,
                            ow, plan, meta, enabled, records, n_existing=len(
                                live_docs(project, it.item_id)))
                    else:
                        action = generate_one(
                            it, project, catalog, a.templates, out_dir, a.mode,
                            ow, plan, meta, enabled, records, anchor='on')
                except NumberingError as e:
                    errors.append({
                        'file': item_folder(it), 'key': it.item_id,
                        'reason': str(e), 'level': 'block',
                    })
                    action = {
                        'itemId': it.item_id, 'action': 'error',
                        'reason': str(e),
                    }
                results.append(action)
                act = action.get('action')
                if act == 'created':
                    created += 1
                elif act == 'skipped':
                    skipped += 1
                elif act == 'overwritten':
                    overwritten += 1
        write_project(a.project, project, backup=True,
                      generated_with={'engineVersion': '1.0.0'})
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'docgen')
    except ProjectStoreError as e:
        return exit_env(str(e), a.as_json, 'docgen')
    except OSError as e:
        return exit_env(str(e), a.as_json, 'docgen')

    n_docs = len(project.get('_docs') or {})
    n_required = sum(1 for it in catalog.items if item_required(it))
    n_optional = len(catalog.items) - n_required
    ok = not any(e.get('level') == 'block' for e in errors)
    summary = '生成 %d / 跳过 %d / 覆盖 %d · 在册 %d 份（必填 %d / 可选 %d / 目录 %d）' % (
        created, skipped, overwritten, n_docs, n_required, n_optional,
        len(catalog.items))
    payload = result_payload(
        ok, 'docgen', summary,
        stats={
            'docs': n_docs,
            'created': created,
            'skipped': skipped,
            'overwritten': overwritten,
            'optionalSkipped': len(skipped_optional),
            'filled': sum(1 for r in records if r.get('状态') == '已填充'),
            'missing': sum(1 for r in records if r.get('状态') == '缺值·保留'),
            'residual': 0,
            'catalog': len(catalog.items),
            'required': n_required,
            'optional': n_optional,
        },
        items=results,
        errors=errors,
    )
    if not a.as_json:
        print(summary)
        for r in results:
            print('  [%s] %s  %s' % (
                r.get('action'), r.get('itemId'), r.get('relPath') or r.get('reason') or ''))
    code = emit_result(payload, a.as_json)
    return 0 if ok else 1 if code == 1 else code


def _generate_append_or_first(item, project, catalog, templates, out_dir, mode,
                              overwrite, plan, meta, enabled, records,
                              n_existing: int) -> dict:
    """Specific --item: first call creates; subsequent calls append."""
    if n_existing == 0 or overwrite:
        return generate_one(
            item, project, catalog, templates, out_dir, mode, overwrite,
            plan, meta, enabled, records, anchor='on')
    # append: pretend no skip by generating a new instance even if live docs exist
    return _force_create(
        item, project, catalog, templates, out_dir, mode,
        plan, meta, enabled, records)


def _force_create(item, project, catalog, templates, out_dir, mode,
                  plan, meta, enabled, records) -> dict:
    """Like generate_one but never skips on existing live docs."""
    folder = item_folder(item)
    tpl = find_template(templates, item)
    has_tpl = tpl is not None
    item_mode = mode if not has_tpl else 'template'
    if has_tpl:
        item_mode = 'template'
    elif mode == 'template':
        item_mode = 'blank'

    doc_no = ''
    if item.numbered and item_mode != 'skip':
        _pool, results = apply_action(project, catalog, item.item_id, 'allocate',
                                      count=1)
        doc_id = results[0]['docId']
        doc_no = results[0]['no']
        fname = numbered_filename(doc_no, item.name)
    elif item_mode == 'skip':
        seq = next_plain_seq(project, item)
        doc_id = unique_doc_id(project, item, seq)
        register_doc(project, doc_id, item, folder, '', 'empty', [], skipped=True)
        return {
            'itemId': item.item_id, 'action': 'skipped',
            'docId': doc_id, 'relPath': folder, 'reason': 'mode=skip',
        }
    elif item_mode == 'upload':
        seq = next_plain_seq(project, item)
        doc_id = unique_doc_id(project, item, seq)
        fname = upload_filename(item.name)
        if seq > 1:
            fname = '%s-%02d.upload.json' % (item.name, seq)
    else:
        seq = next_plain_seq(project, item)
        doc_id = unique_doc_id(project, item, seq)
        fname = plain_filename(item.name) if seq == 1 else '%s-%02d.docx' % (
            item.name, seq)

    rel_path = '%s/%s' % (folder, fname)
    dest = out_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    anchors: list = []
    fill_state = 'draft'
    if item_mode == 'template' and has_tpl:
        tpl_rel = str(tpl.relative_to(templates)).replace('\\', '/')
        before = len(records)
        anchors = fill_from_template(
            tpl, dest, project, plan, meta, enabled, item,
            rel_path, tpl_rel, doc_no, records, anchor='on')
        missing = any(r['状态'] == '缺值·保留' for r in records[before:]
                      if r['文件'] == rel_path)
        fill_state = 'draft' if missing else 'complete'
    elif item_mode == 'upload':
        write_upload_stub(dest, item)
        fill_state = 'empty'
    else:
        write_blank(dest, item, project)
        fill_state = 'draft'
    register_doc(project, doc_id, item, rel_path, doc_no, fill_state, anchors)
    return {
        'itemId': item.item_id, 'action': 'created',
        'docId': doc_id, 'relPath': rel_path, 'docNo': doc_no,
        'mode': item_mode,
    }


if __name__ == '__main__':
    sys.exit(main())
