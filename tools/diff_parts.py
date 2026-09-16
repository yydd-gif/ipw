# -*- coding: utf-8 -*-
"""diff_parts.py —— docx 部件级 / 文本级比对（定性"字节变了到底是不是内容变了"）

用途：
  1) 备份体检（backup_templates.py --verify-only）报出「源漂移」后，用它给漂移定性
  2) 改动模板前后自证"只改了该改的地方"
  3) 注入前后确认没丢页眉/页脚/图片/样式

为什么必须有"文本级"这一层：
  **Word 只要打开另存，字节就变**（清 `fontTable.xml` 里未引用的字体、给 `document.xml` 补 rsid 属性），
  但内容一个字没动。只看字节会误判成"被改了"。
  本工具会给出三种判定：内容等价（仅序列化差异）/ 实质差异 / 部件结构变化。

用法：
    python diff_parts.py                          # 全量：07_模板资产/  vs  00_模板原始备份/
    python diff_parts.py <A.docx> <B.docx>        # 指定两份单比
    python diff_parts.py --brief                  # 只打印有问题的

约定：
    A = 源（现役）   B = 备份（冻结态/旧版）
    退出码：0 = 内容等价；1 = 存在实质差异或结构变化

⚠ 读正文文本前必须删 `mc:Fallback` 子树 —— OOXML 的 mc:AlternateContent 同时存
  DrawingML(Choice) + VML(Fallback) 两份，不删会把同一段文字读两遍。
  （踩过：页脚「第 4 页第 4 页」实为「第 4 页」，`2828` 实为 `28`）
⚠ 一律用 stdlib zipfile + ElementTree，不依赖 python-docx / lxml
  （本机 managed python 3.13.12 两者都没有）
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os
import re
import sys
import io
import zipfile
import argparse
import xml.etree.ElementTree as ET

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SRC  = str(TEMPLATES)
BAK  = str(TEMPLATES_BACKUP)
SKIP = {'00_模板原始备份'}

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
PH = re.compile(r'\{\{[^}]+\}\}')
FALLBACK = re.compile(rb'<mc:Fallback>.*?</mc:Fallback>', re.S)
# 参与"正文文本"比对的部件
TEXT_PARTS = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$')


# ---------------------------------------------------------------- 基础读取
def norm_part_name(n):
    """把命名空间前缀归一，避免 rId 微调造成假差异（保守：只做前缀归一）"""
    return n


def is_tpl(f):
    return f.lower().endswith('.docx') and not f.startswith('~$')


def para_texts(raw):
    """按段落提取可见文本；先删 mc:Fallback 防止双读"""
    raw = FALLBACK.sub(b'', raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    out = []
    for p in root.iter(W + 'p'):
        out.append(''.join(t.text or '' for t in p.iter(W + 't')))
    return out


def hdr_ftr_texts(z):
    """收齐所有正文类部件的段落文本（含 header/footer，别只扫 document.xml）"""
    got = {}
    for n in z.namelist():
        if TEXT_PARTS.match(n):
            got[n] = para_texts(z.read(n))
    return got


# ---------------------------------------------------------------- 单份比对
def diff_one(pa, pb, label_a='源', label_b='备'):
    """返回 (verdict, lines)。verdict ∈ {等价, 实质差异, 结构变化}"""
    L = []
    try:
        za, zb = zipfile.ZipFile(pa), zipfile.ZipFile(pb)
    except zipfile.BadZipFile as e:
        return '结构变化', [f'    ✗ 不是合法 docx：{e}']

    na, nb = set(za.namelist()), set(zb.namelist())
    lost  = sorted(nb - na)   # B 有 A 没有
    added = sorted(na - nb)   # A 有 B 没有

    if lost or added:
        L.append('    ⚠ 部件结构变化')
        if lost:
            L.append(f'      A({label_a}) 缺少: {lost}')
        if added:
            L.append(f'      A({label_a}) 新增: {added}')

    chg = []
    for n in sorted(na & nb):
        a, b = za.read(n), zb.read(n)
        if a != b:
            chg.append((n, len(a), len(b)))
    if chg:
        L.append('    字节有差异的部件：')
        for n, la, lb in chg:
            L.append(f'      ~ {n:<32} {label_a} {la:>7}  {label_b} {lb:>7}  (Δ{la - lb:+d})')

    # ---- 文本级
    ta, tb = hdr_ftr_texts(za), hdr_ftr_texts(zb)
    allp = sorted(set(ta) | set(tb))
    text_same = True
    text_detail = []
    for n in allp:
        x, y = ta.get(n), tb.get(n)
        if x is None or y is None:
            text_same = False
            text_detail.append(f'      {n}: 一侧缺失')
            continue
        if x == y:
            continue
        text_same = False
        if len(x) != len(y):
            text_detail.append(f'      {n}: 段落数不同 {len(x)} vs {len(y)}')
        text_detail.append(f'      {n}: 文本有实质差异')
        for i, (u, v) in enumerate(zip(x, y)):
            if u != v:
                text_detail.append(f'         [段{i}] {label_a}={u[:60]!r}')
                text_detail.append(f'                {label_b}={v[:60]!r}')

    # ---- 占位符
    def keys(txts):
        blob = '\n'.join(t for v in txts.values() if v for t in v)
        return sorted(set(PH.findall(blob)))

    ka, kb = keys(ta), keys(tb)
    ph_same = ka == kb
    if not ph_same:
        text_same = False
        L.append('    ⚠ 占位符 keys 不一致：')
        L.append(f'      A 独有: {sorted(set(ka) - set(kb))}')
        L.append(f'      B 独有: {sorted(set(kb) - set(ka))}')
    else:
        L.append(f'    占位符 keys 一致（{len(ka)} 个）')

    if text_detail:
        L.append('    文本级差异：')
        L.extend(text_detail)
    elif text_same:
        L.append(f'    文本级：全部部件段落文本完全相同（已剔除 mc:Fallback）')

    if lost or added:
        verdict = '结构变化'
    elif text_same:
        verdict = '等价'
    else:
        verdict = '实质差异'
    return verdict, L


# ---------------------------------------------------------------- 全量模式
def walk_src():
    out = {}
    for dp, dn, fn in os.walk(SRC):
        dn[:] = [d for d in dn if d not in SKIP]
        for f in fn:
            if is_tpl(f):
                p = os.path.join(dp, f)
                out[os.path.relpath(p, SRC)] = p
    return out


def run_all(brief=False):
    src = walk_src()
    print('=' * 78)
    print('docx 部件级 / 文本级比对 · 源 vs 备份')
    print('=' * 78)
    print(f'源   : {SRC}')
    print(f'备份 : {BAK}')
    print(f'份数 : {len(src)}')
    print()

    n_eq = n_sub = n_struct = n_miss = 0
    for rel, pa in sorted(src.items()):
        pb = os.path.join(BAK, rel)
        if not os.path.exists(pb):
            n_miss += 1
            print(f'[备份缺失] {rel}')
            continue
        va, vb = os.path.getsize(pa), os.path.getsize(pb)
        if open(pa, 'rb').read() == open(pb, 'rb').read():
            n_eq += 1
            if not brief:
                print(f'[字节一致 ✅] {rel}')
            continue
        verdict, L = diff_one(pa, pb)
        if verdict == '等价':
            n_eq += 1
            print(f'[内容等价 ✅（仅 Word 序列化差异）] {rel}   {va}B vs {vb}B')
        elif verdict == '实质差异':
            n_sub += 1
            print(f'[⚠ 实质差异] {rel}')
        else:
            n_struct += 1
            print(f'[⚠ 结构变化] {rel}')
        if verdict != '等价' or not brief:
            for line in L:
                print(line)
        print()

    print('=' * 78)
    print(f'字节完全一致 / 内容等价 : {n_eq}')
    print(f'实质差异               : {n_sub}')
    print(f'部件结构变化           : {n_struct}')
    print(f'备份缺失               : {n_miss}')
    print('=' * 78)
    if n_sub == 0 and n_struct == 0 and n_miss == 0:
        print('结论：全部模板内容等价 ✅')
        return 0
    print('结论：存在需要人工定性的差异 ❌（先看清是谁改的、改了什么）')
    return 1


def main():
    ap = argparse.ArgumentParser(description='docx 部件级/文本级比对')
    ap.add_argument('pair', nargs='*', help='可选：<A.docx> <B.docx> 单比两份')
    ap.add_argument('--brief', action='store_true', help='全量模式下只打印有问题/等价的判定行')
    a = ap.parse_args()

    if len(a.pair) == 2:
        pa, pb = a.pair
        for p in (pa, pb):
            if not os.path.exists(p):
                print(f'文件不存在: {p}')
                return 1
        print('=' * 78)
        print(f'A(源)  : {pa}')
        print(f'B(备)  : {pb}')
        print('=' * 78)
        if open(pa, 'rb').read() == open(pb, 'rb').read():
            print('字节完全一致 ✅')
            return 0
        print(f'字节不一致：{os.path.getsize(pa)}B vs {os.path.getsize(pb)}B')
        print()
        verdict, L = diff_one(pa, pb)
        for line in L:
            print(line)
        print()
        print(f'判定：{verdict}')
        return 0 if verdict == '等价' else 1

    if a.pair:
        print('用法：diff_parts.py 或 diff_parts.py <A.docx> <B.docx>')
        return 1
    return run_all(brief=a.brief)


if __name__ == '__main__':
    sys.exit(main() or 0)
