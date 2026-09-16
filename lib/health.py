# -*- coding: utf-8 -*-
"""Template-asset health checklist (P7 wizard + CLI).

Reuses backup_templates SHA inventory and locate_docx paragraph/cell scans.
Never writes into assets/templates/.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# Allow running from repo or packed extraResources.
_HERE = Path(__file__).resolve().parent
_REPO_GUESS = _HERE.parent
if str(_REPO_GUESS) not in sys.path:
    sys.path.insert(0, str(_REPO_GUESS))
_ENGINE = _REPO_GUESS / 'assets' / 'engine'
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))
_TOOLS = _REPO_GUESS / 'tools'
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from _common import (  # noqa: E402
    BASE, DICT_PATH, ENGINE_DIR, EXAMPLES, REPO, RULES_PATH, SPEC,
    TEMPLATES, TEMPLATES_BACKUP, TemplateProtectionError, VENDOR,
    assert_not_template_write, iter_templates, work_dir,
)

EXPECT_DOCS = 37
EXPECT_PLACEHOLDERS = 171
# Content-preserving Word resaves; freeze backup is deliberately not overwritten.
KNOWN_DRIFT = {
    '七、竣工验收分册（政务信息化项目）/1、项目情况简介.docx',
    '二、过程分册/4、施工组织方案.docx',
}
W_T = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'
W_P = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'
PART_RE = __import__('re').compile(
    r'^word/(document|header\d*|footer\d*|footnotes|endnotes)\.xml$')
PH_RE = __import__('re').compile(r'\{\{[^{}]+\}\}')

ENGINES = (
    'fill_engine.py', 'datafill_engine.py', 'docgen_engine.py',
    'numbering_engine.py', 'verify_engine.py', 'subtable_engine.py',
    'aggregate_engine.py', 'export_engine.py', 'shell_bridge.py',
    'ai_engine.py',
)
SPEC_FILES = (
    '字段字典.json',
    '表名缩写字典.csv',
    '填数规则.yaml',
    '软件目录.docx',
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def _check(key: str, ok: bool, detail: str, extra=None, level: str = '') -> dict:
    if not level:
        level = 'pass' if ok else 'fail'
    item = {
        'key': key,
        'ok': bool(ok),
        'level': level,  # pass | fail | warn | skip
        'detail': detail,
    }
    if extra:
        item['extra'] = extra
    return item


def _count_placeholders(docx: Path) -> list:
    hits = []
    with zipfile.ZipFile(docx) as z:
        for name in z.namelist():
            if not PART_RE.match(name):
                continue
            try:
                root = ET.fromstring(z.read(name))
            except ET.ParseError:
                continue
            for p in root.iter(W_P):
                full = ''.join(t.text or '' for t in p.iter(W_T))
                hits.extend(PH_RE.findall(full))
    return hits


def _backup_drift() -> dict:
    man_path = TEMPLATES_BACKUP / 'SHA256清单.json'
    out = {
        'manifest': str(man_path),
        'total': 0,
        'copyBad': [],
        'knownDrift': [],
        'unexpectedDrift': [],
        'missingSrc': [],
        'extraSrc': [],
    }
    if not man_path.is_file():
        out['error'] = 'missing SHA256清单.json'
        return out
    man = json.loads(man_path.read_text(encoding='utf-8'))
    files = man.get('files') or []
    out['total'] = int(man.get('total') or len(files))
    listed = set()
    for rec in files:
        vol = rec.get('分册') or ''
        name = rec.get('文件') or ''
        rel = '%s/%s' % (vol, name)
        listed.add(rel)
        bak = TEMPLATES_BACKUP / vol / name
        src = TEMPLATES / vol / name
        if not bak.is_file():
            out['copyBad'].append(rel + ' (副本缺失)')
        elif rec.get('sha256') and _sha256(bak) != rec['sha256']:
            out['copyBad'].append(rel + ' (副本被改动)')
        if not src.is_file():
            out['missingSrc'].append(rel)
        elif rec.get('sha256') and _sha256(src) != rec['sha256']:
            if rel in KNOWN_DRIFT:
                out['knownDrift'].append(rel)
            else:
                out['unexpectedDrift'].append(rel)
    live = []
    for p in iter_templates(TEMPLATES):
        rel = str(p.relative_to(TEMPLATES)).replace('\\', '/')
        live.append(rel)
        if rel not in listed:
            out['extraSrc'].append(rel)
    out['live'] = live
    return out


def _locate_reuse() -> tuple[bool, str, dict]:
    """Call tools/locate_docx.py on 施工日志 (cross-run placeholders)."""
    try:
        from locate_docx import locate  # tools/ on sys.path
    except ImportError as e:
        return False, '无法导入 locate_docx：%s' % e, {}
    sample = None
    for p in iter_templates(TEMPLATES):
        if '施工日志' in p.name:
            sample = p
            break
    if sample is None:
        return False, '未找到施工日志模板', {}
    rows = locate(str(sample))
    n_keys = sum(len(r[2]) for r in rows if len(r) > 2)
    rel = str(sample.relative_to(TEMPLATES)).replace('\\', '/')
    return True, 'locate_docx %s → %d 个位置 / %d 个 key' % (rel, len(rows), n_keys), {
        'file': rel, 'positions': len(rows), 'keys': n_keys,
    }


def _python_runtime() -> dict:
    root = REPO
    plat = sys.platform
    candidates = []
    if plat.startswith('win'):
        candidates.extend([
            root / 'python' / 'python.exe',
            root / 'assets' / 'runtime' / 'win-x64' / 'python.exe',
        ])
    else:
        candidates.extend([
            root / 'python' / 'bin' / 'python3',
            root / 'python' / 'bin' / 'python',
            root / 'assets' / 'runtime' / 'linux-x64' / 'bin' / 'python3',
        ])
    bundled = next((str(p) for p in candidates if p.is_file()), '')
    return {
        'executable': sys.executable,
        'version': sys.version.split()[0],
        'bundled': bundled,
        'vendor': str(VENDOR) if VENDOR.is_dir() else '',
        'platform': plat,
    }


def _pypdf_status() -> tuple[bool, str]:
    try:
        mod = importlib.import_module('pypdf')
        ver = getattr(mod, '__version__', '?')
        return True, 'pypdf %s' % ver
    except Exception as e:
        return False, 'pypdf 不可用：%s（打包时应 vendor 进 lib/vendor）' % e


def _dsh_status() -> dict:
    plugin = REPO / 'packages' / 'dsh-yanshou-docs'
    if not plugin.is_dir():
        plugin = REPO / 'optional' / 'dsh-yanshou-docs'
    dsh_home = (os.environ.get('DSH_HOME') or '').strip()
    return {
        'pluginSource': str(plugin) if plugin.is_dir() else '',
        'dshHome': dsh_home,
        'dshHomeExists': bool(dsh_home) and Path(dsh_home).exists(),
        'optional': True,
        'note': 'dsh 运行时约 420MB，基础包默认不含；见 docs/打包说明.md',
    }


def _ai_status_safe() -> dict:
    try:
        from lib.ai_gate import ai_status
        return ai_status(probe_network=False)
    except Exception as e:
        return {'available': False, 'reason': 'status-error', 'error': str(e)}


def run_health() -> dict:
    """Return a JSON-serialisable checklist. Never writes templates."""
    items = []
    docs = list(iter_templates(TEMPLATES))
    n_docs = len(docs)
    items.append(_check(
        'templates', n_docs == EXPECT_DOCS,
        '%d 份模板（期望 %d）' % (n_docs, EXPECT_DOCS),
        extra={'count': n_docs, 'paths': [
            str(p.relative_to(TEMPLATES)).replace('\\', '/') for p in docs]}))

    ph_total = 0
    per_file = {}
    for p in docs:
        hits = _count_placeholders(p)
        rel = str(p.relative_to(TEMPLATES)).replace('\\', '/')
        per_file[rel] = len(hits)
        ph_total += len(hits)
    items.append(_check(
        'placeholders', ph_total == EXPECT_PLACEHOLDERS,
        '%d 处 {{key}}（期望 %d，locate/段落口径）' % (ph_total, EXPECT_PLACEHOLDERS),
        extra={'count': ph_total, 'perFile': per_file}))

    missing_spec = [n for n in SPEC_FILES if not (SPEC / n).is_file()]
    items.append(_check(
        'spec', not missing_spec,
        '规格文件齐全' if not missing_spec else ('缺 ' + ', '.join(missing_spec)),
        extra={'missing': missing_spec, 'spec': str(SPEC)}))

    missing_eng = [n for n in ENGINES if not (ENGINE_DIR / n).is_file()]
    items.append(_check(
        'engines', not missing_eng,
        '引擎 %d/%d' % (len(ENGINES) - len(missing_eng), len(ENGINES)),
        extra={'missing': missing_eng}))

    drift = _backup_drift()
    copy_ok = not drift.get('copyBad') and not drift.get('error')
    items.append(_check(
        'backup-copy', copy_ok,
        '备份副本完整性 A 段：%s' % (
            '通过' if copy_ok else (drift.get('error') or '%d 处异常' % len(drift.get('copyBad') or []))),
        extra=drift))

    unexpected = drift.get('unexpectedDrift') or []
    known = drift.get('knownDrift') or []
    miss = drift.get('missingSrc') or []
    extra = drift.get('extraSrc') or []
    sync_fail = bool(unexpected or miss or extra)
    if sync_fail:
        items.append(_check(
            'backup-sync', False,
            '源↔备份出现未登记漂移（%d 意外 / %d 缺失 / %d 新增）' % (
                len(unexpected), len(miss), len(extra)),
            extra={'knownDrift': known, 'unexpectedDrift': unexpected,
                   'missingSrc': miss, 'extraSrc': extra}))
    else:
        items.append(_check(
            'backup-sync', True,
            '源↔备份：无意外漂移（已知 fail-loud %d 份，内容零丢失）' % len(known),
            extra={'knownDrift': known},
            level='warn' if known else 'pass'))

    prot_ok = False
    prot_detail = ''
    try:
        probe = TEMPLATES / '__p7_must_not_write__.txt'
        assert_not_template_write(probe)
        prot_detail = '保护未触发'
    except TemplateProtectionError as e:
        prot_ok = True
        prot_detail = str(e)
    items.append(_check('template-protect', prot_ok, prot_detail))

    py = _python_runtime()
    items.append(_check(
        'python', True,
        '当前解释器 %s（%s）%s' % (
            py['version'], py['executable'],
            '；已捆绑 ' + py['bundled'] if py['bundled'] else '；未捆绑便携运行时（开发机可用系统 Python）'),
        extra=py,
        level='pass' if (py['bundled'] or not _looks_packaged()) else 'warn'))

    pdf_ok, pdf_detail = _pypdf_status()
    items.append(_check('pypdf', pdf_ok, pdf_detail, level='pass' if pdf_ok else 'warn'))

    demo = EXAMPLES / 'demo_project.json'
    items.append(_check('examples', demo.is_file(), str(demo)))

    loc_ok, loc_detail, loc_extra = _locate_reuse()
    items.append(_check('locate', loc_ok, loc_detail, extra=loc_extra))

    dsh = _dsh_status()
    items.append(_check(
        'dsh', True,
        'AI/dsh 可选：插件源码%s；DSH_HOME %s' % (
            '已带' if dsh['pluginSource'] else '未打进基础包',
            dsh['dshHome'] or '未设置（正常，基础包不含 ~420MB 运行时）'),
        extra=dsh, level='skip'))

    ai = _ai_status_safe()
    items.append(_check(
        'offline-ai', not ai.get('available'),
        'AI 闸门：available=%s reason=%s（无 Key/断网时应不可用；成册/导出不受影响）' % (
            ai.get('available'), ai.get('reason')),
        extra=ai,
        level='pass' if not ai.get('available') else 'warn'))

    try:
        wd = work_dir()
        items.append(_check('work-dir', True, '可写工作目录 %s' % wd, extra={'work': str(wd)}))
    except OSError as e:
        items.append(_check('work-dir', False, str(e)))

    n_fail = sum(1 for it in items if it['level'] == 'fail')
    n_warn = sum(1 for it in items if it['level'] == 'warn')
    summary = '模板体检 %d 项：%d 失败 / %d 警告' % (len(items), n_fail, n_warn)
    return {
        'ok': n_fail == 0,
        'engine': 'health',
        'summary': summary,
        'stats': {
            'docs': n_docs,
            'placeholders': ph_total,
            'fail': n_fail,
            'warn': n_warn,
            'repo': str(REPO),
            'assets': str(BASE),
            'packagedHint': _looks_packaged(),
        },
        'items': items,
        'errors': [] if n_fail == 0 else [
            {'reason': it['detail'], 'level': 'block', 'key': it['key']}
            for it in items if it['level'] == 'fail'
        ],
    }


def _looks_packaged() -> bool:
    marker = REPO / 'pack-manifest.json'
    if marker.is_file():
        return True
    return (REPO / 'app.asar').is_file() or (REPO.parent / 'app.asar').is_file()
