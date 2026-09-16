# -*- coding: utf-8 -*-
"""locate_docx.py —— docx 位置定位器（部件级，只用 stdlib）

一个 docx 的正文里，每个「位置」编号规则：
  - body 直接子 <w:p>            → 段N（1-based，空段也计数）
  - body 直接子 <w:tbl>          → 表M；表内 <w:tr>/<w:tc> → 表M行R列C
  - <w:sdt>（内容控件）透明展开，其 sdtContent 内的 w:p 仍算 body 段
  - 表格内部的 <w:p> 不计入「段N」

为什么不数「段」用文档大纲级别：段号必须与原标注脚本口径一致，否则映射表全部对不上。

用法：
    python locate_docx.py                       # 扫 07_模板资产，导出 actual_locate.json
    python locate_docx.py --dir <模板目录> --out <输出json>
    python locate_docx.py --dump 二、过程分册/10、施工日志.docx
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, re, sys, io, json, zipfile, argparse
import xml.etree.ElementTree as ET

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

W  = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
PH = re.compile(r'\{\{\s*([A-Za-z0-9_]+)\s*\}\}')
DEFAULT_ASSETS = str(TEMPLATES)
SKIP_DIRS = {'00_模板原始备份'}


def para_text(p):
    out = []
    for n in p.iter():
        if n.tag == W + 't':
            out.append(n.text or '')
        elif n.tag == W + 'tab':
            out.append('\t')
        elif n.tag in (W + 'br', W + 'cr'):
            out.append('\n')
    return ''.join(out).replace('\u3000', ' ').strip()


def locate(path):
    """→ [[位置, 文本, [key,...]], ...]"""
    z = zipfile.ZipFile(path)
    try:
        xml = z.read('word/document.xml')
    finally:
        z.close()
    root = ET.fromstring(xml)
    body = root.find(W + 'body')
    if body is None:
        return []
    res, pno, tno = [], 0, 0

    def feed(child):
        nonlocal pno, tno
        if child.tag == W + 'p':
            pno += 1
            t = para_text(child)
            res.append([f'段{pno}', t, PH.findall(t)])
        elif child.tag == W + 'tbl':
            tno += 1
            for r, tr in enumerate([x for x in child if x.tag == W + 'tr'], 1):
                for c, tc in enumerate([x for x in tr if x.tag == W + 'tc'], 1):
                    t = para_text(tc)
                    res.append([f'表{tno}行{r}列{c}', t, PH.findall(t)])
        elif child.tag == W + 'sdt':
            for sub in child:
                if sub.tag == W + 'sdtContent':
                    for x in sub:
                        feed(x)

    for child in body:
        feed(child)
    return res


def scan(assets=DEFAULT_ASSETS):
    """→ {(分册, 文件名): [[位置,文本,keys],...]}；自动跳过备份与临时文件"""
    out = {}
    for dp, dn, fn in os.walk(assets):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        sec = os.path.basename(dp)
        if sec == os.path.basename(assets):
            continue
        for f in sorted(fn):
            if not f.lower().endswith('.docx') or f.startswith('~$'):
                continue
            out[(sec, f)] = locate(os.path.join(dp, f))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=DEFAULT_ASSETS, help='模板根目录')
    ap.add_argument('--out', default=str(WORK / 'tmp' / 'actual_locate.json'))
    ap.add_argument('--dump', help='只打印某个「分册/文件.docx」的全部位置')
    a = ap.parse_args()

    if a.dump:
        sec, fil = a.dump.replace('\\', '/').split('/', 1)
        for p, t, ks in locate(os.path.join(a.dir, sec, fil)):
            if t or ks:
                print(f'{p:14s} {t[:100]}   {ks if ks else ""}')
        return

    actual = scan(a.dir)
    nph = sum(len(k) for v in actual.values() for _, _, k in v)
    print(f'模板 {len(actual)} 份 / 占位符 {nph} 处 / 总位置 {sum(len(v) for v in actual.values())}')
    zero = [(k, len(v)) for k, v in actual.items() if not any(ks for _, _, ks in v)]
    if zero:
        print(f'零占位符模板 {len(zero)} 份：')
        for k, n in zero:
            print(f'   {k[0]}/{k[1]}  位置{n}')
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fp:
        json.dump({f'{k[0]}|{k[1]}': v for k, v in actual.items()}, fp, ensure_ascii=False, indent=1)
    print(f'已导出 → {a.out}')


if __name__ == '__main__':
    main()
