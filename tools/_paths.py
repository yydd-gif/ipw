# -*- coding: utf-8 -*-
"""Repo layout paths. Importable as `python tools/<script>.py` via local bootstrap."""
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
REPO = TOOLS_DIR.parent
ASSETS = REPO / 'assets'
TEMPLATES = ASSETS / 'templates'
TEMPLATES_BACKUP = ASSETS / 'templates-backup'
SPEC = ASSETS / 'spec'
ENGINE = ASSETS / 'engine'
WORK = REPO / 'work'
DOCS = REPO / 'docs'
DESIGN_DOCS = DOCS / '设计文档'
EXAMPLES = REPO / 'examples'
DICT_PATH = SPEC / '字段字典.json'
MAPPING_CSV = SPEC / '模板字段映射表.csv'
ABBR_CSV = SPEC / '表名缩写字典.csv'
