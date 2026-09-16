#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取值装配引擎 · P0 CLI skeleton（P1 实现 9 类规则 / FillPlan）"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import (
    DICT_PATH, RULES_PATH, emit_progress, emit_result, exit_param,
    result_payload,
)


def main() -> int:
    ap = argparse.ArgumentParser(description='datafill_engine · P0 skeleton')
    ap.add_argument('--project', type=Path, required=True, help='project.json')
    ap.add_argument('--out', type=Path, required=True, help='FillPlan 输出路径')
    ap.add_argument('--dict', type=Path, default=DICT_PATH)
    ap.add_argument('--rules', type=Path, default=RULES_PATH)
    ap.add_argument('--only', default='', help='只算某个 itemId，如 二-01')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()

    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'datafill')

    emit_progress(0, 1, 'P0 skeleton — FillPlan not generated')
    payload = result_payload(
        True, 'datafill',
        'P0 skeleton: datafill 未实现（P1）',
        stats={'docs': 0, 'filled': 0, 'missing': 0, 'residual': 0},
        errors=[{'reason': 'not implemented (P1)', 'level': 'warn'}],
    )
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
