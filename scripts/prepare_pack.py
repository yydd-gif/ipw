#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage vendor/pypdf + pack-manifest + optional runtime before electron-builder.

  python scripts/prepare_pack.py
  python scripts/prepare_pack.py --with-runtime --platform linux-x64
  python scripts/prepare_pack.py --skip-runtime
"""
from __future__ import annotations

import argparse
import json
import struct
import subprocess
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build'
VENDOR = BUILD / 'vendor'
MANIFEST = BUILD / 'pack-manifest.json'


def _png_rgba(path: Path, size: int, rgb: tuple[int, int, int]) -> None:
    """Write a solid-color PNG (no Pillow). electron-builder accepts 256²."""
    r, g, b = rgb
    raw = b''.join(b'\x00' + bytes([r, g, b, 255]) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    blob = (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b'')
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def vendor_pypdf() -> None:
    VENDOR.mkdir(parents=True, exist_ok=True)
    marker = VENDOR / 'pypdf' / '__init__.py'
    if marker.is_file():
        print('reuse vendor pypdf', VENDOR)
        return
    req = ROOT / 'requirements-p4.txt'
    cmd = [
        sys.executable, '-m', 'pip', 'install',
        '-r', str(req),
        '-t', str(VENDOR),
        '--disable-pip-version-check',
        '--no-compile',
    ]
    print(' '.join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))


def write_manifest(platform: str, with_runtime: bool, runtime_kind: str) -> dict:
    fid = {'editorMode': 'E1'}
    fp = ROOT / 'src' / 'fidelity-status.json'
    if fp.is_file():
        try:
            fid = json.loads(fp.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            pass
    data = {
        'product': '验收资料编辑软件',
        'name': 'yanshou-docs',
        'version': json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version'],
        'builtAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'editorMode': fid.get('editorMode') or 'E1',
        'fidelity': {k: fid.get(k) for k in ('v1', 'v2', 'v3', 'v4', 'editorMode')},
        'includes': {
            'electronShell': True,
            'engines': True,
            'templates': True,
            'templatesBackup': True,
            'pythonRuntime': with_runtime,
            'pythonRuntimeKind': runtime_kind,
            'pypdfVendor': True,
            'dshRuntime': False,
            'dshPluginSource': True,
        },
        'optionalAi': {
            'dshRuntimePacked': False,
            'reason': 'dsh runtime ~420MB; keep base pack small',
            'howToAdd': 'docs/打包说明.md §可选 AI / dsh',
        },
        'offline': {
            'aiRequiresKeyAndNetwork': True,
            'restWorksOffline': True,
            'proof': 'python tools/run_p6_regression.py --skip-prior  (offline gate) + 本包 AI 入口置灰',
        },
        'regressionsFromPack': {
            'cwd': 'resources/ (extraResources root)',
            'cmd': 'python tools/run_p7_regression.py --skip-pack',
            'or': 'python tools/run_regression.py  # P0 37/171/0',
        },
        'platform': platform,
        'neverWriteTemplates': True,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    # also drop a copy next to extraResources staging
    (BUILD / 'pack-manifest.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return data


def fetch_runtime(platform: str) -> str:
    dest = BUILD / 'runtime'
    script = ROOT / 'scripts' / 'fetch_python_runtime.py'
    rc = subprocess.call(
        [sys.executable, str(script), '--platform', platform, '--dest', str(dest),
         '--skip-if-missing-network'],
        cwd=str(ROOT),
    )
    marker = dest / 'RUNTIME.json'
    kind = 'missing'
    if marker.is_file():
        try:
            kind = json.loads(marker.read_text(encoding='utf-8')).get('kind') or kind
        except json.JSONDecodeError:
            pass
    if rc != 0 and kind == 'missing':
        print('runtime fetch returned', rc, 'kind', kind)
    return kind


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--platform', default='')
    ap.add_argument('--with-runtime', action='store_true', default=True)
    ap.add_argument('--skip-runtime', action='store_true')
    a = ap.parse_args()
    plat = (a.platform or ('win-x64' if sys.platform.startswith('win') else 'linux-x64'))
    BUILD.mkdir(parents=True, exist_ok=True)
    icon = ROOT / 'build' / 'icon.png'
    if not icon.is_file():
        _png_rgba(icon, 256, (37, 99, 235))
        print('wrote', icon)
    vendor_pypdf()
    kind = 'skipped'
    with_rt = bool(a.with_runtime) and not a.skip_runtime
    (BUILD / 'runtime').mkdir(parents=True, exist_ok=True)
    if with_rt:
        kind = fetch_runtime(plat)
        with_rt = kind not in ('missing', 'skipped')
    else:
        readme = BUILD / 'runtime' / 'README.txt'
        if not (BUILD / 'runtime' / 'RUNTIME.json').is_file():
            readme.write_text(
                'No portable CPython staged. Pack uses system python3/python.\n',
                encoding='utf-8')
    write_manifest(plat, with_rt, kind)
    print('prepare_pack ok', MANIFEST)
    return 0


if __name__ == '__main__':
    sys.exit(main())
