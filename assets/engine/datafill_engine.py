#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取值装配引擎 · P1：按字段字典 + 填数规则算出 FillPlan.

规格：数据与规则规格.md §3.1 / §4 / §6
  python assets/engine/datafill_engine.py --project examples/demo_project.json \\
      --out work/fillplan.json --json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import (
    ABBR_PATH, BASE, DICT_PATH, RULES_PATH, SPEC,
    TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.field_dict import FieldDictError, load_field_dict  # noqa: E402
from lib.project_store import ProjectStoreError, read_project  # noqa: E402
from lib.rule_engine import (  # noqa: E402
    ENGINE_VERSION, RuleLoadError, dumps_fillplan, field_states,
    load_catalog, load_rule_set, resolve_fillplan,
)

ALIAS_PATH = SPEC / '分册别名表.csv'


def main() -> int:
    ap = argparse.ArgumentParser(description='datafill_engine · 取值装配 / FillPlan')
    ap.add_argument('--project', type=Path, help='project.json')
    ap.add_argument('--out', type=Path, help='FillPlan 输出路径')
    ap.add_argument('--dict', type=Path, default=DICT_PATH)
    ap.add_argument('--rules', type=Path, default=RULES_PATH)
    ap.add_argument('--only', default='', help='只算某个 itemId，如 二-01')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.project or not a.out:
        return exit_param('需要 --project / --out', a.as_json, 'datafill')
    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'datafill')

    try:
        assert_not_template_write(a.out)
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'datafill')

    try:
        emit_progress(0, 4, 'load field dict')
        field_dict = load_field_dict(a.dict)
        emit_progress(1, 4, 'load rules')
        rule_set = load_rule_set(a.rules, field_dict)
        emit_progress(2, 4, 'load project')
        project = read_project(a.project, apply_migration=False)
        catalog = load_catalog(ABBR_PATH, ALIAS_PATH)
        emit_progress(3, 4, 'resolve FillPlan')
        plan = resolve_fillplan(
            project, field_dict, rule_set, catalog=catalog, only=a.only)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(dumps_fillplan(plan), encoding='utf-8')
        emit_progress(4, 4, str(a.out.name))
    except FieldDictError as e:
        return exit_env(str(e), a.as_json, 'datafill')
    except RuleLoadError as e:
        return exit_env(str(e), a.as_json, 'datafill')
    except ProjectStoreError as e:
        return exit_env(str(e), a.as_json, 'datafill')
    except OSError as e:
        return exit_env(str(e), a.as_json, 'datafill')

    states = field_states(plan)
    n_filled = sum(1 for s in states.values() if s == '值')
    n_missing = sum(1 for s in states.values() if s == '缺值')
    n_derived = sum(1 for s in states.values() if s == '推导')
    n_docs = len(plan.get('docs') or {})
    items = [
        {'key': k, 'state': states[k],
         'source': ((plan.get('fields') or {}).get(k) or {}).get('source'),
         'ruleId': ((plan.get('fields') or {}).get(k) or {}).get('ruleId')}
        for k in sorted(states)
    ]
    errors = []
    for rec in (plan.get('docs') or {}).values():
        for c in rec.get('conflicts') or []:
            errors.append({
                'key': c.get('key'),
                'reason': '冲突·%s' % (c.get('note') or '多来源'),
                'level': 'warn',
            })

    summary = '%d 字段 / 值 %d / 缺值 %d / 推导 %d · %d 份文档' % (
        len(states), n_filled, n_missing, n_derived, n_docs)
    payload = result_payload(
        True, 'datafill', summary,
        stats={
            'docs': n_docs,
            'filled': n_filled,
            'missing': n_missing,
            'residual': 0,
            'derived': n_derived,
            'enabled': len(field_dict.enabled),
            'engineVersion': ENGINE_VERSION,
            'ruleSetVersion': rule_set.version,
            'dictVersion': field_dict.version,
        },
        items=items,
        errors=errors,
    )
    if not a.as_json:
        print(summary)
        print('  FillPlan  %s' % a.out)
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
