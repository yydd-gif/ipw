#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子表接管引擎 · P0 CLI skeleton（P5 实现 8 张子表行克隆）"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import emit_progress, emit_result, exit_param, result_payload


def main() -> int:
    ap = argparse.ArgumentParser(description='subtable_engine · P0 skeleton')
    ap.add_argument('--doc', type=Path, help='目标 docx')
    ap.add_argument('--table', default='', help='子表 key（8 选 1，空则自动识别）')
    ap.add_argument('--data', type=Path, help='JSON/CSV 数据源')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.doc:
        return exit_param('需要 --doc', a.as_json, 'subtable')

    if not a.doc.exists():
        return exit_param('docx 不存在：%s' % a.doc, a.as_json, 'subtable')

    emit_progress(0, 1, 'P0 skeleton — subtable not applied')
    payload = result_payload(
        True, 'subtable',
        'P0 skeleton: subtable 未实现（P5）',
        stats={'docs': 1, 'filled': 0, 'missing': 0, 'residual': 0},
        errors=[{'reason': 'not implemented (P5)', 'level': 'warn'}],
    )
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
