#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download a portable CPython next to the pack (Windows embeddable / Linux standalone).

Does not commit the ~20–40MB binaries. Pack scripts call this at build time.

  python scripts/fetch_python_runtime.py
  python scripts/fetch_python_runtime.py --platform win-x64
  python scripts/fetch_python_runtime.py --platform linux-x64 --dest build/runtime
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Pinned so CI and laptops fetch the same bits. Engines are 3.12+ stdlib.
WIN_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
# astral/python-build-standalone "install_only" layout: python/bin/python3
LINUX_URLS = [
    'https://github.com/astral-sh/python-build-standalone/releases/download/20250311/cpython-3.12.9+20250311-x86_64-unknown-linux-gnu-install_only.tar.gz',
    'https://github.com/indygreg/python-build-standalone/releases/download/20241016/cpython-3.12.7+20241016-x86_64-unknown-linux-gnu-install_only.tar.gz',
]


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print('download', url)
    req = urllib.request.Request(url, headers={'User-Agent': 'yanshou-docs-pack/0.7'})
    with urllib.request.urlopen(req, timeout=120) as resp, dest.open('wb') as out:
        shutil.copyfileobj(resp, out)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def _enable_embed_site(root: Path) -> None:
    """Windows embeddable: allow extra dirs via python*._pth.

    A present ``python*._pth`` implies isolated mode: PYTHONPATH is ignored.
    Relative paths here are from ``resources/python/`` (python.exe). Engine
    scripts also insert ``Path(__file__).parent`` themselves so a stale ._pth
    cannot resurrect ``No module named '_common'``.
    """
    pth = next(root.glob('python*._pth'), None)
    if pth is None:
        return
    text = pth.read_text(encoding='utf-8', errors='replace')
    lines = [ln.rstrip() for ln in text.splitlines()]
    # Keep the stdlib zip + '.' ; uncomment import site so vendor path works
    # even if PYTHONPATH is missing. Also add pack-root relative hints.
    out = []
    seen_site = False
    for ln in lines:
        if ln.lstrip().startswith('#') and 'import site' in ln:
            out.append('import site')
            seen_site = True
        elif ln.strip() == 'import site':
            out.append(ln)
            seen_site = True
        else:
            out.append(ln)
    if not seen_site:
        out.append('import site')
    extras = ('..\\lib\\vendor', '..\\assets\\engine', '..')
    existing = {ln.replace('/', '\\') for ln in out}
    for extra in extras:
        if extra not in existing:
            out.append(extra)
            existing.add(extra)
    pth.write_text('\n'.join(out) + '\n', encoding='utf-8')


def fetch_win(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / 'RUNTIME.json'
    exe = dest / 'python.exe'
    if exe.is_file() and marker.is_file():
        print('reuse', exe)
        return dest
    with tempfile.TemporaryDirectory(prefix='yz-py-win-') as tmp:
        zpath = Path(tmp) / 'embed.zip'
        _download(WIN_URL, zpath)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(dest)
    _enable_embed_site(dest)
    meta = {
        'platform': 'win-x64',
        'kind': 'cpython-embed',
        'url': WIN_URL,
        'python': 'python.exe',
        'sha256ArchiveNote': 'see upstream python.org',
    }
    marker.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    if not exe.is_file():
        raise FileNotFoundError('python.exe missing after extract: %s' % dest)
    return dest


def fetch_linux(dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / 'RUNTIME.json'
    exe = dest / 'bin' / 'python3'
    if exe.is_file() and marker.is_file():
        print('reuse', exe)
        return dest
    last_err = None
    with tempfile.TemporaryDirectory(prefix='yz-py-linux-') as tmp:
        tgz = Path(tmp) / 'cpython.tgz'
        for url in LINUX_URLS:
            try:
                _download(url, tgz)
                used = url
                last_err = None
                break
            except Exception as e:
                last_err = e
                print('fallback after', url, e)
        else:
            raise RuntimeError('linux runtime download failed: %s' % last_err)
        with tarfile.open(tgz, 'r:gz') as tar:
            tar.extractall(Path(tmp) / 'ex')
        # install_only → <tmp>/ex/python/{bin,lib,...}
        extracted = Path(tmp) / 'ex'
        pyroot = extracted / 'python'
        if not pyroot.is_dir():
            kids = [p for p in extracted.iterdir() if p.is_dir()]
            pyroot = kids[0] if len(kids) == 1 else extracted
        if dest.exists():
            for child in dest.iterdir():
                if child.name == 'RUNTIME.json':
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        for child in pyroot.iterdir():
            target = dest / child.name
            if child.is_dir():
                shutil.copytree(child, target, dirs_exist_ok=True)
            else:
                shutil.copy2(child, target)
        meta = {
            'platform': 'linux-x64',
            'kind': 'python-build-standalone',
            'url': used,
            'python': 'bin/python3',
            'archiveSha256': _sha256(tgz),
        }
        marker.write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    if not exe.is_file():
        raise FileNotFoundError('bin/python3 missing after extract: %s' % dest)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--platform', default='',
                    help='win-x64 | linux-x64 | auto')
    ap.add_argument('--dest', default='',
                    help='extract dir (default build/runtime)')
    ap.add_argument('--skip-if-missing-network', action='store_true')
    a = ap.parse_args()
    plat = (a.platform or 'auto').lower()
    if plat in ('', 'auto'):
        plat = 'win-x64' if sys.platform.startswith('win') else 'linux-x64'
    dest = Path(a.dest) if a.dest else (ROOT / 'build' / 'runtime')
    try:
        if plat in ('win', 'win-x64', 'windows'):
            fetch_win(dest)
        elif plat in ('linux', 'linux-x64'):
            fetch_linux(dest)
        else:
            print('unknown platform', plat, file=sys.stderr)
            return 2
    except Exception as e:
        print('fetch_python_runtime failed:', e, file=sys.stderr)
        if a.skip_if_missing_network:
            dest.mkdir(parents=True, exist_ok=True)
            (dest / 'RUNTIME.json').write_text(json.dumps({
                'platform': plat,
                'kind': 'missing',
                'error': str(e),
                'fallback': 'system-python',
            }, indent=2) + '\n', encoding='utf-8')
            print('wrote fallback marker; pack will use system python')
            return 0
        return 1
    print('ok', dest)
    return 0


if __name__ == '__main__':
    sys.exit(main())
