const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const { installRoot, findPython, pythonEnv } = require('./runtime');

const REPO = installRoot({
  packaged: app.isPackaged,
  resourcesPath: process.resourcesPath,
  dirname: __dirname,
});
const BRIDGE = path.join(REPO, 'assets', 'engine', 'shell_bridge.py');
const PYTHON = findPython(REPO, process.platform, process.env);

function resolveWorkDir() {
  try {
    if (app.isPackaged) return path.join(app.getPath('userData'), 'work');
  } catch {
    /* getPath before ready */
  }
  return path.join(REPO, 'work');
}

let WORK_DIR = path.join(REPO, 'work');

app.commandLine.appendSwitch('no-sandbox');
app.commandLine.appendSwitch('disable-gpu-sandbox');

let mainWindow = null;
let currentProject = null;

function loadFidelity() {
  const p = path.join(__dirname, 'fidelity-status.json');
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return {
      v1: 'BLOCKED',
      v2: 'PARTIAL',
      v3: 'BLOCKED',
      v4: 'unknown',
      editorMode: 'E1',
      note: 'genoffice 未作为 npm 包引入；壳走 E1 表单 + 只读预览',
    };
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    title: '验收资料编辑软件',
    backgroundColor: '#eef0f4',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

function lastJsonLine(text) {
  const lines = String(text || '').split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i].startsWith('{')) {
      try {
        return JSON.parse(lines[i]);
      } catch {
        /* keep looking */
      }
    }
  }
  throw new Error('no JSON contract line in engine output');
}

function runBridge(args, { onLine } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, [BRIDGE, ...args, '--json'], {
      cwd: REPO,
      env: pythonEnv(REPO, WORK_DIR, process.env),
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (buf) => {
      const chunk = buf.toString('utf8');
      stdout += chunk;
      if (onLine) {
        chunk.split(/\r?\n/).forEach((line) => {
          if (line) onLine(line);
        });
      }
      if (mainWindow && !mainWindow.isDestroyed()) {
        chunk.split(/\r?\n/).forEach((line) => {
          if (line.startsWith('#PROGRESS') || line.startsWith('#STAGE')) {
            mainWindow.webContents.send('engine-progress', line);
          }
        });
      }
    });
    child.stderr.on('data', (buf) => {
      stderr += buf.toString('utf8');
    });
    child.on('error', reject);
    child.on('close', (code) => {
      try {
        const payload = lastJsonLine(stdout);
        payload._exit = code;
        payload._stderr = stderr.slice(-800);
        resolve(payload);
      } catch (err) {
        reject(new Error((stderr || stdout || err.message).slice(-1200)));
      }
    });
  });
}

app.whenReady().then(() => {
  WORK_DIR = resolveWorkDir();
  try {
    fs.mkdirSync(WORK_DIR, { recursive: true });
  } catch {
    /* ignore */
  }
  createWindow();
});
app.on('window-all-closed', () => app.quit());

ipcMain.handle('fidelity', () => loadFidelity());
ipcMain.handle('repo-info', () => ({
  repo: REPO,
  python: PYTHON,
  packaged: app.isPackaged,
  workDir: WORK_DIR,
  manual: path.join(REPO, 'docs', '使用手册.md'),
}));
ipcMain.handle('auto-project', () => process.env.YANSHOU_PROJECT || '');

ipcMain.handle('create-project', async (_e, fields) => {
  const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
    title: '选择工程文件夹（空目录即可）',
    properties: ['openDirectory', 'createDirectory'],
  });
  if (canceled || !filePaths[0]) return { cancelled: true };
  const payload = await runBridge([
    '--action', 'create',
    '--dir', filePaths[0],
    '--fields', JSON.stringify(fields || {}),
  ]);
  currentProject = payload.stats && payload.stats.projectPath;
  return payload;
});

ipcMain.handle('open-project', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog(mainWindow, {
    title: '打开工程（选择含 project.json 的文件夹）',
    properties: ['openDirectory'],
  });
  if (canceled || !filePaths[0]) return { cancelled: true };
  const payload = await runBridge(['--action', 'open', '--project', filePaths[0]]);
  currentProject = payload.stats && payload.stats.projectPath;
  return payload;
});

ipcMain.handle('open-path', async (_e, dir) => {
  const payload = await runBridge(['--action', 'open', '--project', dir]);
  currentProject = payload.stats && payload.stats.projectPath;
  return payload;
});

ipcMain.handle('save-fields', async (_e, { projectPath, fields, relPath, syncMode }) => {
  const args = ['--action', 'save-fields', '--project', projectPath, '--fields', JSON.stringify(fields || {})];
  if (relPath) args.push('--rel-path', relPath);
  if (syncMode) args.push('--sync-mode', syncMode);
  return runBridge(args);
});

ipcMain.handle('sync-preview', async (_e, { projectPath, fields }) => {
  return runBridge([
    '--action', 'sync-preview',
    '--project', projectPath,
    '--fields', JSON.stringify(fields || {}),
  ]);
});

ipcMain.handle('save-assets', async (_e, { projectPath, assets, apply }) => {
  const args = [
    '--action', 'save-assets',
    '--project', projectPath,
    '--assets', JSON.stringify(assets || {}),
  ];
  if (apply === false) args.push('--apply', 'false');
  return runBridge(args);
});

ipcMain.handle('apply-subtables', async (_e, projectPath) => {
  return runBridge(['--action', 'apply-subtables', '--project', projectPath]);
});

ipcMain.handle('booklet', async (_e, projectPath) => {
  return runBridge(['--action', 'booklet', '--project', projectPath]);
});

ipcMain.handle('preview', async (_e, { projectPath, docId }) => {
  return runBridge(['--action', 'preview', '--project', projectPath, '--doc-id', docId]);
});

ipcMain.handle('mark-printed', async (_e, { projectPath, docId, printed }) => {
  return runBridge([
    '--action', 'mark-printed',
    '--project', projectPath,
    '--doc-id', docId,
    '--printed', printed ? 'true' : 'false',
  ]);
});

ipcMain.handle('export-pdf', async (_e, { projectPath, mode, docId, force }) => {
  const args = ['--action', 'export', '--project', projectPath, '--mode', mode || 'booklet'];
  if (docId) args.push('--doc-id', docId);
  if (force) args.push('--force');
  return runBridge(args);
});

ipcMain.handle('ai-status', async () => {
  return runBridge(['--action', 'ai-status']);
});

ipcMain.handle('health', async () => {
  return runBridge(['--action', 'health']);
});

ipcMain.handle('open-manual', async () => {
  const manual = path.join(REPO, 'docs', '使用手册.md');
  const fallback = path.join(path.resolve(__dirname, '..'), 'docs', '使用手册.md');
  const target = fs.existsSync(manual) ? manual : fallback;
  if (fs.existsSync(target)) await shell.openPath(target);
  return { ok: fs.existsSync(target), path: target };
});

ipcMain.handle('ai-extract', async (_e, { text, payload }) => {
  const args = ['--action', 'ai-extract'];
  if (text) args.push('--text', text);
  if (payload) args.push('--payload', typeof payload === 'string' ? payload : JSON.stringify(payload));
  return runBridge(args);
});

ipcMain.handle('ai-rewrite', async (_e, { projectPath, mode, text, payload }) => {
  const args = ['--action', 'ai-rewrite', '--project', projectPath, '--mode', mode || 'polish'];
  if (text) args.push('--text', text);
  if (payload) args.push('--payload', typeof payload === 'string' ? payload : JSON.stringify(payload));
  return runBridge(args);
});

ipcMain.handle('ai-apply', async (_e, { projectPath, payload, relPath }) => {
  const args = ['--action', 'ai-apply', '--project', projectPath];
  if (payload) args.push('--payload', typeof payload === 'string' ? payload : JSON.stringify(payload));
  if (relPath) args.push('--rel-path', relPath);
  return runBridge(args);
});

ipcMain.handle('ai-qa', async (_e, projectPath) => {
  return runBridge(['--action', 'ai-qa', '--project', projectPath]);
});

ipcMain.handle('aggregate', async (_e, { projectPath, period, from, to }) => {
  const args = ['--action', 'aggregate', '--project', projectPath, '--period', period || 'week'];
  if (from) args.push('--from', from);
  if (to) args.push('--to', to);
  return runBridge(args);
});

ipcMain.handle('trash-put', async (_e, { projectPath, docId }) => {
  return runBridge(['--action', 'trash-put', '--project', projectPath, '--doc-id', docId]);
});

ipcMain.handle('trash-list', async (_e, projectPath) => {
  return runBridge(['--action', 'trash-list', '--project', projectPath]);
});

ipcMain.handle('show-item', async (_e, filePath) => {
  if (filePath) shell.showItemInFolder(filePath);
});

ipcMain.handle('reveal-root', async (_e, dir) => {
  if (dir) await shell.openPath(dir);
});
