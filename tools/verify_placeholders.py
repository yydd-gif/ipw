# -*- coding: utf-8 -*-
"""占位符注入结果校验：统计 {{key}} 分布、检查未定义 key、检查残留占位。"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os
import re
import json
import zipfile
import collections
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ROOT = str(REPO)
TPL = str(TEMPLATES)
BAK = str(TEMPLATES_BACKUP)
DICTF = str(DICT_PATH)

PH = re.compile(r'\{\{(.+?)\}\}')
LEFT = re.compile(r'[×X]{2,}')
# 允许残留的手填占位（日期/待人工填写的说明位）
DATE_LEFT = re.compile(r'[×X]{2,}\s*[年月日]|[×X]{2,}%|X\.XX%|X个月')


def main():
    d = json.load(open(DICTF, encoding='utf-8'))
    defined = {f['key'] for g in d['groups'] for f in g['fields']}
    defined |= {t['key'] for t in d['tables']}
    defined |= {f['key'] for f in d['disabledFields']}

    all_keys = collections.Counter()
    per_file = {}
    total = 0
    bad_keys = collections.Counter()
    lefts = []

    for root, dirs, files in os.walk(TPL):
        dirs.sort()
        for fn in sorted(files):
            if not fn.endswith('.docx') or fn.startswith('~$'):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, TPL).replace('\\', '/')
            try:
                z = zipfile.ZipFile(p)
                xml = z.read('word/document.xml').decode('utf-8')
            except Exception as e:
                print(f'!! 打不开 {rel}: {e}')
                continue
            # 只取文本
            body = ET.fromstring(xml).find(W + 'body')
            text = ''.join(t.text or '' for t in body.iter(W + 't'))

            keys = PH.findall(text)
            # 过滤掉非字段的 {{（如目录域代码）
            keys = [k for k in keys if not k.startswith('\\')]
            per_file[rel] = keys
            total += len(keys)
            for k in keys:
                all_keys[k] += 1
                if k not in defined:
                    bad_keys[k] += 1

            for m in LEFT.finditer(text):
                seg = text[max(0, m.start() - 12):m.end() + 12]
                if DATE_LEFT.search(seg):
                    continue
                lefts.append((rel, seg))

    print('=' * 70)
    print(f'占位符总数（已注入）: {total}')
    print(f'涉及模板: {sum(1 for v in per_file.values() if v)} / {len(per_file)}')
    print()
    print('—— 各模板占位符数 ——')
    for rel, keys in per_file.items():
        print(f'  {len(keys):>3}  {rel}')
    print()
    print('—— 字段使用频次 ——')
    for k, v in all_keys.most_common():
        print(f'  {v:>3}  {k}')
    print()
    print('—— 未在字典中定义的 key ——')
    print('  无' if not bad_keys else dict(bad_keys))
    print()
    print('—— 残留 [×X] 占位（日期/百分比类已排除）——')
    if not lefts:
        print('  无')
    else:
        for rel, seg in lefts:
            print(f'  {rel}: …{seg}…')
    print()
    print('—— 备份目录 ——')
    nb = sum(1 for r, dd, ff in os.walk(BAK) for f in ff if f.endswith('.docx'))
    print(f'  {BAK} 共 {nb} 个 docx')


if __name__ == '__main__':
    main()
