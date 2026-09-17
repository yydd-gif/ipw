#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总引擎 · P6 T7：施工日志 → 周报 → 月报.

规格：数据与规则规格.md §3.6 / §4.3 aggregate·statistic·count / §4.5
确定性规则引擎取数，不让模型编造事实。窗口内无源文档 → ok=false、exit 1。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows embeddable CPython (python._pth) omits the script dir from sys.path.
_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent.parent, _HERE):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from _common import (
    ABBR_PATH, BASE, DICT_PATH, RULES_PATH, SPEC, TEMPLATES,
    TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.aggregate import (  # noqa: E402
    UNRECORDED, columns_for, four_columns, public_items, resolve_target_values,
    source_docs, source_item_id, target_item_id,
)
from lib.audit_log import log_change  # noqa: E402
from lib.catalog_build import find_template, item_folder, numbered_filename  # noqa: E402
from lib.date_window import resolve_window, window_label  # noqa: E402
from lib.field_dict import FieldDictError, load_field_dict  # noqa: E402
from lib.numbering import NumberingError, apply_action  # noqa: E402
from lib.project_store import ProjectStoreError, read_project, write_project  # noqa: E402
from lib.rule_engine import RuleLoadError, load_catalog, load_rule_set  # noqa: E402

from fill_engine import load_dict, process_docx  # noqa: E402

ALIAS_PATH = SPEC / '分册别名表.csv'


def _root(project_path: Path) -> Path:
    p = Path(project_path)
    return p.parent if p.name == 'project.json' else p


def _project_file(path: Path) -> Path:
    p = Path(path)
    if p.is_dir():
        return p / 'project.json'
    return p


def _slot_text(values: dict, key: str) -> str:
    slot = values.get(key) or {}
    if slot.get('source') == 'S4' and slot.get('value') not in (None, ''):
        return str(slot['value'])
    return ''


def _fill_values(project: dict, t7: dict, extra: dict) -> dict:
    values = {}
    for k, v in project.items():
        if k.startswith('_') or v in (None, ''):
            continue
        values[k] = v
    values.update(t7)
    values.update({k: v for k, v in extra.items() if v not in (None, '')})
    return values


def _write_report(project_path: Path, project: dict, catalog, period: str,
                  columns: dict, extra: dict, src: list, window, out: Path | None) -> dict:
    from docgen_engine import register_doc  # local to avoid import cycle at module load

    root = _root(project_path)
    item = catalog.by_id.get(target_item_id(period))
    if item is None:
        raise ValueError('目录中没有目标项 %s' % target_item_id(period))
    tpl = find_template(TEMPLATES, item)
    if tpl is None:
        raise FileNotFoundError('找不到模板：%s' % item.name)

    dict_raw, meta, enabled = load_dict(DICT_PATH)
    fill_map = _fill_values(project, columns, extra)
    records: list = []

    if out is not None:
        dest = Path(out)
        assert_not_template_write(dest)
        rel_path = str(dest.relative_to(root)).replace('\\', '/') if dest.is_relative_to(root) else dest.name
        doc_no = ''
        doc_id = 'D-AGG-%s' % period
        process_docx(tpl, dest, fill_map, meta, enabled, records, rel_path, anchor='on')
        created = {
            'action': 'written', 'relPath': rel_path, 'docId': doc_id,
            'docNo': doc_no, 'path': str(dest),
        }
    else:
        pool, results = apply_action(project, catalog, item.item_id, 'allocate', count=1)
        doc_id = results[0]['docId']
        doc_no = results[0]['no']
        fill_map['docNo'] = doc_no
        fname = numbered_filename(doc_no, item.name)
        rel_path = '%s/%s' % (item_folder(item), fname)
        dest = root / rel_path
        assert_not_template_write(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        process_docx(tpl, dest, fill_map, meta, enabled, records, rel_path, anchor='on')
        missing = any(r.get('状态') == '缺值·保留' for r in records if r.get('文件') == rel_path)
        fill_state = 'draft' if missing else 'complete'
        register_doc(project, doc_id, item, rel_path, doc_no, fill_state,
                     sorted({r['key'] for r in records if r.get('状态') == '已填充'}))
        created = {
            'action': 'created', 'relPath': rel_path, 'docId': doc_id,
            'docNo': doc_no, 'path': str(dest), 'fillState': fill_state,
        }

    ov = project.setdefault('_documents', {}).setdefault(created['relPath'], {})
    ov.update({k: v for k, v in columns.items() if v})
    for k in ('weather', 'workerCount'):
        if extra.get(k):
            ov[k] = extra[k]
    ov['periodFrom'] = window[0].isoformat()
    ov['periodTo'] = window[1].isoformat()
    ov['weekStart'] = window[0].isoformat()
    ov['docDate'] = window[1].isoformat()
    write_project(project_path, project, backup=True)

    filled = sum(1 for r in records if r.get('状态') == '已填充')
    residual = sum(1 for r in records if r.get('状态') == '缺值·保留')
    created['filled'] = filled
    created['residual'] = residual
    created['records'] = len(records)
    return created


def main() -> int:
    ap = argparse.ArgumentParser(description='aggregate_engine · 日志→周报/月报（T7）')
    ap.add_argument('--period', default='', choices=('', 'week', 'month'))
    ap.add_argument('--from', dest='date_from', default='', help='YYYY-MM-DD')
    ap.add_argument('--to', dest='date_to', default='', help='YYYY-MM-DD')
    ap.add_argument('--project', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--dict', type=Path, default=DICT_PATH)
    ap.add_argument('--rules', type=Path, default=RULES_PATH)
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.period or not a.project:
        return exit_param('需要 --period / --project', a.as_json, 'aggregate')

    pj = _project_file(a.project)
    if not pj.exists():
        return exit_param('project.json 不存在：%s' % pj, a.as_json, 'aggregate')
    if a.out is not None:
        try:
            assert_not_template_write(a.out)
        except TemplateProtectionError as e:
            return exit_env(str(e), a.as_json, 'aggregate')

    try:
        emit_progress(0, 4, 'load rules')
        field_dict = load_field_dict(a.dict)
        rule_set = load_rule_set(a.rules, field_dict)
        catalog = load_catalog(ABBR_PATH, ALIAS_PATH)
        project = read_project(pj, apply_migration=False)
        window = resolve_window(a.period, a.date_from, a.date_to)
        emit_progress(1, 4, window_label(window))

        src = source_docs(project, catalog, a.period, window)
        if not src:
            msg = '本%s无日志，无法汇总（窗口 %s，源项 %s）' % (
                '周' if a.period == 'week' else '月',
                window_label(window), source_item_id(a.period),
            )
            payload = result_payload(
                False, 'aggregate', msg,
                stats={
                    'docs': 0, 'filled': 0, 'missing': 0, 'residual': 0,
                    'period': a.period,
                    'from': window[0].isoformat(),
                    'to': window[1].isoformat(),
                    'sourceItem': source_item_id(a.period),
                    'targetItem': target_item_id(a.period),
                },
                errors=[{'reason': msg, 'level': 'block'}],
            )
            return emit_result(payload, a.as_json)

        emit_progress(2, 4, '%d 份源文档' % len(src))
        values = resolve_target_values(
            project, field_dict, rule_set, catalog, a.period, window)
        columns = four_columns(values, a.period)
        extra = {}
        for key in ('weather', 'workerCount', 'projectStage'):
            text = _slot_text(values, key)
            if text:
                extra[key] = text
        if not extra.get('projectStage') and project.get('projectStage'):
            extra['projectStage'] = str(project['projectStage'])

        created = _write_report(
            pj, project, catalog, a.period, columns, extra, src, window, a.out)
        emit_progress(3, 4, created.get('relPath') or '')
        log_change(
            _root(pj),
            op='engine.aggregate',
            channel='engine',
            period=a.period,
            dateFrom=window[0].isoformat(),
            dateTo=window[1].isoformat(),
            sourceDocs=[d.rel_path or d.doc_id for d in src],
            sourceCount=len(src),
            target=created.get('relPath'),
            docId=created.get('docId'),
            fields=dict(columns),
        )
        emit_progress(4, 4, 'done')
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'aggregate')
    except (FieldDictError, RuleLoadError, ProjectStoreError, NumberingError,
            FileNotFoundError, ValueError, OSError) as e:
        return exit_env(str(e), a.as_json, 'aggregate')

    items = public_items(values, columns, a.period)
    summary = '%s %s：%d 篇源 → %s（四栏已写，未编造）' % (
        '周报' if a.period == 'week' else '月报',
        window_label(window), len(src), created.get('relPath'),
    )
    payload = result_payload(
        True, 'aggregate', summary,
        stats={
            'docs': len(src),
            'filled': created.get('filled') or 0,
            'missing': 0,
            'residual': created.get('residual') or 0,
            'period': a.period,
            'from': window[0].isoformat(),
            'to': window[1].isoformat(),
            'sourceItem': source_item_id(a.period),
            'targetItem': target_item_id(a.period),
            'targetPath': created.get('relPath'),
            'docId': created.get('docId'),
            'docNo': created.get('docNo') or '',
            'unrecorded': UNRECORDED,
            'columns': columns,
        },
        items=items,
    )
    payload['created'] = {k: created[k] for k in created if k != 'records'}
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
