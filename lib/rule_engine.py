# -*- coding: utf-8 -*-
"""填数规则引擎 · 9 类规则 / FillPlan（数据与规则规格.md §4 / §6）.

引擎不存状态：读入 project.json + 字典 + 规则 → 算出 FillPlan → 退出。
同一输入两次运行，FillPlan 逐字节一致（无墙钟、无随机）。
"""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from lib.date_window import Window, in_window, parse_iso_date
from lib.field_dict import FieldDict, FieldSpec, load_field_dict
from lib.yaml_lite import YamlLiteError, load_yaml_file

ENGINE_VERSION = '1.0.0'
PLAN_VERSION = '1.0'
RULE_TYPES = frozenset({
    'direct', 'alias', 'format', 'compose',
    'aggregate', 'statistic', 'count', 'reference', 'condition',
})
SOURCES = frozenset({'S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6'})
CN_VOL = '一二三四五六七八'
TABLE_ASSET_MAP = {
    'deviceList': ('devices',),
    'softwareList': ('softwares',),
    'testItemList': ('testItems', 'testItemList'),
    'trialRunList': ('trialRuns', 'trialRunList'),
    'expertScoreList': ('expertScores', 'expertScoreList'),
    'documentList': ('documents', 'documentList'),
    'documentChecklist': ('documentChecklist',),
    'volumeList': ('volumes', 'volumeList'),
}


class RuleLoadError(ValueError):
    """规则文件语法错误 / 引用未知字段 / 命中 S6 封闭集. CLI maps this to exit 3."""


@dataclass
class Rule:
    raw: dict
    id: str
    target: str
    type: str
    source: str
    on: List[str]
    overridable: bool = True
    confirm: bool = False

    def get(self, key, default=None):
        return self.raw.get(key, default)


@dataclass
class RuleSet:
    path: Path
    raw: dict
    version: str
    policies: dict
    rules: List[Rule]
    tables: dict
    counters: dict
    manual_fields: set
    manual_tables: set
    manual_patterns: List[re.Pattern]
    by_target: Dict[str, List[Rule]] = field(default_factory=dict)
    by_id: Dict[str, Rule] = field(default_factory=dict)
    window: Optional[Window] = None


@dataclass
class CatalogItem:
    item_id: str
    volume: str
    volume_seq: int
    seq: int
    name: str
    abbr: str
    digits: int
    numbered: bool
    importance: str = '普通项'  # 重要项 / 普通项 / 一般项（软件目录.docx 元数据，不成册依据）
    inclusion: str = 'optional'  # required / optional（字典「收录」列）
    required: bool = False      # inclusion==required 元数据；ADR-22 不据此自动建表


@dataclass
class Catalog:
    items: List[CatalogItem]
    by_id: Dict[str, CatalogItem]
    volume_alias: Dict[str, str]  # any name -> standard volume
    volume_seq: Dict[str, int]


@dataclass
class DocCtx:
    doc_id: str
    item_id: str
    rel_path: str
    overrides: dict
    is_project: bool
    abbr: str = ''
    numbered: bool = False
    digits: int = 2


# ---------------------------------------------------------------- load

def load_rule_set(path: Path | str, field_dict: FieldDict) -> RuleSet:
    p = Path(path)
    if not p.exists():
        raise RuleLoadError('填数规则不存在：%s' % p)
    try:
        raw = load_yaml_file(p)
    except YamlLiteError as e:
        raise RuleLoadError('填数规则语法错误：%s' % e) from e
    if not isinstance(raw, dict):
        raise RuleLoadError('填数规则顶层必须是 mapping')

    version = str(raw.get('version') or '')
    if not version:
        raise RuleLoadError('填数规则缺少 version')
    policies = raw.get('policies') or {}
    if not isinstance(policies, dict):
        raise RuleLoadError('policies 必须是 mapping')
    if policies.get('dateAutoFill') is True:
        raise RuleLoadError(
            'policies.dateAutoFill=true 被拒绝（日期不自动填；改 true 必须走变更记录）')

    mf = policies.get('manualFields') or {}
    if isinstance(mf, list):
        # v2.0 草案形态；正式规格是 mapping
        raise RuleLoadError('policies.manualFields 必须是 mapping（fields/tables/patterns）')
    manual_fields = set(mf.get('fields') or [])
    manual_tables = set(mf.get('tables') or [])
    patterns = []
    for pat in mf.get('patterns') or []:
        try:
            patterns.append(re.compile(str(pat)))
        except re.error as e:
            raise RuleLoadError('manualFields.patterns 非法：%s (%s)' % (pat, e)) from e

    rules_raw = raw.get('rules')
    if rules_raw is None:
        rules_raw = []
    if not isinstance(rules_raw, list):
        raise RuleLoadError('rules 必须是 list')

    rules: List[Rule] = []
    by_id: Dict[str, Rule] = {}
    by_target: Dict[str, List[Rule]] = {}
    for i, item in enumerate(rules_raw):
        if not isinstance(item, dict):
            raise RuleLoadError('rules[%d] 必须是 mapping' % i)
        rule = _parse_rule(item, i)
        _validate_rule(rule, field_dict, manual_fields, manual_tables, patterns)
        if rule.id in by_id:
            raise RuleLoadError('重复规则 id：%s' % rule.id)
        by_id[rule.id] = rule
        by_target.setdefault(rule.target, []).append(rule)
        rules.append(rule)

    tables = raw.get('tables') or {}
    if not isinstance(tables, dict):
        raise RuleLoadError('tables 必须是 mapping')
    counters = raw.get('counters') or {}
    if not isinstance(counters, dict):
        raise RuleLoadError('counters 必须是 mapping')

    return RuleSet(
        path=p, raw=raw, version=version, policies=policies,
        rules=rules, tables=tables, counters=counters,
        manual_fields=manual_fields, manual_tables=manual_tables,
        manual_patterns=patterns, by_target=by_target, by_id=by_id,
    )


def _parse_rule(item: dict, idx: int) -> Rule:
    rid = item.get('id')
    rtype = item.get('type')
    source = item.get('source')
    on = item.get('on')
    target = item.get('target')
    if not rid:
        raise RuleLoadError('rules[%d] 缺少 id' % idx)
    if rtype not in RULE_TYPES:
        raise RuleLoadError('规则 %s：type %r 不在 9 类之内' % (rid, rtype))
    if source not in SOURCES:
        raise RuleLoadError('规则 %s：source %r 不是 S0–S6' % (rid, source))
    if not isinstance(on, list) or not on:
        raise RuleLoadError('规则 %s：on 必须是非空 list' % rid)
    if not target:
        # condition 可用 then/else 的 $field.attr 推断
        target = _infer_target(item)
        if not target:
            raise RuleLoadError('规则 %s：缺少 target' % rid)
    overridable = item.get('overridable')
    if overridable is None:
        overridable = True
    return Rule(
        raw=item, id=str(rid), target=str(target), type=str(rtype),
        source=str(source), on=[str(x) for x in on],
        overridable=bool(overridable),
        confirm=bool(item.get('confirm')),
    )


def _infer_target(item: dict) -> str:
    for blob in (item.get('then'), item.get('else')):
        if not isinstance(blob, dict):
            continue
        for k in blob:
            k = str(k)
            if k.startswith('$'):
                return k[1:].split('.', 1)[0]
            if '.' in k:
                return k.split('.', 1)[0]
    return ''


def _validate_rule(rule: Rule, fd: FieldDict,
                   manual_fields: set, manual_tables: set,
                   patterns: Sequence[re.Pattern]) -> None:
    target = rule.target
    if _hits_manual(target, manual_fields, patterns):
        raise RuleLoadError(
            '规则 %s：target=%s 命中 policies.manualFields（S6 封闭集，日期/手填不得自动填）'
            % (rule.id, target))
    if target in fd.tables and target in manual_tables:
        raise RuleLoadError(
            '规则 %s：target 子表 %s 命中 manualFields.tables' % (rule.id, target))

    required = {
        'direct': ('from',),
        'alias': (),
        'format': ('from', 'transform'),
        'compose': ('parts', 'join'),
        'aggregate': (),
        'statistic': (),
        'count': (),
        'reference': ('from',),
        'condition': ('when', 'then', 'else'),
    }[rule.type]
    for k in required:
        if k not in rule.raw:
            raise RuleLoadError('规则 %s：type=%s 缺少 %s' % (rule.id, rule.type, k))
    if rule.type == 'alias':
        if 'from' not in rule.raw and 'candidates' not in rule.raw:
            raise RuleLoadError('规则 %s：alias 需要 from 或 candidates[]' % rule.id)
        if not rule.confirm:
            raise RuleLoadError('规则 %s：alias 必须 confirm: true（S5 不得静默落库）' % rule.id)
    if rule.type == 'statistic':
        transform = rule.get('transform') or {}
        if not isinstance(transform, dict) or not transform.get('mode'):
            raise RuleLoadError('规则 %s：statistic 需要 transform.mode' % rule.id)
    if rule.type in ('aggregate', 'statistic', 'count'):
        from_ = rule.get('from')
        if not isinstance(from_, dict) or not from_.get('docs'):
            raise RuleLoadError('规则 %s：需要 from.docs' % rule.id)
        docs = from_['docs']
        if not isinstance(docs, dict):
            raise RuleLoadError('规则 %s：from.docs 必须是 mapping' % rule.id)
        if not any(k in docs for k in ('itemId', 'volume', 'tag')):
            raise RuleLoadError('规则 %s：from.docs 需要 itemId / volume / tag 三选一' % rule.id)
        if rule.type == 'count' and not (rule.get('transform') or {}).get('mode'):
            raise RuleLoadError('规则 %s：count 需要 transform.mode' % rule.id)
        if rule.type == 'aggregate' and not from_.get('field'):
            raise RuleLoadError('规则 %s：aggregate 需要 from.field' % rule.id)

    for ref in _iter_field_refs(rule):
        if ref not in fd.known_keys:
            raise RuleLoadError(
                '规则 %s：引用了字典里不存在的 key %r（加载期失败）' % (rule.id, ref))
        if _hits_manual(ref, manual_fields, patterns) and ref != rule.target:
            # from.docs 不得引用 manualFields
            if rule.type in ('aggregate', 'statistic', 'count'):
                raise RuleLoadError(
                    '规则 %s：from.docs 引用了 manualFields 字段 %r' % (rule.id, ref))
        if ref in manual_tables:
            raise RuleLoadError(
                '规则 %s：引用了 manualFields.tables %r' % (rule.id, ref))


def _hits_manual(key: str, fields: set, patterns: Sequence[re.Pattern]) -> bool:
    if key in fields:
        return True
    return any(p.search(key) for p in patterns)


def _iter_field_refs(rule: Rule) -> Iterable[str]:
    yield rule.target
    from_ = rule.get('from')
    yield from _refs_in_from(from_)
    for part in rule.get('parts') or []:
        yield from _refs_in_from(part)
    when = rule.get('when') or {}
    if isinstance(when, dict):
        for v in when.values():
            if isinstance(v, list):
                for item in v:
                    yield from _refs_in_from(item)
            else:
                yield from _refs_in_from(v)
    for blob in (rule.get('then'), rule.get('else')):
        if isinstance(blob, dict):
            for k in blob:
                ks = str(k)
                if ks.startswith('$'):
                    yield ks[1:].split('.', 1)[0]
    for c in rule.get('candidates') or []:
        if isinstance(c, str) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', c):
            yield c
    table = None
    if isinstance(from_, dict):
        table = from_.get('table')
    if table:
        yield str(table)


def _refs_in_from(from_) -> Iterable[str]:
    if isinstance(from_, str):
        if from_.startswith('project.') or from_.startswith('doc.'):
            yield from_.split('.', 1)[1]
        return
    if isinstance(from_, dict):
        if from_.get('field'):
            yield str(from_['field'])
        docs = from_.get('docs')
        if isinstance(docs, dict) and docs.get('field'):
            yield str(docs['field'])


# ---------------------------------------------------------------- catalog

def load_catalog(abbr_path: Path, alias_path: Path | None = None) -> Catalog:
    volume_alias: Dict[str, str] = {}
    volume_seq: Dict[str, int] = {}
    if alias_path and Path(alias_path).exists():
        with Path(alias_path).open(encoding='utf-8-sig', newline='') as fh:
            for row in csv.DictReader(fh):
                std = (row.get('标准名') or '').strip()
                alias = (row.get('别名') or '').strip()
                seq_s = (row.get('分册序') or '').strip()
                try:
                    seq = int(seq_s)
                except ValueError:
                    seq = 0
                if std:
                    volume_alias[std] = std
                    if seq:
                        volume_seq[std] = seq
                if alias:
                    volume_alias[alias] = std or alias
                    if seq:
                        volume_seq[alias] = seq
                        volume_seq[std or alias] = seq

    from lib.catalog_flags import is_upload_status, resolve_inclusion

    items: List[CatalogItem] = []
    by_id: Dict[str, CatalogItem] = {}
    if Path(abbr_path).exists():
        with Path(abbr_path).open(encoding='utf-8-sig', newline='') as fh:
            for row in csv.DictReader(fh):
                vol_raw = (row.get('分册') or '').strip()
                std = volume_alias.get(vol_raw, vol_raw)
                vseq = volume_seq.get(vol_raw) or volume_seq.get(std) or _guess_vol_seq(vol_raw)
                try:
                    seq = int(row.get('序号') or 0)
                except ValueError:
                    seq = 0
                try:
                    digits = int(row.get('流水号位数') or 2)
                except ValueError:
                    digits = 2
                cn = CN_VOL[vseq - 1] if 1 <= vseq <= 8 else '?'
                item_id = '%s-%02d' % (cn, seq)
                numbered = (row.get('启用编号') or '').strip() == '是'
                inclusion = resolve_inclusion(
                    item_id=item_id,
                    csv_value=row.get('收录') or '',
                    is_upload=is_upload_status(row.get('模板状态') or ''),
                )
                it = CatalogItem(
                    item_id=item_id, volume=std or vol_raw, volume_seq=vseq,
                    seq=seq, name=(row.get('目录项名') or '').strip(),
                    abbr=(row.get('表名缩写') or '').strip(),
                    digits=digits, numbered=numbered,
                    inclusion=inclusion,
                    required=(inclusion == 'required'),
                )
                items.append(it)
                by_id[item_id] = it
    catalog = Catalog(items=items, by_id=by_id, volume_alias=volume_alias,
                      volume_seq=volume_seq)
    _apply_catalog_importance(catalog, abbr_path)
    return catalog


def _apply_catalog_importance(catalog: Catalog, abbr_path: Path) -> None:
    """Merge 软件目录.docx 重要项/普通项 onto CSV rows as metadata only."""
    from lib.catalog_flags import apply_importance, catalog_docx_path, parse_software_catalog
    docx = catalog_docx_path(abbr_path)
    if not docx:
        return
    flags = parse_software_catalog(
        docx, volume_alias=catalog.volume_alias, volume_seq=catalog.volume_seq)
    apply_importance(catalog.items, flags)


def _guess_vol_seq(name: str) -> int:
    if not name:
        return 0
    ch = name[0]
    if ch in CN_VOL:
        return CN_VOL.index(ch) + 1
    return 0


def normalize_item_id(value: str) -> str:
    s = (value or '').strip()
    m = re.match(r'^([%s])-(\d+)$' % CN_VOL, s)
    if m:
        return '%s-%02d' % (m.group(1), int(m.group(2)))
    return s


def infer_item_id(rel_path: str, catalog: Catalog) -> str:
    parts = rel_path.replace('\\', '/').strip('/').split('/')
    if not parts:
        return ''
    vol_raw = parts[0]
    std = catalog.volume_alias.get(vol_raw, vol_raw)
    vseq = catalog.volume_seq.get(vol_raw) or catalog.volume_seq.get(std) or _guess_vol_seq(vol_raw)
    seq = 0
    if len(parts) > 1:
        m = re.match(r'^(\d+)、', parts[1])
        if m:
            seq = int(m.group(1))
    if vseq and seq:
        return '%s-%02d' % (CN_VOL[vseq - 1], seq)
    return ''


# ---------------------------------------------------------------- FillPlan

def dumps_fillplan(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def resolve_fillplan(project: dict, field_dict: FieldDict, rule_set: RuleSet,
                     catalog: Catalog | None = None,
                     only: str = '',
                     window: Optional[Window] = None) -> dict:
    catalog = catalog or Catalog(items=[], by_id={}, volume_alias={}, volume_seq={})
    if window is not None:
        rule_set.window = window
    only_id = normalize_item_id(only) if only else ''
    attrs = _eval_conditions(project, rule_set)
    all_docs = _collect_docs(project, catalog)
    docs = [d for d in all_docs if d.item_id == only_id] if only_id else all_docs

    fields_map = _resolve_doc(
        DocCtx(doc_id='_project', item_id='', rel_path='', overrides={},
               is_project=True),
        project, field_dict, rule_set, catalog, attrs, docs_all=all_docs,
    )

    docs_out: Dict[str, Any] = {}
    documents: Dict[str, Any] = {}
    for doc in docs:
        values = _resolve_doc(doc, project, field_dict, rule_set, catalog, attrs,
                              docs_all=all_docs)
        missing = sorted(k for k, sl in values.items() if sl.get('state') == 'missing')
        derived = sorted(k for k, sl in values.items() if sl.get('state') == 'derived')
        conflicts = sl_conflicts(values)
        rec = {
            'itemId': doc.item_id,
            'relPath': doc.rel_path,
            'values': {k: _public_slot(values[k]) for k in sorted(values)},
            'conflicts': conflicts,
            'missing': missing,
            'derived': derived,
            'manualPending': sorted(rule_set.manual_fields),
        }
        docs_out[doc.doc_id] = rec
        if doc.rel_path:
            documents[doc.rel_path] = rec

    plan = {
        'conflicts': sl_conflicts(fields_map),
        'derived': sorted(k for k, sl in fields_map.items() if sl.get('state') == 'derived'),
        'dictVersion': field_dict.version,
        'docs': docs_out,
        'documents': documents,
        'engineVersion': ENGINE_VERSION,
        'fields': {k: _public_slot(fields_map[k]) for k in sorted(fields_map)},
        'manualPending': sorted(rule_set.manual_fields),
        'missing': sorted(k for k, sl in fields_map.items() if sl.get('state') == 'missing'),
        'planVersion': PLAN_VERSION,
        'projectSchema': project.get('_schema') or 'yzproj/1.0',
        'ruleSetVersion': rule_set.version,
    }
    return plan


def _public_slot(slot: dict) -> dict:
    out = {
        'ruleId': slot.get('ruleId') or '',
        'source': slot.get('source') or '',
        'state': slot.get('state') or 'missing',
        'value': slot.get('value'),
    }
    if slot.get('bound'):
        out['bound'] = True
    if slot.get('conflicts'):
        out['conflicts'] = slot['conflicts']
    return out


def sl_conflicts(values: dict) -> list:
    out = []
    for k in sorted(values):
        c = values[k].get('conflicts')
        if c:
            out.append({'key': k, **c} if isinstance(c, dict) else c)
    return out


def field_states(plan: dict) -> Dict[str, str]:
    """Map enabled key → 值 / 缺值 / 推导 (DoD ①)."""
    mapping = {'filled': '值', 'missing': '缺值', 'derived': '推导'}
    fields = plan.get('fields') or {}
    return {k: mapping.get((fields[k] or {}).get('state'), '缺值') for k in fields}


# ---------------------------------------------------------------- resolve one doc

def _resolve_doc(doc: DocCtx, project: dict, fd: FieldDict, rs: RuleSet,
                 catalog: Catalog, attrs: dict, docs_all: List[DocCtx]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for spec in fd.enabled_in_order():
        out[spec.key] = _resolve_key(spec, doc, project, fd, rs, catalog, attrs, docs_all)
    return out


def _resolve_key(spec: FieldSpec, doc: DocCtx, project: dict, fd: FieldDict,
                 rs: RuleSet, catalog: Catalog, attrs: dict,
                 docs_all: List[DocCtx]) -> dict:
    key = spec.key
    rules = rs.by_target.get(key) or []
    overridable = all(r.overridable for r in rules) if rules else True
    if spec.scope == 'project' and any(r.overridable is False for r in rules):
        overridable = False

    override_val = doc.overrides.get(key)
    if overridable and not _is_empty(override_val):
        slot = _slot(override_val, 'S3', '', 'filled')
        # still record derived candidate if a rule would have produced something else
        derived_alt = _run_producers(
            spec, doc, project, fd, rs, catalog, attrs, docs_all, skip_override=True)
        if derived_alt and not _is_empty(derived_alt.get('value')) \
                and str(derived_alt.get('value')) != str(slot['value']):
            slot['conflicts'] = {
                'candidates': [
                    {'value': slot['value'], 'source': 'S3'},
                    {'value': derived_alt.get('value'),
                     'source': derived_alt.get('source')},
                ],
                'resolved': 'S3',
                'note': '文档级优先',
            }
        return slot

    produced = _run_producers(spec, doc, project, fd, rs, catalog, attrs, docs_all)
    if produced:
        return produced

    # fallback: project-level raw value (P0 把文档字段也写在顶层)
    raw = project.get(key)
    if not _is_empty(raw):
        src = (project.get('_fieldSources') or {}).get(key) or {}
        source = src.get('source') or ('S3' if spec.scope == 'document' else 'S1')
        return _slot(raw, source, src.get('ruleId') or '', 'filled')
    return _slot(None, '', '', 'missing')


def _run_producers(spec: FieldSpec, doc: DocCtx, project: dict, fd: FieldDict,
                   rs: RuleSet, catalog: Catalog, attrs: dict,
                   docs_all: List[DocCtx], skip_override: bool = False) -> Optional[dict]:
    key = spec.key
    last: Optional[dict] = None
    for rule in rs.by_target.get(key) or []:
        if rule.type == 'condition':
            continue
        if rule.type == 'alias':
            continue  # S5 候选，必须人工确认，不落值
        if _skip_rule(rule, spec, doc, rs):
            continue
        slot = _eval_rule(rule, spec, doc, project, fd, rs, catalog, attrs, docs_all)
        if slot and slot.get('state') != 'missing':
            last = slot
        elif slot and last is None:
            last = slot
    return last


def _skip_rule(rule: Rule, spec: FieldSpec, doc: DocCtx, rs: RuleSet) -> bool:
    # T7 窗口内的汇总目标文档：只用 aggregate/statistic/count，避免项目级样例正文漏进周报
    if getattr(rs, 'window', None) is not None and doc.doc_id == '_aggregate':
        if rule.type == 'direct':
            return True
    # T7 聚合/统计/计数：不对源文档自己套用
    if rule.type in ('aggregate', 'statistic', 'count'):
        src_id = _source_item_id(rule)
        if not doc.is_project and src_id and doc.item_id == src_id:
            return True
        if doc.is_project and rule.type == 'statistic':
            return True
        counter_key = None
        if spec.key in ('trialRunUserCount', 'trialRunBusinessCount'):
            counter_key = spec.key
        if counter_key and rs.counters.get(counter_key) == 'manual':
            return True
    return False


def _source_item_id(rule: Rule) -> str:
    from_ = rule.get('from')
    if isinstance(from_, dict):
        docs = from_.get('docs') or {}
        if isinstance(docs, dict) and docs.get('itemId'):
            return normalize_item_id(str(docs['itemId']))
    return ''


def _eval_rule(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict,
               fd: FieldDict, rs: RuleSet, catalog: Catalog, attrs: dict,
               docs_all: List[DocCtx]) -> dict:
    t = rule.type
    if t == 'direct':
        return _eval_direct(rule, spec, doc, project)
    if t == 'format':
        return _eval_format(rule, spec, doc, project)
    if t == 'compose':
        return _eval_compose(rule, spec, doc, project)
    if t == 'aggregate':
        return _eval_aggregate(rule, spec, doc, project, docs_all, rs)
    if t == 'statistic':
        return _eval_statistic(rule, spec, doc, project, docs_all, rs)
    if t == 'count':
        return _eval_count(rule, spec, doc, project, docs_all, rs)
    if t == 'reference':
        return _eval_reference(rule, spec, doc, project, catalog, attrs)
    return _slot(None, '', rule.id, 'missing')


def _eval_direct(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict) -> dict:
    from_ = rule.get('from')
    from_key = _from_key(from_)
    own = _own_value(spec.key, doc, project)
    looked = _lookup(from_, doc, project)
    if from_key and from_key != spec.key and not _is_empty(own):
        source = 'S3' if spec.key in doc.overrides and not _is_empty(doc.overrides.get(spec.key)) else 'S1'
        return _slot(own, source, rule.id, 'filled')
    if _is_empty(looked):
        return _slot(None, '', rule.id, 'missing')
    inherit = bool(from_key and from_key != spec.key)
    source = rule.source or ('S2' if inherit else 'S1')
    state = 'derived' if inherit or source in ('S2', 'S4', 'S0') else 'filled'
    if source == 'S3':
        state = 'filled'
    return _slot(looked, source, rule.id, state)


def _eval_format(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict) -> dict:
    raw = _lookup(rule.get('from'), doc, project)
    if _is_empty(raw):
        return _slot(None, '', rule.id, 'missing')
    text = _as_text(raw)
    transform = rule.get('transform') or {}
    if transform.get('strip'):
        text = text.strip()
    if transform.get('num'):
        try:
            n = float(text.replace(',', '').replace('，', '').strip())
        except ValueError:
            return _slot(None, '', rule.id, 'missing')
        decimals = transform.get('decimals')
        if decimals is None:
            text = str(int(n)) if n == int(n) else str(n)
        else:
            text = ('%%.%df' % int(decimals)) % n
    pad = transform.get('pad')
    if pad not in (None, False, 0, ''):
        width = int(pad) if not isinstance(pad, bool) else 0
        if width:
            text = text.zfill(width)
    prefix = transform.get('prefix')
    suffix = transform.get('suffix')
    if prefix:
        text = str(prefix) + text
    if suffix:
        text = text + str(suffix)
    return _slot(text, rule.source or 'S2', rule.id, 'derived')


def _eval_compose(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict) -> dict:
    parts = []
    join = rule.get('join')
    if join is None:
        join = ''
    skip_empty = bool(rule.get('skipEmpty', True))
    for part in rule.get('parts') or []:
        val = _lookup(part, doc, project)
        if _is_empty(val):
            if skip_empty:
                continue
            parts.append('')
        else:
            parts.append(_as_text(val))
    if not parts:
        return _slot(None, '', rule.id, 'missing')
    return _slot(str(join).join(parts), rule.source or 'S2', rule.id, 'derived')


def _eval_aggregate(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict,
                    docs_all: List[DocCtx], rs: RuleSet) -> dict:
    from_ = rule.get('from') or {}
    field = from_.get('field')
    src_docs = _match_source_docs(from_, docs_all, rs)
    transform = rule.get('transform') or {}
    dedup = transform.get('dedup')
    if dedup is None:
        dedup = rs.counters.get('logDedup', True)
    join = transform.get('join')
    if join is None:
        join = '；'
    order = transform.get('order') or 'none'
    skip_values = {_as_text(x).strip() for x in (transform.get('skipValues') or [])}
    values = []
    use_project_fallback = rs.window is None
    for d in _order_docs(src_docs, order):
        val = d.overrides.get(field)
        if _is_empty(val) and use_project_fallback:
            val = project.get(field)
        if _is_empty(val):
            continue
        text = _as_text(val)
        if skip_values and text.strip() in skip_values:
            continue
        if dedup and text in values:
            continue
        values.append(text)
    require = rule.get('require') or {}
    min_docs = int(require.get('minDocs') or 0)
    fail = rule.get('fail') or 'warn'
    if min_docs and len(src_docs) < min_docs:
        if fail == 'block' and not values:
            return _slot(None, '', rule.id, 'missing',
                         extra={'block': True,
                                'reason': '源文档不足（需要 ≥%d 份，实际 %d）' % (
                                    min_docs, len(src_docs))})
        if not values:
            return _slot(None, '', rule.id, 'missing')
    if not values:
        return _slot(None, '', rule.id, 'missing')
    return _slot(str(join).join(values), rule.source or 'S4', rule.id, 'derived')


def _eval_statistic(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict,
                    docs_all: List[DocCtx], rs: RuleSet) -> dict:
    from_ = rule.get('from') or {}
    field = from_.get('field')
    src_docs = _match_source_docs(from_, docs_all, rs)
    transform = rule.get('transform') or {}
    mode = transform.get('mode') or ''
    if spec.key == 'workerCount' and rs.counters.get('weeklyWorkerCount'):
        mode = rs.counters['weeklyWorkerCount']
    if spec.key == 'weather' and rs.counters.get('weatherFormat'):
        mode = rs.counters['weatherFormat']
    raw_vals = []
    use_project_fallback = rs.window is None
    for d in src_docs:
        val = d.overrides.get(field)
        if _is_empty(val) and use_project_fallback:
            val = project.get(field)
        if not _is_empty(val):
            raw_vals.append(val)
    if not raw_vals:
        return _slot(None, '', rule.id, 'missing')
    if mode == 'countDays':
        counts: Dict[str, int] = {}
        for v in raw_vals:
            k = _as_text(v)
            counts[k] = counts.get(k, 0) + 1
        tmpl = transform.get('template') or '{value} {n} 天'
        join = transform.get('join') or ' / '
        parts = []
        for k in sorted(counts):
            parts.append(tmpl.replace('{value}', k).replace('{n}', str(counts[k])))
        return _slot(join.join(parts), rule.source or 'S4', rule.id, 'derived')
    nums = []
    for v in raw_vals:
        try:
            nums.append(float(_as_text(v).replace(',', '')))
        except ValueError:
            continue
    if not nums:
        return _slot(None, '', rule.id, 'missing')
    avg = sum(nums) / len(nums)
    peak = max(nums)
    total = sum(nums)
    if mode == 'avg':
        text = _fmt_num(avg)
    elif mode == 'peak':
        text = _fmt_num(peak)
    elif mode == 'sum':
        text = _fmt_num(total)
    else:  # avgAndPeak
        tmpl = transform.get('numberTemplate') or '平均 {avg} 人，最多 {peak} 人'
        text = (tmpl.replace('{avg}', _fmt_num(avg))
                .replace('{peak}', _fmt_num(peak)))
    return _slot(text, rule.source or 'S4', rule.id, 'derived')


def _eval_count(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict,
                docs_all: List[DocCtx], rs: RuleSet) -> dict:
    from_ = rule.get('from') or {}
    transform = rule.get('transform') or {}
    mode = transform.get('mode') or 'rows'
    exclude_empty = bool(transform.get('excludeEmpty', True))
    table = from_.get('table')
    src_docs = _match_source_docs(from_, docs_all, rs)
    n = 0
    if mode == 'docs':
        n = len(src_docs)
    elif mode == 'distinct':
        field = from_.get('field')
        seen = set()
        if table:
            for row in _table_rows(project, table):
                val = row.get(field) if field else json.dumps(row, ensure_ascii=False, sort_keys=True)
                if exclude_empty and _is_empty(val):
                    continue
                seen.add(_as_text(val))
        else:
            for d in src_docs:
                val = d.overrides.get(field)
                if _is_empty(val):
                    val = project.get(field)
                if exclude_empty and _is_empty(val):
                    continue
                seen.add(_as_text(val))
        n = len(seen)
    else:  # rows
        rows = _table_rows(project, table) if table else []
        if exclude_empty:
            rows = [r for r in rows if any(not _is_empty(v) for v in r.values())]
        n = len(rows)
        if n == 0 and not table:
            n = len(src_docs)
    return _slot(str(n), rule.source or 'S4', rule.id, 'derived')


def _eval_reference(rule: Rule, spec: FieldSpec, doc: DocCtx, project: dict,
                    catalog: Catalog, attrs: dict) -> dict:
    # 已绑定的编号永久有效（不重新 allocate — 编号引擎是 P2）
    bound = None
    if spec.key in doc.overrides and not _is_empty(doc.overrides.get(spec.key)):
        bound = doc.overrides.get(spec.key)
    if bound is None:
        docs_idx = project.get('_docs') or {}
        rec = docs_idx.get(doc.doc_id) or {}
        if rec.get('docNo'):
            bound = rec['docNo']
    if bound is None:
        pool = (project.get('_numbering') or {}).get(doc.item_id) or {}
        for item in pool.get('allocated') or []:
            if item.get('docId') == doc.doc_id and item.get('no'):
                bound = item['no']
                break
    if not _is_empty(bound):
        sl = _slot(bound, rule.source or 'S0', rule.id, 'derived')
        sl['bound'] = True
        return sl
    if doc.is_project:
        return _slot(None, '', rule.id, 'missing')
    # 未分配：给出可复现的「将要使用的前缀」但不分配流水（P2）
    return _slot(None, '', rule.id, 'missing')


# ---------------------------------------------------------------- conditions / lookup

def _eval_conditions(project: dict, rs: RuleSet) -> dict:
    attrs: Dict[str, dict] = {}
    dummy = DocCtx(doc_id='_project', item_id='', rel_path='', overrides={}, is_project=True)
    for rule in rs.rules:
        if rule.type != 'condition':
            continue
        ok = _eval_when(rule.get('when') or {}, dummy, project)
        blob = rule.get('then') if ok else rule.get('else')
        if not isinstance(blob, dict):
            continue
        for k, v in blob.items():
            field_name, attr = _dollar_key(str(k))
            attrs.setdefault(field_name, {})[attr or 'value'] = v
    return attrs


def _eval_when(when: dict, doc: DocCtx, project: dict) -> bool:
    if not when:
        return False
    if 'empty' in when:
        return _is_empty(_lookup(when['empty'], doc, project))
    if 'notEmpty' in when:
        return not _is_empty(_lookup(when['notEmpty'], doc, project))
    if 'equals' in when:
        spec = when['equals']
        if isinstance(spec, dict):
            left = _lookup(spec.get('left') or spec.get('field'), doc, project)
            return _as_text(left) == _as_text(spec.get('value'))
        return False
    if 'in' in when:
        spec = when['in']
        if isinstance(spec, dict):
            left = _as_text(_lookup(spec.get('field'), doc, project))
            return left in [ _as_text(x) for x in (spec.get('values') or []) ]
        return False
    return False


def _dollar_key(k: str) -> Tuple[str, str]:
    if k.startswith('$'):
        k = k[1:]
    if '.' in k:
        a, b = k.split('.', 1)
        return a, b
    return k, 'value'


def _lookup(expr, doc: DocCtx, project: dict):
    if expr is None:
        return None
    if not isinstance(expr, str):
        return None
    expr = expr.strip()
    if expr.startswith('project.'):
        return project.get(expr.split('.', 1)[1])
    if expr.startswith('doc.'):
        key = expr.split('.', 1)[1]
        if key in doc.overrides and not _is_empty(doc.overrides.get(key)):
            return doc.overrides.get(key)
        return project.get(key)
    if expr.startswith('numbering.'):
        return None  # handled in reference
    # bare field name
    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', expr):
        if expr in doc.overrides and not _is_empty(doc.overrides.get(expr)):
            return doc.overrides.get(expr)
        return project.get(expr)
    return None


def _from_key(from_) -> str:
    if isinstance(from_, str) and (from_.startswith('project.') or from_.startswith('doc.')):
        return from_.split('.', 1)[1]
    return ''


def _own_value(key: str, doc: DocCtx, project: dict):
    if key in doc.overrides and not _is_empty(doc.overrides.get(key)):
        return doc.overrides.get(key)
    return project.get(key)


def _collect_docs(project: dict, catalog: Catalog) -> List[DocCtx]:
    out: List[DocCtx] = []
    seen_paths = set()
    docs_idx = project.get('_docs') or {}
    if isinstance(docs_idx, dict):
        for doc_id, rec in docs_idx.items():
            if not isinstance(rec, dict):
                continue
            rel = (rec.get('relPath') or '').replace('\\', '/').strip('/')
            item_id = normalize_item_id(rec.get('itemId') or infer_item_id(rel, catalog))
            cat = catalog.by_id.get(item_id)
            overrides = dict((project.get('_documents') or {}).get(rel) or {})
            if rec.get('docNo') and not overrides.get('docNo'):
                overrides['docNo'] = rec['docNo']
            out.append(DocCtx(
                doc_id=str(doc_id), item_id=item_id, rel_path=rel,
                overrides=overrides, is_project=False,
                abbr=(cat.abbr if cat else ''),
                numbered=(cat.numbered if cat else False),
                digits=(cat.digits if cat else 2),
            ))
            if rel:
                seen_paths.add(rel)
    documents = project.get('_documents') or {}
    if isinstance(documents, dict):
        for rel, overrides in documents.items():
            rel_n = str(rel).replace('\\', '/').strip('/')
            if rel_n in seen_paths:
                continue
            item_id = infer_item_id(rel_n, catalog)
            cat = catalog.by_id.get(item_id)
            doc_id = _synth_doc_id(rel_n, overrides if isinstance(overrides, dict) else {}, cat)
            ov = dict(overrides) if isinstance(overrides, dict) else {}
            ov = {k: v for k, v in ov.items() if v not in (None, '')}
            out.append(DocCtx(
                doc_id=doc_id, item_id=item_id, rel_path=rel_n,
                overrides=ov, is_project=False,
                abbr=(cat.abbr if cat else ''),
                numbered=(cat.numbered if cat else False),
                digits=(cat.digits if cat else 2),
            ))
    out.sort(key=lambda d: (d.item_id, d.rel_path, d.doc_id))
    return out


def _synth_doc_id(rel: str, overrides: dict, cat: Optional[CatalogItem]) -> str:
    no = str(overrides.get('docNo') or '')
    m = re.search(r'-(\d+)$', no)
    seq = m.group(1) if m else '01'
    abbr = cat.abbr if cat else (Path(rel).stem.split('_')[0] if rel else 'DOC')
    if cat and cat.abbr:
        abbr = cat.abbr
    elif no:
        # YY123-KGBSB-01 → KGBSB
        parts = no.split('-')
        if len(parts) >= 2:
            abbr = parts[-2] if parts[-1].isdigit() else parts[-1]
    return 'D-%s-%s' % (abbr, seq.zfill(2 if len(seq) <= 2 else len(seq)))


def _doc_date_iso(doc: DocCtx) -> str:
    for key in ('logDate', 'docDate', 'weekStart', 'monthStart', 'date'):
        parsed = parse_iso_date(doc.overrides.get(key))
        if parsed is not None:
            return parsed.isoformat()
    parsed = parse_iso_date(doc.rel_path)
    if parsed is not None:
        return parsed.isoformat()
    return ''


def _match_source_docs(from_: dict, docs_all: List[DocCtx],
                       rs: Optional[RuleSet] = None) -> List[DocCtx]:
    docs_q = from_.get('docs') or {}
    if not isinstance(docs_q, dict):
        return []
    item_id = normalize_item_id(str(docs_q['itemId'])) if docs_q.get('itemId') else ''
    volume = docs_q.get('volume') or ''
    tag = docs_q.get('tag') or ''
    matched = []
    for d in docs_all:
        if item_id and d.item_id != item_id:
            continue
        if volume and not d.rel_path.startswith(str(volume)):
            continue
        if tag:
            continue  # P1: tag 匹配留空（无 tag 索引）
        matched.append(d)
    window = getattr(rs, 'window', None) if rs is not None else None
    # FillPlan / P1: no window → do not drop undated docs (dateWithin is T7).
    if window is not None:
        matched = [d for d in matched if in_window(_doc_date_iso(d), window)]
    return matched


def _order_docs(docs: List[DocCtx], order: str) -> List[DocCtx]:
    if order == 'docNo':
        return sorted(docs, key=lambda d: (str(d.overrides.get('docNo') or ''), d.rel_path))
    if order == 'date':
        return sorted(docs, key=lambda d: (_doc_date_iso(d) or '9999-99-99', d.rel_path))
    # none → 稳定按路径
    return sorted(docs, key=lambda d: d.rel_path)


def _table_rows(project: dict, table: Optional[str]) -> List[dict]:
    if not table:
        return []
    assets = project.get('_assets') or {}
    for key in TABLE_ASSET_MAP.get(table, (table,)):
        rows = assets.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    rows = assets.get(table)
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    return []


def _slot(value, source: str, rule_id: str, state: str, extra: dict | None = None) -> dict:
    if state != 'missing':
        value = _as_text(value) if not _is_empty(value) else None
        if value is None:
            state = 'missing'
            source = ''
    else:
        value = None
    sl = {
        'value': value,
        'source': source if state != 'missing' else '',
        'ruleId': rule_id if state != 'missing' else '',
        'state': state,
    }
    if extra:
        sl.update(extra)
    return sl


def _is_empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == '':
        return True
    return False


def _as_text(v) -> str:
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return str(v)
    return str(v)


def _fmt_num(n: float) -> str:
    if n == int(n):
        return str(int(n))
    s = ('%.2f' % n).rstrip('0').rstrip('.')
    return s
