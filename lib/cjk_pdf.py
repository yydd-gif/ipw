# -*- coding: utf-8 -*-
"""Minimal CJK PDF writer: embed a TrueType font (Identity-H) so Chinese extracts.

Used by export_engine. Merge / overlay is done with pypdf; this module only
*creates* PDF bytes with an embedded system TTF so 中文 does not mojibake.
"""
from __future__ import annotations

import os
import struct
import zlib
from io import BytesIO
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

A4 = (595.276, 841.890)  # points


class CjkPdfError(RuntimeError):
    pass


def find_cjk_font() -> Path:
    env = os.environ.get('YANSHOU_CJK_FONT')
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.extend([
        Path('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'),
        Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc'),
        Path('/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf'),
        Path('/usr/share/fonts/truetype/arphic/uming.ttc'),
        Path('C:/Windows/Fonts/msyh.ttc'),
        Path('C:/Windows/Fonts/simsun.ttc'),
        Path('C:/Windows/Fonts/simhei.ttf'),
        Path('/System/Library/Fonts/STHeiti Light.ttc'),
        Path('/System/Library/Fonts/PingFang.ttc'),
    ])
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        raise CjkPdfError(
            'no CJK TrueType font found; set YANSHOU_CJK_FONT to a .ttf/.ttc path')
    return existing[0]


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from('>H', data, off)[0]


def _i16(data: bytes, off: int) -> int:
    return struct.unpack_from('>h', data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from('>I', data, off)[0]


def _read_ttf_or_ttc(path: Path) -> bytes:
    raw = Path(path).read_bytes()
    if raw[:4] == b'ttcf':
        # first font in collection
        num = _u32(raw, 8)
        if num < 1:
            raise CjkPdfError('empty TTC: %s' % path)
        off = _u32(raw, 12)
        return _slice_sfnt(raw, off)
    return raw


def _slice_sfnt(raw: bytes, offset: int) -> bytes:
    """Rebuild a standalone TTF from a TTC member (copy tables, recompute offsets)."""
    num_tables = _u16(raw, offset + 4)
    records = []
    p = offset + 12
    for _ in range(num_tables):
        tag = raw[p:p + 4]
        checksum = _u32(raw, p + 4)
        toff = _u32(raw, p + 8)
        length = _u32(raw, p + 12)
        records.append((tag, checksum, toff, length))
        p += 16
    out = bytearray()
    header = raw[offset:offset + 12]
    out.extend(header)
    out.extend(b'\x00' * (16 * num_tables))
    while len(out) % 4:
        out.append(0)
    new_records = []
    for tag, checksum, toff, length in records:
        while len(out) % 4:
            out.append(0)
        new_off = len(out)
        chunk = raw[toff:toff + length]
        out.extend(chunk)
        pad = (4 - (length % 4)) % 4
        out.extend(b'\x00' * pad)
        new_records.append((tag, checksum, new_off, length))
    # write table directory
    buf = bytearray(out)
    dp = 12
    for tag, checksum, new_off, length in new_records:
        buf[dp:dp + 4] = tag
        struct.pack_into('>I', buf, dp + 4, checksum)
        struct.pack_into('>I', buf, dp + 8, new_off)
        struct.pack_into('>I', buf, dp + 12, length)
        dp += 16
    return bytes(buf)


class TrueTypeFont:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = _read_ttf_or_ttc(self.path)
        self.tables = self._tables()
        self.units = 1000
        self.ascent = 800
        self.descent = -200
        self.bbox = (0, -200, 1000, 900)
        self.cmap: dict[int, int] = {}
        self.widths: list[int] = []
        self._parse_head()
        self._parse_hmtx()
        self._parse_cmap()

    def _tables(self) -> dict[bytes, tuple[int, int]]:
        data = self.data
        num = _u16(data, 4)
        out = {}
        p = 12
        for _ in range(num):
            tag = data[p:p + 4]
            off = _u32(data, p + 8)
            length = _u32(data, p + 12)
            out[tag] = (off, length)
            p += 16
        return out

    def _table(self, tag: bytes) -> bytes:
        if tag not in self.tables:
            raise CjkPdfError('TTF missing table %s' % tag)
        off, length = self.tables[tag]
        return self.data[off:off + length]

    def _parse_head(self) -> None:
        head = self._table(b'head')
        self.units = _u16(head, 18) or 1000
        x_min = _i16(head, 36)
        y_min = _i16(head, 38)
        x_max = _i16(head, 40)
        y_max = _i16(head, 42)
        self.bbox = (x_min, y_min, x_max, y_max)

    def _parse_hmtx(self) -> None:
        hhea = self._table(b'hhea')
        self.ascent = _i16(hhea, 4)
        self.descent = _i16(hhea, 6)
        n_metrics = _u16(hhea, 34)
        maxp = self._table(b'maxp')
        n_glyphs = _u16(maxp, 4)
        hmtx = self._table(b'hmtx')
        widths = []
        p = 0
        last = 0
        for i in range(n_glyphs):
            if i < n_metrics:
                last = _u16(hmtx, p)
                p += 4
            widths.append(last)
        self.widths = widths

    def _parse_cmap(self) -> None:
        cmap = self._table(b'cmap')
        num = _u16(cmap, 2)
        best = None
        p = 4
        for _ in range(num):
            plat = _u16(cmap, p)
            enc = _u16(cmap, p + 2)
            off = _u32(cmap, p + 4)
            fmt = _u16(cmap, off)
            p += 8
            score = 0
            if plat == 3 and enc == 1 and fmt == 4:
                score = 30
            elif plat == 3 and enc == 10 and fmt == 12:
                score = 40
            elif plat == 0 and fmt in (4, 12):
                score = 20
            elif fmt == 4:
                score = 10
            if best is None or score > best[0]:
                best = (score, fmt, off)
        if not best:
            raise CjkPdfError('no usable cmap')
        _score, fmt, off = best
        if fmt == 4:
            self.cmap = _parse_cmap_fmt4(cmap, off)
        elif fmt == 12:
            self.cmap = _parse_cmap_fmt12(cmap, off)
        else:
            raise CjkPdfError('unsupported cmap format %d' % fmt)

    def gid(self, ch: str) -> int:
        return self.cmap.get(ord(ch), 0)

    def width_em(self, ch: str) -> int:
        g = self.gid(ch)
        if g < len(self.widths):
            return self.widths[g]
        return self.units

    def width_pt(self, ch: str, size: float) -> float:
        return self.width_em(ch) * size / float(self.units)


def _parse_cmap_fmt4(cmap: bytes, off: int) -> dict[int, int]:
    seg_count = _u16(cmap, off + 6) // 2
    end_p = off + 14
    start_p = end_p + 2 * seg_count + 2
    delta_p = start_p + 2 * seg_count
    range_p = delta_p + 2 * seg_count
    mapping = {}
    for i in range(seg_count):
        end = _u16(cmap, end_p + 2 * i)
        start = _u16(cmap, start_p + 2 * i)
        delta = _i16(cmap, delta_p + 2 * i)
        range_off = _u16(cmap, range_p + 2 * i)
        for c in range(start, end + 1):
            if range_off == 0:
                gid = (c + delta) & 0xFFFF
            else:
                glyph_pos = range_p + 2 * i + range_off + 2 * (c - start)
                gid = _u16(cmap, glyph_pos)
                if gid != 0:
                    gid = (gid + delta) & 0xFFFF
            if gid:
                mapping[c] = gid
    return mapping


def _parse_cmap_fmt12(cmap: bytes, off: int) -> dict[int, int]:
    n_groups = _u32(cmap, off + 12)
    mapping = {}
    p = off + 16
    for _ in range(n_groups):
        start = _u32(cmap, p)
        end = _u32(cmap, p + 4)
        glyph = _u32(cmap, p + 8)
        p += 12
        for c in range(start, end + 1):
            mapping[c] = glyph + (c - start)
    return mapping


def _pdf_escape_name(name: str) -> str:
    out = []
    for ch in name.encode('ascii', 'replace').decode('ascii'):
        if ch.isalnum() or ch in '_-':
            out.append(ch)
        else:
            out.append('#%02X' % ord(ch))
    return ''.join(out)


def _tounicode_cmap(pairs: Sequence[Tuple[int, int]]) -> bytes:
    """pairs: (gid, unicode_cp)."""
    lines = [
        '/CIDInit /ProcSet findresource begin',
        '12 dict begin',
        'begincmap',
        '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def',
        '/CMapName /Adobe-Identity-UCS def',
        '/CMapType 2 def',
        '1 begincodespacerange',
        '<0000> <FFFF>',
        'endcodespacerange',
    ]
    chunk = []
    for gid, cp in pairs:
        if gid == 0:
            continue
        chunk.append('<%04X> <%04X>' % (gid, cp))
        if len(chunk) == 100:
            lines.append('%d beginbfchar' % len(chunk))
            lines.extend(chunk)
            lines.append('endbfchar')
            chunk = []
    if chunk:
        lines.append('%d beginbfchar' % len(chunk))
        lines.extend(chunk)
        lines.append('endbfchar')
    lines.extend([
        'endcmap',
        'CMapName currentdict /CMap defineresource pop',
        'end',
        'end',
    ])
    return ('\n'.join(lines) + '\n').encode('ascii')


def wrap_line(text: str, font: TrueTypeFont, size: float, max_width: float) -> List[str]:
    if not text:
        return ['']
    lines: List[str] = []
    cur = ''
    w = 0.0
    for ch in text:
        if ch in '\r':
            continue
        if ch == '\n':
            lines.append(cur)
            cur, w = '', 0.0
            continue
        cw = font.width_pt(ch, size)
        if cur and w + cw > max_width:
            lines.append(cur)
            cur, w = ch, cw
        else:
            cur += ch
            w += cw
    lines.append(cur)
    return lines or ['']


def _hex_gids(text: str, font: TrueTypeFont) -> str:
    parts = []
    for ch in text:
        gid = font.gid(ch)
        parts.append('%04X' % gid)
    return ''.join(parts)


class _Pdf:
    def __init__(self):
        self.objs: List[bytes] = [b'']  # 1-based

    def add(self, body: bytes) -> int:
        self.objs.append(body)
        return len(self.objs) - 1

    def dumps(self) -> bytes:
        buf = BytesIO()
        buf.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
        offsets = [0]
        for i, body in enumerate(self.objs):
            if i == 0:
                continue
            offsets.append(buf.tell())
            buf.write(b'%d 0 obj\n' % i)
            buf.write(body)
            if not body.endswith(b'\n'):
                buf.write(b'\n')
            buf.write(b'endobj\n')
        xref = buf.tell()
        n = len(self.objs)
        buf.write(b'xref\n0 %d\n' % n)
        buf.write(b'0000000000 65535 f \n')
        for i in range(1, n):
            buf.write(b'%010d 00000 n \n' % offsets[i])
        buf.write(
            b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (
                n, xref))
        return buf.getvalue()


def _stream(data: bytes, extra: str = '') -> bytes:
    comp = zlib.compress(data)
    header = '<< /Length %d /Filter /FlateDecode %s >>' % (len(comp), extra)
    return header.encode('ascii') + b'\nstream\n' + comp + b'\nendstream'


def build_text_pdf(
    pages: Sequence[Sequence[str]],
    font: TrueTypeFont,
    *,
    size: float = 11.0,
    leading: float = 16.0,
    page_size: Tuple[float, float] = A4,
    margin: float = 54.0,
    footer: Sequence[str] | None = None,
    footer_size: float = 9.0,
) -> bytes:
    """pages: list of pages, each a list of already-wrapped lines."""
    used_pairs = {}
    for page in pages:
        for line in page:
            for ch in line:
                g = font.gid(ch)
                if g:
                    used_pairs[g] = ord(ch)
    if footer:
        for ft in footer:
            for ch in ft:
                g = font.gid(ch)
                if g:
                    used_pairs[g] = ord(ch)
    # always include a space
    used_pairs.setdefault(font.gid(' '), ord(' '))

    pdf = _Pdf()
    # 1 Catalog, 2 Pages — filled later
    pdf.add(b'<< /Type /Catalog /Pages 2 0 R >>')
    pdf.add(b'placeholder')

    font_file_id = pdf.add(_stream(font.data, '/Length1 %d' % len(font.data)))
    bbox = '[%d %d %d %d]' % font.bbox
    fd_body = (
        '<< /Type /FontDescriptor /FontName /F1CJK /Flags 4 '
        '/FontBBox %s /ItalicAngle 0 /Ascent %d /Descent %d '
        '/CapHeight %d /StemV 80 /FontFile2 %d 0 R >>' % (
            bbox, font.ascent, font.descent, max(font.ascent, 700), font_file_id)
    ).encode('ascii')
    fd_id = pdf.add(fd_body)

    # W array for used gids (contiguous runs)
    gids = sorted(used_pairs)
    w_parts = []
    i = 0
    while i < len(gids):
        start = gids[i]
        run = [font.widths[start] if start < len(font.widths) else font.units]
        i += 1
        while i < len(gids) and gids[i] == gids[i - 1] + 1:
            g = gids[i]
            run.append(font.widths[g] if g < len(font.widths) else font.units)
            i += 1
        w_parts.append('%d [%s]' % (start, ' '.join(str(x) for x in run)))
    w_arr = ' '.join(w_parts) if w_parts else '0 [500]'
    cid_id = pdf.add((
        '<< /Type /Font /Subtype /CIDFontType2 /BaseFont /F1CJK '
        '/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> '
        '/FontDescriptor %d 0 R /DW %d /W [%s] /CIDToGIDMap /Identity >>' % (
            fd_id, font.units, w_arr)
    ).encode('ascii'))
    uni_id = pdf.add(_stream(_tounicode_cmap(sorted(used_pairs.items()))))
    type0_id = pdf.add((
        '<< /Type /Font /Subtype /Type0 /BaseFont /F1CJK /Encoding /Identity-H '
        '/DescendantFonts [%d 0 R] /ToUnicode %d 0 R >>' % (cid_id, uni_id)
    ).encode('ascii'))

    pw, ph = page_size
    page_ids = []
    n_pages = max(1, len(pages))
    for pi in range(n_pages):
        lines = list(pages[pi]) if pi < len(pages) else ['']
        cmds = ['BT', '/F1 %.2f Tf' % size, '%.2f TL' % leading]
        x = margin
        y = ph - margin - size
        cmds.append('1 0 0 1 %.2f %.2f Tm' % (x, y))
        first = True
        for line in lines:
            hexg = _hex_gids(line, font)
            if not first:
                cmds.append('T*')
            first = False
            cmds.append('<%s> Tj' % hexg)
        cmds.append('ET')
        if footer and pi < len(footer) and footer[pi]:
            ft = footer[pi]
            cmds.extend([
                'BT', '/F1 %.2f Tf' % footer_size,
                '1 0 0 1 %.2f %.2f Tm' % (pw / 2.0 - 40, 28),
                '<%s> Tj' % _hex_gids(ft, font),
                'ET',
            ])
        content = ('\n'.join(cmds) + '\n').encode('ascii')
        c_id = pdf.add(_stream(content))
        page_body = (
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] '
            '/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>' % (
                pw, ph, type0_id, c_id)
        ).encode('ascii')
        page_ids.append(pdf.add(page_body))

    kids = ' '.join('%d 0 R' % i for i in page_ids)
    pdf.objs[2] = (
        '<< /Type /Pages /Count %d /Kids [%s] >>' % (len(page_ids), kids)
    ).encode('ascii')
    return pdf.dumps()


def paginate_lines(
    lines: Iterable[str],
    font: TrueTypeFont,
    *,
    size: float = 11.0,
    leading: float = 16.0,
    page_size: Tuple[float, float] = A4,
    margin: float = 54.0,
) -> List[List[str]]:
    pw, ph = page_size
    max_w = pw - 2 * margin
    max_lines = max(1, int((ph - 2 * margin - 24) / leading))
    wrapped: List[str] = []
    for raw in lines:
        wrapped.extend(wrap_line(raw.replace('\t', '    '), font, size, max_w))
    pages: List[List[str]] = []
    for i in range(0, len(wrapped) or 1, max_lines):
        chunk = wrapped[i:i + max_lines]
        pages.append(chunk or [''])
    if not pages:
        pages = [['']]
    return pages


def lines_to_pdf(lines: Iterable[str], font: TrueTypeFont, **kwargs) -> bytes:
    pages = paginate_lines(lines, font, **{
        k: kwargs[k] for k in ('size', 'leading', 'page_size', 'margin') if k in kwargs
    })
    return build_text_pdf(pages, font, **kwargs)
