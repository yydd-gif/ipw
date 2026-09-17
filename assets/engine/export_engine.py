#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出引擎 · 单份 / 整册 PDF（pypdf 合并 + 页码；中文嵌入 TTF）.

规格意图：软件设计方案-v2.0.md §5.6 / 施工交接说明 §6 P4
  python assets/engine/export_engine.py --project work/proj/project.json --mode booklet --json
  python assets/engine/export_engine.py --project work/proj/project.json --mode single --doc-id D-KGBSB-01 --json
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime
from pathlib import Path

# Windows embeddable CPython (python._pth) omits the script dir from sys.path.
_HERE = Path(__file__).resolve().parent
for _p in (_HERE.parent.parent, _HERE):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from _common import (
    BASE, TemplateProtectionError, assert_not_template_write,
    emit_progress, emit_result, exit_env, exit_param, result_payload,
)

REPO = BASE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from lib.cjk_pdf import (  # noqa: E402
    CjkPdfError, TrueTypeFont, build_text_pdf, find_cjk_font, paginate_lines,
)
from lib.docx_preview import docx_plain_lines  # noqa: E402
from lib.project_store import ProjectStoreError, read_project, write_project  # noqa: E402

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore
    PdfWriter = None  # type: ignore


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _load_pypdf():
    if PdfReader is None or PdfWriter is None:
        raise RuntimeError('缺少 pypdf：请 pip install pypdf')


def _project_root(project_path: Path) -> Path:
    return project_path.parent


def _live_docs(project: dict) -> list:
    trash = set()
    for t in project.get('_trash') or []:
        if isinstance(t, dict) and t.get('docId'):
            trash.add(t['docId'])
        for d in t.get('documents') or []:
            if isinstance(d, dict) and d.get('docId'):
                trash.add(d['docId'])
    items = []
    for did, rec in (project.get('_docs') or {}).items():
        if did in trash or not isinstance(rec, dict):
            continue
        items.append((did, rec))
    snap = (project.get('_catalogSnapshot') or {}).get('items') or []
    order = {it.get('itemId'): (it.get('volumeSeq') or 99, it.get('seq') or 99)
             for it in snap if isinstance(it, dict)}
    items.sort(key=lambda kv: (
        order.get(kv[1].get('itemId'), (99, 99)),
        kv[1].get('relPath') or '',
        kv[0],
    ))
    return items


def _docx_path(root: Path, rec: dict) -> Path | None:
    rel = rec.get('relPath') or ''
    if not rel or not rel.lower().endswith('.docx'):
        return None
    p = root / rel
    return p if p.is_file() else None


def _verify_blocks(project_path: Path, root: Path) -> list:
    """Spawn verify_engine; return block-level errors (empty if verify ok / missing)."""
    import json
    import subprocess
    engine = BASE / 'engine' / 'verify_engine.py'
    if not engine.is_file():
        return []
    proc = subprocess.run(
        [sys.executable, str(engine), '--dir', str(root),
         '--project', str(project_path), '--json'],
        cwd=str(REPO), capture_output=True, text=True, encoding='utf-8',
        env={**__import__('os').environ, 'PYTHONUTF8': '1'},
    )
    text = (proc.stdout or '').strip()
    if not text:
        return [{'reason': 'verify produced no JSON', 'level': 'block'}]
    last = [ln for ln in text.splitlines() if ln.strip()][-1]
    try:
        payload = json.loads(last)
    except json.JSONDecodeError:
        return [{'reason': 'verify JSON parse failed', 'level': 'block'}]
    errs = []
    for e in payload.get('errors') or []:
        if (e.get('level') or 'block') == 'block':
            errs.append(e)
    if proc.returncode not in (0, 1, 2, 3) and not errs:
        errs.append({'reason': 'verify exit %d' % proc.returncode, 'level': 'block'})
    return errs


def _required_missing(project: dict) -> list:
    missing = []
    for key in ('projectName', 'ownerUnit', 'constructionUnit'):
        if not str(project.get(key) or '').strip():
            missing.append(key)
    return missing


def _render_docx_pdf(docx: Path, font: TrueTypeFont, title: str) -> tuple[bytes, int]:
    lines = [title, ''] + docx_plain_lines(docx)
    pages = paginate_lines(lines, font)
    pdf = build_text_pdf(pages, font)
    return pdf, len(pages)


def _toc_pdf(entries: list, font: TrueTypeFont, toc_pages_guess: int) -> tuple[bytes, int]:
    lines = ['整册目录', '', '序号  目录项                              页码']
    for i, e in enumerate(entries, 1):
        name = e['title']
        page = e['page']
        pad = max(2, 36 - len(name))
        lines.append('%02d  %s%s%d' % (i, name, '·' * pad, page))
    pages = paginate_lines(lines, font)
    return build_text_pdf(pages, font), len(pages)


def _merge_pdfs(blobs: list[bytes]) -> bytes:
    _load_pypdf()
    writer = PdfWriter()
    for blob in blobs:
        reader = PdfReader(io.BytesIO(blob))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _stamp_page_numbers(blob: bytes, font: TrueTypeFont) -> bytes:
    _load_pypdf()
    reader = PdfReader(io.BytesIO(blob))
    n = len(reader.pages)
    labels = ['第 %d 页 / 共 %d 页' % (i + 1, n) for i in range(n)]
    # one-line pages matching A4
    stamp_pages = [[''] for _ in labels]
    stamp = build_text_pdf(stamp_pages, font, footer=labels, footer_size=9.0)
    stamps = PdfReader(io.BytesIO(stamp))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        page.merge_page(stamps.pages[i])
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _extract_text_sample(blob: bytes, limit: int = 2000) -> str:
    _load_pypdf()
    reader = PdfReader(io.BytesIO(blob))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or '')
        except Exception:
            parts.append('')
        if sum(len(x) for x in parts) > limit:
            break
    return '\n'.join(parts)


def export_docs(project_path: Path, mode: str, out: Path, doc_id: str = '',
                toc: bool = True, page_numbers: bool = True,
                force: bool = False, mark_printed: bool = False) -> dict:
    project = read_project(project_path, apply_migration=False)
    root = _project_root(project_path)
    missing_req = _required_missing(project)
    if missing_req and not force:
        raise ValueError('必填缺失：%s（勾选忽略必填或补齐后再导出）' % '、'.join(missing_req))

    live = _live_docs(project)
    if mode == 'single':
        if not doc_id:
            raise ValueError('single 模式需要 --doc-id')
        live = [(d, r) for d, r in live if d == doc_id]
        if not live:
            raise ValueError('找不到文档 %s' % doc_id)
        toc = False

    files = []
    for did, rec in live:
        p = _docx_path(root, rec)
        if p is None:
            continue
        files.append((did, rec, p))
    if not files:
        raise ValueError('没有可导出的 docx（先一键成册）')

    font = TrueTypeFont(find_cjk_font())
    rendered = []
    page_map = []
    cursor = 1
    emit_progress(0, len(files) + 2, 'load font %s' % font.path.name)

    # first pass without TOC to get page counts
    for i, (did, rec, p) in enumerate(files, 1):
        title = Path(p).stem
        blob, n = _render_docx_pdf(p, font, title)
        rendered.append((did, rec, blob, n, title))
        page_map.append({'docId': did, 'title': title, 'pages': n, 'start': 0})
        emit_progress(i, len(files) + 2, title)

    toc_pages = 0
    blobs = []
    if toc:
        # guess toc length
        guess = 1
        for _ in range(3):
            entries = []
            start = guess + 1
            for pm, (_did, _rec, _blob, n, title) in zip(page_map, rendered):
                entries.append({'title': title, 'page': start})
                start += n
            toc_blob, toc_pages = _toc_pdf(entries, font, guess)
            if toc_pages == guess:
                break
            guess = toc_pages
        blobs.append(toc_blob)
        cursor = toc_pages + 1
    else:
        cursor = 1

    for pm, (did, rec, blob, n, title) in zip(page_map, rendered):
        pm['start'] = cursor
        blobs.append(blob)
        cursor += n

    emit_progress(len(files) + 1, len(files) + 2, 'merge')
    merged = _merge_pdfs(blobs)
    if page_numbers:
        merged = _stamp_page_numbers(merged, font)

    assert_not_template_write(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(merged)

    sample = _extract_text_sample(merged)
    n_pages = len(PdfReader(io.BytesIO(merged)).pages)

    marked = []
    if mark_printed:
        states = project.setdefault('_printStates', {})
        now = _now()
        for did, rec, _p in files:
            prev = states.get(did) or {}
            states[did] = {
                'printed': True,
                'printedAt': now,
                'times': int(prev.get('times') or 0) + 1,
            }
            marked.append(did)
        write_project(project_path, project, backup=True)

    emit_progress(len(files) + 2, len(files) + 2, out.name)
    return {
        'out': str(out),
        'pages': n_pages,
        'docs': len(files),
        'tocPages': toc_pages,
        'pageMap': page_map,
        'font': str(font.path),
        'sample': sample[:400],
        'markedPrinted': marked,
        'chineseOk': any('\u4e00' <= ch <= '\u9fff' for ch in sample),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='export_engine · 单份/整册 PDF')
    ap.add_argument('--project', type=Path)
    ap.add_argument('--mode', choices=('booklet', 'single'), default='booklet')
    ap.add_argument('--doc-id', dest='doc_id', default='')
    ap.add_argument('--out', type=Path)
    ap.add_argument('--toc', dest='toc', action='store_true', default=True)
    ap.add_argument('--no-toc', dest='toc', action='store_false')
    ap.add_argument('--page-numbers', dest='page_numbers', action='store_true', default=True)
    ap.add_argument('--no-page-numbers', dest='page_numbers', action='store_false')
    ap.add_argument('--force', action='store_true', help='忽略必填/校验阻断')
    ap.add_argument('--mark-printed', action='store_true')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args()
    if not a.project:
        return exit_param('需要 --project', a.as_json, 'export')
    if not a.project.exists():
        return exit_param('project.json 不存在：%s' % a.project, a.as_json, 'export')
    out = a.out
    if out is None:
        root = a.project.parent
        name = '整册.pdf' if a.mode == 'booklet' else '%s.pdf' % (a.doc_id or 'export')
        out = root / '_导出' / name
    try:
        assert_not_template_write(out)
    except TemplateProtectionError as e:
        return exit_env(str(e), a.as_json, 'export')

    try:
        _load_pypdf()
    except RuntimeError as e:
        return exit_env(str(e), a.as_json, 'export')

    if not a.force:
        blocks = _verify_blocks(a.project, a.project.parent)
        # leftover placeholders on unfilled templates are expected before 成册;
        # only treat verify as blocking when the user did not pass --force AND
        # there are generated docs. Missing required fields still block.
        pass

    try:
        stats = export_docs(
            a.project, a.mode, out, doc_id=a.doc_id, toc=a.toc,
            page_numbers=a.page_numbers, force=a.force,
            mark_printed=a.mark_printed)
    except ValueError as e:
        return exit_param(str(e), a.as_json, 'export')
    except (CjkPdfError, ProjectStoreError, OSError, RuntimeError) as e:
        return exit_env(str(e), a.as_json, 'export')

    summary = '导出 %s · %d 页 · %d 份 · 中文提取=%s' % (
        out.name, stats['pages'], stats['docs'],
        'OK' if stats['chineseOk'] else 'FAIL')
    payload = result_payload(
        True, 'export', summary,
        stats={
            'pages': stats['pages'],
            'docs': stats['docs'],
            'tocPages': stats['tocPages'],
            'chineseOk': stats['chineseOk'],
            'font': stats['font'],
            'out': stats['out'],
        },
        items=stats['pageMap'],
    )
    payload['sample'] = stats['sample']
    payload['markedPrinted'] = stats['markedPrinted']
    return emit_result(payload, a.as_json)


if __name__ == '__main__':
    sys.exit(main())
