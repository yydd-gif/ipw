# -*- coding: utf-8 -*-
"""gen_mapping_from_templates.py —— 以模板实况为基准重建「模板字段映射表.csv」

⚠ 会覆盖 01_设计文档/模板字段映射表.csv，运行前自动备份到 _历史版本/。

四轮位置分配：
  Pass A 精确命中  —— 原位置存在，且实况 key 集合 == 声称 key 集合
  Pass B key 锚定  —— 未占用位置中 key 有交集，优先「集合相等」，再取位置最近
  Pass C @ 类型锚定 —— 仅含 @ 标记的行，按签名就近分配未占用位置
                     （日期行 → @manualDate；手填/空白行 → @manualFill）
  Pass D 兜底      —— 保留原位，标「设计意图（模板未对应）」

用法：
    python locate_docx.py && python gen_mapping_from_templates.py
    python gen_mapping_from_templates.py --dry-run
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, re, sys, io, json, csv, shutil, argparse, collections, datetime

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PKG  = str(REPO)
DOC  = str(SPEC)
HIST = os.path.join(DOC, '_历史版本')
CSV  = os.path.join(DOC, '模板字段映射表.csv')

ATOMIC = re.compile(r'^段(\d+)$|^表(\d+)行(\d+)列(\d+)$')
DATE   = re.compile(r'年\s*月\s*日|年.{0,4}月.{0,4}日|日期|日\s*期')
HDR    = ['分册', '模板文件', '位置', '类型', '上下文', '目标字段', '置信度', '来源']
SECO   = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8}
TYPE_PRI = {'手填·日期': 0, '手填·正文': 0, '手填·留白': 0, '上传区': 0, '自动生成': 0, '固定文本': 0,
            '子表数据区': 1, '段落模板': 2, '占位文本': 3, '标签留空': 4, '空单元格': 5,
            '前缀插入': 6, '空白占位': 7, '填充位': 8}


def keys_of(t):
    t = (t or '').strip()
    if t.startswith('@'):
        return [], [t]
    return re.findall(r'[A-Za-z][A-Za-z0-9_]{2,}', t), re.findall(r'@[A-Za-z]+', t)


def pidx(p):
    m = ATOMIC.match(p)
    if not m:
        return None
    return int(m.group(1)) if m.group(1) else int(m.group(3)) * 1000 + int(m.group(4))


def sortkey(r):
    m = re.match(r'^(\d+)', r[1])
    m2 = re.match(r'^段(\d+)', r[2])
    m3 = re.match(r'^表(\d+)行(\d+)列(\d+)', r[2])
    p2 = (int(m3.group(1)) * 10000 + int(m3.group(2)) * 100 + int(m3.group(3))
          if m3 else (1000 if r[2].startswith('表') else 0))
    return (SECO.get(r[0][0], 9), int(m.group(1)) if m else 99,
            0 if r[2].startswith('段') else 1,
            int(m2.group(1)) if m2 else 9999, p2)


def rebuild(actual, rows):
    claimed = collections.defaultdict(set)
    resolved = {}
    KEEP_SRC = {'实况核对', '实况校正', '实况校对', '新增（实况补录）', '特殊位置'}

    # Pass A
    pend = []
    for i, r in enumerate(rows, 2):
        sec, fil, pos = r['分册'], r['模板文件'], r['位置']
        real = {p: ks for p, _, ks in actual.get((sec, fil), [])}
        claim, ats = keys_of(r['目标字段'])
        old_src = (r.get('来源') or '').strip()
        if not ATOMIC.match(pos):
            resolved[i] = (pos, r['目标字段'], old_src or '特殊位置'); continue
        if pos in real:
            rk = set(real[pos])
            # 位置含任一声称字段 → 认定该位置正确；目标字段一律以实况为准（幂等）
            if claim and rk and (rk == set(claim) or (set(claim) & rk)):
                tgt = '|'.join(sorted(rk) + [a for a in ats if a not in rk])
                src = old_src if old_src in KEEP_SRC else ('实况核对' if rk == set(claim) else '实况校对')
                resolved[i] = (pos, tgt, src); claimed[(sec, fil)].add(pos); continue
            if not claim and ats and not rk:
                resolved[i] = (pos, '|'.join(ats), old_src or '实况核对')
                claimed[(sec, fil)].add(pos); continue
            if not claim and not ats and not rk:
                pend.append((i, r, claim, ats)); continue
        pend.append((i, r, claim, ats))

    # Pass B
    left = []
    for i, r, claim, ats in pend:
        sec, fil, pos = r['分册'], r['模板文件'], r['位置']
        real = {p: ks for p, _, ks in actual.get((sec, fil), [])}
        if not claim:
            left.append((i, r, claim, ats)); continue
        cands = [(p, ks) for p, ks in real.items()
                 if p not in claimed[(sec, fil)] and set(ks) & set(claim)]
        if not cands:
            left.append((i, r, claim, ats)); continue
        ci = pidx(pos) or 0
        cands.sort(key=lambda x: (0 if set(x[1]) == set(claim) else 1, abs((pidx(x[0]) or 0) - ci)))
        best, bk = cands[0]
        resolved[i] = (best, '|'.join(sorted(set(bk)) + ats), '实况校正')
        claimed[(sec, fil)].add(best)
    # Pass C
    left2 = []
    for i, r, claim, ats in left:
        sec, fil, pos = r['分册'], r['模板文件'], r['位置']
        typ = r['类型']; ci = pidx(pos) or 0
        free = lambda p: p not in claimed[(sec, fil)]
        best = newf = None
        if ATOMIC.match(pos):
            if '日期' in typ or '@manualDate' in (r['目标字段'] or ''):
                ds = [(p, t) for p, t, ks in actual.get((sec, fil), [])
                      if free(p) and not ks and DATE.search(t) and p.startswith('段')]
                ds.sort(key=lambda x: abs((pidx(x[0]) or 0) - ci))
                if ds:
                    best, newf = ds[0][0], '@manualDate'
            if best is None and pos in actual.get((sec, fil), []) and free(pos):
                txt = {p: t for p, t, _ in actual[(sec, fil)]}[pos]
                best = pos
                if any(ks for p, _, ks in actual[(sec, fil)] if p == pos):
                    newf = None
                elif DATE.search(txt):
                    newf = '@manualDate'
                elif '手填' in typ or '留白' in typ or '空' in typ:
                    newf = '@manualFill'
        if best:
            old_src = (r.get('来源') or '').strip()
            if best == pos and old_src in KEEP_SRC:
                src = old_src
            else:
                src = '实况校正' if (newf or best != pos) else '实况核对'
            resolved[i] = (best, newf or '|'.join(claim + ats) or r['目标字段'], src)
            claimed[(sec, fil)].add(best)
        else:
            left2.append((i, r, claim, ats))

    # Pass D
    for i, r, claim, ats in left2:
        tgt = r['目标字段'] if (claim or ats) else '@manualFill'
        resolved[i] = (r['位置'], tgt, '设计意图（模板未对应）')

    out = []
    for i, r in enumerate(rows, 2):
        pos, tgt, src = resolved[i]
        out.append([r['分册'], r['模板文件'], pos, r['类型'], r['上下文'],
                    tgt or r['目标字段'], r['置信度'], src])

    # 补录
    cov = collections.defaultdict(set)
    for row in out:
        p = row[2]
        if ATOMIC.match(p):
            cov[(row[0], row[1])].add(p)
        else:
            m = re.fullmatch(r'表(\d+)行(\d+)-(\d+)', p)
            if m:
                t, a, b = m.groups()
                for rr in range(int(a), int(b) + 1):
                    for cc in range(1, 40):
                        cov[(row[0], row[1])].add(f'表{t}行{rr}列{cc}')
    added = 0
    for (sec, fil), items in sorted(actual.items()):
        for pos, txt, ks in items:
            if ks and pos not in cov[(sec, fil)]:
                out.append([sec, fil, pos, '填充位', txt[:60],
                            '|'.join(sorted(set(ks))), '高', '新增（实况补录）'])
                cov[(sec, fil)].add(pos); added += 1

    # 去重合并
    merged = collections.OrderedDict()
    for row in out:
        k = (row[0], row[1], row[2])
        if k not in merged:
            merged[k] = row
        else:
            o = merged[k]
            seen = []
            for x in (o[5] + '|' + row[5]).split('|'):
                if x and x not in seen:
                    seen.append(x)
            o[5] = '|'.join(seen)
            if TYPE_PRI.get(row[3], 9) < TYPE_PRI.get(o[3], 9):
                o[3] = row[3]
            if row[7] != '设计意图（模板未对应）' and o[7] == '设计意图（模板未对应）':
                o[7] = row[7]
    out = sorted(merged.values(), key=sortkey)
    return out, added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(WORK / 'tmp' / 'actual_locate.json'))
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    actual = {}
    for k, v in json.load(open(a.json, encoding='utf-8')).items():
        s, f = k.split('|', 1)
        actual[(s, f)] = [(p, t, ks) for p, t, ks in v]
    rows = list(csv.DictReader(open(CSV, encoding='utf-8-sig')))
    out, added = rebuild(actual, rows)

    cov = {(r[0], r[1], r[2]) for r in out if ATOMIC.match(r[2])}
    tot = sum(len(ks) for v in actual.values() for _, _, ks in v)
    hit = sum(len(ks) for (s, f), items in actual.items() for p, t, ks in items
              if ks and (s, f, p) in cov)
    print(f'输入 {len(rows)} 行 → 输出 {len(out)} 行（补录 {added}）')
    c = collections.Counter(r[7] for r in out)
    print('来源分布: ' + ' / '.join(f'{k} {v}' for k, v in c.most_common()))
    print(f'占位符覆盖 {hit} / {tot}')
    d = collections.Counter((r[0], r[1], r[2]) for r in out)
    print(f'重复位置 {sum(1 for v in d.values() if v > 1)} 组')

    if a.dry_run:
        print('（dry-run，未写入）'); return
    os.makedirs(HIST, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    bak = os.path.join(HIST, f'模板字段映射表-{stamp}-改前({len(rows)}条).csv')
    if not os.path.exists(bak):
        shutil.copy2(CSV, bak)
    with open(CSV, 'w', encoding='utf-8-sig', newline='') as fp:
        w = csv.writer(fp); w.writerow(HDR); w.writerows(out)
    print(f'已写入 {CSV}\n改前备份 {bak}')


if __name__ == '__main__':
    main()
