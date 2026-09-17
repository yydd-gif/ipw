#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P7 DoD: packaging layout + health wizard + docs + no secrets.

  python tools/run_p7_regression.py
  python tools/run_p7_regression.py --skip-prior
  python tools/run_p7_regression.py --pack dist/linux-unpacked/resources

DoD（施工交接说明 §6 P7）:
  ① 干净 Windows 无系统 Python/Node 双击即用 → 本仓库给 electron-builder
     Win 目标 + 便携 CPython 抓取脚本；本 Linux VM 产出 linux dir/zip 烟测包
  ② 37 份模板齐全、占位符完好（体检向导）
  ③ 导出整册 PDF 依赖 pypdf（vendor 进包）
  ④ 拔网线除 AI 外全部可用（P6 闸门；本脚本复证 + 文档）
永不写入 assets/templates/。dsh 运行时不打进基础包。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SOURCE = TOOLS.parent  # git checkout even when YANSHOU_ROOT points at a pack
sys.path.insert(0, str(TOOLS))
from _paths import ENGINE, REPO, TEMPLATES, WORK  # noqa: E402

sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(REPO))

from _common import TemplateProtectionError, assert_not_template_write  # noqa: E402
from lib.health import EXPECT_DOCS, EXPECT_PLACEHOLDERS, KNOWN_DRIFT, run_health  # noqa: E402


def check(ok: bool, name: str, detail: str, failures: list) -> None:
    mark = 'PASS' if ok else 'FAIL'
    print('  [%s] %s — %s' % (mark, name, detail))
    if not ok:
        failures.append('%s: %s' % (name, detail))


def run(args, cwd=None, timeout=180, env=None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault('PYTHONUTF8', '1')
    return subprocess.run(
        args, cwd=cwd or str(SOURCE), env=e, timeout=timeout,
        capture_output=True, text=True, encoding='utf-8',
    )


def last_json(text: str) -> dict:
    lines = [ln for ln in (text or '').splitlines() if ln.strip()]
    if not lines:
        raise ValueError('empty output')
    for line in reversed(lines):
        if line.strip().startswith('{'):
            return json.loads(line.strip())
    raise ValueError('no JSON line')


def test_health(failures: list) -> dict:
    print('\n-- health wizard / CLI')
    data = run_health()
    stats = data.get('stats') or {}
    by = {it['key']: it for it in data.get('items') or []}
    check(stats.get('docs') == EXPECT_DOCS, '37 templates',
          str(stats.get('docs')), failures)
    check(stats.get('placeholders') == EXPECT_PLACEHOLDERS, '171 placeholders',
          str(stats.get('placeholders')), failures)
    check(data.get('ok') is True, 'health ok (no unexpected fail)',
          data.get('summary'), failures)
    check(by.get('template-protect', {}).get('ok') is True, 'template protect',
          by.get('template-protect', {}).get('detail'), failures)
    sync = by.get('backup-sync') or {}
    extra = sync.get('extra') or {}
    known = set(extra.get('knownDrift') or [])
    check(known <= KNOWN_DRIFT, 'known drift whitelist',
          str(known), failures)
    check(not extra.get('unexpectedDrift'), 'no unexpected source drift',
          str(extra.get('unexpectedDrift')), failures)
    cli = run([sys.executable, str(TOOLS / 'run_health.py'), '--json'])
    check(cli.returncode in (0, 1), 'run_health.py runs',
          'exit %s' % cli.returncode, failures)
    payload = last_json(cli.stdout)
    check(payload.get('engine') in ('health', 'shell') or payload.get('items'),
          'health JSON items', str(len(payload.get('items') or [])), failures)
    br = run([sys.executable, str(ENGINE / 'shell_bridge.py'),
              '--action', 'health', '--json'])
    check(br.returncode in (0, 1), 'shell_bridge health',
          'exit %s' % br.returncode, failures)
    bjp = last_json(br.stdout)
    check(isinstance(bjp.get('items'), list) and len(bjp['items']) >= 8,
          'bridge health checklist', str(len(bjp.get('items') or [])), failures)
    return data


def test_no_template_write(failures: list) -> None:
    print('\n-- template freeze')
    probe = TEMPLATES / 'p7-must-not-exist.txt'
    try:
        assert_not_template_write(probe)
        check(False, 'protect raises', 'did not raise', failures)
    except TemplateProtectionError:
        check(True, 'protect raises', 'TemplateProtectionError', failures)
    check(not probe.exists(), 'no stray file in templates', str(probe), failures)


def test_pack_config(failures: list) -> None:
    print('\n-- pack config')
    yml_path = SOURCE / 'electron-builder.yml'
    if not yml_path.is_file():
        print('  [SKIP] pack config (no electron-builder.yml in this tree)')
        return
    yml = yml_path.read_text(encoding='utf-8')
    pkg = json.loads((SOURCE / 'package.json').read_text(encoding='utf-8'))
    check('nsis' in yml and 'portable' in yml and 'zip' in yml,
          'win targets nsis+zip+portable', 'electron-builder.yml', failures)
    check('linux:' in yml and 'dir' in yml, 'linux dir+zip', 'present', failures)
    check('signAndEditExecutable: false' in yml or 'forceCodeSigning: false' in yml,
          'unsigned win allowed', 'no forced signing', failures)
    check('dshRuntime' not in yml or 'optional/dsh' in yml,
          'dsh plugin source optional path', 'optional/dsh-yanshou-docs', failures)
    check('python' in yml and 'build/runtime' in yml, 'runtime extraResources',
          'python from build/runtime', failures)
    scripts = pkg.get('scripts') or {}
    for key in ('pack', 'pack:linux', 'pack:win', 'p7:smoke'):
        check(key in scripts, 'npm script ' + key, scripts.get(key) or 'missing', failures)
    check(pkg.get('version', '').startswith('0.7') or pkg.get('version', '').startswith('0.8'),
          'version 0.7.x/0.8.x',
          pkg.get('version'), failures)
    check((SOURCE / 'docs' / '使用手册.md').is_file(), 'user manual',
          'docs/使用手册.md', failures)
    check((SOURCE / 'docs' / '打包说明.md').is_file(), 'pack docs',
          'docs/打包说明.md', failures)
    check('electron-builder' in (pkg.get('devDependencies') or {}),
          'electron-builder dep', str((pkg.get('devDependencies') or {}).get('electron-builder')),
          failures)
    packJs = (SOURCE / 'scripts' / 'pack.js').read_text(encoding='utf-8')
    check('npx.cmd' in packJs and 'shell: WIN' in packJs,
          'pack.js windows spawn via npx.cmd + shell', 'present', failures)
    rt = (SOURCE / 'src' / 'runtime.js').read_text(encoding='utf-8')
    check('findPython' in rt and 'python.exe' in rt, 'runtime.js win python',
          'findPython', failures)
    check("path.join(root, 'assets', 'engine')" in rt,
          'pythonEnv prepends assets/engine', 'pythonEnv', failures)


def test_no_secrets(failures: list) -> None:
    print('\n-- no secrets')
    roots = [SOURCE / 'src', SOURCE / 'assets', SOURCE / 'lib', SOURCE / 'tools',
             SOURCE / 'scripts', SOURCE / 'docs', SOURCE / 'packages', SOURCE / '.github']
    pat = re.compile(r'sk-[A-Za-z0-9]{12,}')
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob('*'):
            if not p.is_file():
                continue
            if p.suffix.lower() in {'.png', '.docx', '.zip', '.tgz', '.whl', '.pyc'}:
                continue
            if 'node_modules' in p.parts or 'vendor' in p.parts:
                continue
            try:
                text = p.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            if pat.search(text):
                hits.append(str(p.relative_to(SOURCE)))
    check(not hits, 'no sk- api keys in tree', hits[:5] or 'clean', failures)
    patch = SOURCE / 'packages' / 'dsh-yanshou-docs' / 'cordis.patch.yml'
    if patch.is_file():
        t = patch.read_text(encoding='utf-8')
        check('sk-' not in t, 'patch has no key', 'ok', failures)


def test_offline_docs_and_gate(failures: list) -> None:
    print('\n-- offline proof (P6 gate still holds)')
    env = os.environ.copy()
    env.pop('DEEPSEEK_API_KEY', None)
    env['YANSHOU_AI_OFFLINE'] = '1'
    proc = run(
        [sys.executable, str(ENGINE / 'shell_bridge.py'), '--action', 'ai-status', '--json'],
        env=env,
    )
    check(proc.returncode == 0, 'ai-status offline', 'exit %s' % proc.returncode, failures)
    data = last_json(proc.stdout)
    st = data.get('stats') or data
    check(st.get('available') is False, 'AI unavailable when unplugged',
          str(st.get('reason')), failures)
    manual = (SOURCE / 'docs' / '使用手册.md').read_text(encoding='utf-8')
    pack = (SOURCE / 'docs' / '打包说明.md').read_text(encoding='utf-8')
    check('断网' in manual or '离线' in manual, 'manual mentions offline',
          '使用手册', failures)
    check('新建表格' in manual and '必填' in manual and '可选' in manual
          and '生成必选' in manual,
          'manual on-demand catalog', '使用手册', failures)
    html = (SOURCE / 'src' / 'renderer' / 'index.html').read_text(encoding='utf-8')
    check('生成必选' in html, 'ribbon label 生成必选', 'index.html', failures)
    check('dsh' in pack.lower() and '420' in pack, 'pack docs dsh optional size',
          '打包说明', failures)
    check('electron-builder' in pack and 'nsis' in pack.lower(),
          'pack docs windows targets', 'nsis', failures)


def test_embed_pth(failures: list) -> None:
    print('\n-- embeddable python._pth extras')
    spec = importlib.util.spec_from_file_location(
        'fetch_python_runtime', str(SOURCE / 'scripts' / 'fetch_python_runtime.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tmp = Path(tempfile.mkdtemp(prefix='yz-pth-'))
    try:
        pth = tmp / 'python312._pth'
        pth.write_text('python312.zip\n.\n# import site\n', encoding='utf-8')
        mod._enable_embed_site(tmp)
        lines = [ln.strip() for ln in pth.read_text(encoding='utf-8').splitlines()]
        norm = [ln.replace('/', '\\') for ln in lines]
        check('import site' in lines, 'uncomment import site', str(lines), failures)
        check('..\\lib\\vendor' in norm, 'vendor on ._pth', str(norm), failures)
        check('..\\assets\\engine' in norm, 'engine on ._pth', str(norm), failures)
        check('..' in norm, 'install root on ._pth', str(norm), failures)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_packaged_engine_imports(failures: list) -> None:
    """Simulate Windows embeddable isolation: no script dir on sys.path, and
    PYTHONPATH like the old pythonEnv (install root + vendor only).

    Regular CPython puts the script directory on sys.path so the production
    bug is invisible on Linux unless we pass -P / -I.
    """
    print('\n-- packaged engine import (embeddable isolation)')
    proj = WORK / 'p7-embed-create'
    if proj.exists():
        shutil.rmtree(proj)
    fields = json.dumps({
        'projectName': '打包隔离建档',
        'ownerUnit': '建设单位',
        'constructionUnit': '施工单位',
    }, ensure_ascii=False)
    # Old pythonEnv: root + vendor, *without* assets/engine.
    stale_pp = os.pathsep.join([str(SOURCE), str(SOURCE / 'lib' / 'vendor')])
    env = {
        'PYTHONUTF8': '1',
        'PYTHONSAFEPATH': '1',
        'PYTHONPATH': stale_pp,
        'YANSHOU_ROOT': str(SOURCE),
        'YANSHOU_WORK': str(WORK / 'p7-embed-work'),
    }
    create = run(
        [sys.executable, '-P', str(ENGINE / 'shell_bridge.py'),
         '--action', 'create', '--dir', str(proj),
         '--fields', fields, '--json'],
        env=env,
    )
    combined = (create.stderr or '') + (create.stdout or '')
    check('No module named' not in combined,
          'create has no ModuleNotFoundError',
          (create.stderr or combined)[-300:], failures)
    check(create.returncode == 0, 'create exit 0 under -P + stale PYTHONPATH',
          'exit %s %s' % (create.returncode, combined[-300:]), failures)
    payload = {}
    if create.returncode == 0:
        try:
            payload = last_json(create.stdout)
        except (ValueError, json.JSONDecodeError) as e:
            check(False, 'create JSON', str(e), failures)
    st = payload.get('stats') or {}
    check(bool(st.get('projectPath')), 'create projectPath',
          str(st.get('projectPath')), failures)
    check((proj / 'project.json').is_file(), 'project.json written',
          str(proj / 'project.json'), failures)

    # -I ignores PYTHONPATH entirely (python._pth isolated mode).
    opened = run(
        [sys.executable, '-I', str(ENGINE / 'shell_bridge.py'),
         '--action', 'open', '--project', str(proj / 'project.json'), '--json'],
        env=env,
    )
    ocombo = (opened.stderr or '') + (opened.stdout or '')
    check('No module named' not in ocombo,
          'open -I has no ModuleNotFoundError',
          (opened.stderr or ocombo)[-300:], failures)
    check(opened.returncode == 0, 'open exit 0 under python -I',
          'exit %s %s' % (opened.returncode, ocombo[-300:]), failures)

    scripts = sorted(ENGINE.glob('*_engine.py')) + [ENGINE / 'shell_bridge.py']
    for script in scripts:
        src = script.read_text(encoding='utf-8')
        head, _, _rest = src.partition('from _common import')
        has_boot = 'Path(__file__).resolve().parent' in head
        check(has_boot,
              '%s bootstraps engine dir before _common' % script.name,
              'present' if has_boot else 'missing sys.path insert', failures)
    for script in scripts:
        help_p = run(
            [sys.executable, '-I', str(script), '--help'],
            env=env, timeout=60,
        )
        text = (help_p.stderr or '') + (help_p.stdout or '')
        check(help_p.returncode == 0 and 'No module named' not in text,
              '%s --help under -I' % script.name,
              'exit %s %s' % (help_p.returncode, text[-200:]), failures)


def test_runtime_js(failures: list) -> None:
    print('\n-- src/runtime.js')
    script = r"""
const { installRoot, findPython, pythonEnv } = require('./src/runtime');
const path = require('path');
const fs = require('fs');
const root = installRoot({ packaged: true, resourcesPath: '/tmp/yz-res', dirname: '/x/src' });
if (root !== '/tmp/yz-res') { console.error('root', root); process.exit(1); }
const py = findPython('/no/such', 'win32', {});
if (py !== 'python') { console.error('fallback', py); process.exit(1); }
const env = pythonEnv('/tmp/yz-res', '/tmp/yz-work', { FOO: '1' });
if (env.YANSHOU_ROOT !== '/tmp/yz-res' || env.YANSHOU_WORK !== '/tmp/yz-work') process.exit(2);
const parts = String(env.PYTHONPATH || '').split(path.delimiter);
const engine = path.join('/tmp/yz-res', 'assets', 'engine');
if (parts[0] !== engine) { console.error('engine-first', env.PYTHONPATH); process.exit(3); }
if (!parts.includes('/tmp/yz-res')) { console.error('root missing', env.PYTHONPATH); process.exit(4); }
console.log(JSON.stringify({ ok: true, root, py, pythonpath: env.PYTHONPATH }));
"""
    proc = run(['node', '-e', script], cwd=str(SOURCE))
    check(proc.returncode == 0, 'runtime.js node smoke',
          (proc.stderr or proc.stdout or '')[-200:], failures)


def test_pack_layout(pack_root: Path, failures: list) -> None:
    print('\n-- packed layout', pack_root)
    check(pack_root.is_dir(), 'pack root exists', str(pack_root), failures)
    if not pack_root.is_dir():
        return
    assets = pack_root / 'assets' / 'templates'
    tools = pack_root / 'tools' / 'run_regression.py'
    engines = pack_root / 'assets' / 'engine' / 'fill_engine.py'
    man = pack_root / 'docs' / '使用手册.md'
    check(assets.is_dir(), 'pack has templates', str(assets), failures)
    check(tools.is_file(), 'pack has tools/run_regression.py', str(tools), failures)
    check(engines.is_file(), 'pack has fill_engine', str(engines), failures)
    check(man.is_file(), 'pack has user manual', str(man), failures)
    # dsh runtime must not be huge in base pack
    dsh_rt = list(pack_root.glob('**/dsh-linux*')) + list(pack_root.glob('**/node_modules/@deepseek-ai/**'))
    check(len(dsh_rt) == 0, 'no dsh runtime in base pack', str(dsh_rt[:3]) or 'absent', failures)
    env = {
        'YANSHOU_ROOT': str(pack_root),
        'YANSHOU_WORK': str(WORK / 'p7-pack-work'),
        'PYTHONPATH': os.pathsep.join([
            str(pack_root / 'assets' / 'engine'),
            str(pack_root),
            str(pack_root / 'lib' / 'vendor'),
        ]),
    }
    # P0 from packaged extraResources
    p0 = run(
        [sys.executable, str(pack_root / 'tools' / 'run_regression.py'), '--skip-backup'],
        cwd=str(pack_root), env=env, timeout=240,
    )
    print(p0.stdout[-800:] if p0.stdout else '')
    if p0.stderr:
        print(p0.stderr[-400:])
    check(p0.returncode == 0, 'P0 from packed layout', 'exit %s' % p0.returncode, failures)
    h = run(
        [sys.executable, str(pack_root / 'tools' / 'run_health.py'), '--brief', '--json'],
        cwd=str(pack_root), env=env,
    )
    check(h.returncode in (0, 1), 'health from packed layout',
          'exit %s' % h.returncode, failures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--skip-prior', action='store_true')
    ap.add_argument('--skip-pack', action='store_true',
                    help='do not require a built dist/; still check scripts')
    ap.add_argument('--pack', default='',
                    help='path to extraResources root (e.g. dist/linux-unpacked/resources)')
    a = ap.parse_args()
    failures: list = []
    print('P7 regression')
    print('=' * 68)
    (WORK / 'p7-regression').mkdir(parents=True, exist_ok=True)

    test_health(failures)
    test_no_template_write(failures)
    test_pack_config(failures)
    test_no_secrets(failures)
    test_offline_docs_and_gate(failures)
    test_runtime_js(failures)
    test_embed_pth(failures)
    test_packaged_engine_imports(failures)

    pack_root = Path(a.pack) if a.pack else None
    if not pack_root:
        guess = REPO / 'dist' / 'linux-unpacked' / 'resources'
        if guess.is_dir() and not a.skip_pack:
            pack_root = guess
    if pack_root:
        test_pack_layout(pack_root, failures)
    elif a.skip_pack:
        print('\n-- packed layout SKIP (--skip-pack)')
    else:
        print('\n-- packed layout not present (build with npm run pack:linux)')

    if not a.skip_prior:
        print('\n-- prior P0 + P6 offline subset')
        p0 = run([sys.executable, str(TOOLS / 'run_regression.py')], timeout=240)
        print(p0.stdout[-600:] if p0.stdout else '')
        check(p0.returncode == 0, 'P0 regression', 'exit %s' % p0.returncode, failures)
        p6 = run([sys.executable, str(TOOLS / 'run_p6_regression.py'), '--skip-prior'],
                 timeout=300)
        print(p6.stdout[-800:] if p6.stdout else '')
        check(p6.returncode == 0, 'P6 --skip-prior', 'exit %s' % p6.returncode, failures)

    print()
    print('=' * 68)
    if failures:
        print('FAIL %d' % len(failures))
        for f in failures:
            print('  -', f)
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
