# -*- coding: utf-8 -*-
"""子表识别与行克隆（数据与规则规格.md §2.4 / 软件设计方案 §4.4）.

按 tables[].columns 表头列名识别 8 张清单表，接管表头下、表尾上的数据行：
  不足 → 克隆首个数据行（连同 trPr/tcPr，不动 w:tblGrid）
  多余 → 删除末行
逐格按列号（grid 起点）写入，以处理 gridSpan / vMerge。

空数组：原样保留静态表，不删行。
"""
from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from lib.field_dict import FieldDict, TableSpec, load_field_dict
from lib.rule_engine import TABLE_ASSET_MAP

WNS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'
W_T = '{%s}t' % WNS
W_P = '{%s}p' % WNS
W_R = '{%s}r' % WNS
W_TBL = '{%s}tbl' % WNS
W_TR = '{%s}tr' % WNS
W_TC = '{%s}tc' % WNS
W_TBLPR = '{%s}tblPr' % WNS
W_TBLGRID = '{%s}tblGrid' % WNS
W_GRIDCOL = '{%s}gridCol' % WNS
W_TCPR = '{%s}tcPr' % WNS
W_TRPR = '{%s}trPr' % WNS
W_GRIDSPAN = '{%s}gridSpan' % WNS
W_VMERGE = '{%s}vMerge' % WNS
W_BODY = '{%s}body' % WNS
W_RPR = '{%s}rPr' % WNS
W_RFONTS = '{%s}rFonts' % WNS
W_TCBORDERS = '{%s}tcBorders' % WNS
W_TBLBORDERS = '{%s}tblBorders' % WNS
W_TCW = '{%s}tcW' % WNS
DECL_RE = re.compile(rb'^<\?xml[^?]*\?>')
PART_RE = re.compile(r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')

TAIL_MARKERS = (
    '会签栏', '会签', '备忘记录',
    '承建单位意见', '监理单位意见', '建设单位意见',
    '专家意见', '评分说明', '合计得分',
)
STICKY_AFTER_HEADER = ('总计',)

TABLE_KEYS = (
    'deviceList', 'softwareList', 'testItemList', 'trialRunList',
    'expertScoreList', 'documentList', 'documentChecklist', 'volumeList',
)


def w(tag: str) -> str:
    return '{%s}%s' % (WNS, tag)


def register_ns(raw: bytes) -> None:
    try:
        for _event, (prefix, uri) in ET.iterparse(io.BytesIO(raw), events=['start-ns']):
            if prefix:
                try:
                    ET.register_namespace(prefix, uri)
                except ValueError:
                    pass
    except ET.ParseError:
        pass


def clone_el(el: ET.Element) -> ET.Element:
    n = ET.Element(el.tag, dict(el.attrib))
    n.text = el.text
    n.tail = el.tail
    for ch in el:
        n.append(clone_el(ch))
    return n


def cell_text(tc: ET.Element) -> str:
    return ''.join(t.text or '' for t in tc.iter(W_T))


def para_text(p: ET.Element) -> str:
    return ''.join(t.text or '' for t in p.iter(W_T))


def norm_header(s: str) -> str:
    """Ignore leading/trailing whitespace and full-width spaces; keep 全角括号."""
    return re.sub(r'[\s\u3000]+', '', s or '')


def grid_span(tc: ET.Element) -> int:
    tcpr = tc.find(W_TCPR)
    if tcpr is None:
        return 1
    gs = tcpr.find(W_GRIDSPAN)
    if gs is None:
        return 1
    try:
        return max(1, int(gs.get(w('val')) or gs.get('val') or 1))
    except (TypeError, ValueError):
        return 1


def vmerge_val(tc: ET.Element) -> Optional[str]:
    tcpr = tc.find(W_TCPR)
    if tcpr is None:
        return None
    vm = tcpr.find(W_VMERGE)
    if vm is None:
        return None
    return vm.get(w('val')) or vm.get('val') or 'cont'


def row_cells(tr: ET.Element) -> List[Tuple[int, int, ET.Element, str]]:
    """Return (grid_start, span, tc, text) for each cell in row order."""
    out = []
    col = 0
    for tc in tr.findall(W_TC):
        span = grid_span(tc)
        out.append((col, span, tc, cell_text(tc)))
        col += span
    return out


def cell_at_grid(tr: ET.Element, grid_col: int) -> Optional[ET.Element]:
    col = 0
    for tc in tr.findall(W_TC):
        span = grid_span(tc)
        if col <= grid_col < col + span:
            return tc
        col += span
    return None


def set_cell_text(tc: ET.Element, text: str) -> None:
    """Write visible text, keep first run's rPr (font). Clear extra w:t."""
    text = '' if text is None else str(text)
    ps = [el for el in tc if el.tag == W_P]
    if not ps:
        p = ET.SubElement(tc, W_P)
        r = ET.SubElement(p, W_R)
        t = ET.SubElement(r, W_T)
        t.text = text
        if text != text.strip():
            t.set(XML_SPACE, 'preserve')
        return
    first = ps[0]
    ts = list(first.iter(W_T))
    if not ts:
        r = None
        for el in first:
            if el.tag == W_R:
                r = el
                break
        if r is None:
            r = ET.SubElement(first, W_R)
        t = ET.SubElement(r, W_T)
        ts = [t]
    ts[0].text = text
    if text and text != text.strip():
        ts[0].set(XML_SPACE, 'preserve')
    elif XML_SPACE in ts[0].attrib and (not text or text == text.strip()):
        del ts[0].attrib[XML_SPACE]
    for extra in ts[1:]:
        extra.text = ''
    for p in ps[1:]:
        for t in p.iter(W_T):
            t.text = ''


def tbl_grid_widths(tbl: ET.Element) -> List[str]:
    g = tbl.find(W_TBLGRID)
    if g is None:
        return []
    return [gc.get(w('w')) or gc.get('w') or '' for gc in g.findall(W_GRIDCOL)]


def row_concat(tr: ET.Element) -> str:
    return norm_header(''.join(cell_text(tc) for tc in tr.findall(W_TC)))


def is_tail_row(tr: ET.Element) -> bool:
    raw = ''.join(cell_text(tc) for tc in tr.findall(W_TC))
    compact = norm_header(raw)
    for m in TAIL_MARKERS:
        if compact.startswith(norm_header(m)) or compact == norm_header(m):
            return True
        # 意见/会签 often occupy a full-span first cell
    first = ''
    tcs = tr.findall(W_TC)
    if tcs:
        first = norm_header(cell_text(tcs[0]))
    for m in TAIL_MARKERS:
        nm = norm_header(m)
        if first.startswith(nm):
            return True
    return False


def is_sticky_row(tr: ET.Element) -> bool:
    compact = row_concat(tr)
    return any(norm_header(s) in compact for s in STICKY_AFTER_HEADER)


def match_header(tr: ET.Element, columns: Sequence[str]) -> Optional[List[int]]:
    """If this row is the header, return grid_start for each column. Else None."""
    cells = row_cells(tr)
    nonempty = [(g, sp, tc, norm_header(txt)) for g, sp, tc, txt in cells if norm_header(txt)]
    wanted = [norm_header(c) for c in columns]
    if not wanted:
        return None
    texts = [c[3] for c in nonempty]
    for i in range(0, len(texts) - len(wanted) + 1):
        if texts[i:i + len(wanted)] == wanted:
            return [nonempty[i + j][0] for j in range(len(wanted))]
    return None


def table_rows(tbl: ET.Element) -> List[ET.Element]:
    return [el for el in tbl if el.tag == W_TR]


def detect_table(tbl: ET.Element, spec: TableSpec) -> Optional[dict]:
    rows = table_rows(tbl)
    header_i = None
    mapping = None
    for i, tr in enumerate(rows[:12]):
        m = match_header(tr, spec.columns)
        if m is not None:
            header_i = i
            mapping = m
            break
    if header_i is None or mapping is None:
        return None
    data_start = header_i + 1
    if data_start < len(rows) and is_sticky_row(rows[data_start]):
        data_start += 1
    data_end = len(rows)
    for j in range(data_start, len(rows)):
        if is_tail_row(rows[j]):
            data_end = j
            break
    return {
        'key': spec.key,
        'label': spec.label,
        'columns': list(spec.columns),
        'header_index': header_i,
        'data_start': data_start,
        'data_end': data_end,
        'mapping': mapping,
        'n_data': max(0, data_end - data_start),
        'grid': tbl_grid_widths(tbl),
    }


def detect_all(root: ET.Element, tables: Dict[str, TableSpec],
               only: str = '') -> List[Tuple[ET.Element, dict]]:
    hits = []
    used = set()
    for tbl in root.iter(W_TBL):
        for key, spec in tables.items():
            if only and key != only:
                continue
            if key in used:
                continue
            info = detect_table(tbl, spec)
            if info:
                hits.append((tbl, info))
                used.add(key)
                break
    return hits


def _row_values(row: Any, columns: Sequence[str]) -> List[str]:
    if isinstance(row, dict):
        out = []
        for c in columns:
            if c in row and row[c] not in (None,):
                out.append(str(row[c]))
            else:
                # tolerate ascii parens vs fullwidth
                alt = c.replace('（', '(').replace('）', ')')
                out.append('' if row.get(alt) in (None,) else str(row.get(alt, '')))
        return out
    if isinstance(row, (list, tuple)):
        vals = ['' if v is None else str(v) for v in row]
        if len(vals) < len(columns):
            vals += [''] * (len(columns) - len(vals))
        return vals[:len(columns)]
    return [str(row)] + [''] * (len(columns) - 1)


def fill_table(tbl: ET.Element, info: dict, rows: Sequence[Any]) -> dict:
    """Resize data region to len(rows) and write cells. Empty rows → no-op."""
    trs = table_rows(tbl)
    start = info['data_start']
    end = info['data_end']
    columns = info['columns']
    mapping = info['mapping']
    before_n = max(0, end - start)
    grid_before = tbl_grid_widths(tbl)

    if not rows:
        return {
            'key': info['key'],
            'rowsIn': 0,
            'rowsOut': before_n,
            'unchanged': True,
            'grid': grid_before,
        }

    n = len(rows)
    data_trs = trs[start:end]
    if not data_trs:
        # no template data row: clone header and clear text
        proto = clone_el(trs[info['header_index']])
        for tc in proto.findall(W_TC):
            set_cell_text(tc, '')
        data_trs = [proto]
        # insert at start
        header_el = trs[info['header_index']]
        idx = list(tbl).index(header_el)
        tbl.insert(idx + 1, proto)
        trs = table_rows(tbl)
        start = info['header_index'] + 1
        end = start
        data_trs = trs[start:end]
        # sticky may have shifted; re-read
        if start < len(trs) and is_sticky_row(trs[start]):
            start += 1
        data_trs = trs[start:end] if end > start else [proto]
        before_n = len(data_trs)

    proto = data_trs[0]
    parent_index = list(tbl).index(data_trs[0])

    if n < before_n:
        for extra in data_trs[n:]:
            tbl.remove(extra)
    elif n > before_n:
        # insert clones after current last data row
        last = data_trs[-1]
        insert_at = list(tbl).index(last) + 1
        for _ in range(n - before_n):
            cloned = clone_el(proto)
            tbl.insert(insert_at, cloned)
            insert_at += 1

    trs = table_rows(tbl)
    # data region is now n rows starting at start (start index stable:
    # we only removed/inserted inside the region)
    live = trs[start:start + n]
    written = 0
    for i, (tr, row) in enumerate(zip(live, rows)):
        vals = _row_values(row, columns)
        for col_i, grid_col in enumerate(mapping):
            tc = cell_at_grid(tr, grid_col)
            if tc is None:
                continue
            if vmerge_val(tc) == 'cont' or (vmerge_val(tc) is not None and vmerge_val(tc) != 'restart'):
                # continuation merge: skip unless restart/None
                if vmerge_val(tc) not in (None, 'restart'):
                    continue
            set_cell_text(tc, vals[col_i])
            written += 1

    grid_after = tbl_grid_widths(tbl)
    return {
        'key': info['key'],
        'rowsIn': n,
        'rowsOut': n,
        'unchanged': False,
        'cellsWritten': written,
        'grid': grid_after,
        'gridUnchanged': grid_before == grid_after,
        'headerIndex': info['header_index'],
        'clonedFromEmpty': before_n,
    }


def serialize_part(raw: bytes, root: ET.Element) -> bytes:
    body = ET.tostring(root, encoding='utf-8', xml_declaration=False)
    dm = DECL_RE.match(raw)
    decl = dm.group(0) if dm else b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    return decl + body


def rewrite_docx(src: Path, dst: Path, mutate) -> None:
    """Zip → XML → zip. Preserve ZipInfo order; never touch tblGrid ourselves."""
    with zipfile.ZipFile(src) as zin:
        items = zin.infolist()
        contents = {it.filename: zin.read(it.filename) for it in items}

    mutate(contents)

    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        written = set()
        for it in items:
            zout.writestr(it, contents[it.filename])
            written.add(it.filename)
        for name, data in contents.items():
            if name not in written:
                zout.writestr(name, data)


def apply_subtables(src: Path, dst: Path, field_dict: FieldDict,
                    data_by_key: Dict[str, List[Any]],
                    only: str = '') -> dict:
    """Apply matching subtables. data_by_key values that are None mean skip;
    empty list means keep static."""
    applied = []
    skipped = []

    def mutate(contents: dict) -> None:
        for name in list(contents):
            if not PART_RE.match(name):
                continue
            raw = contents[name]
            try:
                register_ns(raw)
                root = ET.fromstring(raw)
            except ET.ParseError:
                continue
            hits = detect_all(root, field_dict.tables, only=only)
            if not hits:
                continue
            changed = False
            for tbl, info in hits:
                key = info['key']
                if key not in data_by_key:
                    skipped.append({'key': key, 'reason': 'no data', 'nData': info['n_data']})
                    continue
                rows = data_by_key[key]
                if rows is None:
                    skipped.append({'key': key, 'reason': 'skip', 'nData': info['n_data']})
                    continue
                rec = fill_table(tbl, info, rows)
                rec['part'] = name
                applied.append(rec)
                if not rec.get('unchanged'):
                    changed = True
            if changed:
                contents[name] = serialize_part(raw, root)

    rewrite_docx(src, dst, mutate)
    return {'applied': applied, 'skipped': skipped}


def load_rows_file(path: Path, table_key: str = '') -> Dict[str, List[dict]]:
    """JSON (list / {key:[]} / project.json) or CSV → {tableKey: rows}."""
    suffix = path.suffix.lower()
    if suffix in ('.csv', '.tsv'):
        delim = '\t' if suffix == '.tsv' else ','
        with path.open(encoding='utf-8-sig', newline='') as fh:
            reader = csv.DictReader(fh, delimiter=delim)
            rows = [dict(r) for r in reader]
        key = table_key or 'rows'
        return {key: rows}
    data = json.loads(path.read_text(encoding='utf-8'))
    return extract_asset_rows(data, table_key=table_key)


def extract_asset_rows(data: Any, table_key: str = '') -> Dict[str, List[dict]]:
    """Pull subtable rows out of a JSON blob (list, map, or project.json)."""
    if isinstance(data, list):
        key = table_key or 'rows'
        return {key: [r for r in data if isinstance(r, dict) or isinstance(r, list)]}
    if not isinstance(data, dict):
        return {}
    assets = data.get('_assets') if isinstance(data.get('_assets'), dict) else data
    out: Dict[str, List[dict]] = {}
    keys = (table_key,) if table_key else TABLE_KEYS
    for key in keys:
        rows = None
        if key in assets and isinstance(assets[key], list):
            rows = assets[key]
        else:
            for alias in TABLE_ASSET_MAP.get(key, ()):
                if alias in assets and isinstance(assets[alias], list):
                    rows = assets[alias]
                    break
        if rows is None and key in data and isinstance(data[key], list):
            rows = data[key]
        if rows is not None:
            out[key] = [r for r in rows if isinstance(r, (dict, list))]
    return out


def assets_from_project(project: dict) -> Dict[str, List[dict]]:
    return extract_asset_rows(project)


def build_empty_table_docx(columns: Sequence[str], empty_rows: int = 6,
                           span_at: int = -1) -> bytes:
    """Minimal docx: header + N empty data rows. Optional gridSpan on one column.

    Used by P5 regression (3→3 / 10→10 on a 6-row empty table). Not a template.
    """
    n = len(columns)
    # extra grid col when spanning
    grid_n = n + (1 if 0 <= span_at < n else 0)
    col_w = 1200
    grid_xml = ''.join(
        '<w:gridCol w:w="%d"/>' % col_w for _ in range(grid_n))
    border = (
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
    )
    rpr = (
        '<w:rPr><w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/>'
        '<w:sz w:val="21"/></w:rPr>'
    )

    def tc_xml(text: str, span: int = 1) -> str:
        span_xml = ('<w:gridSpan w:val="%d"/>' % span) if span > 1 else ''
        width = col_w * span
        return (
            '<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s'
            '<w:tcBorders>%s</w:tcBorders></w:tcPr>'
            '<w:p><w:r>%s<w:t xml:space="preserve">%s</w:t></w:r></w:p></w:tc>'
            % (width, span_xml, border, rpr, escape(text))
        )

    def tr_xml(texts: Sequence[str]) -> str:
        cells = []
        for i, t in enumerate(texts):
            span = 2 if i == span_at else 1
            cells.append(tc_xml(t, span))
        return '<w:tr>%s</w:tr>' % ''.join(cells)

    header = tr_xml(list(columns))
    data = ''.join(tr_xml([''] * n) for _ in range(empty_rows))
    tbl = (
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        '<w:tblBorders>%s</w:tblBorders></w:tblPr>'
        '<w:tblGrid>%s</w:tblGrid>%s%s</w:tbl>'
        % (border, grid_xml, header, data)
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="%s"><w:body>%s'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1440" w:right="1800" w:bottom="1440" w:left="1800"/>'
        '</w:sectPr></w:body></w:document>'
    ) % (WNS, tbl)
    ct = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
'''
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', ct.encode('utf-8'))
        z.writestr('_rels/.rels', rels.encode('utf-8'))
        z.writestr('word/document.xml', document.encode('utf-8'))
    return buf.getvalue()


def inspect_docx_tables(path: Path, field_dict: FieldDict) -> List[dict]:
    with zipfile.ZipFile(path) as z:
        raw = z.read('word/document.xml')
    register_ns(raw)
    root = ET.fromstring(raw)
    return [info for _tbl, info in detect_all(root, field_dict.tables)]
