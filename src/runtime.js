'use strict';

const fs = require('fs');
const path = require('path');

function installRoot({ packaged, resourcesPath, dirname }) {
  if (packaged) return resourcesPath;
  return path.resolve(dirname, '..');
}

function findPython(root, platform, env) {
  const e = env || process.env;
  const forced = e.YANSHOU_PYTHON || e.PYTHON || e.PYTHON3;
  if (forced) return forced;
  const win = String(platform || '').startsWith('win');
  const candidates = win
    ? [
      path.join(root, 'python', 'python.exe'),
      path.join(root, 'assets', 'runtime', 'win-x64', 'python.exe'),
    ]
    : [
      path.join(root, 'python', 'bin', 'python3'),
      path.join(root, 'python', 'bin', 'python'),
      path.join(root, 'assets', 'runtime', 'linux-x64', 'bin', 'python3'),
    ];
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c;
    } catch {
      /* ignore */
    }
  }
  return win ? 'python' : 'python3';
}

function pythonEnv(root, workDir, baseEnv) {
  const env = { ...(baseEnv || process.env) };
  env.PYTHONUTF8 = '1';
  env.PYTHONIOENCODING = 'utf-8';
  env.YANSHOU_ROOT = root;
  if (workDir) env.YANSHOU_WORK = workDir;
  const vendor = path.join(root, 'lib', 'vendor');
  const parts = [root];
  if (fs.existsSync(vendor)) parts.push(vendor);
  const extra = parts.join(path.delimiter);
  env.PYTHONPATH = env.PYTHONPATH ? extra + path.delimiter + env.PYTHONPATH : extra;
  return env;
}

module.exports = { installRoot, findPython, pythonEnv };
