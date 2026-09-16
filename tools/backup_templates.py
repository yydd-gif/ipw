# -*- coding: utf-8 -*-
"""backup_templates.py —— 建立模板原始备份（只读副本 + SHA256 清单）

作用：给 07_模板资产/ 下的 docx 做一份「出厂态」只读副本，落到
      07_模板资产/00_模板原始备份/，供回溯与 diff 使用。对应铁律 #2。

特性：
  - 源目录**只读**，绝不回写
  - 副本与源保持同名分册结构
  - 副本设 Windows 只读属性（os.chmod S_IREAD）
  - 生成 SHA256清单.json（分册/文件名/字节数/校验和）
  - 已存在且校验和一致 → 跳过（可反复运行做增量校验）
  - 结束时回校验 + 只读检查

⚠ 命名纪律：后续若发现模板被改坏，用本目录的副本做 diff / 还原；
   正式模板改动一律**不要**在本目录进行。

用法：
    python backup_templates.py
    python backup_templates.py --verify-only      # 只体检，不复制（A 副本完整性 + B 源↔备份同步性）
    python backup_templates.py --verify-only --brief   # 只输出一行结论

⚠ --verify-only 的两段体检（2026-09-16 补 B 段，教训见下）：
    [A] 副本完整性：备份文件 sha256 是否 == 清单记录的建档时 sha256
        —— 只证明**副本没被改坏**。
    [B] 源↔备份同步性：**当前**源目录 sha256 是否仍 == 清单记录
        —— 才证明源没跑偏。
    只做 A 会漏掉「源被改过、备份没跟上」这种情况：
    曾有一次零改动复核只看 A 段，得出「全部一致」的假结论；
    实际 `七、竣工验收分册/1、项目情况简介.docx` 已被 Word 重存过。
    所以 B 段必须做，且**有漂移就 exit 1**，方便脚本链兜住。
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, re, sys, io, json, stat, shutil, hashlib, argparse, datetime, collections

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SRC  = str(TEMPLATES)
DST  = str(TEMPLATES_BACKUP)
SKIP = {'00_模板原始备份'}


def sha256(p, buf=1 << 20):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def is_tpl(f):
    return f.lower().endswith('.docx') and not f.startswith('~$')


def _walk_src():
    """返回当前源目录文件集合 {(分册, 文件名)}"""
    out = set()
    for dp, dn, fn in os.walk(SRC):
        dn[:] = [d for d in dn if d not in SKIP]
        rel = os.path.relpath(dp, SRC)
        if rel == '.':
            continue
        for f in fn:
            if is_tpl(f):
                out.add((rel.replace('\\', '/'), f))
    return out


def _mt(p):
    try:
        return datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M:%S')
    except OSError:
        return '—'


def verify_only(man_path, brief=False):
    """两段体检：[A] 副本完整性  [B] 源↔备份同步性。有漂移返回 1。

    铁律 #2 的实际守护点：只做 A 段会漏掉「源被改、备份没跟上」，
    必须两段都过才算「模板资产处于冻结态」。
    """
    man = json.load(open(man_path, encoding='utf-8'))
    key = {(x['分册'], x['文件']): x for x in man['files']}

    # ---- A. 副本完整性（备份 vs 建档时记录）
    bad = []
    for x in man['files']:
        d = os.path.join(DST, x['分册'].replace('/', os.sep), x['文件'])
        if not os.path.exists(d):
            bad.append((x['分册'], x['文件'], '副本缺失'))
        elif sha256(d) != x['sha256']:
            bad.append((x['分册'], x['文件'], '副本被改动'))

    # ---- B. 源↔备份同步性（当前源 vs 建档时记录）
    cur = _walk_src()
    drift, gone = [], []
    for k, x in key.items():
        s = os.path.join(SRC, k[0].replace('/', os.sep), k[1])
        if not os.path.exists(s):
            gone.append(k)
        elif sha256(s) != x['sha256']:
            drift.append((k, s))
    new = sorted(cur - set(key))

    ok = not (bad or drift or gone or new)
    if brief:
        print(f'模板资产体检 {man["total"]} 份 → '
              f'{"冻结态完好 ✅" if ok else "有漂移 ❌"}'
              f'（副本异常 {len(bad)} / 源漂移 {len(drift)} / '
              f'源缺失 {len(gone)} / 新增未备份 {len(new)}）')
        return 0 if ok else 1

    print('=' * 72)
    print('模板资产体检 · 源↔备份（铁律 #2）')
    print('=' * 72)
    print(f'清单建档 : {man.get("created", "?")}   共 {man["total"]} 份')
    print()

    print(f'[A] 副本完整性   {man["total"]} 份 → '
          f'{"全部与建档记录一致 ✅" if not bad else str(len(bad)) + " 处异常 ❌"}')
    for a_, f_, w in bad:
        print(f'      ✗ {a_}/{f_}   ({w})')
    print()

    print(f'[B] 源↔备份同步 {man["total"]} 份 → '
          f'{"当前源仍等于建档记录 ✅" if not (drift or gone) else "源已跑偏 ❌"}')
    if drift:
        print(f'      ⚠ 源已改动、备份仍是旧版（{len(drift)} 份）：')
        for (a_, f_), s in drift:
            print(f'        ~ {a_}/{f_}')
            print(f'            源mtime {_mt(s)}   size {os.path.getsize(s)}')
            print(f'            备mtime {_mt(os.path.join(DST, a_.replace("/", os.sep), f_))}')
        print('        ↳ 若为人工用 Word 打开保存所致，内容未必变（Word 会重排 XML）；')
        print('          请先用 diff_parts.py 做部件级/文本级比对再判定。')
    if gone:
        print(f'      ⚠ 清单里有、源里已没有（{len(gone)} 份，疑改名/删除）：')
        for a_, f_ in gone:
            print(f'        - {a_}/{f_}')
    if new:
        print(f'      ⚠ 源里有、清单里没记（{len(new)} 份，新增未备份）：')
        for a_, f_ in new:
            print(f'        + {a_}/{f_}')
    print()

    if ok:
        print('结论：37 份模板均处于冻结态，源与备份一致 ✅')
    else:
        print('结论：模板资产存在漂移 ❌ —— 处理前先搞清是谁改的、改了什么。')
        print('      核实用：python tools/diff_parts.py <源> <备份>')
        print('      补备份：python tools/backup_templates.py')
    print('=' * 72)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify-only', action='store_true')
    ap.add_argument('--brief', action='store_true', help='配合 --verify-only，只输出一行结论')
    ap.add_argument('--prune', action='store_true',
                    help='同时删除「源目录已不存在」的备份副本（如模板被改名/删除后同步备份）')
    a = ap.parse_args()

    man_path = os.path.join(DST, 'SHA256清单.json')
    if a.verify_only:
        return verify_only(man_path, brief=a.brief)

    # 源目录现有文件清单
    src_files = set()
    for dp, dn, fn in os.walk(SRC):
        dn[:] = [d for d in dn if d not in SKIP]
        rel = os.path.relpath(dp, SRC)
        if rel == '.':
            continue
        for f in fn:
            if is_tpl(f):
                src_files.add((rel.replace('\\', '/'), f))

    # —— prune：清掉源里已不存在的备份副本
    pruned = 0
    if a.prune:
        for dp, dn, fn in os.walk(DST):
            for f in fn:
                if not is_tpl(f):
                    continue
                rel = os.path.relpath(dp, DST).replace('\\', '/')
                if rel == '.':
                    continue
                if (rel, f) not in src_files:
                    os.chmod(os.path.join(dp, f), stat.S_IWRITE)   # 先解只读才能删
                    os.remove(os.path.join(dp, f))
                    pruned += 1
                    print(f'  - 已清理备份中的过期副本 {rel}/{f}')

    os.makedirs(DST, exist_ok=True)
    man = {'created': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
           'purpose': '模板冻结态备份。铁律#2 依据。标注/改名前必须存在此副本。',
           'source': 'assets/templates/', 'files': [], 'total': 0}
    copied = skipped = 0
    for dp, dn, fn in os.walk(SRC):
        dn[:] = [d for d in dn if d not in SKIP]
        rel = os.path.relpath(dp, SRC)
        if rel == '.':
            continue
        outdir = os.path.join(DST, rel)
        for f in sorted(fn):
            if not is_tpl(f):
                continue
            s, d = os.path.join(dp, f), os.path.join(outdir, f)
            h = sha256(s)
            os.makedirs(outdir, exist_ok=True)
            if os.path.exists(d) and sha256(d) == h:
                skipped += 1
            else:
                shutil.copy2(s, d); copied += 1
            try:
                os.chmod(d, stat.S_IREAD)
            except Exception as e:
                print(f'  ! 只读设置失败 {rel}/{f}: {e}')
            man['files'].append({'分册': rel.replace('\\', '/'), '文件': f,
                                 '字节': os.path.getsize(s), 'sha256': h})
    man['total'] = len(man['files'])
    with open(man_path, 'w', encoding='utf-8') as fp:
        json.dump(man, fp, ensure_ascii=False, indent=2)

    print(f'备份目录 {DST}')
    print(f'  新复制 {copied} / 跳过 {skipped} / 清单 {man["total"]} 份')
    for k, v in sorted(collections.Counter(x['分册'] for x in man['files']).items()):
        print(f'    {k:36s} {v:2d}')
    bad = sum(1 for x in man['files']
              if sha256(os.path.join(DST, x['分册'].replace('/', os.sep), x['文件'])) != x['sha256'])
    rw = [p for dp, dn, fn in os.walk(DST) for f in fn
          if is_tpl(f) and os.access(p := os.path.join(dp, f), os.W_OK)]
    print(f'  回校验 {"全部一致 ✅" if bad == 0 else str(bad)+" 处异常 ❌"} / '
          f'只读 {"全部只读 ✅" if not rw else str(len(rw))+" 份仍可写 ❌"}')


if __name__ == '__main__':
    sys.exit(main() or 0)
