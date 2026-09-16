# -*- coding: utf-8 -*-
"""diff_mapping.py —— 映射表 × 模板实况 全量对账

依赖 locate_docx.py 产出的 actual_locate.json（先跑 locate_docx.py）。

检查项：
  A 位置命中    —— 映射表记的「段N / 表M行R列C」在模板里是否还存在
  B 字段对账    —— 映射表声称的字段 vs 该位置真实的 {{key}}
  C 覆盖缺口    —— 模板有 {{key}} 但映射表无任何行覆盖的位置
  D 人读残留    —— 模板里还残留 XXX / ××× / 长下划线 等未标注窝
  E 字段全集    —— 映射表字段 vs 字段字典（39 启用 + 8 子表）
  F run 完整性  —— {{key}} 是否被拆散在多个 <w:r>/<w:t> 里
                  （逻辑上存在、渲染正常，但**按 run 做文本替换会失败**）

用法：
    python diff_mapping.py
    python diff_mapping.py --json <actual_locate.json> --csv <映射表.csv>
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, re, sys, io, json, csv, argparse, collections

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PKG  = str(REPO)
DOC  = str(SPEC)

ATOMIC = re.compile(r'^段(\d+)$|^表(\d+)行(\d+)列(\d+)$')
AT_MARKS = {'@manualDate', '@manualFill', '@upload', '@autoToc', '@autoDivider', '@fixedText'}
SUS = re.compile(r'(XXX|×××|XX年|XX月|XX单位|____|_{4,})')


def keys_of(t):
    t = (t or '').strip()
    if t.startswith('@'):
        return [], [t]
    return re.findall(r'[A-Za-z][A-Za-z0-9_]{2,}', t), re.findall(r'@[A-Za-z]+', t)


def covered_positions(rows, sec, fil):
    """把「表M行A-B」这类区间展开成具体单元格位置"""
    cov = set()
    for r in rows:
        if r['分册'] != sec or r['模板文件'] != fil:
            continue
        p = r['位置']
        if ATOMIC.match(p):
            cov.add(p); continue
        m = re.fullmatch(r'表(\d+)行(\d+)-(\d+)', p)
        if m:
            t, a, b = m.groups()
            for rr in range(int(a), int(b) + 1):
                for cc in range(1, 40):
                    cov.add(f'表{t}行{rr}列{cc}')
            continue
        m = re.fullmatch(r'表(\d+)行(\d+)-(\d+)列(\d+)', p)
        if m:
            t, a, b, c = m.groups()
            for rr in range(int(a), int(b) + 1):
                cov.add(f'表{t}行{rr}列{c}')
    return cov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', dest='locate_json', default=str(WORK / 'tmp' / 'actual_locate.json'))
    ap.add_argument('--csv', default=os.path.join(DOC, '模板字段映射表.csv'))
    a = ap.parse_args()

    actual = {}
    for k, v in json.load(open(a.locate_json, encoding='utf-8')).items():
        s, f = k.split('|', 1)
        actual[(s, f)] = [(p, t, ks) for p, t, ks in v]
    rows = list(csv.DictReader(open(a.csv, encoding='utf-8-sig')))

    print('=' * 84); print('【A】位置命中')
    hit = miss = 0; missl = []
    for i, r in enumerate(rows, 2):
        if not ATOMIC.match(r['位置']):
            continue
        real = {p for p, _, _ in actual.get((r['分册'], r['模板文件']), [])}
        if r['位置'] in real:
            hit += 1
        else:
            miss += 1; missl.append((i, r))
    print(f'  命中 {hit} / 未命中 {miss}')
    for i, r in missl:
        print(f'    ✗ L{i} {r["模板文件"]} 位置「{r["位置"]}」目标={r["目标字段"]}')

    print(); print('=' * 84); print('【B】字段对账')
    bad = 0
    for i, r in enumerate(rows, 2):
        if not ATOMIC.match(r['位置']):
            continue
        real = {p: set(ks) for p, _, ks in actual.get((r['分册'], r['模板文件']), [])}
        if r['位置'] not in real:
            continue
        claim, _ = keys_of(r['目标字段'])
        if set(claim) != real[r['位置']]:
            bad += 1
            d1 = sorted(set(claim) - real[r['位置']]); d2 = sorted(real[r['位置']] - set(claim))
            print(f'  L{i} {r["模板文件"]} {r["位置"]} [{r["类型"]}]')
            if d1: print(f'      声称要填但模板无: {d1}')
            if d2: print(f'      模板有但未声称: {d2}')
    print(f'  不一致 {bad} 处')

    print(); print('=' * 84); print('【C】模板有 {{key}} 但映射表无覆盖的位置')
    n = 0
    for (sec, fil), items in sorted(actual.items()):
        cov = covered_positions(rows, sec, fil)
        for pos, t, ks in items:
            if ks and pos not in cov:
                n += 1
                print(f'  ✗ {sec}/{fil} {pos}  keys={ks}')
                print(f'      {t[:100]}')
    print(f'  合计 {n} 个位置')

    print(); print('=' * 84); print('【D】模板残留的人读占位')
    m = 0
    for (sec, fil), items in sorted(actual.items()):
        for pos, t, ks in items:
            if SUS.search(t):
                m += 1
                print(f'  ⚠ {sec}/{fil} {pos}')
                print(f'      {t[:105]}')
    print(f'  合计 {m} 处')

    print(); print('=' * 84); print('【E】字段全集对账')
    fd = json.load(open(os.path.join(DOC, '字段字典.json'), encoding='utf-8'))
    dis = {f['key'] for f in fd['disabledFields']}
    rem = {f['key'] for f in fd['removedFields']['fields']}
    en  = {f['key'] for g in fd['groups'] for f in g['fields'] if f['key'] not in dis and f['key'] not in rem}
    tb  = {t['key'] for t in fd['tables']}
    got = set()
    for r in rows:
        for k in r['目标字段'].split('|'):
            k = k.strip()
            if k and not k.startswith('@'):
                got.add(k)
    print(f'  字典启用 {len(en)} / 子表 {len(tb)} / 映射表字段 {len(got)}')
    print(f'  ▶ 启用但映射表缺失: {sorted(en - got)}')
    print(f'  ▶ 子表未在映射表:   {sorted(tb - got)}')
    print(f'  ▶ 非字段非法取值:   {sorted(got - en - tb)}')
    print(f'  ▶ @ 标记使用:       {sorted({k for r in rows for k in r["目标字段"].split("|")} & AT_MARKS)}')

    print(); print('=' * 84); print('【F】run 完整性：{{key}} 是否被拆散在多个 w:t 里')
    import zipfile
    import xml.etree.ElementTree as _ET
    W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    import glob
    assets = str(TEMPLATES)
    tot_split = 0; by_key = collections.Counter(); n_tpl = 0
    for dp, dn, fn in os.walk(assets):
        dn[:] = [d for d in dn if d != '00_模板原始备份']
        sec = os.path.basename(dp)
        for f in sorted(fn):
            if not f.lower().endswith('.docx') or f.startswith('~$'):
                continue
            p = os.path.join(dp, f)
            z = zipfile.ZipFile(p); xml = z.read('word/document.xml'); z.close()
            raw = xml.decode('utf-8', 'ignore')
            if len(re.findall(r'\{\{\s*[A-Za-z0-9_]+\s*\}\}', re.sub(r'<[^>]+>', '', raw))) == \
               len(re.findall(r'\{\{\s*[A-Za-z0-9_]+\s*\}\}', raw)):
                continue
            n_tpl += 1
            root = _ET.fromstring(xml)
            for para in (root.find(W + 'body') or root).iter(W + 'p'):
                texts = [t.text or '' for t in para.iter(W + 't')]
                joined = ''.join(texts)
                for m in re.finditer(r'\{\{\s*([A-Za-z0-9_]+)\s*\}\}', joined):
                    if any(re.search(r'\{\{\s*[A-Za-z0-9_]+\s*\}\}', t) for t in texts):
                        continue
                    tot_split += 1; by_key[m.group(1)] += 1
                    print(f'  ⚠ {sec}/{f}  {{{{ {m.group(1)} }}}} 跨 {len([t for t in texts if t])} 个 w:t')
    print(f'  ▶ 受影响模板 {n_tpl} 份 / 拆散占位符 {tot_split} 处')
    if tot_split:
        print(f'  ▶ 受影响字段：{dict(by_key)}')
        print('  ▶ 处置：填充引擎必须实现「同段落内跨 run 合并替换」（见核查报告 E-7）')
    else:
        print('  ▶ 全部 {{key}} 完整落在单个 w:t 内 ✅')


if __name__ == '__main__':
    main()
