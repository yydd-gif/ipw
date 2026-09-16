# -*- coding: utf-8 -*-
"""Read-only HTML preview of a docx (E1 path). Highlights leftover {{key}}."""
from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import List

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
W_T = W + 't'
W_P = W + 'p'
W_TBL = W + 'tbl'
W_TR = W + 'tr'
W_TC = W + 'tc'
W_BODY = W + 'body'
FALLBACK = re.compile(rb'<mc:Fallback>.*?</mc:Fallback>', re.S)
PH = re.compile(r'\{\{([^{}]+)\}\}')
PART_RE = re.compile(r'^word/(document|header\d*|footer\d*)\.xml$')


def _para_text(p) -> str:
    return ''.join(t.text or '' for t in p.iter(W_T))


def _highlight(text: str, required: set[str] | None = None) -> str:
    required = required or set()

    def repl(m):
        key = m.group(1)
        cls = 'ph-req' if key in required else 'ph'
        return '<span class="%s">{{%s}}</span>' % (cls, html.escape(key))

    return PH.sub(repl, html.escape(text, quote=False))


def _walk_block(el, required: set[str], out: List[str]) -> None:
    if el.tag == W_P:
        t = _para_text(el).strip('\u3000 ')
        if t:
            out.append('<p class="pg-p">%s</p>' % _highlight(t, required))
        else:
            out.append('<p class="pg-p">&nbsp;</p>')
        return
    if el.tag == W_TBL:
        out.append('<table class="pg-tbl">')
        for tr in el.findall(W_TR):
            out.append('<tr>')
            for tc in tr.findall(W_TC):
                cell = []
                for p in tc.iter(W_P):
                    cell.append(_para_text(p))
                txt = ' '.join(x for x in cell if x)
                out.append('<td>%s</td>' % _highlight(txt, required))
            out.append('</tr>')
        out.append('</table>')
        return
    for child in list(el):
        _walk_block(child, required, out)


def preview_docx(path: Path | str, required_keys: set[str] | None = None) -> dict:
    """Return {ok, html, text, placeholders, parts}."""
    p = Path(path)
    required = required_keys or {'projectName', 'ownerUnit', 'constructionUnit'}
    if not p.is_file():
        return {
            'ok': False, 'html': '', 'text': '', 'placeholders': [],
            'parts': [], 'error': 'file not found: %s' % p,
        }
    parts = []
    body_html: List[str] = []
    placeholders: List[str] = []
    texts: List[str] = []
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            if 'word/document.xml' not in names:
                return {
                    'ok': False, 'html': '', 'text': '', 'placeholders': [],
                    'parts': names, 'error': 'missing word/document.xml',
                }
            for name in names:
                if PART_RE.match(name):
                    parts.append(name)
            raw = FALLBACK.sub(b'', z.read('word/document.xml'))
            root = ET.fromstring(raw)
            body = root.find(W_BODY)
            nodes = list(body) if body is not None else list(root)
            for child in nodes:
                if child.tag.endswith('}sectPr'):
                    continue
                _walk_block(child, required, body_html)
            full = ''.join(t.text or '' for t in root.iter(W_T))
            texts.append(full)
            placeholders.extend(PH.findall(full))
    except zipfile.BadZipFile as e:
        return {
            'ok': False, 'html': '', 'text': '', 'placeholders': [],
            'parts': [], 'error': 'bad zip: %s' % e,
        }
    except ET.ParseError as e:
        return {
            'ok': False, 'html': '', 'text': '', 'placeholders': [],
            'parts': parts, 'error': 'xml: %s' % e,
        }
    html_body = '\n'.join(body_html) if body_html else '<p class="pg-p">（空文档）</p>'
    return {
        'ok': True,
        'html': html_body,
        'text': '\n'.join(texts),
        'placeholders': sorted(set(placeholders)),
        'parts': parts,
        'error': '',
    }


def docx_plain_lines(path: Path | str) -> List[str]:
    """Flatten a docx to plain lines for PDF export."""
    p = Path(path)
    lines: List[str] = []
    with zipfile.ZipFile(p) as z:
        raw = FALLBACK.sub(b'', z.read('word/document.xml'))
        root = ET.fromstring(raw)
        body = root.find(W_BODY)
        nodes = list(body) if body is not None else list(root)

        def walk(el):
            if el.tag == W_P:
                t = _para_text(el).replace('\u3000', ' ').rstrip()
                lines.append(t)
                return
            if el.tag == W_TBL:
                for tr in el.findall(W_TR):
                    cells = []
                    for tc in tr.findall(W_TC):
                        cells.append(' '.join(_para_text(p) for p in tc.iter(W_P)).strip())
                    lines.append('  |  '.join(cells))
                lines.append('')
                return
            for child in list(el):
                if child.tag.endswith('}sectPr'):
                    continue
                walk(child)

        for child in nodes:
            walk(child)
    return lines
