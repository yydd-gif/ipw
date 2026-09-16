# -*- coding: utf-8 -*-
"""Atomic read/write of `project.json` with auto-backup and `_schema` migration stub.

规格：`docs/设计文档/数据与规则规格.md` §2 / §8。
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

CURRENT_SCHEMA = 'yzproj/1.0'
ENGINE_VERSION_DEFAULT = '1.0.0'
BACKUP_KEEP = 20

RESERVED_ORDER = [
    '_schema',
    '_generatedWith',
    '_assets',
    '_documents',
    '_numbering',
    '_printStates',
    '_catalogSnapshot',
    '_docs',
    '_trash',
    '_fieldSources',
]

RESERVED = set(RESERVED_ORDER)

EMPTY_RESERVED = {
    '_assets': dict,
    '_documents': dict,
    '_numbering': dict,
    '_printStates': dict,
    '_catalogSnapshot': dict,
    '_docs': dict,
    '_trash': list,
    '_fieldSources': dict,
}


class ProjectStoreError(ValueError):
    """project.json 读写 / 迁移失败."""


def read_project(path: Path | str, apply_migration: bool = False) -> dict:
    """Read project.json. Missing `_schema` is filled in-memory as yzproj/1.0.

    When `apply_migration` is true and the in-memory document changed,
    an automatic backup is taken and the migrated document is written back
    (规格 §8：打开旧工程时自动备份后迁移).
    """
    p = Path(path)
    if not p.exists():
        raise ProjectStoreError('project.json 不存在：%s' % p)
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        raise ProjectStoreError('project.json 不是合法 JSON：%s (%s)' % (p, e)) from e
    if not isinstance(data, dict):
        raise ProjectStoreError('project.json 顶层必须是 object')
    migrated, changed = migrate_project(data)
    if apply_migration and changed:
        write_project(p, migrated, backup=True)
    return migrated


def write_project(path: Path | str, data: dict, backup: bool = True,
                  generated_with: dict | None = None) -> Path:
    """Atomically write project.json (tmp + fsync + os.replace).

    Previous file is copied to `<工程>/_logs/backup/project-YYYYMMDD-HHmm.json`
    and only the newest 20 backups are kept.
    """
    p = Path(path)
    _assert_not_frozen(p)
    if not isinstance(data, dict):
        raise ProjectStoreError('project data must be a dict')
    migrated, _changed = migrate_project(data)
    if generated_with:
        gw = dict(migrated.get('_generatedWith') or {})
        gw.update(generated_with)
        migrated['_generatedWith'] = gw
    _ensure_reserved(migrated)
    payload = _canonical(migrated)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'

    p.parent.mkdir(parents=True, exist_ok=True)
    if backup and p.exists():
        _backup(p)

    tmp = p.with_name(p.name + '.tmp')
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode('utf-8'))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(str(tmp), str(p))
    return p


def migrate_project(data: dict) -> Tuple[dict, bool]:
    """Return (migrated_copy, changed). Stub: only fills missing `_schema`.

    Future major versions drop in `lib/migrate_<from>_to_<to>.py` with
    `migrate(data) -> dict`. Unknown schemas raise ProjectStoreError.
    """
    out = json.loads(json.dumps(data, ensure_ascii=False))  # deep copy via json
    changed = False
    schema = out.get('_schema')
    if not schema:
        out['_schema'] = CURRENT_SCHEMA
        changed = True
        schema = CURRENT_SCHEMA
    if schema == CURRENT_SCHEMA:
        if _ensure_reserved(out):
            changed = True
        return out, changed
    migrated = _run_migrate_hook(schema, CURRENT_SCHEMA, out)
    migrated['_schema'] = CURRENT_SCHEMA
    _ensure_reserved(migrated)
    return migrated, True


def backup_dir_for(project_path: Path) -> Path:
    return Path(project_path).resolve().parent / '_logs' / 'backup'


def list_backups(project_path: Path) -> List[Path]:
    d = backup_dir_for(project_path)
    if not d.exists():
        return []
    files = sorted(d.glob('project-*.json'))
    return files


# ---------------------------------------------------------------- internals

def _ensure_reserved(data: dict) -> bool:
    changed = False
    if '_schema' not in data or not data['_schema']:
        data['_schema'] = CURRENT_SCHEMA
        changed = True
    if not isinstance(data.get('_generatedWith'), dict):
        data['_generatedWith'] = {
            'dictVersion': '',
            'ruleSetVersion': '',
            'engineVersion': ENGINE_VERSION_DEFAULT,
        }
        changed = True
    else:
        gw = data['_generatedWith']
        for k in ('dictVersion', 'ruleSetVersion', 'engineVersion'):
            gw.setdefault(k, '')
    for key, factory in EMPTY_RESERVED.items():
        if key not in data or data[key] is None:
            data[key] = factory()
            changed = True
        else:
            expected = dict if factory is dict else list
            if not isinstance(data[key], expected):
                raise ProjectStoreError('%s 必须是 %s' % (key, expected.__name__))
    return changed


def _canonical(data: dict) -> dict:
    """Stable key order: schema + generatedWith, user fields, remaining reserved."""
    out: Dict[str, Any] = {}
    if '_schema' in data:
        out['_schema'] = data['_schema']
    if '_generatedWith' in data:
        out['_generatedWith'] = data['_generatedWith']
    user_keys = [k for k in data.keys() if not k.startswith('_')]
    for k in user_keys:
        out[k] = data[k]
    for k in RESERVED_ORDER:
        if k in ('_schema', '_generatedWith'):
            continue
        if k in data:
            out[k] = data[k]
    for k, v in data.items():
        if k not in out:
            out[k] = v
    return out


def _backup(path: Path) -> Path:
    dest_dir = backup_dir_for(path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M')
    dest = dest_dir / ('project-%s.json' % stamp)
    n = 1
    while dest.exists():
        dest = dest_dir / ('project-%s-%02d.json' % (stamp, n))
        n += 1
    shutil.copy2(str(path), str(dest))
    existing = sorted(dest_dir.glob('project-*.json'))
    extra = len(existing) - BACKUP_KEEP
    if extra > 0:
        for old in existing[:extra]:
            try:
                old.unlink()
            except OSError:
                pass
    return dest


def _run_migrate_hook(from_schema: str, to_schema: str, data: dict) -> dict:
    from_id = from_schema.replace('/', '_').replace('.', '_')
    to_id = to_schema.replace('/', '_').replace('.', '_')
    mod_name = 'migrate_%s_to_%s' % (from_id, to_id)
    try:
        import importlib
        mod = importlib.import_module('lib.%s' % mod_name)
    except ImportError:
        raise ProjectStoreError(
            'unsupported _schema %r (expected %r); '
            'migration hook lib/%s.py is not implemented'
            % (from_schema, to_schema, mod_name)) from None
    if not hasattr(mod, 'migrate'):
        raise ProjectStoreError('%s.py 缺少 migrate(data) -> dict' % mod_name)
    result = mod.migrate(data)
    if not isinstance(result, dict):
        raise ProjectStoreError('%s.migrate 必须返回 dict' % mod_name)
    return result


def _assert_not_frozen(path: Path) -> None:
    """Refuse writes that land under frozen template trees (红线 1)."""
    target = Path(path).resolve()
    for i, part in enumerate(target.parts):
        if part in ('templates', 'templates-backup'):
            if i > 0 and target.parts[i - 1] == 'assets':
                raise ProjectStoreError(
                    'refusing to write inside frozen templates: %s' % target)
