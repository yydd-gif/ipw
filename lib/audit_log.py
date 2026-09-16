# -*- coding: utf-8 -*-
"""Project-side audit trail (软件设计方案-v2.0 M14).

Writes append-only JSONL under <工程>/_logs/:
  changes.jsonl  — every write (engine + AI + shell)
  ai.jsonl       — AI channel only (draft/polish/expand/extract/apply/qa)
Never invents records; callers pass the facts they actually wrote.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def logs_dir(project_root: Path | str) -> Path:
    return Path(project_root) / '_logs'


def append_jsonl(path: Path, record: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False)
    with path.open('a', encoding='utf-8') as fh:
        fh.write(line + '\n')
        fh.flush()
    return path


def log_change(project_root: Path | str, op: str, **fields: Any) -> dict:
    rec: Dict[str, Any] = {'at': fields.pop('at', None) or _now(), 'op': op}
    rec.update(fields)
    root = Path(project_root)
    append_jsonl(logs_dir(root) / 'changes.jsonl', rec)
    channel = str(rec.get('channel') or '')
    if channel == 'ai' or op.startswith('ai.'):
        append_jsonl(logs_dir(root) / 'ai.jsonl', rec)
    return rec


def read_jsonl(path: Path | str) -> list:
    p = Path(path)
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def latest_ai(project_root: Path | str) -> Optional[dict]:
    rows = read_jsonl(logs_dir(project_root) / 'ai.jsonl')
    return rows[-1] if rows else None
