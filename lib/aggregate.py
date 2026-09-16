# -*- coding: utf-8 -*-
"""T7 helpers: period windows, source docs, four-column values.

Deterministic. Does not call a model. Fabricated facts are out of scope —
values are joined from existing document fields via the 9-class rule engine.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from lib.date_window import Window, in_window, parse_iso_date
from lib.rule_engine import (
    Catalog, DocCtx, FieldDict, RuleSet, _collect_docs, _eval_conditions,
    _resolve_doc, normalize_item_id,
)

UNRECORDED = '（日志未记载）'

PERIOD_SOURCE = {'week': '二-10', 'month': '二-11'}
PERIOD_TARGET = {'week': '二-11', 'month': '二-12'}
PERIOD_COLUMNS = {
    'week': ('weeklyDone', 'weeklyUndone', 'weeklyProblem', 'weeklyPlan'),
    'month': ('monthlyDone', 'monthlyUndone', 'monthlyProblem', 'monthlyPlan'),
}


def source_item_id(period: str) -> str:
    return PERIOD_SOURCE.get(period, '二-10')


def target_item_id(period: str) -> str:
    return PERIOD_TARGET.get(period, '二-11')


def columns_for(period: str) -> Tuple[str, ...]:
    return PERIOD_COLUMNS.get(period, PERIOD_COLUMNS['week'])


def doc_date(doc: DocCtx) -> Optional[str]:
    for key in ('logDate', 'docDate', 'weekStart', 'monthStart', 'date'):
        parsed = parse_iso_date(doc.overrides.get(key))
        if parsed is not None:
            return parsed.isoformat()
    parsed = parse_iso_date(doc.rel_path)
    if parsed is not None:
        return parsed.isoformat()
    parsed = parse_iso_date(doc.doc_id)
    if parsed is not None:
        return parsed.isoformat()
    return None


def docs_in_window(docs: List[DocCtx], window: Optional[Window]) -> List[DocCtx]:
    if window is None:
        return list(docs)
    out = []
    for d in docs:
        if in_window(doc_date(d), window):
            out.append(d)
    return out


def source_docs(project: dict, catalog: Catalog, period: str,
                window: Optional[Window]) -> List[DocCtx]:
    all_docs = _collect_docs(project, catalog)
    item_id = normalize_item_id(source_item_id(period))
    matched = [d for d in all_docs if d.item_id == item_id]
    return docs_in_window(matched, window)


def resolve_target_values(project: dict, field_dict: FieldDict, rule_set: RuleSet,
                          catalog: Catalog, period: str,
                          window: Optional[Window]) -> Dict[str, dict]:
    """Run FillPlan producers as if filling a new weekly/monthly report."""
    rule_set.window = window
    all_docs = _collect_docs(project, catalog)
    attrs = _eval_conditions(project, rule_set)
    dummy = DocCtx(
        doc_id='_aggregate',
        item_id=normalize_item_id(target_item_id(period)),
        rel_path='', overrides={}, is_project=False,
    )
    values = _resolve_doc(dummy, project, field_dict, rule_set, catalog, attrs,
                          all_docs)
    return values


def four_columns(values: Dict[str, dict], period: str) -> Dict[str, str]:
    """Materialise the four report columns. Missing → UNRECORDED, never invent."""
    out = {}
    for key in columns_for(period):
        slot = values.get(key) or {}
        text = slot.get('value')
        if text in (None, ''):
            out[key] = UNRECORDED
        else:
            out[key] = str(text)
    return out


def public_items(values: Dict[str, dict], extra: Dict[str, str],
                 period: str) -> list:
    keys = list(columns_for(period))
    for extra_key in ('weather', 'workerCount', 'projectStage'):
        if extra_key not in keys:
            keys.append(extra_key)
    items = []
    for key in keys:
        if key in extra:
            items.append({
                'key': key, 'value': extra[key],
                'source': 'S4', 'ruleId': 't7.column',
            })
            continue
        slot = values.get(key) or {}
        items.append({
            'key': key,
            'value': slot.get('value'),
            'source': slot.get('source') or '',
            'ruleId': slot.get('ruleId') or '',
            'state': slot.get('state') or 'missing',
        })
    return items
