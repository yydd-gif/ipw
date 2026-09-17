# -*- coding: utf-8 -*-
"""目录快照 / 模板定位 / 工程内路径.

清单规模以 `表名缩写字典.csv` 为准（56 = 37 有模板 + 19 上传项）。
分册名一律走别名表标准名，才能对上 `assets/templates/` 的实际目录。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional

from lib.inclusion import inclusion_label
from lib.rule_engine import Catalog, CatalogItem, load_catalog

UPLOAD_TYPE = '上传附件'
GOV_VOL_MARK = '政务信息化'
ENGINEERING = '工程建设类'
GOV = '政务信息化类'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return 'sha256:%s' % h.hexdigest()


def item_folder(item: CatalogItem) -> str:
    """工程内目录项文件夹：`{分册}/{序号}、{目录项名}`."""
    return '%s/%d、%s' % (item.volume, item.seq, item.name)


def template_filename(item: CatalogItem) -> str:
    return '%d、%s.docx' % (item.seq, item.name)


def find_template(templates: Path, item: CatalogItem) -> Optional[Path]:
    """Locate the live template; try standard volume then alias-less fallbacks."""
    name = template_filename(item)
    candidates = [
        Path(templates) / item.volume / name,
        Path(templates) / name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    # 容错：同序号 + 文件名以目录项名结尾
    vol_dir = Path(templates) / item.volume
    if vol_dir.is_dir():
        prefix = '%d、' % item.seq
        for p in sorted(vol_dir.glob('*.docx')):
            if p.name.startswith('~$'):
                continue
            if p.name.startswith(prefix) and item.name in p.name:
                return p
    return None


def data_type_for(item: CatalogItem, has_template: bool) -> str:
    if not has_template:
        return UPLOAD_TYPE
    if GOV_VOL_MARK in (item.volume or ''):
        return GOV
    return ENGINEERING


def snapshot_item(item: CatalogItem, templates: Path) -> dict:
    tpl = find_template(templates, item)
    has = tpl is not None
    return {
        'itemId': item.item_id,
        'volume': item.volume,
        'volumeSeq': item.volume_seq,
        'seq': item.seq,
        'name': item.name,
        'relPath': item_folder(item),
        'hasTemplate': has,
        'dataType': data_type_for(item, has),
        # importance 仅展示；收录只看字典 inclusion，不从 软件目录.docx 重要/普通推导
        'importance': '普通项',
        'templateFile': tpl.name if tpl else '',
        'abbr': item.abbr,
        'docDigits': item.digits,
        'numbered': item.numbered,
        'inclusion': item.inclusion,
        'inclusionLabel': inclusion_label(item.inclusion),
    }


def build_catalog_snapshot(catalog: Catalog, templates: Path,
                           source_paths: List[Path], parsed_at: str) -> dict:
    items = [snapshot_item(it, templates) for it in catalog.items]
    hashes = []
    for p in source_paths:
        if p and Path(p).exists():
            hashes.append(sha256_file(Path(p)))
    return {
        'version': '1.0',
        'parsedAt': parsed_at,
        'sourceHash': '|'.join(hashes),
        'items': items,
    }


def numbered_filename(doc_no: str, name: str) -> str:
    return '%s_%s.docx' % (doc_no, name)


def plain_filename(name: str) -> str:
    return '%s.docx' % name


def upload_filename(name: str) -> str:
    return '%s.upload.json' % name
