#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编号引擎 · allocate / release / restore（目录项内不重排）.

规格：数据与规则规格.md §2.5 / §3.5
  python assets/engine/numbering_engine.py --project proj.json --item 二-01 --json
  python assets/engine/numbering_engine.py --project proj.json --item 开工报审表 \\
      --action release --no YY123-KGBSB-02 --json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import (
    ABBR_PATH, BASE, SPEC, TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.numbering import NumberingError, apply_action, allocated_seq_set  # noqa: E402
from lib.project_store import ProjectStoreError, read_project, write_project  # noqa: E402
from lib.rule_engine import load_catalog  # noqa: E402

ALIAS_PATH = SPEC / '分册别名表.csv'


def main() -> int:
    ap = argparse.ArgumentParser(description='numbering_engine · 编号分配/释放/还原')
    ap.add_argument('--item', default='', help='目录项名或 itemId')
    ap.add_argument('--action', choices=('allocate', 'release', 'restore'),
                    default='allocate')
    ap.add_argument('--count', type=int, default=1)
    ap.add_argument('--no', dest='doc_no', default='', help='release/restore 的目标编号')
    ap.add_argument('--doc-id', dest='doc_id', default='')
    ap.add_argument('--project', type=Path)
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.project or not a.item:
        return exit_param('需要 --project / --item', a.as_json, 'numbering')
    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'numbering')
    if a.action in ('release', 'restore') and not (a.doc_no or a.doc_id):
        return exit_param('release/restore 需要 --no 或 --doc-id', a.as_json, 'numbering')
    if a.action == 'restore' and not (a.doc_no and a.doc_id):
        return exit_param('restore 需要同时提供 --no 与 --doc-id', a.as_json, 'numbering')

    try:
        assert_not_template_write(a.project)
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'numbering')

    try:
        emit_progress(0, 2, 'load project')
        project = read_project(a.project, apply_migration=False)
        catalog = load_catalog(ABBR_PATH, ALIAS_PATH)
        emit_progress(1, 2, a.action)
        pool, results = apply_action(
            project, catalog, a.item, a.action,
            count=a.count, no=a.doc_no, doc_id=a.doc_id)
        write_project(a.project, project, backup=True,
                      generated_with={'engineVersion': '1.0.0'})
        emit_progress(2, 2, results[0]['no'] if results else a.item)
    except NumberingError as e:
        payload = result_payload(
            False, 'numbering', str(e),
            errors=[{'reason': str(e), 'level': 'block'}],
        )
        emit_result(payload, a.as_json)
        return 1
    except ProjectStoreError as e:
        return exit_env(str(e), a.as_json, 'numbering')
    except OSError as e:
        return exit_env(str(e), a.as_json, 'numbering')

    seqs = allocated_seq_set(pool)
    items = [{'docId': r.get('docId'), 'no': r.get('no'), 'seq': r.get('seq')}
             for r in results]
    summary = '%s %s → %s (max=%s allocated=%s released=%s)' % (
        a.action, a.item,
        '、'.join(r['no'] for r in results),
        pool.get('max'), seqs, pool.get('released') or [])
    payload = result_payload(
        True, 'numbering', summary,
        stats={
            'docs': len(results),
            'filled': len(results),
            'missing': 0,
            'residual': 0,
            'max': pool.get('max'),
            'allocated': len(pool.get('allocated') or []),
            'released': len(pool.get('released') or []),
        },
        items=items,
    )
    if not a.as_json:
        print(summary)
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
