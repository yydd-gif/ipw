# -*- coding: utf-8 -*-
"""模板字段映射：扫描模板，为每个待填点推断目标字段，输出映射表。

处理策略
- 段落：按关键词匹配字段字典 aliases；含多个占位的长句标记为「段落模板」并列出内含字段
- 表格：先判断每行是「信息行」还是「数据行」；数据行合并为一整段并归给子表 key（如 deviceList）
- 信息行的空单元格：向左找最近的非空标签单元格匹配字段
- 通用属性标签（社会统一信用代码/联系人/联系电话）：再向左找单位标签组合成 key
- 日期：一律不自动填充也不注入占位符（工头 2026-09-12 定）——
        只登记位置，产出 @manualDate，类型记为「手填·日期」，不计入待填点、不参与填充引擎
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import csv
import json
import os
import re
import zipfile
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
# 扫描源必须是「原始模板」而非「当前模板」——
# 当前模板已注入 {{}} 占位符，占位文本/空单元格特征已消失，
# 直接扫当前模板会把映射表打回原形。原始备份一旦生成即永久保留。
ROOT = str(TEMPLATES_BACKUP)
# ⚠ 旧版生成器：不要覆盖 assets/spec 里的正式映射表。输出到 work/。
OUT = str(WORK / '模板字段映射表.generated.csv')

with open(DICT_PATH, encoding='utf-8') as f:
    D = json.load(f)

# 通用属性标签不能当独立别名注册 —— 它们必须与「X单位」组合才能确定归属
# （否则「联系电话」会被无条件当成第一组注册的 ownerPhone）
GENERIC_ATTR = {'联系电话', '联系人', '社会统一信用代码'}

ALIAS = {}
for g in D['groups']:
    for fd in g['fields']:
        ALIAS[fd['label']] = fd['key']
        for a in fd.get('aliases', []):
            if a in GENERIC_ATTR:
                continue
            ALIAS.setdefault(a, fd['key'])

# 单位/主体前缀（用于组合「X单位联系人」这类复合字段）
UNIT_PREFIX = {'建设单位': 'owner', '承建单位': 'construction', '施工单位': 'construction',
               '监理单位': 'supervision', '设计单位': 'design',
               '评审专家': 'expert', '专家': 'expert'}
ATTR_SUFFIX = {'社会统一信用代码': 'CreditCode', '联系人': 'Contact', '联系电话': 'Phone'}
# 「项目」「工程」单独出现时不足以判定为项目名（如「本项目…」「政务信息化项目」），
# 仅在「前缀插入」场景显式使用
GENERIC_ALIAS = {'项目', '工程'}

# ── 日期策略（2026-09-12 工头定：所有日期都不自动填）────────────────
MANUAL_DATE = '@manualDate'
# 日期类标签：原日期字段已从字典移除，这里仅用于识别「这个位置是日期」
DATE_LABELS = ('开工日期', '完工日期', '竣工日期', '评审时间', '移交时间', '创建时间',
               '日期', '时间')
# 整段去掉这些字符后若无实质内容 → 纯日期位置
DATE_STRIP = re.compile(r'[×X\u3000\s年月日\d:：.。、,，（）()－\-至到]')
# 「标签：__」形式的非日期留空（说明文号/编号这类是真字段）
LABEL_BLANK = re.compile(r'(文号|编号|名称|单位|地点|金额|人数|笔数|地址)[：:]\s*[\u3000 ]{2,}')
# 意见/结论类栏位（人工手写正文）
OPINION_TAIL = re.compile(r'(意见|结论|总结|建议|说明)$')

# 表格子表配置：(模板文件名, 表号) -> (子表 key, 前 N 行为信息行)
# N 为 None 时按行特征自动判断信息行/数据行
TABLE_KEY = {
    ('2、项目软硬件配置清单及移交清单.docx', 1): ('deviceList', 3),
    ('2、项目软硬件配置清单及移交清单.docx', 2): ('softwareList', 3),
    ('6、试运行记录.docx', 1): ('trialRunList', 3),
    ('8、设备安装调试记录表.docx', 1): ('testItemList', 3),
    ('9、竣工验收评审意见表（个人）.docx', 1): ('expertScoreList', 3),
    ('2、验收资料目录.docx', 1): ('documentChecklist', 0),
    ('9、文档移交表.docx', 1): ('documentList', 2),
    ('1、验收资料封面.docx', 1): ('volumeList', 1),
}

# 整篇无占位点的模板，补一条说明记录
TEMPLATE_NOTE = {
    '2、目录.docx': ('整篇', '自动生成', '目录由系统按分册结构自动生成，无人工填写项', '@autoToc', '高'),
    '3、验收资料隔页.docx': ('整篇', '自动生成', '隔页由系统按分册自动生成，无人工填写项', '@autoDivider', '高'),
    '8、质保期承诺书.docx': ('整篇', '固定文本', '正文为固定承诺文案，无需填写', '@fixedText', '高'),
}
# 数据行判定：列数 ≥ 此值
DATA_COLS = 5
DATE_ONLY_MAX = 4      # 去壳后剩余字数 ≤ 此值 → 纯日期
SIGN_BLOCK_MAX = 30    # 签章+日期短句的长度上限

# ---------------------------------------------------------------------------
# 显式补充行：标题下的空段、纯提示语栏等脚本无法自动识别的固定位置
# (分册, 模板文件, 位置, 类型, 上下文, 目标字段, 置信度)
# ---------------------------------------------------------------------------
EXTRA_ROWS = [
    # 2026-09-12 清空：原有 6 条（二4 段25/27/29、七1 段10/段12、七11 表1行8列2）
    # 属新增字段 projectBackground / projectGoal / projectContent 的建议落点。
    # 工头明确「模板文档由他手动标注」，故不计入映射表（映射表只反映文档实际待填点）。
    # 落点清单另见 规范/占位符速查表.md 第六节。
]


def norm(s):
    return re.sub(r'\s+', '', s or '')


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(W + 't'))


def all_fields_in(text):
    """长句里能识别出的所有字段（日期不计入，泛化词「项目/工程」不计入）"""
    found = []
    # 「×××项目」「XXX工程」这类带占位符的才认定为项目名（标题行常见）
    if re.search(r'[×X]{2,}\s*(项目|工程)', text):
        found.append('projectName')
    for label, key in ALIAS.items():
        if len(label) < 2 or label in GENERIC_ALIAS:
            continue
        if label in text and key not in found:
            found.append(key)
    return found


def manual_type(txt):
    """手填位置细分：日期留白 vs 意见/签章正文"""
    s = norm(txt)
    if OPINION_TAIL.search(s.rstrip('：:')):
        return '手填·正文'
    if len(s) > 15 and re.search(r'意见|结论|总结|签字|签章|盖章|印章', s):
        return '手填·正文'
    return '手填·日期'


def is_date_only(t):
    """去掉日期壳后没有实质内容 → 纯日期位置"""
    return len(DATE_STRIP.sub('', t)) <= DATE_ONLY_MAX


def is_sign_block(t):
    """签章/落款这类短句：整格人工手写（含日期）"""
    s = norm(t)
    return bool(re.search(r'年\s*月\s*日', s)) and bool(re.search(r'签章|签字|盖章|日期', s)) \
        and len(s) <= SIGN_BLOCK_MAX


def split_date(text):
    """返回 (是否含日期留白, 去掉日期留白后的剩余文本)"""
    has = bool(re.search(r'[×X\u3000\s]*年[×X\u3000\s]*月[×X\u3000\s]*日', norm(text)))
    rest = re.sub(r'[×X\u3000\s]*年[×X\u3000\s]*月[×X\u3000\s]*日', '', text).strip()
    rest = rest.strip('，,。、:：（）()　 ')
    return has, rest


def has_label_blank(text):
    return bool(LABEL_BLANK.search(text))


def is_opinion_box(rest):
    """「监理单位意见：」这类意见栏，人工手写"""
    s = norm(rest)
    return len(s) <= 12 and bool(OPINION_TAIL.search(s))


def date_verdict(txt):
    """含日期的文本如何处置：
    'manual'    → 手填，不注入
    'continue'  → 放行给后续分支（日期中夹着真字段）
    None        → 不含日期
    """
    has, rest = split_date(txt)
    if not has:
        return None, rest
    if is_date_only(txt) or is_sign_block(txt):
        return 'manual', rest
    if has_label_blank(txt):
        return 'continue', rest
    if is_opinion_box(rest):
        return 'manual', rest
    if re.search(r'[×X]{2,}', txt):
        return 'continue', rest
    # 日期 + 正文，正文里已无具体字段 → 手填
    if not all_fields_in(norm(rest)):
        return 'manual', rest
    return 'continue', rest


def guess_cell(cells, idx):
    label = ''
    for j in range(idx - 1, -1, -1):
        if norm(cells[j]):
            label = norm(cells[j])
            break
    if not label:
        return '', '低'
    if label in ALIAS:
        return ALIAS[label], '高'
    if any(d in label for d in DATE_LABELS):
        return MANUAL_DATE, '高'
    hit = next((s for s in ATTR_SUFFIX if label.endswith(s)), None)
    if hit:
        suffix = ATTR_SUFFIX[hit]
        # 标签自身含主体（如「监理单位联系人」「评审专家姓名」）→ 直接组合
        for u, p in UNIT_PREFIX.items():
            if u in label:
                return p + suffix, '高'
        # 否则向左一直找主体：跳过空格、同类属性标签与中间栏（如「项目负责人」），
        # 命中最近的一个单位/专家标签即组合
        for j in range(idx - 1, -1, -1):
            cj = norm(cells[j])
            if not cj or cj.endswith(hit):
                continue
            for u, p in UNIT_PREFIX.items():
                if u in cj:
                    return p + suffix, '高'
    for k, v in ALIAS.items():
        if k and len(k) >= 2 and k in label:
            return v, '中'
    if re.search(r'日期|时间', label):
        return MANUAL_DATE, '中'
    return '', '低'


def special(text):
    """特殊句式 -> (key, 置信度)；不匹配返回 None"""
    t = norm(text)
    if re.match(r'^[×X]{2}单位$', t) or re.match(r'^[×X]{2}（单位(盖章|名称)）$', t):
        return 'constructionUnit', '高'
    if re.match(r'^[×X]{2}年[×X]{2}月[×X]{2}日$', t) or re.match(r'^[×X\s]*年[×X\s]*月[×X\s]*日$', t):
        return MANUAL_DATE, '高'
    if re.match(r'^\d+\.[×X]{2,}', t):
        return 'expertReviewItems', '高'
    if '致：' in t:
        m = re.search(r'[（(]([^）)]*)[）)]', t)
        if m:
            keys = [UNIT_PREFIX[u] + 'Unit' for u in UNIT_PREFIX if u in m.group(1)]
            if keys:
                return '/'.join(keys), '高'
    if is_sign_block(t):
        return MANUAL_DATE, '高'
    # 落款处的联系方式（承诺书/申请函等由承建方出具，主体默认承建单位）
    if '联系人' in t and ('联系电话' in t or '手机' in t):
        return 'constructionContact/constructionPhone', '中'
    return None


def main():
    rows = []
    for dirpath, _, files in os.walk(ROOT):
        for fn in sorted(files):
            if not fn.endswith('.docx') or fn.startswith('~$'):
                continue
            path = os.path.join(dirpath, fn)
            vol = os.path.relpath(path, ROOT).split(os.sep)[0]
            z = zipfile.ZipFile(path)
            body = ET.fromstring(z.read('word/document.xml')).find(W + 'body')

            pi = ti = 0
            if fn in TEMPLATE_NOTE:
                loc, typ, desc, key, conf = TEMPLATE_NOTE[fn]
                rows.append([vol, fn, loc, typ, desc, key, conf])
            for el in body:
                if el.tag == W + 'p':
                    pi += 1
                    txt = ptext(el).strip()
                    if not txt:
                        continue
                    t = norm(txt)
                    m_lab = re.match(r'^(.{2,12})[：:]\s*$', t)
                    blanks = re.findall(r'[\u3000 ]{6,}', txt)
                    keys4 = all_fields_in(t) if blanks else []
                    verdict, rest = date_verdict(txt)
                    if not (re.search(r'[×X]{2,}', txt) or '文档编号' in t or m_lab
                            or t in ('项目', '工程') or verdict
                            or '上传' in t or keys4):
                        continue
                    if '上传附件' in t or '上传设备签收表' in t:
                        rows.append([vol, fn, f'段{pi}', '上传区', txt[:60], '@upload', '高'])
                        continue
                    if m_lab:
                        lab = m_lab.group(1)
                        if any(d in lab for d in DATE_LABELS):
                            rows.append([vol, fn, f'段{pi}', '手填·日期', txt[:60], MANUAL_DATE, '高'])
                            continue
                        key = ALIAS.get(lab)
                        if not key:
                            continue
                        rows.append([vol, fn, f'段{pi}', '标签留空', txt[:60], key, '高'])
                        continue
                    if t in ('项目', '工程'):
                        rows.append([vol, fn, f'段{pi}', '前缀插入', txt[:60], 'projectName', '中'])
                        continue
                    if '文档编号' in t:
                        rows.append([vol, fn, f'段{pi}', '文档编号', txt[:60], 'docNo', '高'])
                        continue
                    # 日期位置：纯日期/签章块/无其它字段 → 只登记手填
                    if verdict == 'manual':
                        rows.append([vol, fn, f'段{pi}', manual_type(txt), txt[:60], MANUAL_DATE, '高'])
                        continue
                    if blanks and keys4:
                        rows.append([vol, fn, f'段{pi}', '空白占位', txt[:60],
                                     keys4[0] if len(keys4) == 1 else '（含 ' + '/'.join(keys4) + '）', '中'])
                        continue
                    fs = all_fields_in(t)
                    sp = special(txt)
                    if sp:
                        typ = manual_type(txt) if sp[0] == MANUAL_DATE else '占位文本'
                        rows.append([vol, fn, f'段{pi}', typ, txt[:60], sp[0], '高'])
                        continue
                    n_ph = len(re.findall(r'[×X]{2,}', t))
                    if n_ph >= 2 and len(txt) > 25:
                        rows.append([vol, fn, f'段{pi}', '段落模板', txt[:60],
                                     '（含 ' + '/'.join(fs or ['?']) + '）', '中'])
                    elif fs:
                        rows.append([vol, fn, f'段{pi}', '占位文本', txt[:60], fs[0], '中'])
                    else:
                        rows.append([vol, fn, f'段{pi}', '占位文本', txt[:60], '', '低'])

                elif el.tag == W + 'tbl':
                    ti += 1
                    tcfg = TABLE_KEY.get((fn, ti))
                    subkey = tcfg[0] if tcfg else '待指定子表'
                    n_info = tcfg[1] if tcfg else None
                    all_rows = []
                    for tr in el.findall(W + 'tr'):
                        all_rows.append([''.join(ptext(p) for p in tc.findall(W + 'p')).strip()
                                         for tc in tr.findall(W + 'tc')])

                    data_start = None
                    for ri, cells in enumerate(all_rows, 1):
                        ncol = len(cells)
                        nfilled = sum(1 for c in cells if norm(c))
                        if n_info is not None:
                            is_data = ri > n_info
                        else:
                            is_data = (ncol >= DATA_COLS and nfilled <= 2)
                        if is_data:
                            if data_start is None:
                                data_start = ri
                            continue
                        if data_start is not None:
                            rows.append([vol, fn, f'表{ti}行{data_start}-{ri - 1}', '子表数据区',
                                         '动态数据区（行数按实际增删）', subkey,
                                         '高' if tcfg else '低'])
                            data_start = None
                        for ci, c in enumerate(cells, 1):
                            if not norm(c):
                                key, conf = guess_cell(cells, ci - 1)
                                if key == MANUAL_DATE:
                                    rows.append([vol, fn, f'表{ti}行{ri}列{ci}', '手填·日期',
                                                 ' | '.join(cells)[:60], MANUAL_DATE, '高'])
                                    continue
                                if not key and sum(1 for x in cells if norm(x)) <= 1:
                                    continue
                                rows.append([vol, fn, f'表{ti}行{ri}列{ci}', '空单元格',
                                             ' | '.join(cells)[:60], key, conf])
                            elif re.search(r'[×X]{2,}', c):
                                sp = special(c)
                                if sp:
                                    key, conf = sp
                                elif len(c) > 25 and len(re.findall(r'[×X]{2,}', c)) >= 2:
                                    key = '（段落模板：' + '/'.join(all_fields_in(norm(c)) or ['?']) + '）'
                                    conf = '中'
                                else:
                                    key, conf = guess_cell(cells, ci - 1)
                                typ = manual_type(c) if key == MANUAL_DATE else '占位文本'
                                rows.append([vol, fn, f'表{ti}行{ri}列{ci}', typ,
                                             c[:60], key, conf])
                            else:
                                verdict, rest = date_verdict(c)
                                if verdict is None:
                                    continue
                                if verdict == 'manual':
                                    rows.append([vol, fn, f'表{ti}行{ri}列{ci}', manual_type(c),
                                                 c[:60], MANUAL_DATE, '高'])
                                    continue
                                rf = all_fields_in(norm(rest))
                                if rf:
                                    rows.append([vol, fn, f'表{ti}行{ri}列{ci}', '段落模板',
                                                 c[:60], '（含 ' + '/'.join(rf) + '）', '中'])
                                else:
                                    rows.append([vol, fn, f'表{ti}行{ri}列{ci}', manual_type(c),
                                                 c[:60], MANUAL_DATE, '高'])
                    if data_start is not None:
                        rows.append([vol, fn, f'表{ti}行{data_start}-{len(all_rows)}', '子表数据区',
                                     '动态数据区（行数按实际增删）', subkey,
                                     '高' if tcfg else '低'])

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # 显式补充行：标题下的空段、提示语栏等脚本无法自动识别的固定位置
    have = {(r[0], r[1], r[2]) for r in rows}
    for ex in EXTRA_ROWS:
        if (ex[0], ex[1], ex[2]) not in have:
            rows.append(list(ex))
    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分册', '模板文件', '位置', '类型', '上下文', '目标字段', '置信度'])
        w.writerows(rows)

    manual = [r for r in rows if r[5] == MANUAL_DATE]
    work = [r for r in rows if r[5] != MANUAL_DATE]
    hi = sum(1 for r in work if r[6] == '高')
    mid = sum(1 for r in work if r[6] == '中')
    lo = sum(1 for r in work if r[6] == '低')
    print(f'共 {len(rows)} 条记录 -> {OUT}')
    print(f'  需填充 {len(work)} 条（高 {hi} / 中 {mid} / 低 {lo}）')
    print(f'  手填·日期 {len(manual)} 条（不注入占位符，人工手写）\n')
    print('=== 需人工确认（低置信） ===')
    for r in work:
        if r[6] == '低':
            print(f'  {r[1][:20]:<22}{r[2]:<14}{r[3]:<10}{r[4][:42]}')


if __name__ == '__main__':
    main()
