#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P7 模板资产体检 CLI（向导同一套清单）。

  python tools/run_health.py
  python tools/run_health.py --json
  python tools/run_health.py --brief
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import ENGINE, REPO  # noqa: E402

sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO))

from lib.health import run_health  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description='模板资产体检向导（CLI）')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--brief', action='store_true')
    a = ap.parse_args()
    payload = run_health()
    if a.json:
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload.get('ok') else 1
    print(payload.get('summary') or '')
    print('仓库/包根：%s' % payload.get('stats', {}).get('repo'))
    for it in payload.get('items') or []:
        mark = {'pass': 'PASS', 'fail': 'FAIL', 'warn': 'WARN', 'skip': 'SKIP'}.get(
            it.get('level'), '?')
        print('  [%s] %s — %s' % (mark, it.get('key'), it.get('detail')))
    return 0 if payload.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
