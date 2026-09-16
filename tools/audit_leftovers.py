# -*- coding: utf-8 -*-
"""复查：模板中尚未被 {{}} 覆盖、但疑似仍需填写的点位。
规则：
  P1 段落/单元格 含 '文档编号' 但无 {{docNo}}
  P2 含 2 个以上连续 X/× 的占位文本（非日期/百分比）
  P3 含 '年…月…日' 的年月日空位
  P4 整格为空 且 该单元格所在行其他格含标签词（单位/名称/编号/日期/金额/地点/人）
输出到 规范/漏标复查.csv
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, re, csv, zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ROOT = str(TEMPLATES)
OUT = str(WORK / '漏标复查.csv')

PH = re.compile(r'\{\{')
XPH = re.compile(r'[×Xx]{2,}')
DATE = re.compile(r'[×Xx_\s]{0,6}年[×Xx_\s]{0,6}月[×Xx_\s]{0,6}日')
LABELS = ('单位', '名称', '编号', '日期', '金额', '地点', '签字', '盖章', '电话', '文号', '代码')


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(W + 't'))


def main():
    rows = []
    for root, dirs, files in os.walk(ROOT):
        for fn in sorted(files):
            if not fn.endswith('.docx') or fn.startswith('~$'):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ROOT)
            vol = rel.split(os.sep)[0]
            z = zipfile.ZipFile(p)
            body = ET.fromstring(z.read('word/document.xml')).find(W + 'body')
            pi = ti = 0
            for el in body:
                if el.tag == W + 'p':
                    pi += 1
                    txt = ptext(el)
                    if PH.search(txt):
                        continue
                    if '文档编号' in txt:
                        rows.append([vol, fn, f'段{pi}', 'P1-文档编号未占位', txt.strip()[:110]])
                    for m in XPH.finditer(txt):
                        seg = txt[max(0, m.start()-8):m.end()+10]
                        if re.search(r'[年月日%]', seg):
                            continue
                        rows.append([vol, fn, f'段{pi}', 'P2-占位文本未标注', txt.strip()[:110]])
                        break
                    if DATE.search(txt) and '{{' not in txt:
                        rows.append([vol, fn, f'段{pi}', 'P3-日期空位', txt.strip()[:110]])
                elif el.tag == W + 'tbl':
                    ti += 1
                    for ri, tr in enumerate(el.findall(W + 'tr'), 1):
                        tcs = tr.findall(W + 'tc')
                        cells = [''.join(ptext(x) for x in tc.findall(W + 'p')).strip() for tc in tcs]
                        joined = ' | '.join(cells)
                        if PH.search(joined):
                            continue
                        if '文档编号' in joined:
                            rows.append([vol, fn, f'表{ti}行{ri}', 'P1-文档编号未占位', joined[:110]])
                        if XPH.search(joined):
                            seg = XPH.search(joined)
                            s = joined[max(0, seg.start()-8):seg.end()+10]
                            if not re.search(r'[年月日%]', s):
                                rows.append([vol, fn, f'表{ti}行{ri}', 'P2-占位文本未标注', joined[:110]])
                        if DATE.search(joined):
                            rows.append([vol, fn, f'表{ti}行{ri}', 'P3-日期空位', joined[:110]])
                        for ci, c in enumerate(cells, 1):
                            if c == '' and any(k in joined for k in LABELS):
                                rows.append([vol, fn, f'表{ti}行{ri}列{ci}', 'P4-空单元格(标签行)', joined[:110]])
    seen = set()
    uniq = []
    for r in rows:
        k = tuple(r)
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分册', '模板文件', '位置', '类型', '上下文'])
        w.writerows(uniq)
    print(f'疑似漏标/待人工确认: {len(uniq)} 条 -> {OUT}')
    print()
    import collections
    c = collections.Counter(r[3] for r in uniq)
    for k, v in c.most_common():
        print(f'  {k}: {v}')
    print()
    for r in uniq:
        if r[3].startswith('P1') or r[3].startswith('P2'):
            print(f'  ★ [{r[3]}] {r[0]}/{r[1]} {r[2]}  → {r[4]}')


if __name__ == '__main__':
    main()
