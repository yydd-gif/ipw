#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子表接管引擎 · P5（8 张清单表按表头列名识别 + 行克隆）

规格：数据与规则规格.md §3.4 / 软件设计方案 §4.4
  python assets/engine/subtable_engine.py --doc <docx> --json
  python assets/engine/subtable_engine.py --doc <docx> --table deviceList --data rows.json --json
  python assets/engine/subtable_engine.py --doc <docx> --project <project.json> --json

红线：zip→XML 部件级写回；永不写入 assets/templates/。
空数组：静态表原样保留。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _common import (
    DICT_PATH, REPO, TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.field_dict import FieldDictError, load_field_dict  # noqa: E402
from lib.project_store import ProjectStoreError, read_project  # noqa: E402
from lib.subtable import (  # noqa: E402
    TABLE_KEYS, apply_subtables, assets_from_project, load_rows_file,
)


def _merge_data(*maps) -> dict:
    out = {}
    for m in maps:
        if not m:
            continue
        for k, rows in m.items():
            out[k] = rows
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='subtable_engine · P5 行克隆')
    ap.add_argument('--doc', type=Path, help='目标 docx')
    ap.add_argument('--out', type=Path, help='输出路径（默认覆盖 --doc）')
    ap.add_argument('--table', default='', help='子表 key（8 选 1，空则自动识别）')
    ap.add_argument('--data', type=Path, help='JSON/CSV 数据源')
    ap.add_argument('--project', type=Path, help='project.json（从 _assets 取数）')
    ap.add_argument('--dict', type=Path, default=DICT_PATH, dest='dict_path')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()

    if not a.doc:
        return exit_param('需要 --doc', a.as_json, 'subtable')
    if not a.doc.exists():
        return exit_param('docx 不存在：%s' % a.doc, a.as_json, 'subtable')
    if a.table and a.table not in TABLE_KEYS:
        return exit_param(
            '非法 --table：%s（%s）' % (a.table, '/'.join(TABLE_KEYS)),
            a.as_json, 'subtable')

    dst = a.out or a.doc
    try:
        assert_not_template_write(dst)
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'subtable')

    try:
        fd = load_field_dict(a.dict_path)
    except FieldDictError as e:
        return exit_env(str(e), a.as_json, 'subtable')

    data_maps = []
    if a.project:
        try:
            pj = a.project if a.project.name == 'project.json' else (
                a.project / 'project.json' if a.project.is_dir() else a.project)
            project = read_project(pj, apply_migration=False)
        except (ProjectStoreError, OSError) as e:
            return exit_param('无法读 project：%s' % e, a.as_json, 'subtable')
        data_maps.append(assets_from_project(project))
    if a.data:
        if not a.data.exists():
            return exit_param('数据文件不存在：%s' % a.data, a.as_json, 'subtable')
        try:
            data_maps.append(load_rows_file(a.data, table_key=a.table))
        except (OSError, json.JSONDecodeError, ValueError) as e:
            return exit_param('数据文件无效：%s' % e, a.as_json, 'subtable')

    data_by_key = _merge_data(*data_maps)
    if a.table:
        # restrict
        if a.table not in data_by_key:
            # explicit empty → keep static
            data_by_key = {a.table: []}
        else:
            data_by_key = {a.table: data_by_key[a.table]}

    emit_progress(0, 1, a.doc.name)
    try:
        result = apply_subtables(
            a.doc, dst, fd, data_by_key, only=a.table)
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'subtable')
    except (OSError, ValueError) as e:
        return exit_env(str(e), a.as_json, 'subtable')

    applied = result.get('applied') or []
    skipped = result.get('skipped') or []
    rows_out = sum(int(x.get('rowsOut') or 0) for x in applied)
    n_changed = sum(1 for x in applied if not x.get('unchanged'))
    keys = [x.get('key') for x in applied] or [x.get('key') for x in skipped]
    if a.table and not applied and not skipped:
        payload = result_payload(
            False, 'subtable',
            '未在文档中识别到子表 %s' % a.table,
            stats={'docs': 1, 'filled': 0, 'tables': 0},
            errors=[{'reason': 'table not found: %s' % a.table, 'level': 'block'}],
        )
        return emit_result(payload, a.as_json)

    summary = '%d 张子表 / %d 行写入 / %d 张改动' % (
        len(applied) or len(skipped), rows_out, n_changed)
    errors = []
    for rec in applied:
        if rec.get('gridUnchanged') is False:
            errors.append({
                'key': rec.get('key'), 'reason': 'tblGrid changed', 'level': 'block',
            })
    ok = not any(e.get('level') == 'block' for e in errors)
    payload = result_payload(
        ok, 'subtable', summary,
        stats={
            'docs': 1,
            'filled': rows_out,
            'missing': 0,
            'residual': 0,
            'tables': len(applied),
            'changed': n_changed,
        },
        items=applied + skipped,
        errors=errors,
    )
    emit_progress(1, 1, ','.join(k for k in keys if k) or a.doc.name)
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
