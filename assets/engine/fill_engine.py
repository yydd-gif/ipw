#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验收资料编辑软件 · 填充引擎 v0.1（P0）

职责：读 project.json + 字段字典，把模板里的 {{key}} 替换成实际值，
      输出到工程/工作目录。只读 templates，永不回写。

工程约定：
  - docx 走部件级操作：zip 读入 → 逐 part 改 XML → 按原 infolist() 顺序写回
  - 缺值不填空、保留 {{key}} 原样
  - 日期不自动填
  - 同段落跨 run 合并替换（splice）—— 实测 6 份模板 / 14 处被 Word 拆散

用法：
  python assets/engine/fill_engine.py --demo
  python assets/engine/fill_engine.py --project examples/demo_project.json \\
      --templates assets/templates --out work/demo-fill --json
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from _common import (
    BASE, DICT_PATH, EXAMPLES, REPO, TEMPLATES, WORK,
    TemplateProtectionError, assert_not_template_write, emit_progress,
    emit_result, exit_env, exit_param, iter_templates, result_payload,
)

# ---------------------------------------------------------------- 常量

WNS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'

PART_RE = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')
PH_RE = re.compile(r'\{\{([^{}]+)\}\}')
DECL_RE = re.compile(rb'^<\?xml[^?]*\?>')
DATE_PREFIX = 'date:'
PLACEHOLDER_HINTS = ('#rows', '/rows', 'image:', 'upload:')


def w(tag: str) -> str:
    return '{%s}%s' % (WNS, tag)


def rel(p: Path) -> str:
    for root in (REPO, BASE):
        try:
            return str(p.relative_to(root)).replace('\\', '/')
        except ValueError:
            continue
    return str(p).replace('\\', '/')


def register_ns(raw: bytes) -> None:
    """Keep OOXML prefixes (w:/r:/mc:…) instead of ns0: on serialize."""
    try:
        for _event, (prefix, uri) in ET.iterparse(io.BytesIO(raw), events=['start-ns']):
            if prefix:
                try:
                    ET.register_namespace(prefix, uri)
                except ValueError:
                    pass
    except ET.ParseError:
        pass


# ---------------------------------------------------------------- 字典

def load_dict(path: Path):
    """返回 (字典原文, {key: 字段元数据}, 启用 key 集合)"""
    data = json.loads(path.read_text(encoding='utf-8'))
    meta, enabled = {}, set()
    for g in data.get('groups', []):
        for f in g.get('fields', []):
            meta[f['key']] = f
            enabled.add(f['key'])
    for f in data.get('disabledFields', []):
        meta.setdefault(f['key'], f)
    for f in data.get('removedFields', {}).get('fields', []):
        meta.setdefault(f['key'], f)
    return data, meta, enabled


def build_values(proj: dict, enabled: set, doc_rel: str) -> dict:
    """项目级字段 + 文档级覆盖 → 本次填充的取值表"""
    values = {}
    for k, v in proj.items():
        if k.startswith('_'):
            continue
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        values[k] = v
    overrides = (proj.get('_documents') or {}).get(norm_rel(doc_rel)) or {}
    for k, v in overrides.items():
        if v not in (None, ''):
            values[k] = v
    return values


def values_from_plan(plan: dict, doc_rel: str, fallback: dict) -> dict:
    """Reuse a FillPlan when --plan is given (P1 shape; P0 accepts a flat map)."""
    if not plan:
        return fallback
    key = norm_rel(doc_rel)
    docs = plan.get('documents') or plan.get('docs') or {}
    if key in docs and isinstance(docs[key], dict):
        merged = dict(fallback)
        merged.update({k: v for k, v in docs[key].items() if v not in (None, '')})
        return merged
    if isinstance(plan.get('values'), dict):
        merged = dict(fallback)
        merged.update({k: v for k, v in plan['values'].items() if v not in (None, '')})
        return merged
    return fallback


def norm_rel(p: str) -> str:
    return p.replace('\\', '/').strip('/')


# ---------------------------------------------------------------- 替换

def splice(runs, start: int, end: int, new_text: str) -> None:
    """在 run 序列的全文偏移 [start, end) 处替换为 new_text，其余 run 原样保留.

    CRITICAL: placeholders may be split across adjacent <w:t> nodes in the
    same paragraph (e.g. <w:t>{{</w:t><w:t>weather</w:t><w:t>}}</w:t>).
    Callers MUST pass the full paragraph run list and offsets into the
    concatenated paragraph text — never replace per-run.
    """
    pos, placed = 0, False
    for el in runs:
        txt = el.text or ''
        s, e = pos, pos + len(txt)
        pos = e
        if e <= start or s >= end:
            continue
        head = txt[:max(0, start - s)]
        tail = txt[min(len(txt), end - s):]
        el.text = (head + new_text + tail) if not placed else (head + tail)
        placed = True
        if el.text and el.text != el.text.strip():
            el.set(XML_SPACE, 'preserve')
        elif XML_SPACE in el.attrib:
            del el.attrib[XML_SPACE]


def fill_part(raw: bytes, values: dict, meta: dict, enabled: set,
              records: list, doc_rel: str, part_name: str) -> bytes:
    try:
        register_ns(raw)
        root = ET.fromstring(raw)
    except ET.ParseError:
        return raw

    for p in root.iter(w('p')):
        runs = [el for el in p.iter(w('t'))]
        if not runs:
            continue
        full = ''.join(el.text or '' for el in runs)
        if '{{' not in full:
            continue

        for m in reversed(list(PH_RE.finditer(full))):
            raw_key = m.group(1).strip()
            ctx = full[max(0, m.start() - 18):m.end() + 18].replace('\n', ' ')
            fld = meta.get(raw_key)

            if raw_key.startswith(DATE_PREFIX):
                records.append(rec(doc_rel, part_name, raw_key, '日期·禁用', '', ctx))
                continue
            if any(h in raw_key for h in PLACEHOLDER_HINTS):
                records.append(rec(doc_rel, part_name, raw_key, '特殊占位符·引擎3处理', '', ctx))
                continue

            val = values.get(raw_key)
            if fld is None:
                records.append(rec(doc_rel, part_name, raw_key, '未定义 key', '', ctx))
                continue
            if val in (None, ''):
                records.append(rec(doc_rel, part_name, raw_key, '缺值·保留', '', ctx))
                continue

            splice(runs, m.start(), m.end(), str(val))
            records.append(rec(doc_rel, part_name, raw_key, '已填充',
                               str(val), ctx, fld.get('label', '')))

    body = ET.tostring(root, encoding='utf-8', xml_declaration=False)
    dm = DECL_RE.match(raw)
    decl = dm.group(0) if dm else b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    return decl + body


def rec(doc, part, key, status, value, ctx, label=''):
    return {'文件': doc, '部件': part.replace('word/', '').replace('.xml', ''),
            'key': key, '中文标签': label, '状态': status,
            '替换值': value, '所在处原文': ctx}


# ---------------------------------------------------------------- 文档处理

def process_docx(src: Path, dst: Path, values: dict, meta: dict, enabled: set,
                 records: list, doc_rel: str) -> int:
    assert_not_template_write(dst)
    with zipfile.ZipFile(src) as zin:
        items = zin.infolist()
        contents = {it.filename: zin.read(it.filename) for it in items}

    touched = 0
    for name in list(contents):
        if PART_RE.match(name):
            before = len(records)
            contents[name] = fill_part(contents[name], values, meta, enabled,
                                       records, doc_rel, name)
            touched += sum(1 for r in records[before:] if r['状态'] == '已填充')

    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for it in items:
            zout.writestr(it, contents[it.filename])
    return touched


def scan_residual(root_dir: Path) -> list:
    """扫输出目录里还剩多少 {{}}（逐 <w:t>；左括号从未被切开，不会漏检）"""
    hits = []
    for p in sorted(root_dir.rglob('*.docx')):
        if p.name.startswith('~$'):
            continue
        try:
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    if not PART_RE.match(name):
                        continue
                    try:
                        raw = z.read(name)
                        register_ns(raw)
                        tree = ET.fromstring(raw)
                    except ET.ParseError:
                        continue
                    for t in tree.iter(w('t')):
                        txt = t.text or ''
                        if '{{' in txt:
                            hits.append((rel(p), name, txt.strip()[:40]))
        except zipfile.BadZipFile:
            hits.append((rel(p), '-', '文件损坏'))
    return hits


def empty_out_dir(out_dir: Path) -> None:
    if not out_dir.exists():
        return
    for p in sorted(out_dir.rglob('*'), reverse=True):
        try:
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------- 主流程

def run(project_path: Path, templates: Path, out_dir: Path, report_path: Path,
        as_json: bool = False, plan: dict | None = None, anchor: str = 'off') -> int:
    try:
        assert_not_template_write(out_dir)
        assert_not_template_write(report_path)
    except TemplateProtectionError as e:
        return exit_env(str(e), as_json=as_json, engine='fill')

    if not project_path.exists():
        return exit_param('project.json 不存在：%s' % project_path, as_json, 'fill')
    if not templates.exists():
        return exit_env('模板目录不存在：%s' % templates, as_json, 'fill')

    dict_path = DICT_PATH
    if not dict_path.exists():
        return exit_env('字段字典不存在：%s' % dict_path, as_json, 'fill')

    proj = json.loads(project_path.read_text(encoding='utf-8'))
    data, meta, enabled = load_dict(dict_path)

    docs = list(iter_templates(templates))
    if not docs:
        return exit_env('模板目录里没找到 docx：%s' % templates, as_json, 'fill')

    empty_out_dir(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records, filled_total = [], 0
    total = len(docs)
    for i, src in enumerate(docs, 1):
        doc_rel = str(src.relative_to(templates)).replace('\\', '/')
        values = build_values(proj, enabled, doc_rel)
        if plan is not None:
            values = values_from_plan(plan, doc_rel, values)
        dst = out_dir / src.relative_to(templates)
        n = process_docx(src, dst, values, meta, enabled, records, doc_rel)
        filled_total += n
        emit_progress(i, total, doc_rel)
        if not as_json:
            print('  %-46s 填充 %2d 处' % (doc_rel[:46], n))

    missing = sorted({r['key'] for r in records if r['状态'] == '缺值·保留'})
    unknown = sorted({r['key'] for r in records if r['状态'] == '未定义 key'})
    residual = scan_residual(out_dir)
    date_disabled = sum(1 for r in records if r['状态'] == '日期·禁用')
    missing_n = sum(1 for r in records if r['状态'] == '缺值·保留')

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open('w', newline='', encoding='utf-8-sig') as fh:
        wr = csv.DictWriter(fh, fieldnames=['文件', '部件', 'key', '中文标签',
                                            '状态', '替换值', '所在处原文'])
        wr.writeheader()
        for r in records:
            wr.writerow(r)

    summary = '%d 份 / %d 处已填充 / %d 处残留' % (len(docs), filled_total, len(residual))
    errors = []
    for r in records:
        if r['状态'] in ('缺值·保留', '未定义 key'):
            errors.append({
                'file': r['文件'], 'part': r['部件'], 'key': r['key'],
                'reason': r['状态'], 'level': 'block' if r['状态'] == '未定义 key' else 'warn',
            })
    for path, part, txt in residual:
        errors.append({
            'file': path, 'part': part, 'key': '',
            'reason': '残留 %s' % txt, 'level': 'block',
        })

    payload = result_payload(
        ok=(len(unknown) == 0),
        engine='fill',
        summary=summary,
        stats={
            'docs': len(docs),
            'filled': filled_total,
            'missing': missing_n,
            'residual': len(residual),
            'unknown': len(unknown),
            'dateDisabled': date_disabled,
            'anchor': anchor,
        },
        items=[{'file': r['文件'], 'key': r['key'], 'status': r['状态']}
               for r in records if r['状态'] == '已填充'][:],
        errors=errors,
    )

    if not as_json:
        print('\n' + '=' * 62)
        print('填充引擎 v0.1  报告')
        print('=' * 62)
        print('  字典          %s  (v%s / 启用 %d 字段)' % (
            rel(dict_path), data.get('version'), len(enabled)))
        print('  模板           %d 份' % len(docs))
        print('  输出           %s' % rel(out_dir))
        print('  已填充         %d 处' % filled_total)
        print('  缺值·保留      %d 处  %s' % (
            missing_n,
            ('→ ' + '、'.join(missing[:12]) + ('…' if len(missing) > 12 else '')) if missing else ''))
        print('  未定义 key     %d 个 %s' % (len(unknown), unknown if unknown else ''))
        print('  日期·禁用      %d 处' % date_disabled)
        print('  残留 {{}}      %d 处 %s' % (
            len(residual),
            '（应为 0，未填字段按约定保留→见缺值）' if residual else ''))
        print('  报告           %s' % rel(report_path))
        if anchor == 'on':
            print('  锚点           P0 跳过写入（P2 实现 yz_ 书签 / customXml）')
        print('=' * 62)
        print(summary)

    return emit_result(payload, as_json) if as_json else (0 if payload['ok'] else 1)


def load_plan(path: Path | None) -> dict | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def demo(as_json: bool = False, anchor: str = 'off') -> int:
    demo_path = EXAMPLES / 'demo_project.json'
    if not demo_path.exists():
        return exit_env('找不到示例数据：%s' % demo_path, as_json, 'fill')
    out_dir = WORK / 'demo-fill'
    report = WORK / 'demo-fill-report.csv'
    if not as_json:
        print('>> 试跑：读 %s' % rel(demo_path))
        print('>> 模板：%s' % rel(TEMPLATES))
        print('>> 输出：%s' % rel(out_dir))
        print()
    return run(demo_path, TEMPLATES, out_dir, report, as_json=as_json, anchor=anchor)


def main() -> int:
    ap = argparse.ArgumentParser(description='验收资料填充引擎 v0.1（P0）')
    ap.add_argument('--demo', action='store_true', help='用 examples/demo_project.json 试跑')
    ap.add_argument('--project', type=Path, help='project.json 路径')
    ap.add_argument('--templates', type=Path, default=TEMPLATES, help='模板目录')
    ap.add_argument('--out', type=Path, help='输出工程目录')
    ap.add_argument('--plan', type=Path, help='复用已有 FillPlan（保证与预览一致）')
    ap.add_argument('--anchor', choices=('on', 'off'), default='on',
                    help='是否写入字段锚点（P0 接受参数但不落书签，P2 实现）')
    ap.add_argument('--report', type=Path, help='报告 CSV 路径')
    ap.add_argument('--json', action='store_true', dest='as_json', help='输出契约 JSON')
    a = ap.parse_args()

    try:
        if a.demo:
            return demo(as_json=a.as_json, anchor=a.anchor)
        if not (a.project and a.out):
            return exit_param('需要 --project / --out，或直接 --demo', a.as_json, 'fill')
        rpt = a.report or (a.out.parent / '填充报告.csv')
        plan = load_plan(a.plan) if a.plan else None
        return run(a.project, a.templates, a.out, rpt,
                   as_json=a.as_json, plan=plan, anchor=a.anchor)
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'fill')


if __name__ == '__main__':
    sys.exit(main())
