# -*- coding: utf-8 -*-
"""Deterministic smart-fill extractor (alias / label patterns).

Does NOT call a model. Results are tagged source='rules' so they are never
passed off as live-model replies. Human confirmation is still required
before write-back (T11 / P6 DoD ②).
"""
from __future__ import annotations

import re
from typing import Dict, List

from lib.field_dict import FieldDict, FieldSpec

# Fields the confirmation panel aims to surface (~10 candidates).
PREFERRED_KEYS = (
    'projectName',
    'ownerUnit',
    'constructionUnit',
    'supervisionUnit',
    'contractNo',
    'contractAmount',
    'buildSite',
    'projectManager',
    'approvalDocNo',
    'projectGoal',
    'projectContent',
    'projectBackground',
    'constructionContact',
    'chiefSupervisor',
)

# Only strip a *following field label* glued onto the same capture, not
# legitimate values that happen to end in 工程/项目.
_NEXT_LABEL = re.compile(
    r'(?:建设单位|施工单位|监理单位|合同编号|合同金额|施工地点|项目经理|'
    r'方案审核|建设目标|主要建设内容|项目背景).*$')


def _clean_value(raw: str) -> str:
    text = (raw or '').strip().strip('：:；;，,。.')
    text = text.split('\n')[0].strip()
    text = re.sub(r'^[\s"\'“”]+', '', text)
    text = re.sub(r'[\s"\'“”]+$', '', text)
    cut = _NEXT_LABEL.search(text)
    if cut and cut.start() >= 2:
        text = text[:cut.start()].strip().strip('：:；;，,')
    return text[:200]


def _norm(s: str) -> str:
    return re.sub(r'\s+', '', (s or '')).lower()


def _aliases(spec: FieldSpec) -> List[str]:
    names = [spec.label, spec.key] + list(spec.aliases or [])
    out = []
    seen = set()
    for n in names:
        n = (n or '').strip()
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return sorted(out, key=len, reverse=True)


def _patterns_for(alias: str) -> List[re.Pattern]:
    esc = re.escape(alias)
    return [
        re.compile(esc + r'\s*[:：]\s*(.+)$', re.M),
        re.compile(esc + r'\s*[为是]\s*(.+)$', re.M),
        re.compile(r'[（(]' + esc + r'[）)]\s*[:：]?\s*(.+)$', re.M),
    ]


def extract_candidates(text: str, field_dict: FieldDict,
                       limit: int = 10) -> List[dict]:
    """Return up to `limit` field candidates from free text. source='rules'."""
    blob = text or ''
    if not blob.strip():
        return []
    found: Dict[str, dict] = {}
    ordered_specs: List[FieldSpec] = []
    by_key = {s.key: s for s in field_dict.enabled_in_order()}
    for key in PREFERRED_KEYS:
        if key in by_key:
            ordered_specs.append(by_key[key])
    for spec in field_dict.enabled_in_order():
        if spec.key not in PREFERRED_KEYS:
            ordered_specs.append(spec)

    for spec in ordered_specs:
        if spec.key in found:
            continue
        if spec.scope == 'auto' and spec.key in ('docNo',):
            continue
        for alias in _aliases(spec):
            if len(alias) < 2:
                continue
            for pat in _patterns_for(alias):
                m = pat.search(blob)
                if not m:
                    continue
                val = _clean_value(m.group(1))
                if not val or _norm(val) == _norm(alias):
                    continue
                found[spec.key] = {
                    'key': spec.key,
                    'label': spec.label,
                    'value': val,
                    'confidence': 0.72 if alias == spec.label else 0.6,
                    'source': 'rules',
                    'matchedAlias': alias,
                    'confirmed': False,
                }
                break
            if spec.key in found:
                break
        if len(found) >= limit:
            break

    # Prefer the advertised ~10 keys, keep encounter order of PREFERRED_KEYS.
    ranked = []
    for key in PREFERRED_KEYS:
        if key in found:
            ranked.append(found.pop(key))
    ranked.extend(found.values())
    return ranked[:limit]
