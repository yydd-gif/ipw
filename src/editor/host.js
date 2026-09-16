'use strict';

/**
 * Load the bundled GenOffice adapter. Missing bundle → E1 fallback.
 */
const fs = require('fs');
const path = require('path');
const { assertNotTemplateWrite, assertProjectDoc, isFrozenTemplatePath } = require('./protect');

const BUNDLE = path.join(__dirname, 'bundle.cjs');
const PIN = path.join(__dirname, '..', '..', 'vendor', 'genoffice', 'PIN.json');

let embed = null;
let loadError = null;

function tryLoad() {
  if (embed || loadError) return;
  if (!fs.existsSync(BUNDLE)) {
    loadError = 'bundle missing (run npm run embed:build)';
    return;
  }
  try {
    embed = require('./bundle.cjs');
  } catch (err) {
    loadError = String(err && err.message || err);
  }
}

function status() {
  tryLoad();
  if (!embed) {
    return {
      available: false,
      editorMode: 'E1',
      reason: loadError || 'genoffice embed unavailable',
    };
  }
  const st = typeof embed.engineStatus === 'function' ? embed.engineStatus() : { available: true };
  let pin = st.pin;
  if (!pin && fs.existsSync(PIN)) {
    try { pin = JSON.parse(fs.readFileSync(PIN, 'utf8')); } catch { /* ignore */ }
  }
  return {
    available: true,
    editorMode: 'genoffice-embed',
    reason: '',
    pin: pin || null,
  };
}

const sessions = new Map();
let seq = 1;

function projectRootOf(projectPath) {
  const p = path.resolve(projectPath);
  return path.basename(p) === 'project.json' ? path.dirname(p) : p;
}

async function openDoc({ repoRoot, projectPath, relPath }) {
  const st = status();
  if (!st.available) return { ok: false, ...st };
  const root = projectRootOf(projectPath);
  const filePath = path.resolve(root, relPath);
  assertProjectDoc(filePath, root);
  if (isFrozenTemplatePath(filePath, repoRoot)) {
    return {
      ok: false,
      available: true,
      fallback: 'E1',
      reason: 'frozen templates are read-only; open the project copy',
    };
  }
  const bytes = new Uint8Array(fs.readFileSync(filePath));
  const opened = await embed.openBytes(bytes);
  const id = 's' + (seq++);
  sessions.set(id, {
    parsed: opened.parsed,
    filePath,
    projectRoot: root,
    relPath,
    repoRoot,
  });
  return {
    ok: true,
    available: true,
    editorMode: 'genoffice-embed',
    sessionId: id,
    html: opened.render.html,
    stats: opened.render.stats,
    relPath,
    filePath,
  };
}

function collectDirty(htmlEdits) {
  return Array.isArray(htmlEdits) ? htmlEdits : [];
}

async function saveDoc({ repoRoot, sessionId, edits }) {
  const st = status();
  if (!st.available) return { ok: false, ...st };
  const sess = sessions.get(sessionId);
  if (!sess) return { ok: false, reason: 'session expired' };
  assertNotTemplateWrite(sess.filePath, repoRoot || sess.repoRoot);
  assertProjectDoc(sess.filePath, sess.projectRoot);
  const out = await embed.saveWithEdits(sess.parsed, collectDirty(edits));
  fs.writeFileSync(sess.filePath, Buffer.from(out));
  const reopened = await embed.openBytes(new Uint8Array(fs.readFileSync(sess.filePath)));
  sess.parsed = reopened.parsed;
  return {
    ok: true,
    html: reopened.render.html,
    stats: reopened.render.stats,
    relPath: sess.relPath,
  };
}

function closeDoc(sessionId) {
  sessions.delete(sessionId);
  return { ok: true };
}

module.exports = { status, openDoc, saveDoc, closeDoc, tryLoad };
