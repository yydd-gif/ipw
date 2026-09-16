# -*- coding: utf-8 -*-
"""编号池 · `{合同编号}-{表名缩写}-{流水号}`，目录项内不重排.

规格：数据与规则规格.md §2.5 / §3.5；软件设计方案.md §3.6.

不变量（P2 DoD 必须锁死）：
1. allocate 取 released 中序号最小者；released 空则 max += 1
2. release 时若序号 == max，则 max -= 1；否则进 released（中间号留坑）
3. restore 从 released 移除并绑回原 docId；不重新分配
4. 删掉 02 之后 03 仍是 03
5. 尾号释放后 max 回退，下一号仍接在新的 max 之后
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from lib.rule_engine import Catalog, CatalogItem, normalize_item_id


class NumberingError(ValueError):
    """编号动作无法完成（缺项 / 找不到号 / 重复绑定）."""


def make_prefix(contract_no: str, abbr: str) -> str:
    c = (contract_no or '').strip()
    a = (abbr or '').strip()
    if c and a:
        return '%s-%s' % (c, a)
    return c or a


def format_no(prefix: str, seq: int, digits: int) -> str:
    body = '%0*d' % (int(digits or 2), int(seq))
    prefix = (prefix or '').strip()
    return '%s-%s' % (prefix, body) if prefix else body


def parse_seq(no: str) -> int:
    """流水号 = 编号最后一个 '-' 段（合同编号本身不含尾部流水号）."""
    if not no:
        raise NumberingError('空编号')
    tail = str(no).rsplit('-', 1)[-1]
    if not re.fullmatch(r'\d+', tail):
        raise NumberingError('无法解析流水号：%s' % no)
    return int(tail)


def make_doc_id(abbr: str, seq: int, digits: int) -> str:
    return 'D-%s-%0*d' % (abbr, int(digits or 2), int(seq))


def empty_pool(prefix: str, digits: int) -> dict:
    return {
        'prefix': prefix,
        'digits': int(digits or 2),
        'allocated': [],
        'released': [],
        'max': 0,
    }


def ensure_pool(project: dict, item_id: str, prefix: str, digits: int) -> dict:
    numbering = project.setdefault('_numbering', {})
    pool = numbering.get(item_id)
    if not isinstance(pool, dict):
        pool = empty_pool(prefix, digits)
        numbering[item_id] = pool
    pool.setdefault('prefix', prefix)
    if prefix and not pool.get('prefix'):
        pool['prefix'] = prefix
    pool.setdefault('digits', int(digits or 2))
    if not isinstance(pool.get('allocated'), list):
        pool['allocated'] = []
    if not isinstance(pool.get('released'), list):
        pool['released'] = []
    pool.setdefault('max', 0)
    return pool


def _today() -> str:
    return date.today().isoformat()


def _allocated_nos(pool: dict) -> List[str]:
    out = []
    for rec in pool.get('allocated') or []:
        if isinstance(rec, dict) and rec.get('no'):
            out.append(rec['no'])
    return out


def _find_allocated(pool: dict, doc_id: str = '', no: str = '') -> Optional[dict]:
    for rec in pool.get('allocated') or []:
        if not isinstance(rec, dict):
            continue
        if doc_id and rec.get('docId') == doc_id:
            return rec
        if no and rec.get('no') == no:
            return rec
    return None


def allocate_one(pool: dict, abbr: str, doc_id: str = '') -> dict:
    """Allocate one number into pool. Returns {docId, no, seq, reused}."""
    digits = int(pool.get('digits') or 2)
    prefix = pool.get('prefix') or abbr
    released = list(pool.get('released') or [])
    reused = False
    if released:
        released.sort(key=parse_seq)
        no = released.pop(0)
        pool['released'] = released
        seq = parse_seq(no)
        reused = True
    else:
        pool['max'] = int(pool.get('max') or 0) + 1
        seq = int(pool['max'])
        no = format_no(prefix, seq, digits)
    if not doc_id:
        doc_id = make_doc_id(abbr, seq, digits)
    if _find_allocated(pool, doc_id=doc_id) or _find_allocated(pool, no=no):
        raise NumberingError('编号已在册：%s / %s' % (doc_id, no))
    rec = {'docId': doc_id, 'no': no, 'at': _today()}
    pool.setdefault('allocated', []).append(rec)
    return {'docId': doc_id, 'no': no, 'seq': seq, 'reused': reused}


def release_one(pool: dict, doc_id: str = '', no: str = '') -> dict:
    rec = _find_allocated(pool, doc_id=doc_id, no=no)
    if rec is None:
        raise NumberingError('在册编号不存在：docId=%s no=%s' % (doc_id, no))
    pool['allocated'] = [r for r in (pool.get('allocated') or []) if r is not rec]
    seq = parse_seq(rec['no'])
    max_n = int(pool.get('max') or 0)
    if seq == max_n:
        # 尾部回退；已释放的更大号不应再留在 released
        pool['max'] = max_n - 1
        pool['released'] = [
            n for n in (pool.get('released') or []) if parse_seq(n) < pool['max']
        ]
        tail = True
    else:
        if rec['no'] not in (pool.get('released') or []):
            pool.setdefault('released', []).append(rec['no'])
            pool['released'].sort(key=parse_seq)
        tail = False
    return {
        'docId': rec.get('docId') or doc_id,
        'no': rec['no'],
        'seq': seq,
        'tail': tail,
    }


def restore_one(pool: dict, doc_id: str, no: str) -> dict:
    if not doc_id or not no:
        raise NumberingError('restore 需要 --doc-id 与 --no')
    released = list(pool.get('released') or [])
    if no in released:
        released.remove(no)
        pool['released'] = released
    existing = _find_allocated(pool, doc_id=doc_id) or _find_allocated(pool, no=no)
    if existing:
        # 已在册：保持原绑定，不重新分配
        if existing.get('docId') != doc_id or existing.get('no') != no:
            raise NumberingError(
                'restore 冲突：已有 %s↔%s，不能绑 %s↔%s'
                % (existing.get('docId'), existing.get('no'), doc_id, no))
        return {'docId': doc_id, 'no': no, 'seq': parse_seq(no), 'already': True}
    seq = parse_seq(no)
    if seq > int(pool.get('max') or 0):
        pool['max'] = seq
    pool.setdefault('allocated', []).append({
        'docId': doc_id, 'no': no, 'at': _today(),
    })
    return {'docId': doc_id, 'no': no, 'seq': seq, 'already': False}


def allocated_seq_set(pool: dict) -> List[int]:
    return sorted(parse_seq(n) for n in _allocated_nos(pool))


def resolve_item(catalog: Catalog, token: str) -> CatalogItem:
    """优先 itemId，其次目录项名 / 缩写."""
    raw = (token or '').strip()
    if not raw:
        raise NumberingError('需要 --item')
    nid = normalize_item_id(raw)
    if nid in catalog.by_id:
        return catalog.by_id[nid]
    hits = [it for it in catalog.items if it.item_id == raw or it.name == raw
            or it.abbr == raw]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise NumberingError('目录项名不唯一：%s（%s）' % (
            raw, '、'.join(h.item_id for h in hits)))
    raise NumberingError('未知目录项：%s' % raw)


def apply_action(project: dict, catalog: Catalog, item_token: str, action: str,
                 count: int = 1, no: str = '', doc_id: str = '') -> Tuple[dict, List[dict]]:
    """Mutate project['_numbering'] and return (pool, result items)."""
    item = resolve_item(catalog, item_token)
    prefix = make_prefix(str(project.get('contractNo') or ''), item.abbr)
    pool = ensure_pool(project, item.item_id, prefix, item.digits)
    if pool.get('prefix') != prefix and prefix:
        # 合同编号后补：已分配号保持原样，新号用新前缀
        pool['prefix'] = prefix
    action = (action or 'allocate').strip()
    results: List[dict] = []
    if action == 'allocate':
        n = int(count or 1)
        if n < 1:
            raise NumberingError('--count 必须 ≥ 1')
        for _ in range(n):
            results.append(allocate_one(pool, item.abbr, doc_id=doc_id if n == 1 else ''))
    elif action == 'release':
        results.append(release_one(pool, doc_id=doc_id, no=no))
    elif action == 'restore':
        results.append(restore_one(pool, doc_id=doc_id, no=no))
    else:
        raise NumberingError('未知 action：%s' % action)
    return pool, results
