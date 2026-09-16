# -*- coding: utf-8 -*-
"""
模板占位符注入脚本 —— 验收资料编辑工具
=====================================
以 规范/模板字段映射表.csv 为唯一依据，对 模版/ 下的 docx 批量注入 {{字段}} 占位符。
保留原格式；占位符统一为灰色加粗（PH 视觉标记，便于人工识别与程序定位）。

用法：
    python inject_placeholders.py            # 预览（dry-run，不改任何文件）
    python inject_placeholders.py --apply    # 备份原模板后原地注入

设计要点：
  1. 定位与扫描脚本完全一致：位置 = 段N（body 顶层第 N 段）/ 表N行M列C（第 N 表第 M 行第 C 格）
  2. 替换走 splice()：按全文偏移在 w:t 序列上替换，未触及的 run 与其格式原样保留
  3. 日期类位置（@manualDate）、子表数据区、上传区、自动生成、固定文本一律跳过
  4. 长句/多字段混排的「段落模板」用 CUSTOM 定向规则，逐条定制，不套通用规则
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
import csv
import sys
import shutil

from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = str(REPO)
TPL = str(TEMPLATES)
BAK = str(TEMPLATES_BACKUP)
MAP = str(MAPPING_CSV)
REPORT = str(WORK / '占位符注入报告.csv')
XMLSPACE = '{http://www.w3.org/XML/1998/namespace}space'

APPLY = '--apply' in sys.argv

# 整块跳过、不做文本注入的类型
SKIP_TYPES = {'子表数据区', '@upload', '@fixedText', '@autoToc', '@autoDivider'}

# ---------------------------------------------------------------------------
# 定向规则表：(模板文件名, 位置) -> [(正则, 替换), ...]
# 用于「段落模板」这类长句多字段混排；空列表 = 确认无需注入（纯手写区）
# 优先级高于通用规则。
# ---------------------------------------------------------------------------
CUSTOM = {
    # —— 七10 验收专家组评审意见：开头综述段 ——
    ('10、验收专家组评审意见.docx', '段3'): [
        (r'对[×X]{2,}单位实施的', '对{{ownerUnit}}实施的'),
        (r'“[×X]{2,}项目”', '“{{projectName}}”'),
        (r'审批文号：[×X]{2,}', '审批文号：{{approvalDocNo}}'),
    ],
    # —— 七3 数据治理承诺书 ——
    ('3、数据治理承诺书.docx', '段6'): [
        (r'在[×X]{2,}项目验收阶段', '在{{projectName}}验收阶段'),
    ],
    ('3、数据治理承诺书.docx', '段7'): [],          # 纯日期承诺期，手写
    # —— 七6 竣工验收申请函：长句综述段 ——
    ('6、竣工验收申请函.docx', '段6'): [
        (r'我单位[×X]{2,}项目', '我单位{{projectName}}'),
        (r'合同金额[×X]{2,}万元', '合同金额{{contractAmount}}万元'),
        (r'建设地点在[×X]{2,}（等地）', '建设地点在{{buildSite}}（等地）'),
        (r'主要建设内容包含：1\.\s*;\s*2\.\s*;\s*3\.\s*……（或等）',
         '主要建设内容包含：{{projectContent}}'),
        (r'承建单位为[×X]{2,}公司', '承建单位为{{constructionUnit}}'),
        (r'监理单位为[×X]{2,}公司', '监理单位为{{supervisionUnit}}'),
        (r'使用单位为[×X]{2,}单位', '使用单位为{{ownerUnit}}'),
    ],
    # —— 七7 竣工验收申请表 ——
    ('7、竣工验收申请表.docx', '表1行9列2'): [
        (r'验收组提出了\s+项整改意见', '验收组提出了{{rectificationCount}}项整改意见'),
    ],
    ('7、竣工验收申请表.docx', '表1行12列2'): [],   # 签字盖章区，手写
    ('7、竣工验收申请表.docx', '表1行13列2'): [],
    ('7、竣工验收申请表.docx', '表1行14列2'): [],
    # —— 二5 工程开工令 ——
    ('5、工程开工令.docx', '表1行1列1'): [
        (r'致：\s+（承建单位）', '致：{{constructionUnit}}（承建单位）'),
        (r'开始对\s+项目施工', '开始对{{projectName}}项目施工'),
    ],
    ('5、工程开工令.docx', '表1行2列1'): [],        # 意见勾选+签章区，手写
    # —— 二2 项目经理授权书 ——
    ('2、项目经理授权书.docx', '段6'): [
        (r'我公司\s+同志', '我公司{{projectManager}}同志'),
        (r'身份证号\s+，', '身份证号{{managerIdCard}}，'),
        (r'为\s+项目的项目经理', '为{{projectName}}项目的项目经理'),
    ],
    # —— 五7 试运行评价意见 ——
    ('7、试运行评价意见.docx', '段3'): [
        # 段首与「方案审核文号」相邻，必须合并成一条：拆两条会重叠，后者被去重丢弃
        (r'^\s+项目（方案审核文号[:：]\s+）',
         '{{projectName}}（方案审核文号：{{approvalDocNo}}）'),
        (r'经过\s+人员使用', '经过{{trialRunUserCount}}人员使用'),
        (r'已处理\s+笔业务', '已处理{{trialRunBusinessCount}}笔业务'),
    ],
    # —— 五8 初步验收申请表：自检综述段 ——
    ('8、初步验收申请表.docx', '表1行5列1'): [
        (r'我单位承建的[×X]{2,}项目', '我单位承建的{{projectName}}'),
        (r'如下：1、[×X]{2,}\s*2、[×X]{2,}', '如下：{{projectContent}}'),
    ],
    # —— 五9 初步验收意见 ——
    ('9、初步验收意见.docx', '表1行10列2'): [],     # 监理意见+签章，手写
    ('9、初步验收意见.docx', '表1行12列2'): [],     # 建设单位意见+签章，手写
    # —— 六6 项目验收申请报告 ——
    ('6、项目验收申请报告.docx', '表1行1列1'): [
        (r'完成了\s+项目，', '完成了{{projectName}}项目，'),
    ],
    # —— 六7 验收结论 ——
    ('7、验收结论.docx', '段2'): [
        (r'表明\s+项目', '表明{{projectName}}项目'),
        (r'合同编号：\s+）', '合同编号：{{contractNo}}）'),
    ],
    # —— 七1 项目情况简介：「三、项目建设内容」下的提示语整段替换 ——
    ('1、项目情况简介.docx', '段12'): [
        (r'对照项目批复文件对已完成和未完成的内容进行说明。', '{{projectContent}}'),
    ],
    # —— 七11 竣工验收意见审核表：「项目主要建设内容」栏提示语整段替换 ——
    ('11、竣工验收意见审核表.docx', '表1行8列2'): [
        (r'对项目建设内容情况进行描述。', '{{projectContent}}'),
    ],
}

# 吞噬后缀：占位文本 [×X]{2,} 之后若是这些词，且目标字段相匹配，则一并吃掉
SWALLOW = ('工程', '项目', '单位', '公司')
SWALLOW_KEYS = ('projectName',)


def parse_keys(field):
    """把映射表的「目标字段」解析成 key 列表"""
    f = (field or '').strip()
    if not f or f == '?':
        return []
    m = re.match(r'^[（(]含\s*(.+?)[)）]$', f)
    if m:
        f = m.group(1)
    m = re.match(r'^段落模板[：:]\s*(.+)$', f)
    if m:
        f = m.group(1)
    if f in ('?', ''):
        return []
    return [x.strip() for x in f.split('/') if x.strip()]


# --------------------------- XML 基础操作 ---------------------------

def top_blocks(body):
    """body 顶层直接子元素中的段落与表格（与扫描脚本计数口径一致）"""
    paras, tbls = [], []
    for el in body.iterchildren():
        if el.tag == qn('w:p'):
            paras.append(el)
        elif el.tag == qn('w:tbl'):
            tbls.append(el)
    return paras, tbls


def ptext(el):
    return ''.join(t.text or '' for t in el.iter(qn('w:t')))


def locate(paras, tbls, pos):
    m = re.match(r'^段(\d+)$', pos)
    if m:
        i = int(m.group(1)) - 1
        return paras[i] if 0 <= i < len(paras) else None
    m = re.match(r'^表(\d+)行(\d+)列(\d+)$', pos)
    if m:
        ti, ri, ci = map(int, m.groups())
        if ti <= len(tbls):
            trs = tbls[ti - 1].findall(qn('w:tr'))
            if ri <= len(trs):
                tcs = trs[ri - 1].findall(qn('w:tc'))
                if ci <= len(tcs):
                    return tcs[ci - 1]
    return None


def splice(el, spans):
    """按全文偏移在 w:t 序列上做区间替换；未触及的 run 与格式原样保留。
       spans: [(start, end, new_text)]，可重叠部分自动丢弃后者。"""
    ts = list(el.iter(qn('w:t')))
    if not ts or not spans:
        return False
    texts = [t.text or '' for t in ts]
    starts, pos = [], 0
    for s in texts:
        starts.append(pos)
        pos += len(s)
    total = pos

    # 去重叠：按 start 排序后过滤
    clean, last_end = [], -1
    for sp in sorted(spans, key=lambda x: x[0]):
        if sp[0] < last_end:
            continue
        clean.append(sp)
        last_end = max(last_end, sp[1])

    changed = False
    for a, b, new in sorted(clean, key=lambda x: -x[0]):
        if a < 0 or b > total or a > b:
            continue
        ia = 0
        for i in range(len(ts)):
            if starts[i] <= a <= starts[i] + len(texts[i]):
                ia = i
        ib = ia
        for i in range(len(ts)):
            if starts[i] < b <= starts[i] + len(texts[i]):
                ib = i
        head = texts[ia][:a - starts[ia]]
        tail = texts[ib][b - starts[ib]:]
        ts[ia].text = head + new + (tail if ib == ia else '')
        ts[ia].set(XMLSPACE, 'preserve')
        if ib != ia:
            for i in range(ia + 1, ib):
                ts[i].text = ''
            ts[ib].text = tail
            ts[ib].set(XMLSPACE, 'preserve')
        for i in range(ia, ib + 1):
            texts[i] = ts[i].text or ''
        p2 = starts[ia]
        for i in range(ia, len(ts)):
            starts[i] = p2
            p2 += len(texts[i])
        changed = True
    return changed


def make_ph_run(text):
    r = OxmlElement('w:r')
    rpr = OxmlElement('w:rPr')
    col = OxmlElement('w:color')
    col.set(qn('w:val'), '808080')
    rpr.append(col)
    rpr.append(OxmlElement('w:b'))
    r.append(rpr)
    t = OxmlElement('w:t')
    t.set(XMLSPACE, 'preserve')
    t.text = text
    r.append(t)
    return r


def append_to_target(el, text):
    """把占位符追加到目标（段落 or 单元格最后一个段落）末尾。
       若目标段落原本只有空白（未填的空单元格），先清掉空白再写占位符，
       避免留下一长串前导空格。
       幂等保护：目标已含同一占位符时不再重复追加（脚本可安全重跑）。"""
    if text in ptext(el):
        return False
    if el.tag == qn('w:p'):
        ps = [el]
    else:
        ps = el.findall(qn('w:p'))
        if not ps:
            p = OxmlElement('w:p')
            el.append(p)
            ps = [p]
    if not ptext(el).strip():
        for t in el.iter(qn('w:t')):
            t.text = ''
    ps[-1].append(make_ph_run(text))
    return True


# --------------------------- 各类 span 计算 ---------------------------

def spans_placeholder(full, keys):
    """占位文本：把 [×X]{2,} 串按出现顺序绑定字段；projectName / *Unit 可吞噬后缀词"""
    spans, idx = [], 0
    for m in re.finditer(r'[×X]{2,}', full):
        if idx >= len(keys):
            break
        key = keys[idx]
        a, b = m.start(), m.end()
        if key in SWALLOW_KEYS or key.endswith('Unit'):
            if full[b:b + 2] in SWALLOW:
                b += 2
        spans.append((a, b, '{{%s}}' % key))
        idx += 1
    return spans


def is_date_gap(full, s, e):
    """空格组是否属于日期留白（前后紧邻 年/月/日）"""
    before = full[max(0, s - 1):s]
    after = full[e:e + 1]
    return ('年' in before or '月' in before or '日' in before
            or '年' in after or '月' in after or '日' in after)


def spans_gaps(full, keys):
    """空白占位 / 前缀插入：连续空格（或下划线）组按顺序绑定字段，日期组跳过"""
    spans, idx = [], 0
    for m in re.finditer(r'[ \u3000_]{2,}', full):
        if idx >= len(keys):
            break
        s, e = m.start(), m.end()
        if is_date_gap(full, s, e):
            continue
        spans.append((s, e, '{{%s}}' % keys[idx]))
        idx += 1
    return spans


def spans_custom(full, rules):
    spans = []
    for pat, repl in rules:
        for m in re.finditer(pat, full):
            new = re.sub(pat, repl, m.group(0))
            if new != m.group(0):
                spans.append((m.start(), m.end(), new))
    return spans


# --------------------------- 主流程 ---------------------------

def main():
    rows = list(csv.DictReader(open(MAP, encoding='utf-8-sig')))
    by = {}
    for r in rows:
        by.setdefault((r['分册'], r['模板文件']), []).append(r)

    if APPLY:
        # 备份保护：原始备份一旦建立就不再覆盖，避免「已注入版」回写覆盖真源
        has_bak = os.path.isdir(BAK) and any(
            f.endswith('.docx') for _, _, fs in os.walk(BAK) for f in fs)
        if has_bak:
            print('原始备份已存在，跳过备份（保护真源）->', BAK)
        else:
            shutil.copytree(TPL, BAK)
            print('已备份原模板 ->', BAK)

    report, stat = [], {}
    warned_custom = []
    locked_files = []

    for (vol, fn), rs in sorted(by.items()):
        path = os.path.join(TPL, vol, fn)
        if not os.path.exists(path):
            print('!! 找不到模板:', path)
            continue

        # 可写性预检：Word/WPS 打开的文件被独占，整份跳过（避免 save 时崩溃中断全局）
        try:
            with open(path, 'r+b'):
                pass
        except PermissionError:
            print('  !! 文件被占用（可能正被 Word 打开），整份跳过:', fn)
            for r in rs:
                report.append([vol, fn, r['位置'], r['类型'], r['目标字段'],
                               '', '', '文件被占用（跳过）'])
            stat['locked'] = stat.get('locked', 0) + len(rs)
            locked_files.append(fn)
            continue

        doc = Document(path)
        paras, tbls = top_blocks(doc.element.body)
        touched = False

        for r in rs:
            typ, field, pos = r['类型'], r['目标字段'], r['位置']
            if field == '@manualDate' or typ in SKIP_TYPES or field.startswith('@'):
                report.append([vol, fn, pos, typ, field, '', '', '跳过（手填/非注入）'])
                stat['skip'] = stat.get('skip', 0) + 1
                continue

            el = locate(paras, tbls, pos)
            if el is None:
                report.append([vol, fn, pos, typ, field, '', '', '定位失败'])
                stat['fail'] = stat.get('fail', 0) + 1
                print('  !! 定位失败', fn, pos)
                continue

            old = ptext(el)
            keys = parse_keys(field)
            rules = CUSTOM.get((fn, pos))

            # 重跑守卫：非定制位置若已含占位符，说明此前注入过，跳过不动
            if rules is None and '{{' in old:
                report.append([vol, fn, pos, typ, field, old[:300], old[:300],
                               '已注入（跳过）'])
                stat['already'] = stat.get('already', 0) + 1
                continue

            if rules is not None:
                spans = spans_custom(old, rules)
                if spans:
                    splice(el, spans)
            elif typ in ('标签留空', '空单元格'):
                if keys:
                    append_to_target(el, '{{%s}}' % keys[0])
            elif typ in ('占位文本', '空白占位', '前缀插入'):
                spans = (spans_placeholder(old, keys) if typ == '占位文本'
                         else spans_gaps(old, keys if typ == '空白占位' else ['projectName']))
                if spans:
                    splice(el, spans)
                else:
                    report.append([vol, fn, pos, typ, field, old[:60], old[:60],
                                   '未命中占位片段'])
                    stat['nomatch'] = stat.get('nomatch', 0) + 1
                    continue
            elif typ == '段落模板':
                # 无定制规则：只登记，不乱改
                report.append([vol, fn, pos, typ, field, old[:60], old[:60], '待定制'])
                stat['pending'] = stat.get('pending', 0) + 1
                warned_custom.append((fn, pos))
                continue
            else:
                report.append([vol, fn, pos, typ, field, old[:60], old[:60], '类型未处理'])
                stat['other'] = stat.get('other', 0) + 1
                continue

            new = ptext(el)
            status = '已注入' if new != old else '无变化'
            if new != old:
                touched = True
            report.append([vol, fn, pos, typ, field, old[:300], new[:300], status])
            stat[status] = stat.get(status, 0) + 1

        if APPLY and touched:
            try:
                doc.save(path)
            except PermissionError:
                print('  !! 保存失败，文件被占用:', fn)
                for rec in report:
                    if rec[0] == vol and rec[1] == fn and rec[7] == '已注入':
                        rec[7] = '文件被占用（未保存）'
                stat['locked'] = stat.get('locked', 0) + 1
                locked_files.append(fn)

    with open(REPORT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['分册', '模板文件', '位置', '类型', '目标字段', '原文', '注入后', '状态'])
        w.writerows(report)

    print()
    print('=' * 60)
    print(('【已写入】' if APPLY else '【dry-run 预览】') + ' 注入统计')
    for k, v in sorted(stat.items(), key=lambda x: -x[1]):
        print(f'  {k:<10} {v}')
    print(f'  报告 -> {REPORT}')
    if warned_custom:
        print()
        print('  待定制段落模板:', len(warned_custom))
        for fn, pos in warned_custom:
            print(f'    - {fn} {pos}')
    if locked_files:
        print()
        print('  ⚠ 以下模板被占用（Word/WPS 打开中），本次未处理，关闭后重跑本脚本即可：')
        for fn in sorted(set(locked_files)):
            print(f'    - {fn}')


if __name__ == '__main__':
    main()
