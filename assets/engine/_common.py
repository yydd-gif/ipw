#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for the 7 deterministic engines.

Layout (施工交接说明 §5):
  assets/engine/<this file>
  BASE = parents[1] = assets/
  REPO = assets' parent
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
BASE = ENGINE_DIR.parent  # assets/  — equivalent of the pack-root parents[1] fix
REPO = BASE.parent
TEMPLATES = BASE / 'templates'
SPEC = BASE / 'spec'
TEMPLATES_BACKUP = BASE / 'templates-backup'
EXAMPLES = REPO / 'examples'
DICT_PATH = SPEC / '字段字典.json'
ABBR_PATH = SPEC / '表名缩写字典.csv'
RULES_PATH = SPEC / '填数规则.yaml'
VENDOR = REPO / 'lib' / 'vendor'

# Packaged extraResources put pypdf here; keep importable without system site-packages.
for _vendor in (VENDOR, REPO / 'vendor'):
    if _vendor.is_dir() and str(_vendor) not in sys.path:
        sys.path.insert(0, str(_vendor))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def work_dir() -> Path:
    """Writable engine scratch. Packaged installs must not write next to extraResources."""
    env = (os.environ.get('YANSHOU_WORK') or '').strip()
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(REPO / 'work')
    candidates.append(Path(tempfile.gettempdir()) / 'yanshou-work')
    last_err = None
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / '.write-test'
            probe.write_text('ok', encoding='utf-8')
            probe.unlink()
            return cand
        except OSError as e:
            last_err = e
            continue
    raise OSError('no writable work dir: %s' % last_err)


WORK = Path(os.environ['YANSHOU_WORK']) if os.environ.get('YANSHOU_WORK') else (REPO / 'work')

SKIP_DIR_NAMES = {'00_模板原始备份'}


class TemplateProtectionError(Exception):
    """Raised when a caller tries to write into frozen template assets."""


def wns_tag(tag: str, ns: str = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main') -> str:
    return '{%s}%s' % (ns, tag)


def iter_templates(root: Path):
    """Yield live template docx files; skip backups, lock files, and .gitkeep dirs."""
    if not root.exists():
        return
    for p in sorted(root.rglob('*.docx')):
        if p.name.startswith('~$'):
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        yield p


def frozen_roots():
    roots = []
    for p in (TEMPLATES, TEMPLATES_BACKUP):
        try:
            roots.append(p.resolve())
        except OSError:
            pass
    return roots


def assert_not_template_write(path: Path) -> Path:
    """Refuse any write whose resolved path sits under frozen template trees."""
    target = Path(path).resolve()
    for frozen in frozen_roots():
        try:
            target.relative_to(frozen)
        except ValueError:
            continue
        raise TemplateProtectionError(
            'refusing to write inside frozen templates: %s' % target)
    return target


def emit_progress(done: int, total: int, desc: str) -> None:
    print('#PROGRESS %d/%d %s' % (done, total, desc), flush=True)


def result_payload(ok: bool, engine: str, summary: str,
                   stats=None, items=None, errors=None) -> dict:
    return {
        'ok': bool(ok),
        'engine': engine,
        'summary': summary,
        'stats': stats or {},
        'items': items or [],
        'errors': errors or [],
    }


def emit_result(payload: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False), flush=True)
    else:
        print(payload.get('summary', ''), flush=True)
        for err in payload.get('errors') or []:
            print('  [%s] %s' % (err.get('level', 'warn'), err.get('reason', '')),
                  file=sys.stderr)
    if payload.get('ok'):
        return 0
    # default business failure; callers may sys.exit() a more specific code
    return 1


def exit_param(msg: str, as_json: bool = False, engine: str = '') -> int:
    if as_json:
        print(json.dumps(result_payload(
            False, engine or 'unknown', msg,
            errors=[{'reason': msg, 'level': 'block'}],
        ), ensure_ascii=False))
    else:
        print(msg, file=sys.stderr)
    return 2


def exit_env(msg: str, as_json: bool = False, engine: str = '') -> int:
    if as_json:
        print(json.dumps(result_payload(
            False, engine or 'unknown', msg,
            errors=[{'reason': msg, 'level': 'block'}],
        ), ensure_ascii=False))
    else:
        print(msg, file=sys.stderr)
    return 3
