#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验闸门 · P0：残留占位符扫描（§7 全量口径在 P2 补齐）"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from _common import (
    DICT_PATH, emit_progress, emit_result, exit_env, exit_param,
    result_payload, wns_tag,
)

W_T = wns_tag('t')
W_P = wns_tag('p')
PART_RE = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')
PH_RE = re.compile(r'\{\{([^{}]+)\}\}')


def load_enabled(dict_path: Path) -> set:
    if not dict_path.exists():
        return set()
    data = json.loads(dict_path.read_text(encoding='utf-8'))
    keys = set()
    for g in data.get('groups', []):
        for f in g.get('fields', []):
            keys.add(f['key'])
    return keys


def scan_file(path: Path) -> list:
    hits = []
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not PART_RE.match(name):
                    continue
                try:
                    root = ET.fromstring(z.read(name))
                except ET.ParseError:
                    hits.append({
                        'file': str(path), 'part': name, 'key': '',
                        'reason': 'XML 无法解析', 'level': 'block',
                    })
                    continue
                for p in root.iter(W_P):
                    full = ''.join(t.text or '' for t in p.iter(W_T))
                    for m in PH_RE.finditer(full):
                        hits.append({
                            'file': str(path), 'part': name, 'key': m.group(1).strip(),
                            'reason': '残留占位符 {{%s}}' % m.group(1).strip(),
                            'level': 'block',
                        })
    except zipfile.BadZipFile:
        hits.append({
            'file': str(path), 'part': '-', 'key': '',
            'reason': '文件损坏', 'level': 'block',
        })
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description='verify_engine · P0 residual scan')
    ap.add_argument('--dir', type=Path, help='待校验目录')
    ap.add_argument('--dict', type=Path, default=DICT_PATH)
    ap.add_argument('--project', type=Path, help='给了才能做一致性校验（P2）')
    ap.add_argument('--level', choices=('block', 'all'), default='block')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.dir:
        return exit_param('需要 --dir', a.as_json, 'verify')

    if not a.dir.exists():
        return exit_param('校验目录不存在：%s' % a.dir, a.as_json, 'verify')

    docs = sorted(p for p in a.dir.rglob('*.docx') if not p.name.startswith('~$'))
    if not docs:
        return exit_env('校验目录里没找到 docx：%s' % a.dir, a.as_json, 'verify')

    enabled = load_enabled(a.dict)
    errors = []
    for i, doc in enumerate(docs, 1):
        emit_progress(i, len(docs), str(doc.name))
        errors.extend(scan_file(doc))

    residual_enabled = [e for e in errors if e.get('key') in enabled]
    unknown = [e for e in errors if e.get('key') and e.get('key') not in enabled
               and e.get('reason', '').startswith('残留')]
    if a.level == 'block':
        shown = [e for e in errors if e.get('level') == 'block']
    else:
        shown = errors

    ok = len(residual_enabled) == 0 and not any(
        e.get('reason') in ('文件损坏', 'XML 无法解析') for e in errors)
    summary = '%d 份 / 残留 %d 处（启用字段 %d / 未定义 %d）' % (
        len(docs), len(errors), len(residual_enabled), len(unknown))
    payload = result_payload(
        ok, 'verify', summary,
        stats={
            'docs': len(docs),
            'filled': 0,
            'missing': len(residual_enabled),
            'residual': len(errors),
        },
        errors=shown,
    )
    code = emit_result(payload, a.as_json)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
