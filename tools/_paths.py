# -*- coding: utf-8 -*-
"""Repo / packed extraResources layout paths.

Works as `python tools/<script>.py` from the git repo **or** from a packaged
`resources/` tree (Electron extraResources). Honors YANSHOU_ROOT / YANSHOU_WORK.
"""
import os
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
_env_root = (os.environ.get('YANSHOU_ROOT') or '').strip()
REPO = Path(_env_root).resolve() if _env_root else TOOLS_DIR.parent
ASSETS = REPO / 'assets'
TEMPLATES = ASSETS / 'templates'
TEMPLATES_BACKUP = ASSETS / 'templates-backup'
SPEC = ASSETS / 'spec'
ENGINE = ASSETS / 'engine'
_env_work = (os.environ.get('YANSHOU_WORK') or '').strip()
WORK = Path(_env_work) if _env_work else (REPO / 'work')
DOCS = REPO / 'docs'
DESIGN_DOCS = DOCS / '设计文档'
EXAMPLES = REPO / 'examples'
DICT_PATH = SPEC / '字段字典.json'
MAPPING_CSV = SPEC / '模板字段映射表.csv'
ABBR_CSV = SPEC / '表名缩写字典.csv'
VENDOR = REPO / 'lib' / 'vendor'

if VENDOR.is_dir() and str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
