#!/usr/bin/env node
/**
 * Prepare extraResources then invoke electron-builder.
 *
 *   node scripts/pack.js --linux
 *   node scripts/pack.js --win
 *   node scripts/pack.js --linux --dir-only
 *
 * Windows NSIS / portable / zip must run on a Windows builder (or wine, unsupported here).
 */
const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT = path.resolve(__dirname, '..');
const args = process.argv.slice(2);
const wantWin = args.includes('--win');
const wantMac = args.includes('--mac');
const dirOnly = args.includes('--dir-only');
const skipRuntime = args.includes('--skip-runtime');
const wantLinux = args.includes('--linux') || (!wantWin && !wantMac);

function run(cmd, cmdArgs, opts = {}) {
  console.log('+', cmd, cmdArgs.join(' '));
  const r = spawnSync(cmd, cmdArgs, {
    cwd: ROOT,
    stdio: 'inherit',
    env: process.env,
    ...opts,
  });
  if (r.status !== 0) {
    process.exit(r.status == null ? 1 : r.status);
  }
}

const py = process.env.PYTHON || process.env.PYTHON3 || (process.platform === 'win32' ? 'python' : 'python3');
const plat = wantWin ? 'win-x64' : 'linux-x64';
const prep = [path.join(ROOT, 'scripts', 'prepare_pack.py'), '--platform', plat];
if (skipRuntime) prep.push('--skip-runtime');
run(py, prep);

const eb = [path.join(ROOT, 'node_modules', '.bin', 'electron-builder')];
const ebCmd = process.platform === 'win32' ? eb[0] + '.cmd' : eb[0];
const ebBin = fs.existsSync(ebCmd) ? ebCmd : (fs.existsSync(eb[0]) ? eb[0] : 'electron-builder');

const ebArgs = [];
if (wantWin) {
  if (dirOnly) ebArgs.push('--win', 'dir');
  else ebArgs.push('--win', 'nsis', 'zip', 'portable');
} else if (wantMac) {
  ebArgs.push('--mac', 'dir');
} else if (wantLinux) {
  if (dirOnly) ebArgs.push('--linux', 'dir');
  else ebArgs.push('--linux', 'dir', 'zip');
}
ebArgs.push('--publish', 'never');

const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
if (!fs.existsSync(path.join(ROOT, 'node_modules', 'electron-builder'))) {
  console.error('electron-builder is not installed. Run npm install first.');
  process.exit(1);
}
run(ebBin, ebArgs);

console.log('pack artifacts under dist/');
