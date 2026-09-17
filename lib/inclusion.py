# -*- coding: utf-8 -*-
"""ADR-21 catalog inclusion: required vs optional.

真源只有 `表名缩写字典.csv` 的「收录」列（必选 / 可选）→ 字段 `inclusion`。
**禁止**从 `软件目录.docx` 的「重要/普通/一般」推导（该文件没有「必须」字段）。

`docgen --item all` / 一键成册只生成必选；可选默认 0 份，由右键「新建表格」追加。
"""
from __future__ import annotations

from typing import Iterable, List, Optional

INCLUSION_REQUIRED = 'required'
INCLUSION_OPTIONAL = 'optional'
INCLUSION_COL = '收录'
TEMPLATE_STATUS_COL = '模板状态'
REQUIRED_LABEL = '必选'
OPTIONAL_LABEL = '可选'
UPLOAD_STATUS = '上传项'
HAS_TEMPLATE_STATUS = '有模板'

# 首刀（仅在「收录」列为空时回退；正常以字典列为准）
# 上传项全部可选；二-01～05 有模板也显式可选；其余有模板 = 必选
# 37 有模板 − 5 显式可选 = 32 必选；19 上传 + 5 = 24 可选
FIRST_CUT_OPTIONAL_TEMPLATE_IDS = ('二-01', '二-02', '二-03', '二-04', '二-05')
FIRST_CUT_REQUIRED_COUNT = 32
FIRST_CUT_OPTIONAL_COUNT = 24

_REQUIRED_TOKENS = {
    REQUIRED_LABEL, INCLUSION_REQUIRED, '是', 'true', 'True', '1',
}
_OPTIONAL_TOKENS = {
    OPTIONAL_LABEL, INCLUSION_OPTIONAL, '否', 'false', 'False', '0',
}


def first_cut_inclusion(item_id: str, template_status: str = '',
                        has_template: Optional[bool] = None) -> str:
    """Dictionary-only fallback. Never reads 软件目录.docx."""
    if item_id in FIRST_CUT_OPTIONAL_TEMPLATE_IDS:
        return INCLUSION_OPTIONAL
    status = (template_status or '').strip()
    if status == UPLOAD_STATUS or has_template is False:
        return INCLUSION_OPTIONAL
    if status == HAS_TEMPLATE_STATUS or has_template is True:
        return INCLUSION_REQUIRED
    return INCLUSION_OPTIONAL


def parse_inclusion(raw: str, item_id: str = '', template_status: str = '',
                    has_template: Optional[bool] = None) -> str:
    s = (raw or '').strip()
    if s in _REQUIRED_TOKENS:
        return INCLUSION_REQUIRED
    if s in _OPTIONAL_TOKENS:
        return INCLUSION_OPTIONAL
    return first_cut_inclusion(item_id, template_status, has_template)


def inclusion_label(value: str) -> str:
    return REQUIRED_LABEL if value == INCLUSION_REQUIRED else OPTIONAL_LABEL


def is_required(item) -> bool:
    if item is None:
        return False
    if isinstance(item, dict):
        inc = item.get('inclusion') or ''
        if inc:
            return inc == INCLUSION_REQUIRED
        return first_cut_inclusion(
            item.get('itemId') or '',
            has_template=item.get('hasTemplate')) == INCLUSION_REQUIRED
    inc = getattr(item, 'inclusion', '') or ''
    if inc:
        return inc == INCLUSION_REQUIRED
    return first_cut_inclusion(getattr(item, 'item_id', '') or '') == INCLUSION_REQUIRED


def booklet_items(items: Iterable) -> List:
    """One-click booklet / `--item all`: required catalog rows only."""
    return [it for it in items if is_required(it)]
