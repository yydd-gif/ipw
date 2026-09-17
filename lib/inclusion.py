# -*- coding: utf-8 -*-
"""ADR-21 catalog inclusion: required vs optional.

真源：`表名缩写字典.csv` 的「收录」列（必选 / 可选）。
`docgen --item all` / 一键成册只生成必选；可选默认 0 份，由右键「新建表格」追加。
"""
from __future__ import annotations

from typing import Iterable, List

INCLUSION_REQUIRED = 'required'
INCLUSION_OPTIONAL = 'optional'
INCLUSION_COL = '收录'
REQUIRED_LABEL = '必选'
OPTIONAL_LABEL = '可选'

# 首刀：上传项全部可选；有模板默认可选，例外为 二-01～05
FIRST_CUT_REQUIRED_IDS = ('二-01', '二-02', '二-03', '二-04', '二-05')

_REQUIRED_TOKENS = {
    REQUIRED_LABEL, INCLUSION_REQUIRED, '是', 'true', 'True', '1',
}
_OPTIONAL_TOKENS = {
    OPTIONAL_LABEL, INCLUSION_OPTIONAL, '否', 'false', 'False', '0',
}


def parse_inclusion(raw: str, item_id: str = '') -> str:
    s = (raw or '').strip()
    if s in _REQUIRED_TOKENS:
        return INCLUSION_REQUIRED
    if s in _OPTIONAL_TOKENS:
        return INCLUSION_OPTIONAL
    if item_id in FIRST_CUT_REQUIRED_IDS:
        return INCLUSION_REQUIRED
    return INCLUSION_OPTIONAL


def inclusion_label(value: str) -> str:
    return REQUIRED_LABEL if value == INCLUSION_REQUIRED else OPTIONAL_LABEL


def is_required(item) -> bool:
    if item is None:
        return False
    if isinstance(item, dict):
        inc = item.get('inclusion') or ''
        if inc:
            return inc == INCLUSION_REQUIRED
        return (item.get('itemId') or '') in FIRST_CUT_REQUIRED_IDS
    inc = getattr(item, 'inclusion', '') or ''
    if inc:
        return inc == INCLUSION_REQUIRED
    return (getattr(item, 'item_id', '') or '') in FIRST_CUT_REQUIRED_IDS


def booklet_items(items: Iterable) -> List:
    """One-click booklet / `--item all`: required catalog rows only."""
    return [it for it in items if is_required(it)]
