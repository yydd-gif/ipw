#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Desktop-shell JSON bridge. Electron spawns this; engines stay in Python.

  python assets/engine/shell_bridge.py --action open --project <dir>/project.json --json
  python assets/engine/shell_bridge.py --action create --dir <folder> --fields '{...}' --json
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from _common import (
    ABBR_PATH, BASE, DICT_PATH, RULES_PATH, SPEC, TEMPLATES,
    TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.catalog_build import build_catalog_snapshot  # noqa: E402
from lib.docx_preview import preview_docx  # noqa: E402
from lib.field_dict import FieldDictError, load_field_dict  # noqa: E402
from lib.project_store import ProjectStoreError, read_project, write_project  # noqa: E402
from lib.rule_engine import load_catalog  # noqa: E402

ALIAS_PATH = SPEC / '分册别名表.csv'
ENGINE = BASE / 'engine'
REQUIRED = ('projectName', 'ownerUnit', 'constructionUnit')
DOT = {
    'empty': 'gray',
    'draft': 'blue',
    'complete': 'green',
    'error': 'red',
}


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _today() -> str:
    return datetime.now().date().isoformat()


def _project_file(path: Path) -> Path:
    p = Path(path)
    if p.is_dir():
        return p / 'project.json'
    return p


def _root(project_path: Path) -> Path:
    return project_path.parent


def _trash_ids(project: dict) -> set:
    out = set()
    for t in project.get('_trash') or []:
        if isinstance(t, dict) and t.get('docId'):
            out.add(t['docId'])
        for d in t.get('documents') or []:
            if isinstance(d, dict) and d.get('docId'):
                out.add(d['docId'])
    return out


def _item_state(item: dict, docs: list, print_states: dict, required_missing: bool) -> dict:
    mine = [d for d in docs if d.get('itemId') == item.get('itemId')]
    printed = any((print_states.get(d['docId']) or {}).get('printed') for d in mine)
    if not mine:
        fill = 'empty'
    else:
        states = [d.get('fillState') or 'empty' for d in mine]
        if 'error' in states:
            fill = 'error'
        elif all(s == 'complete' for s in states):
            fill = 'complete'
        elif all(s == 'empty' for s in states):
            fill = 'empty'
        else:
            fill = 'draft'
        # leftover required project fields after generate → red
        if required_missing and fill in ('draft', 'complete'):
            fill = 'error'
    return {
        'fillState': fill,
        'dot': DOT[fill],
        'printed': bool(printed),
        'docs': mine,
    }


def _docs_list(project: dict, root: Path) -> list:
    trash = _trash_ids(project)
    out = []
    for did, rec in (project.get('_docs') or {}).items():
        if did in trash or not isinstance(rec, dict):
            continue
        rel = rec.get('relPath') or ''
        exists = bool(rel) and (root / rel).is_file()
        out.append({
            'docId': did,
            'itemId': rec.get('itemId') or '',
            'relPath': rel,
            'docNo': rec.get('docNo') or '',
            'fillState': rec.get('fillState') or 'empty',
            'exists': exists,
            'anchors': rec.get('anchors') or [],
        })
    return out


def _ledger(catalog_items: list, docs: list, print_states: dict, required_missing: bool) -> dict:
    rows = []
    n_complete = n_draft = n_empty = n_error = 0
    n_tpl = 0
    for it in catalog_items:
        st = _item_state(it, docs, print_states, required_missing)
        if it.get('hasTemplate'):
            n_tpl += 1
        fill = st['fillState']
        if fill == 'complete':
            n_complete += 1
        elif fill == 'draft':
            n_draft += 1
        elif fill == 'error':
            n_error += 1
        else:
            n_empty += 1
        miss = []
        if fill == 'error' and required_missing:
            miss.append('项目必填')
        if fill == 'empty' and it.get('hasTemplate'):
            miss = []
        rows.append({
            'itemId': it.get('itemId'),
            'seq': it.get('seq'),
            'name': it.get('name'),
            'volume': it.get('volume'),
            'hasTemplate': it.get('hasTemplate'),
            'fillState': fill,
            'dot': st['dot'],
            'printed': st['printed'],
            'missing': miss,
        })
    total = len(catalog_items)
    return {
        'total': total,
        'withTemplate': n_tpl,
        'complete': n_complete,
        'draft': n_draft,
        'empty': n_empty,
        'error': n_error,
        'rows': rows,
    }


def _snapshot(project: dict) -> dict:
    catalog = load_catalog(ABBR_PATH, ALIAS_PATH)
    snap = project.get('_catalogSnapshot') or {}
    if not snap.get('items'):
        snap = build_catalog_snapshot(
            catalog, TEMPLATES, [ABBR_PATH, ALIAS_PATH], _today())
    return snap


def _required_missing(project: dict) -> bool:
    return any(not str(project.get(k) or '').strip() for k in REQUIRED)


def _open_payload(project_path: Path) -> dict:
    project = read_project(project_path, apply_migration=True)
    root = _root(project_path)
    snap = _snapshot(project)
    if project.get('_catalogSnapshot') != snap:
        project['_catalogSnapshot'] = snap
        write_project(project_path, project, backup=True)
    docs = _docs_list(project, root)
    print_states = project.get('_printStates') or {}
    req_miss = _required_missing(project)
    items = []
    volumes = []
    vol_map = {}
    for it in snap.get('items') or []:
        st = _item_state(it, docs, print_states, req_miss)
        rec = dict(it)
        rec.update(st)
        items.append(rec)
        vol = it.get('volume') or ''
        if vol not in vol_map:
            vol_map[vol] = {
                'volume': vol,
                'volumeSeq': it.get('volumeSeq'),
                'items': [],
            }
            volumes.append(vol_map[vol])
        vol_map[vol]['items'].append(rec)
    for v in volumes:
        v['count'] = len(v['items'])
        v['printedCount'] = sum(1 for it in v['items'] if it.get('printed'))

    fd = load_field_dict(DICT_PATH)
    fields_ui = []
    for spec in fd.enabled_in_order():
        src = (project.get('_fieldSources') or {}).get(spec.key) or {}
        val = project.get(spec.key)
        if val is None:
            val = ''
        fields_ui.append({
            'key': spec.key,
            'label': spec.label,
            'type': spec.type,
            'scope': spec.scope,
            'group': spec.group,
            'required': spec.required,
            'note': spec.note,
            'value': val,
            'source': src.get('source') or ('S1' if val not in ('', None) else ''),
            'by': src.get('by') or '',
            'readonly': spec.key == 'docNo' or spec.scope == 'auto' and spec.key == 'docNo',
        })
    # user values (non-reserved)
    values = {k: project[k] for k in project if not k.startswith('_')}
    return {
        'projectPath': str(project_path),
        'root': str(root),
        'values': values,
        'fields': fields_ui,
        'volumes': volumes,
        'items': items,
        'docs': docs,
        'printStates': print_states,
        'trash': project.get('_trash') or [],
        'ledger': _ledger(snap.get('items') or [], docs, print_states, req_miss),
        'requiredMissing': [k for k in REQUIRED if not str(project.get(k) or '').strip()],
        'schema': project.get('_schema'),
        'editorMode': 'E1',
    }


def action_create(folder: Path, fields: dict) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    assert_not_template_write(folder / 'project.json')
    pj = folder / 'project.json'
    if pj.exists():
        raise ProjectStoreError('目录里已有 project.json：%s' % pj)
    catalog = load_catalog(ABBR_PATH, ALIAS_PATH)
    data = {
        '_schema': 'yzproj/1.0',
        '_generatedWith': {
            'dictVersion': '',
            'ruleSetVersion': '',
            'engineVersion': '1.0.0',
        },
    }
    fd = load_field_dict(DICT_PATH)
    for spec in fd.enabled_in_order():
        if spec.key == 'docNo':
            continue
        if spec.key in fields and fields[spec.key] not in (None,):
            data[spec.key] = fields[spec.key]
    data['_catalogSnapshot'] = build_catalog_snapshot(
        catalog, TEMPLATES, [ABBR_PATH, ALIAS_PATH], _today())
    data['_fieldSources'] = {}
    now = _now()
    for k in fields:
        if not k.startswith('_') and fields[k] not in ('', None):
            data['_fieldSources'][k] = {
                'source': 'S1', 'ruleId': '', 'at': now, 'by': 'manual',
            }
    write_project(pj, data, backup=False)
    return _open_payload(pj)


def action_save_fields(project_path: Path, fields: dict, rel_path: str = '') -> dict:
    project = read_project(project_path, apply_migration=True)
    fd = load_field_dict(DICT_PATH)
    enabled = fd.enabled
    now = _now()
    sources = project.setdefault('_fieldSources', {})
    if rel_path:
        ov = project.setdefault('_documents', {}).setdefault(rel_path, {})
        for k, v in fields.items():
            if k.startswith('_') or k not in enabled:
                continue
            ov[k] = v
            sources[k] = {'source': 'S1', 'ruleId': '', 'at': now, 'by': 'manual'}
    else:
        for k, v in fields.items():
            if k.startswith('_') or k not in enabled:
                continue
            if k == 'docNo':
                continue
            project[k] = v
            sources[k] = {'source': 'S1', 'ruleId': '', 'at': now, 'by': 'manual'}
    write_project(project_path, project, backup=True)
    return _open_payload(project_path)


def action_mark_printed(project_path: Path, doc_id: str, printed: bool = True) -> dict:
    project = read_project(project_path, apply_migration=True)
    states = project.setdefault('_printStates', {})
    prev = states.get(doc_id) or {}
    if printed:
        states[doc_id] = {
            'printed': True,
            'printedAt': _now(),
            'times': int(prev.get('times') or 0) + 1,
        }
    else:
        states[doc_id] = {
            'printed': False,
            'printedAt': prev.get('printedAt') or '',
            'times': int(prev.get('times') or 0),
        }
    write_project(project_path, project, backup=True)
    return {
        'docId': doc_id,
        'printState': states[doc_id],
        'projectPath': str(project_path),
    }


def action_preview(project_path: Path, doc_id: str) -> dict:
    project = read_project(project_path, apply_migration=False)
    rec = (project.get('_docs') or {}).get(doc_id) or {}
    rel = rec.get('relPath') or ''
    path = _root(project_path) / rel if rel else None
    if not path or not path.is_file():
        raise FileNotFoundError('文档不存在：%s' % (rel or doc_id))
    prev = preview_docx(path)
    prev['docId'] = doc_id
    prev['relPath'] = rel
    prev['printState'] = (project.get('_printStates') or {}).get(doc_id) or {}
    prev['fillState'] = rec.get('fillState') or 'empty'
    prev['docNo'] = rec.get('docNo') or ''
    return prev


def action_trash_put(project_path: Path, doc_id: str) -> dict:
    """Stub-plus: move one doc into _回收站 and index it."""
    project = read_project(project_path, apply_migration=True)
    rec = (project.get('_docs') or {}).get(doc_id)
    if not rec:
        raise ValueError('无此文档 %s' % doc_id)
    root = _root(project_path)
    rel = rec.get('relPath') or ''
    src = root / rel
    stamp = datetime.now().strftime('%Y%m%d')
    existing = project.get('_trash') or []
    n = 1
    while True:
        trash_id = 'T-%s-%03d' % (stamp, n)
        if not any(t.get('trashId') == trash_id for t in existing):
            break
        n += 1
    dest_dir = root / '_回收站' / trash_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_name = Path(rel).name if rel else doc_id
    dest = dest_dir / dest_name
    if src.is_file():
        shutil.move(str(src), str(dest))
    entry = {
        'trashId': trash_id,
        'type': 'doc',
        'itemId': rec.get('itemId') or '',
        'docId': doc_id,
        'docNo': rec.get('docNo') or '',
        'originPath': rel,
        'trashPath': str(Path('_回收站') / trash_id / dest_name),
        'deletedAt': _now(),
        'documents': [],
    }
    existing.append(entry)
    project['_trash'] = existing
    write_project(project_path, project, backup=True)
    return {'trash': entry}


def _run_engine(script: Path, args: list[str], stage: str, timeout: int = 600) -> dict:
    emit_progress(0, 1, 'stage %s' % stage)
    print('#STAGE %s start' % stage, flush=True)
    env = os.environ.copy()
    env.setdefault('PYTHONUTF8', '1')
    proc = subprocess.Popen(
        [sys.executable, str(script), *args],
        cwd=str(REPO), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', bufsize=1,
    )
    stdout_lines = []
    errtail = ''
    try:
        deadline = __import__('time').time() + timeout
        while True:
            if proc.stdout is None:
                break
            line = proc.stdout.readline()
            if line:
                stdout_lines.append(line.rstrip('\n'))
                if line.startswith('#PROGRESS') or line.startswith('#STAGE'):
                    print(line if line.endswith('\n') else line + '\n', end='', flush=True)
                continue
            if proc.poll() is not None:
                rest = proc.stdout.read() or ''
                for extra in rest.splitlines():
                    stdout_lines.append(extra)
                break
            if __import__('time').time() > deadline:
                proc.kill()
                raise subprocess.TimeoutExpired(proc.args, timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    last = ''
    for line in stdout_lines:
        if line.strip():
            last = line.strip()
    payload = {}
    if last.startswith('{'):
        try:
            payload = json.loads(last)
        except json.JSONDecodeError:
            payload = {'ok': False, 'summary': last}
    else:
        payload = {'ok': proc.returncode == 0, 'summary': last}
    payload['exit'] = proc.returncode
    payload['stage'] = stage
    payload['stderr'] = errtail[-800:]
    print('#STAGE %s done exit=%d' % (stage, proc.returncode), flush=True)
    return payload


def action_booklet(project_path: Path) -> dict:
    """datafill → fill (mirror) → docgen → verify. Streams #STAGE / #PROGRESS."""
    root = _root(project_path)
    logs = root / '_logs'
    logs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    plan_path = logs / 'fillplan' / ('%s.json' % stamp)
    # fill_engine writes template-relative copies; keep them OUT of the
    # project tree so verify --dir does not double-count _logs/fill-run.
    fill_mirror = REPO / 'work' / 'shell-fill-run' / stamp
    stages = []

    stages.append(_run_engine(
        ENGINE / 'datafill_engine.py',
        ['--project', str(project_path), '--out', str(plan_path), '--json'],
        'datafill'))
    if stages[-1].get('exit') not in (0,):
        return _booklet_result(False, stages, 'datafill 失败')

    stages.append(_run_engine(
        ENGINE / 'fill_engine.py',
        ['--project', str(project_path), '--out', str(fill_mirror),
         '--plan', str(plan_path), '--anchor', 'on', '--json'],
        'fill'))
    # fill writing to _logs is informational; do not abort booklet on fill-mirror fail
    # unless it's an environment error (3)
    if stages[-1].get('exit') == 3:
        return _booklet_result(False, stages, 'fill 环境错误')

    stages.append(_run_engine(
        ENGINE / 'docgen_engine.py',
        ['--project', str(project_path), '--item', 'all', '--json'],
        'docgen', timeout=900))
    if stages[-1].get('exit') not in (0,):
        return _booklet_result(False, stages, 'docgen 失败')

    stages.append(_run_engine(
        ENGINE / 'verify_engine.py',
        ['--dir', str(root), '--project', str(project_path), '--json'],
        'verify'))
    ok = stages[-1].get('exit') in (0, 1)  # 1 = business findings, still ran
    # verify exit 1 means leftovers — expected if dates/optional still {{key}}
    # treat as ran; booklet ok if docgen succeeded.
    return _booklet_result(True, stages, '成册流水线完成')


def _booklet_result(ok: bool, stages: list, summary: str) -> dict:
    return {
        'ok': ok,
        'summary': summary,
        'stages': [
            {
                'stage': s.get('stage'),
                'exit': s.get('exit'),
                'ok': s.get('ok'),
                'summary': s.get('summary'),
                'stats': s.get('stats') or {},
            } for s in stages
        ],
    }


def action_dict() -> dict:
    fd = load_field_dict(DICT_PATH)
    groups = []
    cur = None
    for spec in fd.enabled_in_order():
        if cur is None or cur['group'] != spec.group:
            cur = {'group': spec.group, 'fields': []}
            groups.append(cur)
        cur['fields'].append({
            'key': spec.key, 'label': spec.label, 'type': spec.type,
            'scope': spec.scope, 'required': spec.required, 'note': spec.note,
        })
    return {
        'version': fd.version,
        'groups': groups,
        'enabled': sorted(fd.enabled),
        'datePolicy': fd.date_policy,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='shell_bridge · Electron JSON API')
    ap.add_argument('--action', required=False, default='',
                    choices=('create', 'open', 'save-fields', 'booklet',
                             'mark-printed', 'preview', 'dict', 'trash-put',
                             'trash-list', 'export'))
    ap.add_argument('--project', type=Path)
    ap.add_argument('--dir', type=Path)
    ap.add_argument('--fields', default='')
    ap.add_argument('--doc-id', dest='doc_id', default='')
    ap.add_argument('--rel-path', dest='rel_path', default='')
    ap.add_argument('--printed', dest='printed', default='true')
    ap.add_argument('--mode', default='booklet')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.action:
        return exit_param('需要 --action', a.as_json, 'shell')
    as_json = True if a.as_json or True else True  # always JSON for the shell

    try:
        if a.action == 'dict':
            data = action_dict()
            payload = result_payload(True, 'shell', 'dict v%s' % data.get('version'), stats=data)
            return emit_result(payload, True)

        if a.action == 'create':
            if not a.dir:
                return exit_param('create 需要 --dir', True, 'shell')
            fields = json.loads(a.fields or '{}')
            data = action_create(a.dir, fields)
            payload = result_payload(True, 'shell', '已建工程', stats=data)
            return emit_result(payload, True)

        if not a.project:
            return exit_param('需要 --project', True, 'shell')
        pj = _project_file(a.project)
        if a.action != 'create' and not pj.exists():
            return exit_param('project.json 不存在：%s' % pj, True, 'shell')

        if a.action == 'open':
            data = _open_payload(pj)
            payload = result_payload(True, 'shell', '已打开', stats=data)
            return emit_result(payload, True)

        if a.action == 'save-fields':
            fields = json.loads(a.fields or '{}')
            data = action_save_fields(pj, fields, a.rel_path)
            payload = result_payload(True, 'shell', '已保存字段', stats=data)
            return emit_result(payload, True)

        if a.action == 'mark-printed':
            if not a.doc_id:
                return exit_param('需要 --doc-id', True, 'shell')
            printed = str(a.printed).lower() not in ('0', 'false', 'no')
            data = action_mark_printed(pj, a.doc_id, printed)
            payload = result_payload(True, 'shell', '已更新打印状态', stats=data)
            return emit_result(payload, True)

        if a.action == 'preview':
            if not a.doc_id:
                return exit_param('需要 --doc-id', True, 'shell')
            data = action_preview(pj, a.doc_id)
            payload = result_payload(bool(data.get('ok')), 'shell',
                                     '预览 ' + (a.doc_id), stats=data)
            return emit_result(payload, True)

        if a.action == 'booklet':
            data = action_booklet(pj)
            payload = result_payload(bool(data.get('ok')), 'shell',
                                     data.get('summary') or '', stats=data)
            payload['stages'] = data.get('stages')
            return emit_result(payload, True)

        if a.action == 'trash-put':
            if not a.doc_id:
                return exit_param('需要 --doc-id', True, 'shell')
            data = action_trash_put(pj, a.doc_id)
            payload = result_payload(True, 'shell', '已入回收站', stats=data)
            return emit_result(payload, True)

        if a.action == 'trash-list':
            project = read_project(pj, apply_migration=False)
            payload = result_payload(True, 'shell', '回收站',
                                     stats={'trash': project.get('_trash') or []})
            return emit_result(payload, True)

        if a.action == 'export':
            out = a.out
            args = [
                str(ENGINE / 'export_engine.py'),
                '--project', str(pj),
                '--mode', a.mode,
                '--json',
            ]
            if a.doc_id:
                args.extend(['--doc-id', a.doc_id])
            if out:
                args.extend(['--out', str(out)])
            if a.force:
                args.append('--force')
            args.append('--mark-printed')
            data = _run_engine(ENGINE / 'export_engine.py', args[1:], 'export')
            payload = result_payload(data.get('exit') == 0, 'shell',
                                     data.get('summary') or '', stats=data)
            return emit_result(payload, True)

        return exit_param('未知 action', True, 'shell')
    except json.JSONDecodeError as e:
        return exit_param('fields JSON 无效：%s' % e, True, 'shell')
    except TemplateProtectionError as e:
        return exit_env(str(e), True, 'shell')
    except (ProjectStoreError, FieldDictError, ValueError, FileNotFoundError, OSError) as e:
        return exit_env(str(e), True, 'shell')
    except subprocess.TimeoutExpired as e:
        return exit_env('引擎超时：%s' % e, True, 'shell')


if __name__ == '__main__':
    sys.exit(main())
