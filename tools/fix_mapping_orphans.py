# -*- coding: utf-8 -*-
"""把映射表中指向已删除字段的行订正为手填口径。
规则：
  - 目标字段 == 已删 key           → 类型改「手填·留白」，目标字段改 @manualFill
  - 目标字段 == （含 a/b）且含已删 key → 剔除已删 key；若清空则 @manualFill
  - 特殊：六9 表1行1列2 模板实际已用 ownerUnit → 目标字段订正为 ownerUnit
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import csv, json, re, os

ROOT = str(REPO)
DICTF = str(DICT_PATH)
MAPF = str(MAPPING_CSV)

d = json.load(open(DICTF, encoding='utf-8'))
removed = {f['key'] for f in d['removedFields']['fields']}

# 模板实际已改用的目标（人工核对结果）
OVERRIDE = {
    ('六、竣工验收报告', '9、文档移交表.docx', '表1行1列2'): 'ownerUnit',
}

rows = list(csv.reader(open(MAPF, encoding='utf-8-sig')))
head, body = rows[0], rows[1:]
changed = []
for r in body:
    vol, fn, loc, typ, ctx, tgt = r[0], r[1], r[2], r[3], r[4], r[5]
    orig_tgt, orig_typ = tgt, typ
    key = (vol, fn, loc)
    if key in OVERRIDE:
        r[5] = OVERRIDE[key]
        r[6] = '定稿'
    elif tgt in removed:
        r[3] = '手填·留白'
        r[5] = '@manualFill'
        r[6] = '工头定'
    elif tgt.startswith('（含') and '）' in tgt:
        inner = tgt[2:tgt.rindex('）')]
        keep = [x.strip() for x in inner.split('/') if x.strip() and x.strip() not in removed]
        if keep:
            r[5] = '（含 ' + '/'.join(keep) + '）'
        else:
            r[3] = '手填·留白'
            r[5] = '@manualFill'
            r[6] = '工头定'
    if (r[3], r[5]) != (orig_typ, orig_tgt):
        changed.append((vol, fn, loc, orig_typ, orig_tgt, r[3], r[5]))

with open(MAPF, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(head)
    w.writerows(body)

print(f'订正 {len(changed)} 行：')
for c in changed:
    print(f'  {c[1]} {c[2]:14} {c[3]}/{c[4]}  →  {c[5]}/{c[6]}')

# 复查：映射表里是否还有指向已删字段的引用
left = [r for r in body if any(k in r[5] for k in removed)]
print()
print(f'剩余指向已删字段的行: {len(left)}')
for r in left:
    print(f'  !! {r[1]} {r[2]} → {r[5]}')
