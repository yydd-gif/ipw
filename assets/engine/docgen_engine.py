#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文档生成引擎 · P0 CLI skeleton（P2 实现一键成册 / 追加 / 无模板三选一）"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _common import TEMPLATES, emit_progress, emit_result, exit_param, result_payload


def main() -> int:
    ap = argparse.ArgumentParser(description='docgen_engine · P0 skeleton')
    ap.add_argument('--project', type=Path)
    ap.add_argument('--item', default='', help='all 或具体 itemId')
    ap.add_argument('--count', type=int, default=1)
    ap.add_argument('--mode', choices=('template', 'blank', 'upload', 'skip'),
                    default='template')
    ap.add_argument('--templates', type=Path, default=TEMPLATES)
    ap.add_argument('--out', type=Path, help='输出根目录（默认从 --project 推断）')
    ap.add_argument('--overwrite', action='store_true')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.project or not a.item:
        return exit_param('需要 --project / --item', a.as_json, 'docgen')

    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'docgen')

    emit_progress(0, 1, 'P0 skeleton — documents not generated')
    payload = result_payload(
        True, 'docgen',
        'P0 skeleton: docgen 未实现（P2）',
        stats={'docs': 0, 'filled': 0, 'missing': 0, 'residual': 0},
        errors=[{'reason': 'not implemented (P2)', 'level': 'warn'}],
    )
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
