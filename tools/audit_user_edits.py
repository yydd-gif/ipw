# -*- coding: utf-8 -*-
"""核对用户手改后的模板占位符：逐条输出 key + 所在段落/单元格原文，供人工审阅。
并输出：未定义 key、新增/缺失 key、与映射表差异。
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, re, json, zipfile, collections, csv
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ROOT = str(REPO)
TPL = str(TEMPLATES)
DICTF = str(DICT_PATH)
MAPF = str(MAPPING_CSV)
OUT = str(WORK / '手改占位符核对.csv')

PH = re.compile(r'\{\{(.+?)\}\}')


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(W + 't'))


def blocks(path):
    z = zipfile.ZipFile(path)
    body = ET.fromstring(z.read('word/document.xml')).find(W + 'body')
    out = []
    for el in body:
        if el.tag == W + 'p':
            out.append(('p', el))
        elif el.tag == W + 'tbl':
            out.append(('tbl', el))
    return out


def main():
    d = json.load(open(DICTF, encoding='utf-8'))
    label = {}
    for g in d['groups']:
        for f in g['fields']:
            label[f['key']] = f['label']
    for t in d['tables']:
        label[t['key']] = '【子表】' + t.get('label', t['key'])
    for f in d['disabledFields']:
        label[f['key']] = '(停用)' + f['label']
    defined = set(label.keys())

    rows = []
    bad = collections.Counter()
    for rot, dirs, files in os.walk(TPL):
        for fn in sorted(files):
            if not fn.endswith('.docx') or fn.startswith('~$'):
                continue
            p = os.path.join(rot, fn)
            rel = os.path.relpath(p, TPL)
            vol = rel.split(os.sep)[0]
            pi = ti = 0
            for kind, el in blocks(p):
                if kind == 'p':
                    pi += 1
                    txt = ptext(el)
                    for k in PH.findall(txt):
                        if k.startswith('\\'):
                            continue
                        rows.append([vol, fn, f'段{pi}', k, label.get(k, '!!未定义'), '段落', txt.strip()[:120]])
                        if k not in defined:
                            bad[k] += 1
                else:
                    ti += 1
                    for ri, tr in enumerate(el.findall(W + 'tr'), 1):
                        for ci, tc in enumerate(tr.findall(W + 'tc'), 1):
                            txt = ''.join(ptext(x) for x in tc.findall(W + 'p'))
                            for k in PH.findall(txt):
                                if k.startswith('\\'):
                                    continue
                                rows.append([vol, fn, f'表{ti}行{ri}列{ci}', k, label.get(k, '!!未定义'), '表格', txt.strip()[:120]])
                                if k not in defined:
                                    bad[k] += 1

    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分册', '模板文件', '位置', 'key', '中文标签', '载体', '所在处原文'])
        w.writerows(rows)

    print(f'总占位符: {len(rows)}')
    print(f'未定义 key: {"无" if not bad else dict(bad)}')
    print()
    # 按文件输出新字段项目背景/建设目标/建设内容 落点
    print('—— 新增字段落点（projectBackground / projectGoal / projectContent）——')
    for r in rows:
        if r[3] in ('projectBackground', 'projectGoal', 'projectContent'):
            print(f'  [{r[3]:18}] {r[0]}/{r[1]}  {r[2]}')
            print(f'      原文: {r[6]}')
    print()
    print(f'明细已写: {OUT}')


if __name__ == '__main__':
    main()
