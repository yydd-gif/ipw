#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排版体检 · 一次性扫出模板里的「排版事故」（模板资产核查 第四类检查）

背景：前三轮核查只查了「占位符 / 字段 / 映射」，**没查排版**。
      2026-09-16 第四轮补查，扫出 6 份模板「段前分页」失控（每段强制新起一页）。

检查项：
  T1 段前分页（w:pageBreakBefore）失控  —— 占比 > 50% 且文档长度合理 → 事故
  T2 硬分页（w:br type=page）与段前分页混用
  T3 页眉 / 页脚覆盖缺失
  T4 页码域（PAGE / NUMPAGES）口径不统一
  T5 纸张尺寸 / 页边距不一致
  T6 中文字体混用、西文误用中文字体
  T7 空段落带分页（会产生空白页）

用法：
  python audit_typography.py                 # 扫 07_模板资产（跳过 00_模板原始备份）
  python audit_typography.py --json out.json
  python audit_typography.py --root <目录>

口径纪律（本项目踩过四次假阳性，务必遵守）：
  - 一律用 stdlib xml.etree.ElementTree，**不要用正则剥 '<...>'** 读正文
  - 读 w:t 前**必须删掉 mc:Fallback 子树**，否则 Choice/Fallback 双读，文字会重复
    （踩过：页脚「第 4 页第 4 页」实为「第 4 页」）
  - 域（PAGE/NUMPAGES）的缓存值也是 w:t，别当成"游离脏数字"
  - ★ **on/off 类元素必须读 w:val，不能"存在即启用"** ★
    w:pageBreakBefore / w:keepNext / w:keepLines / w:widowControl 等都是 on/off 元素：
      <w:pageBreakBefore/>             → 启用（缺省 val = true）
      <w:pageBreakBefore w:val="1"/>   → 启用
      <w:pageBreakBefore w:val="0"/>   → **关闭！**
    本脚本初版没读 val，把 199 处「显式关闭」误报成「段前分页失控」，
    据此差点批量删掉这些元素并已写好转工具。**教训：先读 val，再下结论。**
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)

import argparse
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path

import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MC = '{http://schemas.openxmlformats.org/markup-compatibility/2006}'

BASE = REPO
DEFAULT_ROOT = TEMPLATES
SKIP_DIR = '00_模板原始备份'
A4 = (210.0, 297.0)          # mm
EMU_PER_MM = 56.6929
PBB_ALERT = 0.50             # 段前分页占比告警线
MIN_PARAS = 6                # 短于这个段落数不判"失控"（小表格类文档天然如此）


# ---------------------------------------------------------------- 基础

def drop_fallback(root: ET.Element) -> int:
    """删 mc:Fallback 子树，避免 Choice/Fallback 双读导致文字重复"""
    n = 0
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag == MC + 'Fallback':
                parent.remove(child)
                n += 1
    return n


def para_text(p: ET.Element) -> str:
    out = []
    for n in p.iter():
        if n.tag == W + 't':
            out.append(n.text or '')
        elif n.tag == W + 'tab':
            out.append('\t')
        elif n.tag in (W + 'br', W + 'cr'):
            out.append('\n')
    return ''.join(out).replace('\u3000', ' ').strip()


def to_mm(v):
    try:
        return round(int(v) / EMU_PER_MM, 1)
    except (TypeError, ValueError):
        return None


# OOXML on/off 元素的"关闭"取值（缺省 val 表示 true）
_OFF_VALS = {'0', 'false', 'off', 'no', 'none'}


def is_on(el: ET.Element) -> bool:
    """on/off 类元素是否**真启用** —— 必须读 w:val，不能"存在即启用"

    <w:pageBreakBefore/>             → True （缺省 val = true）
    <w:pageBreakBefore w:val="1"/>   → True
    <w:pageBreakBefore w:val="0"/>   → False  ★ 这一条是 2026-09-16 的教训
    """
    if el is None:
        return False
    v = el.get(W + 'val')
    if v is None:
        return True
    return v.strip().lower() not in _OFF_VALS


def part_text(raw: bytes) -> str:
    try:
        root = ET.fromstring(raw)
    except ET.XMLSyntaxError:
        return ''
    drop_fallback(root)
    return ''.join(t.text or '' for t in root.iter(W + 't')).strip()


# ---------------------------------------------------------------- 单份体检

def audit_one(path: Path) -> dict:
    r = {'文件': path.name, '分册': path.parent.name}
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        doc_raw = z.read('word/document.xml')
        hdr = sorted(n for n in names if n.startswith('word/header') and n.endswith('.xml'))
        ftr = sorted(n for n in names if n.startswith('word/footer') and n.endswith('.xml'))
        head_txt = [(n.split('/')[-1], part_text(z.read(n))) for n in hdr]
        foot_txt = [(n.split('/')[-1], part_text(z.read(n))) for n in ftr]
        npage = nnum = 0
        for n in hdr + ftr:
            try:
                hr = ET.fromstring(z.read(n))
            except ET.XMLSyntaxError:
                continue
            for t in hr.iter(W + 'instrText'):
                u = (t.text or '').upper()
                if 'NUMPAGES' in u:
                    nnum += 1
                elif 'PAGE' in u:
                    npage += 1
        # 部件级 w:p 计数（含表格内），用于校验
        raw_txt = doc_raw.decode('utf-8', 'ignore')

    root = ET.fromstring(doc_raw)
    drop_fallback(root)

    paras = list(root.iter(W + 'p'))
    tot = len(paras)
    content = sum(1 for p in paras if para_text(p))
    pbb = 0            # 真启用（w:val 缺失或为真值）
    pbb_off = 0        # 显式关闭 <w:pageBreakBefore w:val="0"/> —— 不是问题，别报
    pbb_empty = 0
    for p in paras:
        pr = p.find(W + 'pPr')
        el = pr.find(W + 'pageBreakBefore') if pr is not None else None
        if el is None:
            continue
        if not is_on(el):
            pbb_off += 1
            continue
        pbb += 1
        if not para_text(p):
            pbb_empty += 1
    brk = len([b for b in root.iter(W + 'br') if b.get(W + 'type') == 'page'])

    sect = []
    for sp in root.iter(W + 'sectPr'):
        pg = sp.find(W + 'pgSz')
        mg = sp.find(W + 'pgMar')
        if pg is None:
            continue
        sect.append({
            'w': to_mm(pg.get(W + 'w')), 'h': to_mm(pg.get(W + 'h')),
            'orient': pg.get(W + 'orient') or 'portrait',
            'mar': None if mg is None else [to_mm(mg.get(W + k)) for k in
                                            ('left', 'right', 'top', 'bottom')],
        })

    cn, en, sz = Counter(), Counter(), Counter()
    for rf in root.iter(W + 'rFonts'):
        cn[rf.get(W + 'eastAsia') or '(继承)'] += 1
        en[rf.get(W + 'ascii') or '(继承)'] += 1
    for s in root.iter(W + 'sz'):
        sz[s.get(W + 'val')] += 1

    r.update({
        '总段数': tot, '有内容段': content,
        '段前分页': pbb, '段前分页_显式关闭': pbb_off, '空段带分页': pbb_empty,
        '硬分页': brk,
        '段前分页占比': round(pbb / max(content, 1), 3),
        '节数': len(sect), '节设置': sect,
        '有页眉': bool(hdr), '有页脚': bool(ftr),
        '页眉内容': [t for _, t in head_txt if t],
        '页脚内容': [t for _, t in foot_txt if t],
        'PAGE域': npage, 'NUMPAGES域': nnum,
        '中文字体': dict(cn), '西文字体': dict(en), '字号半磅': dict(sz),
        '_raw_w_p': len(__import__('re').findall(r'<w:p[ />]', raw_txt)),
    })
    return r


# ---------------------------------------------------------------- 汇总

def report(root: Path, rows: list) -> None:
    line = '=' * 78

    print(line)
    print('【T1】段前分页（w:pageBreakBefore）失控')
    hit = [r for r in rows if r['段前分页占比'] > PBB_ALERT and r['有内容段'] >= MIN_PARAS]
    if not hit:
        print('  无')
    for r in sorted(hit, key=lambda x: -x['段前分页占比']):
        print('  X  %-44s 总段%4d / 有内容%4d / 分页%4d  = %3.0f%%'
              % (r['文件'][:44], r['总段数'], r['有内容段'], r['段前分页'],
                 r['段前分页占比'] * 100))
    n_on = sum(r['段前分页'] for r in rows)
    n_off = sum(r['段前分页_显式关闭'] for r in rows)
    print('  >> 受影响 %d 份。后果：每段强制新起一页，1-2 页的短文档会打成 15-21 页' % len(hit))
    print('  >> 全包：真启用 %d 处 / 显式关闭(w:val="0") %d 处' % (n_on, n_off))
    if n_off and not n_on:
        print('  >> 注：那 %d 处 w:val="0" 是「显式关闭段前分页」，Word 另存/复制时常见，'
              '**不是问题，别删**' % n_off)

    print()
    print('【T2】分页符类型混用')
    mixed = [r for r in rows if r['硬分页'] and r['段前分页']]
    print('  硬分页合计 %d 处 / 段前分页合计 %d 处'
          % (sum(r['硬分页'] for r in rows), sum(r['段前分页'] for r in rows)))
    for r in mixed:
        print('  !  %-44s 硬分页%d + 段前分页%d' % (r['文件'][:44], r['硬分页'], r['段前分页']))

    print()
    print('【T3】页眉 / 页脚覆盖')
    nh = sum(1 for r in rows if r['有页眉'])
    nf = sum(1 for r in rows if r['有页脚'])
    print('  有页眉 %d / 有页脚 %d （总 %d 份）' % (nh, nf, len(rows)))
    for key, label in (('有页眉', '缺页眉'), ('有页脚', '缺页脚')):
        miss = [r for r in rows if not r[key]]
        if miss:
            print('  %s %d 份：%s' % (label, len(miss),
                                     '、'.join(x['文件'][:20] for x in miss[:8])))
    empty_h = [r for r in rows if r['有页眉'] and not r['页眉内容']]
    empty_f = [r for r in rows if r['有页脚'] and not r['页脚内容']]
    print('  页眉存在但内容为空 %d 份 / 页脚存在但内容为空 %d 份'
          % (len(empty_h), len(empty_f)))

    print()
    print('【T4】页码域口径')
    styles = Counter()
    for r in rows:
        if not r['有页脚']:
            styles['无页脚·无页码'] += 1
        elif r['PAGE域'] and r['NUMPAGES域']:
            styles['第X页 共Y页（PAGE+NUMPAGES）'] += 1
        elif r['PAGE域']:
            styles['第 X 页（仅 PAGE）'] += 1
        else:
            styles['有页脚但无页码域'] += 1
    for k, v in styles.most_common():
        print('  %-34s %d 份' % (k, v))

    print()
    print('【T5】纸张 / 页边距')
    psz = Counter()
    for r in rows:
        for s in r['节设置']:
            psz[(s['w'], s['h'], s['orient'])] += 1
    for k, v in psz.most_common():
        tag = '' if (k[0], k[1]) == A4 and k[2] == 'portrait' else '   <== 非 A4 纵向'
        print('  %s x %s %-9s  %d 节%s' % (k[0], k[1], k[2], v, tag))
    mar = Counter(tuple(s['mar']) for r in rows for s in r['节设置'] if s['mar'])
    if len(mar) > 1:
        print('  ! 页边距有 %d 种不同取值：' % len(mar))
        for k, v in mar.most_common():
            print('      左%s/右%s/上%s/下%s  %d 节' % (*k, v))

    print()
    print('【T6】字体')
    cn, en = Counter(), Counter()
    for r in rows:
        cn.update(r['中文字体'])
        en.update(r['西文字体'])
    real_cn = {k: v for k, v in cn.items() if k != '(继承)'}
    real_en = {k: v for k, v in en.items() if k != '(继承)'}
    print('  中文字体 %d 种：%s' % (len(real_cn), real_cn))
    print('  西文字体 %d 种：%s' % (len(real_en), real_en))
    bad = sum(v for k, v in real_en.items()
              if k in ('宋体', '黑体', '仿宋', '仿宋_GB2312', '楷体'))
    if bad:
        print('  ! 西文位置误用中文字体：%d 处（应用 Times New Roman 等）' % bad)

    print()
    print('【T7】空段落带分页（会产生空白页）')
    tot_empty = sum(r['空段带分页'] for r in rows)
    for r in rows:
        if r['空段带分页']:
            print('  !  %-44s %d 处' % (r['文件'][:44], r['空段带分页']))
    if not tot_empty:
        print('  无')

    print()
    print(line)
    print('汇总：%d 份模板 · 段前分页失控 %d 份 · 缺页眉 %d 份 · 缺页脚 %d 份'
          % (len(rows), len(hit),
             sum(1 for r in rows if not r['有页眉']),
             sum(1 for r in rows if not r['有页脚'])))
    print('★ 本脚本只读，不改任何 docx。要修由工头决定（铁律 #1）。')
    print(line)


def main() -> int:
    ap = argparse.ArgumentParser(description='模板排版体检（只读）')
    ap.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='模板根目录')
    ap.add_argument('--json', type=Path, help='把明细写入 JSON')
    ap.add_argument('--only', help='只查文件名含该子串的模板')
    a = ap.parse_args()

    root = a.root
    if not root.exists():
        print('!! 目录不存在：%s' % root)
        return 1
    files = [p for p in sorted(root.rglob('*.docx')) if SKIP_DIR not in str(p)]
    if a.only:
        files = [p for p in files if a.only in p.name]
    if not files:
        print('!! 没找到 docx')
        return 1

    rows = []
    for p in files:
        try:
            rows.append(audit_one(p))
        except zipfile.BadZipFile:
            print('  !! 损坏：%s' % p.name)

    report(root, rows)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
        print('明细已写入 %s' % a.json)
    return 0


if __name__ == '__main__':
    sys.exit(main())
