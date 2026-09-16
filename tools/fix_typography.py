#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
排版修复 · 删除**真启用**的「段前分页」（w:pageBreakBefore）

════════════════════════════════════════════════════════════════════════════
★ 先说一条用血换来的教训（2026-09-16）

  `w:pageBreakBefore` 是 OOXML 的 **on/off 类元素**，必须读 `w:val`：

      <w:pageBreakBefore/>            → 启用（缺省 val 视为 true）
      <w:pageBreakBefore w:val="1"/>  → 启用
      <w:pageBreakBefore w:val="0"/>  → **关闭！不是启用！**

  我第一版体检脚本 `audit_typography.py` **没读 val**，把本包 199 处
  「显式关闭」误报成「段前分页失控」，并据此写了本工具准备批量删除。
  复核时才发现 199 处全是 `w:val="0"`，真启用 **0 处** —— 纯属假阳性。

  本工具已改为**只针对真启用**的元素；本包当前目标数为 0，运行即报「无可修」。
  **不要为了"清理"去删 `w:val="0"` 的元素** —— 那是 Word 另存/复制时固化格式的
  正常产物，删了无益且徒增风险。
════════════════════════════════════════════════════════════════════════════

设计原则（铁律驱动）：
  1. 部件级操作：zip 读入 → 只改 word/document.xml → 其余部件原样写回（保留 ZipInfo）
  2. **最小字节改动**：只精确删除目标空元素，**不做 ElementTree round-trip**
     （ET 序列化会改写命名空间前缀 / 属性顺序 / 自闭合风格，风险远大于收益）
  3. 五重安全网（任一不过就回滚该文件）：
       S1 改后仍是合法 XML（ET 可解析）
       S2 改前改后 **逐 w:t 文本完全一致**（证明没碰到一个字）
       S3 删除数量 == 预告数量
       S4 除 document.xml 外，所有部件**字节完全一致**
       S5 改后真启用的 pageBreakBefore 归零
  4. 拒绝在 00_模板原始备份/ 下写入（那是回滚点）

用法：
  python fix_typography.py --list                    # 看待修清单
  python fix_typography.py --dry-run                 # 只预告，不落盘
  python fix_typography.py --apply                   # 真改
  python fix_typography.py --apply --ids 七-1,七-3   # 只改指定编号
  python fix_typography.py --restore --ids 七-1      # 从 00_模板原始备份/ 还原
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
import hashlib
import re
import shutil
import sys
import zipfile
from pathlib import Path

import xml.etree.ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
BASE = REPO
TPL = TEMPLATES
BAK = TEMPLATES_BACKUP
DOC = 'word/document.xml'

# 候选清单：编号 → (分册目录, 文件名)
# 注：这 6 份是 2026-09-16 体检**误报**出来的，复核后确认它们全是 w:val="0"（关闭），
#     真启用数为 0。保留清单以便将来真有需要时可直接用。
TARGETS = {
    '七-1':  ('七、竣工验收分册（政务信息化项目）', '1、项目情况简介.docx'),
    '七-3':  ('七、竣工验收分册（政务信息化项目）', '3、数据治理承诺书.docx'),
    '七-6':  ('七、竣工验收分册（政务信息化项目）', '6、竣工验收申请函.docx'),
    '七-10': ('七、竣工验收分册（政务信息化项目）', '10、验收专家组评审意见.docx'),
    '五-7':  ('五、初步验收分册（政务信息化项目）', '7、试运行评价意见.docx'),
    '六-8':  ('六、竣工验收报告', '8、质保期承诺书.docx'),
}

# 空元素候选：<pfx:pageBreakBefore ...attrs... />
PB_PAT = re.compile(
    rb'<(?P<pfx>[A-Za-z0-9_]+:)?pageBreakBefore(?P<attrs>(?:\s[^>]*?)?)\s*/>')
VAL_PAT = re.compile(rb'w:val\s*=\s*"([^"]*)"')
OFF_VALS = {b'0', b'false', b'off', b'no', b'none'}
# 成对形式（该元素是空标记，理论不出现；出现则拒绝动手）
PB_PAIRED = re.compile(
    rb'<(?P<pfx>[A-Za-z0-9_]+:)?pageBreakBefore(?:\s[^>]*?)?>')


def is_on_span(m: re.Match) -> bool:
    """按 w:val 判定该处是否**真启用**"""
    vm = VAL_PAT.search(m.group('attrs') or b'')
    if vm is None:
        return True                      # 缺省 val = true
    return vm.group(1).strip().lower() not in OFF_VALS


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def w_t_texts(xml: bytes) -> list:
    """取所有 w:t 文本（读文本一律走 ET，不剥标签）"""
    root = ET.fromstring(xml)
    return [t.text or '' for t in root.iter(W + 't')]


def pbb_on_count(xml: bytes) -> int:
    """真启用的 pageBreakBefore 数量（ET 口径，读 w:val）"""
    n = 0
    for el in ET.fromstring(xml).iter(W + 'pageBreakBefore'):
        v = el.get(W + 'val')
        if v is None or v.strip().lower() not in {'0', 'false', 'off', 'no', 'none'}:
            n += 1
    return n


def read_zip(path: Path):
    with zipfile.ZipFile(path) as z:
        return [(it, z.read(it.filename)) for it in z.infolist()]


def write_zip(path: Path, items) -> None:
    """按原 infolist 顺序写回；保留 ZipInfo（日期/压缩方式/属性）"""
    tmp = path.with_suffix('.docx.tmp')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for it, data in items:
            zout.writestr(it, data)
    tmp.replace(path)


def verify(before_items, after_items, expect_removed: int) -> tuple:
    """五重安全网。返回 (是否通过, [消息])"""
    msgs = []
    b = dict((it.filename, d) for it, d in before_items)
    a = dict((it.filename, d) for it, d in after_items)

    if set(b) != set(a):
        return False, ['S4 失败：部件清单变化']

    diff = [n for n in b if n != DOC and b[n] != a[n]]
    if diff:
        return False, ['S4 失败：非目标部件被改动 -> %s' % diff]
    msgs.append('S4 通过：除 %s 外 %d 个部件字节完全一致' % (DOC, len(b) - 1))

    try:
        a_txt = w_t_texts(a[DOC])
    except ET.ParseError as e:
        return False, ['S1 失败：改后 XML 非法 -> %s' % e]
    msgs.append('S1 通过：改后 XML 合法')

    b_txt = w_t_texts(b[DOC])
    if b_txt != a_txt:
        n = sum(1 for x, y in zip(b_txt, a_txt) if x != y)
        return False, ['S2 失败：w:t 文本变了（%d/%d 个不同）' % (n, len(b_txt))]
    msgs.append('S2 通过：%d 个 w:t 文本逐字一致（没碰到一个字）' % len(a_txt))

    left = pbb_on_count(a[DOC])
    if left:
        return False, ['S5 失败：仍残留 %d 处真启用' % left]
    msgs.append('S5 通过：真启用的 pageBreakBefore 已归零')

    removed = pbb_on_count(b[DOC]) - left
    if removed != expect_removed:
        return False, ['S3 失败：删除 %d != 预告 %d' % (removed, expect_removed)]
    msgs.append('S3 通过：删除 %d 处（与预告一致）' % expect_removed)
    return True, msgs


def fix_one(path: Path, dry: bool) -> dict:
    if BAK in path.parents:
        return {'文件': path.name, '状态': '拒绝（备份目录只读）'}

    items = read_zip(path)
    idx = next(i for i, (it, _) in enumerate(items) if it.filename == DOC)
    xml = items[idx][1]

    if PB_PAIRED.search(PB_PAT.sub(b'', xml)):
        return {'文件': path.name, '状态': '拒绝（发现成对形式 pageBreakBefore，需人工看）'}

    spans = [m.span() for m in PB_PAT.finditer(xml) if is_on_span(m)]
    n_all = len(list(PB_PAT.finditer(xml)))
    n_off = n_all - len(spans)

    if not spans:
        return {'文件': path.name,
                '状态': '跳过（真启用 0 处；另有 %d 处 w:val="0" 显式关闭，**不应删**）' % n_off}

    if dry:
        return {'文件': path.name, '状态': '待删 %d 处（另 %d 处 w:val="0" 保持不动）'
                                          % (len(spans), n_off),
                '_sha': sha(xml)[:12]}

    # 倒序删除，避免偏移错位
    new_xml = xml
    for s, e in reversed(spans):
        new_xml = new_xml[:s] + new_xml[e:]
    new_items = list(items)
    new_items[idx] = (items[idx][0], new_xml)

    ok, msgs = verify(items, new_items, len(spans))
    if not ok:
        return {'文件': path.name, '状态': '已回滚（未写盘）', '明细': msgs}

    write_zip(path, new_items)
    return {'文件': path.name, '状态': '已修复', '删除': len(spans),
            '改前字节': len(xml), '改后字节': len(new_xml), '明细': msgs}


def restore(cid: str) -> str:
    d, n = TARGETS[cid]
    src, dst = BAK / d / n, TPL / d / n
    if not src.exists():
        return '  还原失败：备份不存在 %s' % src
    shutil.copy2(src, dst)
    return '  已还原 %s' % n


def main() -> int:
    ap = argparse.ArgumentParser(description='删除真启用的段前分页（部件级，只改 document.xml）')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--restore', action='store_true')
    ap.add_argument('--ids', help='逗号分隔的编号；默认全部')
    a = ap.parse_args()

    ids = [x.strip() for x in a.ids.split(',')] if a.ids else list(TARGETS)
    bad = [x for x in ids if x not in TARGETS]
    if bad:
        print('!! 未知编号：%s' % bad)
        return 1

    if a.restore:
        for cid in ids:
            print(restore(cid))
        return 0

    if a.list or not (a.dry_run or a.apply):
        print('候选清单（注意：复核后确认这 6 份真启用数均为 0）')
        for cid in ids:
            d, n = TARGETS[cid]
            print('  %-6s  %-44s' % (cid, n))
        print('\n用 --dry-run 预演，--apply 落盘，--restore 从备份还原。')
        return 0

    print('=' * 76)
    print('排版修复 · 删除真启用的「段前分页」  %s'
          % ('[预演]' if not a.apply else '[落盘]'))
    print('=' * 76)

    total, fails = 0, []
    for cid in ids:
        d, n = TARGETS[cid]
        p = TPL / d / n
        if not p.exists():
            print('\n  [!] %s  文件不存在' % cid)
            fails.append(cid)
            continue
        r = fix_one(p, dry=not a.apply)
        print('\n  [%s] %s' % (cid, n))
        print('        → %s' % r['状态'])
        for m in r.get('明细', []):
            print('          %s' % m)
        if r['状态'].startswith(('拒绝', '已回滚')):
            fails.append(cid)
        total += r.get('删除', 0)

    print('\n' + '-' * 76)
    if a.apply:
        print('合计删除 %d 处 · 失败 %d 份 %s' % (total, len(fails), fails or ''))
        print('回滚点：assets/templates-backup/')
    else:
        print('预演合计待删 %d 处。加 --apply 落盘。' % total)
    print('=' * 76)
    return 0 if not fails else 2


if __name__ == '__main__':
    sys.exit(main())
