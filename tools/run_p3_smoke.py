#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3 smoke: dsh bundle checks that do not need a live model key.

  python tools/run_p3_smoke.py

Always:
  - static contract (package.json / patch / no secrets / 7 tools / no dsh.client)
  - Python-side template-protection + a source audit of policy.ts
  - dump-config *expectation* file is present (not claimed as a live dump)

If pnpm/node: build + pack + policy unit tests against lib/policy.mjs
If dsh CLI:   --version (incl. env -i), --from-default-profile sdk,
              plugin add <tarball>, live --dump-config (never invented)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from _paths import ENGINE, REPO, TEMPLATES, TEMPLATES_BACKUP  # noqa: E402

sys.path.insert(0, str(ENGINE))
from _common import TemplateProtectionError, assert_not_template_write  # noqa: E402

PKG = REPO / 'packages' / 'dsh-yanshou-docs'
SRC = PKG / 'src'
PATCH = PKG / 'cordis.patch.yml'
PKG_JSON = PKG / 'package.json'
EXPECT_DUMP = PKG / 'test' / 'dump-config.expectation.md'

TOOLS_WANTED = [
    'yanshou_datafill',
    'yanshou_docgen',
    'yanshou_fill',
    'yanshou_numbering',
    'yanshou_verify',
    'yanshou_aggregate',
    'yanshou_subtable',
]
PEERS = (
    '@deepseek-ai/cordis',
    '@deepseek-ai/dsh-tools',
    '@deepseek-ai/schemastery',
)
SECRET_RE = re.compile(
    r'(sk-[A-Za-z0-9]{8,}|api[_-]?key\s*[:=]\s*[\'\"]?(?!DEEPSEEK_API_KEY)[A-Za-z0-9_\-]{8,})',
    re.I,
)


def check(ok: bool, name: str, detail: str, failures: list) -> None:
    mark = 'PASS' if ok else 'FAIL'
    print('  [%s] %s — %s' % (mark, name, detail))
    if not ok:
        failures.append('%s: %s' % (name, detail))


def which(name: str) -> str | None:
    return shutil.which(name)


def run(args, cwd=None, env=None, timeout=120) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    e.setdefault('PYTHONUTF8', '1')
    return subprocess.run(
        args, cwd=cwd or str(REPO), env=e,
        capture_output=True, text=True, encoding='utf-8',
        timeout=timeout,
    )


def static_contract(failures: list) -> dict:
    print('== static contract ==')
    data = json.loads(PKG_JSON.read_text(encoding='utf-8'))
    dsh = data.get('dsh') or {}
    bundle = dsh.get('bundle') or {}
    check(data.get('name') == 'dsh-yanshou-docs', 'package name', data.get('name'), failures)
    check(str(data.get('version', '')).startswith('0.2'), 'version 0.2.x',
          str(data.get('version')), failures)
    check('client' not in dsh, 'no dsh.client', json.dumps(dsh), failures)
    check(bundle.get('patch') == './cordis.patch.yml', 'dsh.bundle.patch only',
          json.dumps(bundle), failures)
    peers = data.get('peerDependencies') or {}
    meta = (data.get('peerDependenciesMeta') or {})
    for name in PEERS:
        ver = str(peers.get(name, ''))
        check(name in peers, 'peer %s present' % name, ver or 'missing', failures)
        check(ver and '^' not in ver and ver[0].isdigit(),
              'peer %s exact (no ^)' % name, ver, failures)
        check(bool((meta.get(name) or {}).get('optional')),
              'peer %s optional' % name, json.dumps(meta.get(name)), failures)

    patch = PATCH.read_text(encoding='utf-8')
    check('id: yanshou-docs' in patch, 'patch inserts yanshou-docs', 'id present', failures)
    check('installRoot' in patch and 'workspaceRoot' in patch,
          'dual-track paths', 'installRoot+workspaceRoot', failures)
    check('deepseek-flash' in patch, 'legal model name', 'deepseek-flash', failures)
    check('model: deepseek-chat' not in patch and 'model: deepseek-reasoner' not in patch,
          'no model alias as config value', 'only flash/v4-pro', failures)
    check('You are a coding agent' not in patch, 'persona not coding-agent', 'overridden', failures)
    check('验收资料助手' in patch, 'persona is docs assistant', 'prefix present', failures)
    check('danger-full-access' not in patch,
          'bundle patch does not disable approval', 'no danger-full-access', failures)
    check('sk-' not in patch, 'no sk- token in patch', 'env-only', failures)
    check('apiKey:' not in patch and 'api_key:' not in patch.lower(),
          'no apiKey field in patch', 'env-only', failures)
    # stronger: no sk- secrets anywhere under the package (except this comment in README is ok)
    leaked = []
    for p in PKG.rglob('*'):
        if not p.is_file():
            continue
        if 'node_modules' in p.parts or p.suffix in {'.tgz', '.png', '.docx'}:
            continue
        try:
            text = p.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError):
            continue
        for m in SECRET_RE.finditer(text):
            leaked.append('%s:%s' % (p.relative_to(PKG), m.group(0)[:12]))
    check(not leaked, 'no committed API keys', leaked[:3] or 'clean', failures)

    tools_src = (SRC / 'tools.ts').read_text(encoding='utf-8')
    for t in TOOLS_WANTED:
        check('name: \'%s\'' % t in tools_src or 'name: "%s"' % t in tools_src,
              'tool %s registered' % t, 'src/tools.ts', failures)

    policy = (SRC / 'policy.ts').read_text(encoding='utf-8')
    check('realpathSync' in policy, 'policy uses realpathSync', 'symlink/junction', failures)
    check('config.installRoot' in policy, 'policy base is installRoot', 'not workspaceRoot', failures)
    check("err.name = 'TemplateProtectionError'" in policy,
          'TemplateProtectionError name', 'policy.ts', failures)

    tsdown = (PKG / 'tsdown.config.mjs').read_text(encoding='utf-8')
    check('neverBundle' in tsdown, 'tsdown neverBundle', 'deps.neverBundle', failures)

    check(EXPECT_DUMP.is_file(), 'dump-config expectation file',
          str(EXPECT_DUMP.relative_to(REPO)), failures)
    expect = EXPECT_DUMP.read_text(encoding='utf-8')
    check('# == dsh-yanshou-docs' in expect, 'expectation mentions layer header',
          'not a live dump', failures)
    check('不是一次真实 dump' in expect or '不是' in expect,
          'expectation labelled as not live', 'disclaimer', failures)
    return data


def python_policy(failures: list) -> None:
    print('== python template protection ==')
    probe = TEMPLATES / '_p3_smoke_probe.txt'
    try:
        assert_not_template_write(probe)
        check(False, 'refuse write templates/', 'did not throw', failures)
    except TemplateProtectionError as e:
        check(True, 'refuse write templates/', str(e)[:80], failures)
    probe_b = TEMPLATES_BACKUP / '_p3_smoke_probe.txt'
    try:
        assert_not_template_write(probe_b)
        check(False, 'refuse write templates-backup/', 'did not throw', failures)
    except TemplateProtectionError as e:
        check(True, 'refuse write templates-backup/', str(e)[:80], failures)

    # symlink bypass (POSIX)
    tmp = Path(tempfile.mkdtemp(prefix='p3-policy-'))
    try:
        sneak = tmp / 'sneak'
        try:
            sneak.symlink_to(TEMPLATES, target_is_directory=True)
            try:
                assert_not_template_write(sneak / 'x.docx')
                check(False, 'refuse write via symlink', 'did not throw', failures)
            except TemplateProtectionError:
                check(True, 'refuse write via symlink', str(sneak), failures)
        except OSError as e:
            check(True, 'symlink test skipped', str(e), failures)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def maybe_build_pack_test(failures: list) -> Path | None:
    print('== build / pack / policy tests (node) ==')
    pnpm = which('pnpm')
    node = which('node')
    if not pnpm or not node:
        print('  [SKIP] pnpm/node not on PATH — land sources only')
        return None
    nv = run([node, '--version'])
    print('  node', (nv.stdout or nv.stderr).strip())
    inst = run([pnpm, 'install'], cwd=str(PKG), timeout=180)
    check(inst.returncode == 0, 'pnpm install',
          (inst.stderr or inst.stdout)[-400:], failures)
    if inst.returncode != 0:
        return None
    built = run([pnpm, 'build'], cwd=str(PKG), timeout=180)
    check(built.returncode == 0, 'pnpm build',
          (built.stderr or built.stdout)[-400:], failures)
    idx = PKG / 'lib' / 'index.mjs'
    pol = PKG / 'lib' / 'policy.mjs'
    check(idx.is_file(), 'lib/index.mjs exists', str(idx), failures)
    check(pol.is_file(), 'lib/policy.mjs exists', str(pol), failures)
    if idx.is_file():
        body = idx.read_text(encoding='utf-8')
        for t in TOOLS_WANTED:
            check(t in body, 'built bundle contains %s' % t, 'lib/index.mjs', failures)
        check('@deepseek-ai/dsh-tools' in body, 'does not bundle dsh-tools',
              'import left external', failures)
    if pol.is_file():
        test = run([node, str(PKG / 'test' / 'policy.test.mjs')], cwd=str(PKG))
        check(test.returncode == 0, 'policy unit tests',
              (test.stdout + test.stderr)[-400:], failures)

    packed = run([pnpm, 'pack'], cwd=str(PKG), timeout=120)
    tgz = PKG / 'dsh-yanshou-docs-0.2.0.tgz'
    # pnpm pack may write to cwd or print name
    if not tgz.is_file():
        for cand in PKG.glob('dsh-yanshou-docs-*.tgz'):
            tgz = cand
            break
    check(packed.returncode == 0 and tgz.is_file(), 'pnpm pack tarball',
          str(tgz) if tgz.is_file() else (packed.stderr or packed.stdout)[-300:],
          failures)
    return tgz if tgz.is_file() else None


def maybe_dsh(failures: list, tgz: Path | None) -> None:
    print('== dsh CLI (optional live dump-config) ==')
    dsh = which('dsh')
    extra = str(Path.home() / '.local' / 'bin')
    if not dsh and (Path(extra) / 'dsh').exists():
        dsh = str(Path(extra) / 'dsh')
    if not dsh:
        print('  [SKIP] dsh CLI not found — not inventing --dump-config output')
        print('  blocker: install deepseek-harness-sdk==0.1.5rc1 and set DSH_HOME')
        return

    home = Path(tempfile.mkdtemp(prefix='p3-dsh-home-'))
    env = {
        'DSH_HOME': str(home),
        'PATH': os.environ.get('PATH', ''),
        'HOME': os.environ.get('HOME', ''),
        'LANG': os.environ.get('LANG', 'C.UTF-8'),
    }
    # do not pass DEEPSEEK_API_KEY even if present — smoke must not need it
    env.pop('DEEPSEEK_API_KEY', None)

    ver = run([dsh, '--version'], env=env)
    check(ver.returncode == 0, 'dsh --version', (ver.stdout or ver.stderr).strip(), failures)

    # env -i, system PATH only
    isolated = run(
        ['env', '-i',
         'PATH=/usr/bin:/bin',
         'HOME=' + env['HOME'],
         'DSH_HOME=' + str(home),
         dsh, '--version'],
        env={},
    )
    check(isolated.returncode == 0 and '0.1.5-rc.1' in (isolated.stdout + isolated.stderr),
          'env -i dsh --version (no Node on PATH)',
          (isolated.stdout or isolated.stderr).strip(), failures)

    # Derive profile from sdk. `dsh --profile yanshou --from-default-profile sdk`
    # will try to *boot* after creating; we only need the files, so dump-default
    # after init. Use plugin? Construction: dsh --profile yanshou --from-default-profile sdk
    init = run([dsh, '--profile', 'yanshou', '--from-default-profile', 'sdk',
                '--dump-config'], env=env, timeout=90)
    prof = home / 'profiles' / 'yanshou' / 'package.json'
    # Creating may boot and fail without a TTY; profile dir should still exist.
    if not prof.is_file():
        # second try: dump-default-config of sdk does not create yanshou;
        # run from-default-profile with dump-config which should write the profile.
        print('  [info] profile init stdout/err:', (init.stdout + init.stderr)[-500:])
    check(prof.is_file() or init.returncode == 0, 'from-default-profile sdk',
          str(prof) if prof.is_file() else (init.stderr or init.stdout)[-300:],
          failures)
    if prof.is_file():
        manifest = json.loads(prof.read_text(encoding='utf-8'))
        bundles = ((manifest.get('dsh') or {}).get('profile') or {}).get('bundles') or []
        check(bundles[:2] == ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-sdk-app']
              or set(bundles) >= {'@deepseek-ai/dsh-base', '@deepseek-ai/dsh-sdk-app'},
              'sdk bundles before plugin add', json.dumps(bundles), failures)

    if tgz is None:
        print('  [SKIP] live plugin add — no tarball from pack step')
        shutil.rmtree(home, ignore_errors=True)
        return

    pnpm = which('pnpm')
    if not pnpm:
        print('  [SKIP] live plugin add — pnpm missing (dsh plugin forwards to pnpm)')
        shutil.rmtree(home, ignore_errors=True)
        return

    added = run([dsh, 'plugin', '--profile', 'yanshou', 'add', str(tgz)],
                env=env, timeout=180)
    print('  [info] plugin add rc=%s' % added.returncode)
    if added.returncode != 0:
        check(False, 'dsh plugin add tarball',
              (added.stderr or added.stdout)[-600:], failures)
        shutil.rmtree(home, ignore_errors=True)
        return
    check(True, 'dsh plugin add tarball', tgz.name, failures)

    if prof.is_file():
        manifest = json.loads(prof.read_text(encoding='utf-8'))
        bundles = ((manifest.get('dsh') or {}).get('profile') or {}).get('bundles') or []
        check(bundles == [
            '@deepseek-ai/dsh-base',
            '@deepseek-ai/dsh-sdk-app',
            'dsh-yanshou-docs',
        ] or (len(bundles) >= 3 and bundles[-1] == 'dsh-yanshou-docs'),
            'bundles [dsh-base, dsh-sdk-app, dsh-yanshou-docs]',
            json.dumps(bundles), failures)

    dump = run([dsh, '--profile', 'yanshou', '--dump-config'], env=env, timeout=90)
    out = dump.stdout or ''
    err = dump.stderr or ''
    check(dump.returncode == 0, 'dsh --dump-config exit 0', err[-300:], failures)
    check('# == dsh-yanshou-docs' in out, 'dump-config layer header',
          'live output contains # == dsh-yanshou-docs' if '# == dsh-yanshou-docs' in out
          else 'NOT present; not faking it', failures)
    check('id: yanshou-docs' in out, 'dump-config yanshou-docs row',
          'present' if 'id: yanshou-docs' in out else 'NOT present', failures)
    check('sdk-jsonrpc-server' in out, 'dump-config jsonrpc server',
          'present' if 'sdk-jsonrpc-server' in out else 'NOT present', failures)
    # dump-config prints the stacked tree: earlier sdk-app layer still contains
    # "coding agent". Winning row is the last layer (后层按行胜出).
    last = out.split('# == dsh-yanshou-docs')[-1] if '# == dsh-yanshou-docs' in out else ''
    check('验收资料助手' in last, 'dump-config winning persona (last layer)',
          'docs assistant' if '验收资料助手' in last else 'NOT in last layer', failures)
    check('You are a coding agent' not in last,
          'dump-config last layer is not coding-agent',
          'ok' if 'You are a coding agent' not in last else 'last layer still coding agent',
          failures)
    check('model: deepseek-chat' not in last, 'dump-config no model alias in last layer',
          'ok' if 'model: deepseek-chat' not in last else 'alias leaked', failures)
    check('model: deepseek-flash' in last, 'dump-config last layer model',
          'deepseek-flash' if 'model: deepseek-flash' in last else 'missing', failures)

    # keep a copy under work/ (gitignored) for humans; do not treat as source
    try:
        dest = REPO / 'work' / 'p3-dump-config.yml'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding='utf-8')
        print('  [info] live dump-config saved to work/p3-dump-config.yml (gitignored)')
    except OSError:
        pass

    shutil.rmtree(home, ignore_errors=True)


def main() -> int:
    print('P3 smoke · %s' % PKG)
    failures: list[str] = []
    if not PKG_JSON.is_file():
        print('package missing:', PKG)
        return 2
    static_contract(failures)
    python_policy(failures)
    tgz = maybe_build_pack_test(failures)
    maybe_dsh(failures, tgz)

    print()
    if failures:
        print('P3 smoke FAILED (%d)' % len(failures))
        for f in failures:
            print('  -', f)
        return 1
    print('P3 smoke PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
