# -*- coding: utf-8 -*-
"""导出映射表中「复杂类型」条目的完整原文，供注入规则定制。
   仅读，不改任何文件。"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os
import re
import csv
import zipfile
import html
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ROOT = str(REPO)
TPL = str(TEMPLATES)
MAP = str(MAPPING_CSV)


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(W + 't'))


def blocks(path):
    """返回 (段落列表, 表格列表)，均为 body 顶层直接子元素"""
    z = zipfile.ZipFile(path)
    body = ET.fromstring(z.read('word/document.xml')).find(W + 'body')
    paras, tbls = [], []
    for el in body:
        if el.tag == W + 'p':
            paras.append(el)
        elif el.tag == W + 'tbl':
            tbls.append(el)
    return paras, tbls


def cells_of(tbl):
    out = []
    for tr in tbl.findall(W + 'tr'):
        out.append([''.join(ptext(p) for p in tc.findall(W + 'p'))
                    for tc in tr.findall(W + 'tc')])
    return out


def locate(paras, tbls, pos):
    """pos: 段N | 表N行M列C | 表N行M-M2 | 表N（整表）| 整篇"""
    m = re.match(r'^段(\d+)$', pos)
    if m:
        i = int(m.group(1)) - 1
        return 'P', paras[i] if i < len(paras) else None
    m = re.match(r'^表(\d+)行(\d+)列(\d+)$', pos)
    if m:
        ti, ri, ci = map(int, m.groups())
        try:
            return 'C', tbls[ti - 1].findall(W + 'tr')[ri - 1].findall(W + 'tc')[ci - 1]
        except Exception:
            return 'C', None
    m = re.match(r'^表(\d+)(?:行(\d+)(?:-(\d+))?)?', pos)
    if m:
        ti = int(m.group(1))
        return 'T', tbls[ti - 1] if ti - 1 < len(tbls) else None
    return 'X', None


def main():
    rows = list(csv.DictReader(open(MAP, encoding='utf-8-sig')))
    targets = [r for r in rows if r['类型'] in ('段落模板', '前缀插入', '空白占位')]

    # 按模板分组
    by_file = {}
    for r in targets:
        by_file.setdefault(r['分册'] + '/' + r['模板文件'], []).append(r)

    print('=' * 78)
    print('一、复杂类型条目全文（段落模板 / 前缀插入 / 空白占位）')
    print('=' * 78)
    for key, rs in by_file.items():
        path = os.path.join(TPL, key.replace('/', os.sep))
        if not os.path.exists(path):
            print('!! 找不到模板:', key)
            continue
        paras, tbls = blocks(path)
        print('\n### ' + key)
        for r in rs:
            kind, el = locate(paras, tbls, r['位置'])
            if el is None:
                print(f"  [{r['位置']}] <定位失败> {r['类型']} -> {r['目标字段']}")
                continue
            if kind == 'P':
                full = ptext(el)
            elif kind == 'C':
                full = ''.join(ptext(p) for p in el.findall(W + 'p'))
            else:
                full = '(表格)'
            print(f"  [{r['位置']}] {r['类型']} -> {r['目标字段']}")
            print(f"      原文: {full!r}")

    print('\n\n' + '=' * 78)
    print('二、子表数据区结构与所用表格（表号 / 行数 / 列数 / 前几行）')
    print('=' * 78)
    subs = [r for r in rows if r['类型'] == '子表数据区']
    seen = set()
    for r in subs:
        path = os.path.join(TPL, r['分册'].replace('/', os.sep), r['模板文件'])
        if not os.path.exists(path):
            path = os.path.join(TPL, r['分册'], r['模板文件'])
        ti = int(re.match(r'^表(\d+)', r['位置']).group(1))
        ck = (r['模板文件'], ti)
        if ck in seen:
            continue
        seen.add(ck)
        paras, tbls = blocks(path)
        print(f"\n### {r['模板文件']}  表{ti}  ->  {r['目标字段']}  位置={r['位置']}")
        tbl = tbls[ti - 1]
        cs = cells_of(tbl)
        print(f'    共 {len(cs)} 行')
        for i, row in enumerate(cs[:4], 1):
            print(f'    行{i}: ' + ' | '.join(repr(c)[:26] for c in row))
        print('    ...')
        for i, row in enumerate(cs[-2:], len(cs) - 1):
            print(f'    行{i}: ' + ' | '.join(repr(c)[:26] for c in row))
        print(f'    列数: {[len(x) for x in cs]}')


if __name__ == '__main__':
    main()
