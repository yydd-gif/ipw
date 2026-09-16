# -*- coding: utf-8 -*-
"""扫描验收资料模板的占位点：人读占位文本 / 文档编号 / 日期占位 / 空单元格。
输出 CSV 明细，供人工确认与后续占位符标注。
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, csv, re, zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ROOT = str(TEMPLATES)
OUT = str(WORK / '模板占位点扫描明细.csv')


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(W + 't'))


def walk(path):
    """返回 [(kind, index, cells)]，kind = 'p' 段落 / 'tbl' 表格"""
    z = zipfile.ZipFile(path)
    xml = z.read('word/document.xml')
    body = ET.fromstring(xml).find(W + 'body')
    out = []
    for el in body:
        tag = el.tag
        if tag == W + 'p':
            out.append(('p', ptext(el)))
        elif tag == W + 'tbl':
            rows = []
            for tr in el.findall(W + 'tr'):
                cells = []
                for tc in tr.findall(W + 'tc'):
                    cells.append(''.join(ptext(p) for p in tc.findall(W + 'p')).strip())
                rows.append(cells)
            out.append(('tbl', rows))
    return out


def guess_field(ctx):
    c = ctx
    if '文档编号' in c:
        return 'docNo'
    if '工程名称' in c or '项目名称' in c:
        return 'projectName'
    if re.search(r'年\s*月\s*日', c):
        return 'signDate'
    if '监理' in c:
        return 'supervisionUnit'
    if '施工单位' in c:
        return 'constructionUnit'
    if '建设单位' in c:
        return 'ownerUnit'
    if '承建单位' in c:
        return 'constructionUnit'
    if '日期' in c:
        return 'date'
    if '天气' in c:
        return 'weather'
    if '地点' in c:
        return 'buildSite'
    if '负责人' in c or '项目经理' in c:
        return 'projectManager'
    return ''


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows_out = []
    for root, dirs, files in os.walk(ROOT):
        for fn in sorted(files):
            if not fn.endswith('.docx'):
                continue
            path = os.path.join(root, fn)
            rel = os.path.relpath(path, ROOT)
            vol = rel.split(os.sep)[0]
            blocks = walk(path)
            ti = 0
            pi = 0
            for kind, data in blocks:
                if kind == 'p':
                    pi += 1
                    txt = data.strip()
                    if not txt:
                        continue
                    loc = f'段{pi}'
                    if re.search(r'×|XX', txt):
                        rows_out.append([vol, fn, '占位文本', loc, txt, guess_field(txt)])
                    if '文档编号' in txt:
                        rows_out.append([vol, fn, '文档编号', loc, txt, 'docNo'])
                    if re.search(r'年\s*月\s*日', txt):
                        rows_out.append([vol, fn, '日期占位', loc, txt, 'signDate'])
                else:
                    ti += 1
                    for ri, cells in enumerate(data, 1):
                        joined = ' | '.join(cells)
                        if not joined.strip():
                            continue
                        loc = f'表{ti}行{ri}'
                        if re.search(r'×|XX', joined):
                            rows_out.append([vol, fn, '占位文本', loc, joined, guess_field(joined)])
                        if '文档编号' in joined:
                            rows_out.append([vol, fn, '文档编号', loc, joined, 'docNo'])
                        if re.search(r'年\s*月\s*日', joined):
                            rows_out.append([vol, fn, '日期占位', loc, joined, 'signDate'])
                        n_empty = sum(1 for c in cells if c == '')
                        if n_empty:
                            rows_out.append([vol, fn, f'空单元格×{n_empty}', loc, joined, guess_field(joined)])
    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分册', '模板文件', '占位类型', '位置', '上下文', '建议字段key'])
        w.writerows(rows_out)
    print(f'写出 {len(rows_out)} 条 -> {OUT}')

    from collections import Counter
    cnt = Counter(r[2].split('×')[0] for r in rows_out)
    for k, v in cnt.most_common():
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main()
