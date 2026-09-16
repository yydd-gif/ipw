#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总引擎 · P0 CLI skeleton（P6 实现日志→周报→月报）"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import emit_progress, emit_result, exit_param, result_payload


def main() -> int:
    ap = argparse.ArgumentParser(description='aggregate_engine · P0 skeleton')
    ap.add_argument('--period', default='', choices=('', 'week', 'month'))
    ap.add_argument('--from', dest='date_from', default='', help='YYYY-MM-DD')
    ap.add_argument('--to', dest='date_to', default='', help='YYYY-MM-DD')
    ap.add_argument('--project', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.period or not a.project:
        return exit_param('需要 --period / --project', a.as_json, 'aggregate')

    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'aggregate')

    emit_progress(0, 1, 'P0 skeleton — aggregate not produced')
    payload = result_payload(
        True, 'aggregate',
        'P0 skeleton: aggregate 未实现（P6）',
        stats={'docs': 0, 'filled': 0, 'missing': 0, 'residual': 0},
        errors=[{'reason': 'not implemented (P6)', 'level': 'warn'}],
    )
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
