#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1 DoD regression: 数据与规则（施工交接说明 §6 P1）.

  python tools/run_p1_regression.py

Does not replace P0 `tools/run_regression.py` (still 37/171/0).
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import ENGINE, EXAMPLES, REPO, SPEC, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ENGINE))

from lib.field_dict import load_field_dict  # noqa: E402
from lib.project_store import (  # noqa: E402
    CURRENT_SCHEMA, ProjectStoreError, migrate_project, read_project, write_project,
)
from lib.rule_engine import (  # noqa: E402
    RuleLoadError, dumps_fillplan, field_states, load_catalog, load_rule_set,
    resolve_fillplan,
)
from lib.yaml_lite import load_yaml_file  # noqa: E402

DICT_PATH = SPEC / '字段字典.json'
RULES_PATH = SPEC / '填数规则.yaml'
ABBR_PATH = SPEC / '表名缩写字典.csv'
ALIAS_PATH = SPEC / '分册别名表.csv'
DEMO = EXAMPLES / 'demo_project.json'

NINE_TYPES = {
    'direct', 'alias', 'format', 'compose',
    'aggregate', 'statistic', 'count', 'reference', 'condition',
}


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


def write_temp_rules(base: dict, mutate) -> Path:
    data = copy.deepcopy(base)
    mutate(data)
    # dump via json→ we need YAML. Use a tiny emitter for our subset.
    path = Path(tempfile.mkdtemp(prefix='yz-p1-')) / 'rules.yaml'
    path.write_text(_dump_yaml(data), encoding='utf-8')
    return path


def _dump_yaml(obj, indent=0) -> str:
    """Sufficient emitter for the rule file subset (maps/lists/scalars)."""
    sp = '  ' * indent
    if isinstance(obj, dict):
        if not obj:
            return '{}'
        lines = []
        for k, v in obj.items():
            key = _yaml_key(k)
            if isinstance(v, (dict, list)):
                if not v:
                    lines.append('%s%s: %s' % (sp, key, '{}' if isinstance(v, dict) else '[]'))
                else:
                    lines.append('%s%s:' % (sp, key))
                    dumped = _dump_yaml(v, indent + 1)
                    lines.append(dumped if dumped.endswith('\n') else dumped)
            else:
                lines.append('%s%s: %s' % (sp, key, _yaml_scalar(v)))
        return '\n'.join(lines) + ('\n' if indent == 0 else '')
    if isinstance(obj, list):
        lines = []
        for item in obj:
            if isinstance(item, dict):
                inner = _dump_yaml(item, indent + 1).splitlines()
                if not inner:
                    lines.append('%s- {}' % sp)
                else:
                    first = inner[0].lstrip()
                    lines.append('%s- %s' % (sp, first))
                    for extra in inner[1:]:
                        lines.append(extra)
            else:
                lines.append('%s- %s' % (sp, _yaml_scalar(item)))
        return '\n'.join(lines)
    return '%s%s' % (sp, _yaml_scalar(obj))


def _yaml_key(k: str) -> str:
    if k.startswith('$') or ':' in k or ' ' in k:
        return json.dumps(k, ensure_ascii=False)
    return k


def _yaml_scalar(v) -> str:
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    s = str(v)
    if s == '' or any(ch in s for ch in ':#{}[]&*!|>%@`"\'') or s.strip() != s:
        return json.dumps(s, ensure_ascii=False)
    return s


def main() -> int:
    failures = []
    print('=' * 68)
    print('P1 regression · 数据与规则')
    print('=' * 68)

    fd = load_field_dict(DICT_PATH)
    check(len(fd.enabled) == 39, 'enabled field count',
          '%d (expect 39)' % len(fd.enabled), failures)

    print('\n-- load 填数规则.yaml')
    try:
        rs = load_rule_set(RULES_PATH, fd)
        check(True, 'rules load', 'version %s / %d rules' % (rs.version, len(rs.rules)), failures)
    except Exception as e:
        check(False, 'rules load', str(e), failures)
        print('\n'.join(failures))
        return 1

    types_present = {r.type for r in rs.rules}
    check(types_present == NINE_TYPES, '9 rule kinds',
          'got %s' % ','.join(sorted(types_present)), failures)
    targets = {r.target for r in rs.rules}
    missing_targets = sorted(fd.enabled - targets)
    check(not missing_targets, '39 fields covered',
          'ok' if not missing_targets else 'no rule for: %s' % missing_targets[:8],
          failures)

    catalog = load_catalog(ABBR_PATH, ALIAS_PATH)
    demo = read_project(DEMO)

    print('\n-- FillPlan (demo)')
    plan1 = resolve_fillplan(demo, fd, rs, catalog=catalog)
    plan2 = resolve_fillplan(demo, fd, rs, catalog=catalog)
    b1 = dumps_fillplan(plan1).encode('utf-8')
    b2 = dumps_fillplan(plan2).encode('utf-8')
    check(b1 == b2, 'idempotent FillPlan',
          'same input twice → %d bytes identical' % len(b1), failures)

    states = field_states(plan1)
    check(set(states) == fd.enabled, 'fields map covers 39',
          '%d keys' % len(states), failures)

    print('\n  39 字段三态（demo 工程）：')
    for key in sorted(states):
        spec = fd.get(key)
        sl = (plan1.get('fields') or {}).get(key) or {}
        print('    %-24s  %s  source=%-3s  rule=%s' % (
            key, states[key], sl.get('source') or '-', sl.get('ruleId') or '-'))
        if spec and spec.required is True and spec.scope == 'project' and states[key] == '缺值':
            check(False, 'required %s' % key, 'demo 缺值', failures)
    bad_state = [k for k, s in states.items() if s not in ('值', '缺值', '推导')]
    check(not bad_state, 'each of 39 has 值/缺值/推导',
          'ok' if not bad_state else str(bad_state), failures)

    # 值 / 缺值 / 推导 as applicable
    empty_proj = {'_schema': CURRENT_SCHEMA}
    empty_plan = resolve_fillplan(empty_proj, fd, rs, catalog=catalog)
    empty_states = field_states(empty_plan)
    n_empty_missing = sum(1 for s in empty_states.values() if s == '缺值')
    check(n_empty_missing == 39, 'all-missing on empty project',
          '%d/39 缺值' % n_empty_missing, failures)
    numbered_with_no = [
        did for did, rec in (plan1.get('docs') or {}).items()
        if ((rec.get('values') or {}).get('docNo') or {}).get('value')
    ]
    check(len(numbered_with_no) >= 1, 'docNo bound on documents',
          '%d docs with docNo' % len(numbered_with_no), failures)

    # 推导：format / compose / aggregate on demo
    derived_demo = [k for k, s in states.items() if s == '推导']
    check('contractAmount' in derived_demo, 'format → 推导',
          'contractAmount=%s' % states.get('contractAmount'), failures)
    check('buildSite' in derived_demo, 'compose → 推导',
          'buildSite=%s' % states.get('buildSite'), failures)
    check('weeklyDone' in derived_demo, 'aggregate → 推导',
          'weeklyDone=%s' % states.get('weeklyDone'), failures)

    # 值：projectName
    check(states.get('projectName') == '值', 'direct → 值',
          'projectName=%s' % states.get('projectName'), failures)

    print('\n-- change one rule, only its target moves')
    raw_rules = load_yaml_file(RULES_PATH)
    mutated_path = write_temp_rules(raw_rules, lambda d: _bump_decimals(d, 0))
    try:
        rs2 = load_rule_set(mutated_path, fd)
        plan_m = resolve_fillplan(demo, fd, rs2, catalog=catalog)
        changed = []
        for k in fd.enabled:
            a = (plan1.get('fields') or {}).get(k) or {}
            b = (plan_m.get('fields') or {}).get(k) or {}
            if (a.get('value'), a.get('state'), a.get('source'), a.get('ruleId')) != (
                    b.get('value'), b.get('state'), b.get('source'), b.get('ruleId')):
                changed.append(k)
        check(changed == ['contractAmount'], 'rule isolation',
              'changed %s' % (changed or 'nothing'), failures)
    finally:
        shutil.rmtree(mutated_path.parent, ignore_errors=True)

    print('\n-- unknown dict key (load-time error)')
    bad_path = write_temp_rules(raw_rules, lambda d: d['rules'].append({
        'id': 'proj.doesNotExist',
        'target': 'doesNotExist',
        'type': 'direct',
        'from': 'project.doesNotExist',
        'source': 'S1',
        'on': ['T1'],
    }))
    try:
        load_rule_set(bad_path, fd)
        check(False, 'unknown key', 'load succeeded, should have failed', failures)
        unknown_ok = False
    except RuleLoadError as e:
        check('doesNotExist' in str(e), 'unknown key', str(e)[:120], failures)
        unknown_ok = True
    finally:
        shutil.rmtree(bad_path.parent, ignore_errors=True)

    print('\n-- date auto-fill rejected (exit 3)')
    date_path = write_temp_rules(raw_rules, lambda d: d['rules'].append({
        'id': 'fmt.startDate',
        'target': 'startDate',
        'type': 'direct',
        'from': 'project.startDate',
        'source': 'S2',
        'on': ['T1'],
    }))
    proc = run_cmd([
        sys.executable, str(ENGINE / 'datafill_engine.py'),
        '--project', str(DEMO),
        '--out', str(WORK / 'p1-date-fillplan.json'),
        '--rules', str(date_path),
        '--json',
    ])
    try:
        payload = last_json_line(proc.stdout) if proc.stdout.strip() else {}
    except Exception:
        payload = {}
    check(proc.returncode == 3, 'date auto-fill exit',
          'exit %d (expect 3) summary=%s' % (proc.returncode, payload.get('summary', proc.stderr[-200:])),
          failures)
    shutil.rmtree(date_path.parent, ignore_errors=True)

    # unknown key via CLI too
    proc2 = run_cmd([
        sys.executable, str(ENGINE / 'datafill_engine.py'),
        '--project', str(DEMO),
        '--out', str(WORK / 'p1-unknown-fillplan.json'),
        '--rules', str(bad_path) if False else _recreate_unknown(raw_rules),
        '--json',
    ])
    # _recreate_unknown returns path; handle cleanup below
    return _cli_and_store(failures, fd, rs, catalog, demo, plan1, unknown_ok, proc2)


def _recreate_unknown(raw_rules) -> str:
    p = write_temp_rules(raw_rules, lambda d: d['rules'].append({
        'id': 'proj.doesNotExist',
        'target': 'doesNotExist',
        'type': 'direct',
        'from': 'project.doesNotExist',
        'source': 'S1',
        'on': ['T1'],
    }))
    _recreate_unknown.last = p  # type: ignore[attr-defined]
    return str(p)


def _bump_decimals(data: dict, decimals: int) -> None:
    for rule in data.get('rules') or []:
        if rule.get('id') == 'fmt.contractAmount':
            tf = dict(rule.get('transform') or {})
            tf['decimals'] = decimals
            rule['transform'] = tf


def _cli_and_store(failures, fd, rs, catalog, demo, plan1, unknown_ok, proc_unknown):
    check(proc_unknown.returncode == 3, 'unknown key CLI exit',
          'exit %d (expect 3)' % proc_unknown.returncode, failures)
    last = getattr(_recreate_unknown, 'last', None)
    if last:
        shutil.rmtree(Path(last).parent, ignore_errors=True)

    print('\n-- datafill CLI (demo)')
    WORK.mkdir(parents=True, exist_ok=True)
    out1 = WORK / 'p1-fillplan-a.json'
    out2 = WORK / 'p1-fillplan-b.json'
    cmd = [sys.executable, str(ENGINE / 'datafill_engine.py'),
           '--project', str(DEMO), '--json']
    p_a = run_cmd(cmd + ['--out', str(out1)])
    p_b = run_cmd(cmd + ['--out', str(out2)])
    check(p_a.returncode == 0 and p_b.returncode == 0, 'datafill demo exit',
          'a=%d b=%d' % (p_a.returncode, p_b.returncode), failures)
    try:
        ja = last_json_line(p_a.stdout)
        check('#PROGRESS' in p_a.stdout, 'progress lines',
              'stdout has #PROGRESS', failures)
        check(ja.get('engine') == 'datafill', 'engine id', str(ja.get('engine')), failures)
        check(ja.get('ok') is True, 'ok', str(ja.get('ok')), failures)
    except Exception as e:
        check(False, 'datafill json', str(e), failures)
    if out1.exists() and out2.exists():
        check(out1.read_bytes() == out2.read_bytes(), 'CLI FillPlan bytes',
              '%d bytes' % out1.stat().st_size, failures)
        # last line is JSON, plan file is canonical
        check(out1.read_bytes() == dumps_fillplan(plan1).encode('utf-8'),
              'CLI vs library FillPlan', 'byte-identical', failures)

    missing = run_cmd([sys.executable, str(ENGINE / 'datafill_engine.py'), '--json'])
    check(missing.returncode == 2, 'missing args exit 2',
          'exit %d' % missing.returncode, failures)
    try:
        last_json_line(missing.stdout)
        check(True, 'missing args --json', 'last line is JSON', failures)
    except Exception as e:
        check(False, 'missing args --json', str(e), failures)

    print('\n-- project_store')
    td = Path(tempfile.mkdtemp(prefix='yz-proj-'))
    try:
        pj = td / 'project.json'
        write_project(pj, {'projectName': '甲'}, backup=False)
        data = read_project(pj)
        check(data.get('_schema') == CURRENT_SCHEMA, 'schema injected',
              data.get('_schema'), failures)
        write_project(pj, {**data, 'projectName': '乙'}, backup=True)
        backups = list((td / '_logs' / 'backup').glob('project-*.json'))
        check(len(backups) >= 1, 'auto backup', '%d file(s)' % len(backups), failures)
        migrated, changed = migrate_project({'projectName': '丙'})
        check(changed and migrated['_schema'] == CURRENT_SCHEMA, 'migrate stub',
              'missing schema → %s' % migrated['_schema'], failures)
        try:
            migrate_project({'_schema': 'yzproj/9.9', 'projectName': 'x'})
            check(False, 'unknown schema', 'should raise', failures)
        except ProjectStoreError as e:
            check('unsupported _schema' in str(e), 'unknown schema', str(e)[:100], failures)
        try:
            write_project(TEMPLATES / 'project.json', {'projectName': 'nope'})
            check(False, 'template write', 'did not refuse', failures)
        except ProjectStoreError:
            check(True, 'template write', 'ProjectStoreError', failures)
    finally:
        shutil.rmtree(td, ignore_errors=True)

    print('\n' + '=' * 68)
    if failures:
        print('RESULT: FAIL (%d)' % len(failures))
        for f in failures:
            print('  - %s' % f)
        return 1
    print('RESULT: PASS  P1 DoD')
    print('=' * 68)
    return 0


if __name__ == '__main__':
    sys.exit(main())
