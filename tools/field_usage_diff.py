# -*- coding: utf-8 -*-
"""字典字段 vs 模板实际使用 对照：列出未使用字段、停用字段、子表标注情况。"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, re, json, zipfile, collections
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ROOT = str(REPO)
TPL = str(TEMPLATES)
DICTF = str(DICT_PATH)
PH = re.compile(r'\{\{(.+?)\}\}')


def main():
    d = json.load(open(DICTF, encoding='utf-8'))
    used = collections.Counter()
    rows_syntax = []
    for root, dirs, files in os.walk(TPL):
        for fn in sorted(files):
            if not fn.endswith('.docx') or fn.startswith('~$'):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, TPL)
            xml = zipfile.ZipFile(p).read('word/document.xml').decode('utf-8')
            txt = ''.join(t.text or '' for t in ET.fromstring(xml).iter(W + 't'))
            for k in PH.findall(txt):
                if k.startswith('\\'):
                    continue
                if k.startswith('#rows:') or k.startswith('/rows'):
                    rows_syntax.append((rel, k))
                else:
                    used[k] += 1

    allf = []
    for g in d['groups']:
        for f in g['fields']:
            allf.append((f['key'], f['label'], g.get('label', g.get('name', '')), '启用'))
    dis = [(f['key'], f['label'], 'disabled', '停用') for f in d['disabledFields']]
    tabs = [(t['key'], t.get('label', ''), 'table', '子表') for t in d['tables']]

    print('=' * 66)
    print(f'模板实际使用 key: {len(used)} 种')
    print(f'字典启用字段: {len(allf)}  停用字段: {len(dis)}  子表: {len(tabs)}')
    print()
    print('—— 启用字段中「模板里未使用」的 ——')
    miss = [f for f in allf if f[0] not in used]
    for k, lab, grp, _ in miss:
        print(f'  · {k:26} {lab}   [{grp}]')
    if not miss:
        print('  无')
    print()
    print('—— 子表 key 是否在模板中标注 ——')
    for k, lab, _, _ in tabs:
        mark = '已标注' if k in used else '未标注'
        print(f'  · {k:20} {lab:16} {mark}')
    print()
    print('—— 动态行语法 {{#rows:...}} ——')
    print('  无' if not rows_syntax else rows_syntax)
    print()
    print('—— 模板用了但字典未启用/未定义的 ——')
    known = {f[0] for f in allf} | {t[0] for t in tabs} | {f[0] for f in dis}
    for k in used:
        if k not in known:
            print(f'  !! {k}')
    print('  （以上为空即全部有定义）')


if __name__ == '__main__':
    main()
