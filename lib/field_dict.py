# -*- coding: utf-8 -*-
"""字段字典加载器 · `assets/spec/字段字典.json` 是启用字段的唯一真源."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


class FieldDictError(ValueError):
    """字典缺失、损坏或结构不合法."""


@dataclass
class FieldSpec:
    key: str
    label: str = ''
    type: str = 'text'
    scope: str = 'project'
    required: Any = False
    default: str = ''
    note: str = ''
    aliases: List[str] = field(default_factory=list)
    group: str = ''
    status: str = 'enabled'  # enabled | disabled | removed
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_enabled(self) -> bool:
        return self.status == 'enabled'


@dataclass
class TableSpec:
    key: str
    label: str = ''
    columns: List[str] = field(default_factory=list)
    used_by: List[str] = field(default_factory=list)
    note: str = ''


@dataclass
class FieldDict:
    path: Path
    raw: Dict[str, Any]
    version: str
    fields: Dict[str, FieldSpec]
    tables: Dict[str, TableSpec]
    date_policy: Dict[str, Any]
    table_policy: Dict[str, Any]

    @property
    def enabled(self) -> Set[str]:
        return {k for k, f in self.fields.items() if f.status == 'enabled'}

    @property
    def disabled(self) -> Set[str]:
        return {k for k, f in self.fields.items() if f.status == 'disabled'}

    @property
    def removed(self) -> Set[str]:
        return {k for k, f in self.fields.items() if f.status == 'removed'}

    @property
    def known_keys(self) -> Set[str]:
        """规则允许引用的 key：启用 + 停用 + 归档 + 子表."""
        return set(self.fields) | set(self.tables)

    def get(self, key: str) -> Optional[FieldSpec]:
        return self.fields.get(key)

    def enabled_in_order(self) -> List[FieldSpec]:
        return [f for f in self.fields.values() if f.status == 'enabled']

    def project_keys(self) -> List[str]:
        return [f.key for f in self.enabled_in_order() if f.scope == 'project']


def load_field_dict(path: Path | str) -> FieldDict:
    p = Path(path)
    if not p.exists():
        raise FieldDictError('字段字典不存在：%s' % p)
    try:
        raw = json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        raise FieldDictError('字段字典不是合法 JSON：%s (%s)' % (p, e)) from e
    if not isinstance(raw, dict):
        raise FieldDictError('字段字典顶层必须是 object')

    fields: Dict[str, FieldSpec] = {}
    for group in raw.get('groups') or []:
        gname = group.get('group') or ''
        for item in group.get('fields') or []:
            spec = _field_from(item, group=gname, status='enabled')
            if spec.key in fields:
                raise FieldDictError('字段字典重复 key：%s' % spec.key)
            fields[spec.key] = spec

    for item in raw.get('disabledFields') or []:
        spec = _field_from(item, status='disabled')
        fields.setdefault(spec.key, spec)

    removed_block = raw.get('removedFields') or {}
    for item in removed_block.get('fields') or []:
        spec = _field_from(item, status='removed')
        fields.setdefault(spec.key, spec)

    tables: Dict[str, TableSpec] = {}
    for item in raw.get('tables') or []:
        key = item.get('key') or ''
        if not key:
            continue
        tables[key] = TableSpec(
            key=key,
            label=item.get('label') or '',
            columns=list(item.get('columns') or []),
            used_by=list(item.get('usedBy') or []),
            note=item.get('note') or '',
        )

    enabled_n = sum(1 for f in fields.values() if f.status == 'enabled')
    if enabled_n == 0:
        raise FieldDictError('字段字典没有任何启用字段')

    return FieldDict(
        path=p,
        raw=raw,
        version=str(raw.get('version') or ''),
        fields=fields,
        tables=tables,
        date_policy=dict(raw.get('datePolicy') or {}),
        table_policy=dict(raw.get('tablePolicy') or {}),
    )


def _field_from(item: dict, group: str = '', status: str = 'enabled') -> FieldSpec:
    key = item.get('key') or ''
    if not key:
        raise FieldDictError('字段条目缺少 key')
    extra = {k: v for k, v in item.items()
             if k not in ('key', 'label', 'type', 'scope', 'required',
                          'default', 'note', 'aliases')}
    return FieldSpec(
        key=key,
        label=item.get('label') or '',
        type=item.get('type') or 'text',
        scope=item.get('scope') or 'project',
        required=item.get('required', False),
        default=item.get('default') if item.get('default') is not None else '',
        note=item.get('note') or '',
        aliases=list(item.get('aliases') or []),
        group=group or (item.get('was') or ''),
        status=status,
        extra=extra,
    )
