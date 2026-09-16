# -*- coding: utf-8 -*-

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from _paths import (
    REPO, TEMPLATES, TEMPLATES_BACKUP, SPEC, DESIGN_DOCS, WORK,
    DICT_PATH, MAPPING_CSV, EXAMPLES,
)
import os, sys, zipfile
from xml.etree import ElementTree as ET
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
ROOT = str(TEMPLATES)


def ptext(p):
    return ''.join(t.text or '' for t in p.iter(W + 't'))


for rel in sys.argv[1:]:
    p = os.path.join(ROOT, *rel.replace('\\', '/').split('/'))
    print('=' * 70)
    print(rel)
    z = zipfile.ZipFile(p)
    body = ET.fromstring(z.read('word/document.xml')).find(W + 'body')
    pi = ti = 0
    for el in body:
        if el.tag == W + 'p':
            pi += 1
            print(f'  P{pi}: {ptext(el).strip()}')
        elif el.tag == W + 'tbl':
            ti += 1
            print(f'  -- 表{ti} --')
            for ri, tr in enumerate(el.findall(W + 'tr'), 1):
                cells = [''.join(ptext(x) for x in tc.findall(W + 'p')).strip() for tc in tr.findall(W + 'tc')]
                print(f'    R{ri}: ' + ' | '.join(cells))
