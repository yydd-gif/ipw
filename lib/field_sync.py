# -*- coding: utf-8 -*-
"""半自动字段同步（数据与规则规格.md §5.3 / 软件设计方案-v2.0 §4.9）.

E1 路径：表单改项目级字段 → 提示 仅本份 / 同步全册 / 撤销。
有 P2 锚点（yz_ 书签）时按书签精准回写；否则对选中文档走 form-driven 再填充。
「仅本份」只写 _documents[relPath]，不改项目级值，不碰其他文档。
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple
from xml.etree import ElementTree as ET

from lib.project_store import read_project, write_project
from lib.subtable import (
    WNS, W_T, XML_SPACE, PART_RE, register_ns, rewrite_docx,
    serialize_part,
)

W_BS = '{%s}bookmarkStart' % WNS
W_BE = '{%s}bookmarkEnd' % WNS
W_NAME = '{%s}name' % WNS
W_ID = '{%s}id' % WNS
YZ_NS = 'http://yanshou.local/field-anchors/1'


def _attr(el: ET.Element, local: str) -> str:
    return (el.get('{%s}%s' % (WNS, local))
            or el.get(local)
            or '')


def walk(el: ET.Element):
    yield el
    for ch in el:
        yield from walk(ch)


def collect_anchor_names(root: ET.Element) -> List[str]:
    names = []
    for el in root.iter(W_BS):
        n = _attr(el, 'name')
        if n.startswith('yz_'):
            names.append(n)
    return names


def bookmark_text_nodes(root: ET.Element, name: str) -> List[ET.Element]:
    inside = False
    bid = None
    nodes = []
    for el in walk(root):
        if el.tag == W_BS and _attr(el, 'name') == name:
            inside = True
            bid = _attr(el, 'id')
            continue
        if inside and el.tag == W_BE and _attr(el, 'id') == bid:
            break
        if inside and el.tag == W_T:
            nodes.append(el)
    return nodes


def set_bookmark_text(root: ET.Element, name: str, value: str) -> bool:
    nodes = bookmark_text_nodes(root, name)
    if not nodes:
        return False
    value = '' if value is None else str(value)
    nodes[0].text = value
    if value and value != value.strip():
        nodes[0].set(XML_SPACE, 'preserve')
    for n in nodes[1:]:
        n.text = ''
    return True


def patch_custom_xml_ledger(contents: dict, fields: Dict[str, str]) -> None:
    raw = contents.get('customXml/item1.xml')
    if not raw:
        return
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return
    start = text.find('<![CDATA[')
    end = text.find(']]>')
    if start < 0 or end < 0:
        return
    blob = text[start + 9:end]
    try:
        ledger = json.loads(blob)
    except json.JSONDecodeError:
        return
    if not isinstance(ledger, dict):
        return
    for key, val in fields.items():
        for bname, rec in ledger.items():
            if not isinstance(rec, dict):
                continue
            if bname == 'yz_%s' % key or bname.startswith('yz_%s_' % key):
                rec['value'] = str(val)
    payload = json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    payload = payload.replace(']]>', ']]]]><![CDATA[>')
    body = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<yz:ledger xmlns:yz="%s"><![CDATA[%s]]></yz:ledger>' % (YZ_NS, payload)
    )
    contents['customXml/item1.xml'] = body.encode('utf-8')


def patch_docx_fields(src: Path, dst: Path, fields: Dict[str, str]) -> dict:
    """Replace yz_<key> bookmark text. Missing anchors are reported, not errors."""
    patched, missing = [], []

    def mutate(contents: dict) -> None:
        for name in list(contents):
            if not PART_RE.match(name):
                continue
            raw = contents[name]
            try:
                register_ns(raw)
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            present = set(collect_anchor_names(root))
            changed = False
            for key, val in fields.items():
                bname = 'yz_%s' % key
                aliases = [n for n in present if n == bname or n.startswith(bname + '_')]
                if not aliases:
                    if key not in missing:
                        missing.append(key)
                    continue
                for n in aliases:
                    if set_bookmark_text(root, n, str(val)):
                        if key not in patched:
                            patched.append(key)
                        changed = True
            if changed:
                contents[name] = serialize_part(raw, root)
        if patched:
            patch_custom_xml_ledger(contents, {
                k: fields[k] for k in patched if k in fields
            })

    rewrite_docx(src, dst, mutate)
    return {
        'ok': True,
        'patched': patched,
        'missingAnchors': [k for k in fields if k not in patched],
        'src': str(src),
        'dst': str(dst),
    }


def live_docs(project: dict) -> List[Tuple[str, dict]]:
    trash = set()
    for t in project.get('_trash') or []:
        if isinstance(t, dict) and t.get('docId'):
            trash.add(t['docId'])
        for d in t.get('documents') or []:
            if isinstance(d, dict) and d.get('docId'):
                trash.add(d['docId'])
    out = []
    for did, rec in (project.get('_docs') or {}).items():
        if did in trash or not isinstance(rec, dict):
            continue
        out.append((did, rec))
    return out


def docs_with_field(root: Path, project: dict, key: str) -> List[dict]:
    """Docs whose yz_<key> bookmark exists (or that simply exist, as fallback)."""
    bname = 'yz_%s' % key
    hits = []
    for did, rec in live_docs(project):
        rel = rec.get('relPath') or ''
        path = root / rel if rel else None
        info = {'docId': did, 'relPath': rel, 'hasAnchor': False, 'exists': False}
        if path and path.is_file() and path.suffix.lower() == '.docx':
            info['exists'] = True
            try:
                with zipfile.ZipFile(path) as z:
                    raw = z.read('word/document.xml')
                root_el = ET.fromstring(raw)
                names = collect_anchor_names(root_el)
                info['hasAnchor'] = any(n == bname or n.startswith(bname + '_') for n in names)
            except (zipfile.BadZipFile, ET.ParseError, KeyError):
                pass
        hits.append(info)
    return hits


def apply_this_doc(project_path: Path, rel_path: str, fields: dict,
                   at: str) -> dict:
    """仅本份：archive 值不动，覆盖只落在这一份。"""
    project = read_project(project_path, apply_migration=True)
    ov = project.setdefault('_documents', {}).setdefault(rel_path, {})
    written = {}
    for k, v in fields.items():
        if k.startswith('_') or k == 'docNo':
            continue
        old = project.get(k)
        if str(old if old is not None else '') == str(v if v is not None else ''):
            continue
        ov[k] = v
        written[k] = v
    write_project(project_path, project, backup=True)
    root = project_path.parent
    doc_path = root / rel_path
    patch = None
    if written and doc_path.is_file() and doc_path.suffix.lower() == '.docx':
        patch = patch_docx_fields(doc_path, doc_path, {k: str(v) for k, v in written.items()})
    return {
        'mode': 'this',
        'relPath': rel_path,
        'fields': written,
        'projectUntouched': True,
        'patch': patch,
    }


def apply_all_docs(project_path: Path, fields: dict, at: str,
                   skip_overridden: bool = True) -> dict:
    """同步全册：改项目级值，再回写各份（已「仅本份」锁定的 key 跳过）。"""
    project = read_project(project_path, apply_migration=True)
    sources = project.setdefault('_fieldSources', {})
    written = {}
    for k, v in fields.items():
        if k.startswith('_') or k == 'docNo':
            continue
        old = project.get(k)
        if str(old if old is not None else '') == str(v if v is not None else ''):
            continue
        project[k] = v
        sources[k] = {'source': 'S1', 'ruleId': '', 'at': at, 'by': 'manual'}
        written[k] = v
    write_project(project_path, project, backup=True)
    root = project_path.parent
    patches = []
    skipped = []
    overrides = project.get('_documents') or {}
    for did, rec in live_docs(project):
        rel = rec.get('relPath') or ''
        path = root / rel
        if not path.is_file() or path.suffix.lower() != '.docx':
            continue
        ov = overrides.get(rel) or {}
        local = {}
        for k, v in written.items():
            if skip_overridden and k in ov and ov[k] not in (None, ''):
                skipped.append({'relPath': rel, 'key': k})
                continue
            local[k] = v
        if not local:
            continue
        patches.append(patch_docx_fields(path, path, {k: str(v) for k, v in local.items()}))
    return {
        'mode': 'all',
        'fields': written,
        'patches': patches,
        'skippedLocked': skipped,
        'others': max(0, len(patches) - 1),
    }
