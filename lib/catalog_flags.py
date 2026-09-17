# -*- coding: utf-8 -*-
"""Catalog inclusion (required vs optional) and importance metadata.

Source of truth for booklet generation: dictionary column ``收录`` → field
``inclusion`` (``required`` / ``optional``). Do **not** derive required from
软件目录.docx 重要项 / 普通项 / 一般项 — that file has no 必须 field.

First-version roster (until ``收录`` is fully populated):
  - every **upload** item → optional
  - catalog ids **二-01～二-05** → optional
  - every other **templated** item → required
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Tuple
from xml.etree import ElementTree as ET

W_T = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'
W_P = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'
CN_VOL = '一二三四五六七八'

# Last parenthetical is the metadata bag; names may contain （个人） etc.
ITEM_RE = re.compile(
    r'^(\d+)\s*[.．、]?\s*(.+?)\s*（([^）]*)）\s*；?\s*$'
)
IMPORTANCE_TOKENS = ('重要项', '普通项', '一般项')
INCLUSION_REQUIRED = 'required'
INCLUSION_OPTIONAL = 'optional'
OPTIONAL_TEMPLATED_IDS = frozenset('二-%02d' % n for n in range(1, 6))
_REQUIRED_TOKENS = frozenset({
    'required', '必选', '必须', '必填', '收录',
})
_OPTIONAL_TOKENS = frozenset({
    'optional', '可选', '非必须', '不收录',
})
UPLOAD_STATUS = frozenset({'上传项', '上传', 'upload'})


def catalog_docx_path(abbr_path: Path | None = None,
                      extra: Iterable[Path] | None = None) -> Path | None:
    """Prefer assets/spec/软件目录.docx, then docs/原始资料 copy."""
    candidates = []
    if abbr_path:
        candidates.append(Path(abbr_path).parent / '软件目录.docx')
    if extra:
        candidates.extend(Path(p) for p in extra)
    seen = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return p
    return None


def _para_texts(path: Path) -> list:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read('word/document.xml'))
    out = []
    for p in root.iter(W_P):
        t = ''.join(n.text or '' for n in p.iter(W_T)).strip()
        if t:
            out.append(t)
    return out


def _importance_from_meta(meta: str) -> str:
    if '重要项' in meta:
        return '重要项'
    if '一般项' in meta:
        return '一般项'
    if '普通项' in meta:
        return '普通项'
    return '普通项'


def parse_inclusion(raw: str) -> str:
    """Return required/optional from a 收录 cell, or '' if blank/unknown."""
    s = (raw or '').strip()
    if not s:
        return ''
    key = s.lower()
    if s in _REQUIRED_TOKENS or key in _REQUIRED_TOKENS:
        return INCLUSION_REQUIRED
    if s in _OPTIONAL_TOKENS or key in _OPTIONAL_TOKENS:
        return INCLUSION_OPTIONAL
    return ''


def is_upload_status(status: str) -> bool:
    return (status or '').strip() in UPLOAD_STATUS


def default_inclusion(*, item_id: str, is_upload: bool) -> str:
    """First-version roster used when 收录 is empty."""
    if is_upload or (item_id or '') in OPTIONAL_TEMPLATED_IDS:
        return INCLUSION_OPTIONAL
    return INCLUSION_REQUIRED


def resolve_inclusion(*, item_id: str, csv_value: str = '',
                      is_upload: bool = False) -> str:
    parsed = parse_inclusion(csv_value)
    if parsed:
        return parsed
    return default_inclusion(item_id=item_id, is_upload=is_upload)


def item_inclusion(item) -> str:
    """CatalogItem or snapshot dict → required/optional."""
    if item is None:
        return INCLUSION_OPTIONAL
    if isinstance(item, dict):
        parsed = parse_inclusion(str(item.get('inclusion') or ''))
        if parsed:
            return parsed
        if 'required' in item and item.get('required') is not None:
            return INCLUSION_REQUIRED if item.get('required') else INCLUSION_OPTIONAL
        return INCLUSION_OPTIONAL
    parsed = parse_inclusion(str(getattr(item, 'inclusion', '') or ''))
    if parsed:
        return parsed
    if getattr(item, 'required', None) is not None:
        return INCLUSION_REQUIRED if item.required else INCLUSION_OPTIONAL
    return INCLUSION_OPTIONAL


def item_required(item) -> bool:
    """True only when inclusion is required. Missing flag → optional (do not mass-create)."""
    return item_inclusion(item) == INCLUSION_REQUIRED


def parse_software_catalog(path: Path,
                           volume_alias: Dict[str, str] | None = None,
                           volume_seq: Dict[str, int] | None = None,
                           ) -> Dict[Tuple[int, int], str]:
    """Return {(volumeSeq, seq): importance} from 软件目录.docx (metadata only)."""
    alias = volume_alias or {}
    vseq_map = volume_seq or {}
    flags: Dict[Tuple[int, int], str] = {}
    if not path or not Path(path).is_file():
        return flags
    current_vseq = 0
    for text in _para_texts(Path(path)):
        m = ITEM_RE.match(text)
        if m and any(tok in m.group(3) for tok in IMPORTANCE_TOKENS):
            try:
                seq = int(m.group(1))
            except ValueError:
                continue
            if current_vseq:
                flags[(current_vseq, seq)] = _importance_from_meta(m.group(3))
            continue
        raw = text.strip()
        std = alias.get(raw, raw)
        vseq = vseq_map.get(raw) or vseq_map.get(std) or _guess_vol_seq(raw)
        if vseq:
            current_vseq = vseq
    return flags


def _guess_vol_seq(name: str) -> int:
    if not name:
        return 0
    ch = name[0]
    if ch in CN_VOL:
        return CN_VOL.index(ch) + 1
    if '变更' in name:
        return 4
    return 0


def apply_importance(items: Iterable, flags: Dict[Tuple[int, int], str]) -> None:
    """Mutate CatalogItem.importance only. Never stamps required/inclusion."""
    for it in items:
        key = (int(getattr(it, 'volume_seq', 0) or 0),
               int(getattr(it, 'seq', 0) or 0))
        it.importance = flags.get(key) or getattr(it, 'importance', None) or '普通项'
