# -*- coding: utf-8 -*-
"""P5 catalog polish: 8-volume cover rows, 目录勾选表, 隔页 8 组.

八 1 封面模板只列 5 卷；八 3 隔页只有 5 组。工头定模板不改，程序侧补齐 8 分册。
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, List, Sequence
from xml.etree import ElementTree as ET

from lib.subtable import (
    WNS, W_P, W_R, W_T, W_BODY, clone_el, para_text, register_ns, serialize_part,
)

W_PPR = '{%s}pPr' % WNS
W_SECTPR = '{%s}sectPr' % WNS
W_PAGEBREAK = '{%s}pageBreakBefore' % WNS
W_VAL = '{%s}val' % WNS
CN = '一二三四五六七八'

# Short names matching the frozen cover/divider templates (first 5) plus 六/七/八.
VOLUME_SHORT = [
    '依据分册',
    '过程分册',
    '图纸分册',
    '变更分册',
    '初步验收与试运行分册',
    '竣工验收报告',
    '竣工验收分册',
    '封面页',
]


def structure_data(project: dict) -> dict:
    """Rows to feed subtable_engine: _assets plus S0/S4 catalog defaults."""
    from lib.subtable import assets_from_project
    data = assets_from_project(project or {})
    if 'volumeList' not in data:
        data['volumeList'] = default_volume_rows()
    if 'documentChecklist' not in data:
        items = ((project or {}).get('_catalogSnapshot') or {}).get('items') or []
        data['documentChecklist'] = default_checklist_rows(items)
    return data


def apply_structure_to_docx(dest: Path, project: dict) -> dict:
    """Subtables + 8-volume divider, in place. Never writes templates."""
    from lib.field_dict import load_field_dict
    from lib.subtable import apply_subtables
    dict_path = Path(__file__).resolve().parents[1] / 'assets' / 'spec' / '字段字典.json'
    fd = load_field_dict(dict_path)
    data = structure_data(project)
    sub = apply_subtables(dest, dest, fd, data)
    div = None
    if '隔页' in dest.name:
        div = expand_divider_docx(dest, dest)
    return {'subtables': sub, 'divider': div}


def default_volume_rows() -> List[dict]:
    rows = []
    for i, name in enumerate(VOLUME_SHORT):
        rows.append({'卷号': '第%s卷' % CN[i], '文档名称': name})
    return rows


def default_checklist_rows(catalog_items: Sequence[dict],
                           existing_names: Iterable[str] | None = None) -> List[dict]:
    """八 2 验收资料目录：一行一个目录项。"""
    have = {str(n) for n in (existing_names or [])}
    rows = []
    for it in catalog_items:
        if not isinstance(it, dict):
            continue
        name = it.get('name') or ''
        if not name:
            continue
        provided = '☑已提供' if name in have else '□已提供'
        rows.append({
            '资料名称': name,
            '是否提供': provided,
            '页码': '',
            '备注': it.get('volume') or '',
        })
    return rows


def _set_para_text(p: ET.Element, text: str) -> None:
    ts = list(p.iter(W_T))
    if not ts:
        r = ET.SubElement(p, W_R)
        t = ET.SubElement(r, W_T)
        t.text = text
        return
    ts[0].text = text
    for t in ts[1:]:
        t.text = ''


def _add_page_break_before(p: ET.Element) -> None:
    ppr = p.find(W_PPR)
    if ppr is None:
        ppr = ET.Element(W_PPR)
        p.insert(0, ppr)
    el = ppr.find(W_PAGEBREAK)
    if el is None:
        el = ET.SubElement(ppr, W_PAGEBREAK)
    el.set(W_VAL, '1')


def _has_sectpr(el: ET.Element) -> bool:
    return any(ch.tag == W_SECTPR for ch in el.iter())


def expand_divider_body(root: ET.Element) -> dict:
    """Clone the last 分册 block until VOLUME_SHORT (8) are present."""
    body = root.find(W_BODY)
    if body is None:
        return {'ok': False, 'reason': 'no body', 'volumes': 0}
    children = list(body)
    title_idxs = [
        i for i, el in enumerate(children)
        if el.tag == W_P and para_text(el).strip() == '验收文档分目录'
    ]
    if not title_idxs:
        return {'ok': False, 'reason': 'no divider titles', 'volumes': 0}

    existing = []
    for ti in title_idxs:
        for j in range(ti + 1, len(children)):
            el = children[j]
            if el.tag != W_P:
                break
            t = para_text(el).strip()
            if t == '验收文档分目录':
                break
            if _has_sectpr(el):
                break
            if t:
                existing.append(t)
                break

    missing = [n for n in VOLUME_SHORT if n not in existing]
    if not missing:
        return {'ok': True, 'reason': 'already 8', 'volumes': len(existing), 'added': []}

    last_title = title_idxs[-1]
    end = last_title + 1
    while end < len(children) and children[end].tag == W_P and not _has_sectpr(children[end]):
        end += 1
    group = children[last_title:end]
    if not group:
        return {'ok': False, 'reason': 'empty group', 'volumes': len(existing)}

    # insert clones before the first follower (sectPr or next non-p)
    follower = children[end] if end < len(children) else None
    added = []
    for name in missing:
        clones = [clone_el(el) for el in group]
        _add_page_break_before(clones[0])
        named = False
        for el in clones:
            t = para_text(el).strip()
            if not t or t == '验收文档分目录':
                continue
            _set_para_text(el, name)
            named = True
            break
        if not named and len(clones) > 1:
            _set_para_text(clones[-1], name)
        for el in clones:
            if follower is not None:
                idx = list(body).index(follower)
                body.insert(idx, el)
            else:
                # keep sectPr last if present as direct child
                body.append(el)
        added.append(name)
    return {
        'ok': True,
        'reason': 'expanded',
        'volumes': len(existing) + len(added),
        'added': added,
    }


def expand_divider_docx(src: Path, dst: Path) -> dict:
    with zipfile.ZipFile(src) as zin:
        items = zin.infolist()
        contents = {it.filename: zin.read(it.filename) for it in items}
    raw = contents.get('word/document.xml')
    if not raw:
        return {'ok': False, 'reason': 'no document.xml'}
    register_ns(raw)
    root = ET.fromstring(raw)
    info = expand_divider_body(root)
    if info.get('ok') and info.get('added'):
        contents['word/document.xml'] = serialize_part(raw, root)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        written = set()
        for it in items:
            zout.writestr(it, contents[it.filename])
            written.add(it.filename)
        for name, data in contents.items():
            if name not in written:
                zout.writestr(name, data)
    info['src'] = str(src)
    info['dst'] = str(dst)
    return info
