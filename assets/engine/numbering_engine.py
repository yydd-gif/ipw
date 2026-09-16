#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编号引擎 · P0 CLI skeleton（P2 实现 allocate/release/restore，目录项内不重排）"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import emit_progress, emit_result, exit_param, result_payload


def main() -> int:
    ap = argparse.ArgumentParser(description='numbering_engine · P0 skeleton')
    ap.add_argument('--item', required=True, help='目录项名或 itemId')
    ap.add_argument('--action', choices=('allocate', 'release', 'restore'),
                    default='allocate')
    ap.add_argument('--count', type=int, default=1)
    ap.add_argument('--no', dest='doc_no', default='', help='release/restore 的目标编号')
    ap.add_argument('--doc-id', dest='doc_id', default='')
    ap.add_argument('--project', type=Path, required=True)
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()

    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'numbering')

    emit_progress(0, 1, 'P0 skeleton — numbering not allocated')
    payload = result_payload(
        True, 'numbering',
        'P0 skeleton: numbering 未实现（P2）',
        stats={'docs': 0, 'filled': 0, 'missing': 0, 'residual': 0},
        errors=[{'reason': 'not implemented (P2)', 'level': 'warn'}],
    )
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
