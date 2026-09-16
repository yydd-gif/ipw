# -*- coding: utf-8 -*-
"""生成目录项「表名缩写」与文档编号字典。

规则：
- 表名缩写 = 表名每个汉字的拼音声母取大写字母（括号内补充说明不参与）
- 是否启用编号 = 模板文件内是否含「文档编号」标签（由脚本扫描模板自动判定）
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import csv
import html
import os
import re
import zipfile

TPL_ROOT = str(TEMPLATES)
OUT = str(WORK / '表名缩写字典.generated.csv')

# 汉字 -> 拼音声母
S = {
    '开': 'K', '工': 'G', '报': 'B', '审': 'S', '表': 'B', '项': 'X', '目': 'M',
    '经': 'J', '理': 'L', '授': 'S', '权': 'Q', '书': 'S', '施': 'S', '组': 'Z',
    '织': 'Z', '方': 'F', '案': 'A', '程': 'C', '令': 'L', '设': 'S', '备': 'B',
    '箱': 'X', '验': 'Y', '收': 'S', '记': 'J', '录': 'L', '安': 'A', '装': 'Z',
    '调': 'D', '试': 'S', '日': 'R', '志': 'Z', '周': 'Z', '月': 'Y', '初': 'C',
    '步': 'B', '运': 'Y', '行': 'X', '申': 'S', '请': 'Q', '评': 'P', '价': 'J',
    '意': 'Y', '见': 'J', '封': 'F', '面': 'M', '基': 'J', '础': 'C', '信': 'X',
    '息': 'X', '拓': 'T', '扑': 'P', '图': 'T', '培': 'P', '训': 'X', '告': 'G',
    '结': 'J', '论': 'L', '质': 'Z', '保': 'B', '期': 'Q', '承': 'C', '诺': 'N',
    '文': 'W', '档': 'D', '移': 'Y', '交': 'J', '情': 'Q', '况': 'K', '简': 'J',
    '介': 'J', '软': 'R', '硬': 'Y', '件': 'J', '配': 'P', '置': 'Z', '清': 'Q',
    '单': 'D', '及': 'J', '数': 'S', '据': 'J', '治': 'Z', '料': 'L', '竣': 'J',
    '预': 'Y', '家': 'J', '核': 'H', '隔': 'G', '页': 'Y', '中': 'Z', '标': 'B',
    '通': 'T', '知': 'Z', '合': 'H', '同': 'T', '补': 'B', '充': 'C', '协': 'X',
    '议': 'Y', '复': 'F', '印': 'Y', '招': 'Z', '控': 'K', '制': 'Z', '计': 'J',
    '纸': 'Z', '隐': 'Y', '蔽': 'B', '资': 'Z', '的': 'D', '维': 'W', '用': 'Y',
    '户': 'H', '册': 'C', '签': 'Q', '明': 'M', '量': 'L', '证': 'Z', '附': 'F',
    '间': 'J', '手': 'S', '变': 'B', '更': 'G', '专': 'Z', '函': 'H', '材': 'C',
}

# (分册, 序号, 目录项名, 是否有模板, 流水号位数)
DATA = [
    ('一、依据分册', 1, '中标通知书', False, 2),
    ('一、依据分册', 2, '合同及补充协议复印件', False, 2),
    ('一、依据分册', 3, '项目招标控制价评审报告及评审清单', False, 2),

    ('二、过程分册', 1, '开工报审表', True, 2),
    ('二、过程分册', 2, '项目经理授权书', True, 2),
    ('二、过程分册', 3, '施工组织方案报审表', True, 2),
    ('二、过程分册', 4, '施工组织方案', True, 2),
    ('二、过程分册', 5, '工程开工令', True, 2),
    ('二、过程分册', 6, '设备及材料（辅材）清单', False, 2),
    ('二、过程分册', 7, '设备开箱验收记录', True, 2),
    ('二、过程分册', 8, '设备安装调试记录表', True, 2),
    ('二、过程分册', 9, '设备签收单', False, 2),
    ('二、过程分册', 10, '施工日志', True, 3),
    ('二、过程分册', 11, '项目周报', True, 3),
    ('二、过程分册', 12, '项目月报', True, 3),
    ('二、过程分册', 13, '质量证明文件', False, 2),

    ('三、图纸分册', 1, '项目设计图纸', False, 2),
    ('三、图纸分册', 2, '项目施工图纸', False, 2),
    ('三、图纸分册', 3, '项目竣工图纸', False, 2),
    ('三、图纸分册', 4, '隐蔽工程资料', False, 2),

    ('四、变更分册', 1, '变更资料', False, 2),

    ('五、初步验收与试运行分册', 1, '试运行申请表', True, 2),
    ('五、初步验收与试运行分册', 2, '运行期间的运维方案', False, 2),
    ('五、初步验收与试运行分册', 3, '培训方案', False, 2),
    ('五、初步验收与试运行分册', 4, '培训记录表', False, 2),
    ('五、初步验收与试运行分册', 5, '用户手册', False, 2),
    ('五、初步验收与试运行分册', 6, '试运行记录表', True, 3),
    ('五、初步验收与试运行分册', 7, '试运行评价意见', True, 2),
    ('五、初步验收与试运行分册', 8, '初步验收申请表', True, 2),
    ('五、初步验收与试运行分册', 9, '初步验收意见', True, 2),

    ('六、竣工验收报告', 1, '封面', True, 2),
    ('六、竣工验收报告', 2, '目录', True, 2),
    ('六、竣工验收报告', 3, '基础信息', True, 2),
    ('六、竣工验收报告', 4, '设备拓扑图', True, 2),
    ('六、竣工验收报告', 5, '培训记录表', True, 2),
    ('六、竣工验收报告', 6, '项目验收申请报告', True, 2),
    ('六、竣工验收报告', 7, '验收结论', True, 2),
    ('六、竣工验收报告', 8, '质保期承诺书', True, 2),
    ('六、竣工验收报告', 9, '文档移交表', True, 2),
    ('六、竣工验收报告', 10, '设备移交表', True, 2),
    ('六、竣工验收报告', 11, '附件', False, 2),

    ('七、竣工验收分册', 1, '项目情况简介', True, 2),
    ('七、竣工验收分册', 2, '项目软硬件配置清单及移交清单', True, 2),
    ('七、竣工验收分册', 3, '数据治理承诺书', True, 2),
    ('七、竣工验收分册', 4, '项目质保方案', False, 2),
    ('七、竣工验收分册', 5, '项目运维方案', False, 2),
    ('七、竣工验收分册', 6, '竣工验收申请函', True, 2),
    ('七、竣工验收分册', 7, '竣工验收申请表', True, 2),
    ('七、竣工验收分册', 8, '竣工验收预审意见表', True, 2),
    ('七、竣工验收分册', 9, '竣工验收评审意见表（个人）', True, 2),
    ('七、竣工验收分册', 10, '验收专家组评审意见', True, 2),
    ('七、竣工验收分册', 11, '竣工验收意见审核表', True, 2),

    ('八、封面页', 1, '验收资料封面', True, 2),
    ('八、封面页', 2, '验收资料目录', True, 2),
    ('八、封面页', 3, '验收资料隔页', True, 2),
]

# 缩写过长时的手工精简建议（key = 分册+序号）
OVERRIDE = {
    ('七、竣工验收分册', 2): 'RYJPZQD',
}


def scan_docno(root=TPL_ROOT):
    """扫描模板，返回 {纯文件名(去序号前缀): 是否含「文档编号」标签}"""
    res = {}
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith('.docx'):
                continue
            z = zipfile.ZipFile(os.path.join(dirpath, fn))
            x = z.read('word/document.xml').decode('utf-8')
            t = re.sub(r'</w:p>', '\n', x)
            t = re.sub(r'<[^>]+>', '', t)
            t = html.unescape(t)
            res[re.sub(r'^\d+、', '', fn[:-5])] = any('文档编号' in l for l in t.split('\n'))
    return res


def to_abbr(name, override_key=None):
    if override_key and override_key in OVERRIDE:
        return OVERRIDE[override_key]
    core = name.split('（')[0].split('(')[0]
    out, miss = [], []
    for ch in core:
        if ch in S:
            out.append(S[ch])
        elif '\u4e00' <= ch <= '\u9fff':
            miss.append(ch)
    return ''.join(out), miss


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    docno = scan_docno()

    def has_label(name):
        core = name.split('（')[0].split('(')[0]
        if core in docno:
            return docno[core]
        return any(h for p, h in docno.items() if p and (p in core or core in p))

    rows, seen, dup, missing = [], {}, [], set()
    for vol, no, name, has_tpl, width in DATA:
        abbr = to_abbr(name, (vol, no))
        if isinstance(abbr, tuple):
            abbr, miss = abbr
            missing.update(miss)
        label = has_label(name)
        note = []
        if not has_tpl:
            note.append('上传项，无模板')
        elif not label:
            note.append('模板内无「文档编号」标签，不编号')
        rows.append([vol, no, name, '有模板' if has_tpl else '上传项', abbr,
                     len(abbr), width, '是' if label else '否',
                     '是' if label else '否', '；'.join(note)])
        if abbr in seen:
            dup.append((abbr, seen[abbr], f'{vol}{no}.{name}'))
        else:
            seen[abbr] = f'{vol}{no}.{name}'

    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分册', '序号', '目录项名', '模板状态', '表名缩写', '缩写长度',
                    '流水号位数', '含编号标签', '启用编号', '备注'])
        w.writerows(rows)

    on = [r for r in rows if r[8] == '是']
    print(f'共 {len(rows)} 项 -> {OUT}')
    print(f'启用编号 {len(on)} 项（模板内含「文档编号」标签）：')
    for r in on:
        print(f"  {r[0][:2]} {r[1]:>2}. {r[2]:<18} {r[4]}")
    print(f'\n未收录汉字: {sorted(missing) if missing else "无"}')
    print(f'缩写重复: {dup if dup else "无"}')
    print(f'缩写超 10 位: {[d[0] + " <- " + d[1] for d in [(a, n) for a, n in
          [(r[4], f"{r[0]}{r[1]}.{r[2]}") for r in rows] if len(a) > 10]]}')


if __name__ == '__main__':
    main()
