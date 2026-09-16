#!/usr/bin/env node
/**
 * Policy unit tests. Import the built policy module (no @deepseek-ai runtime needed).
 */
import { mkdtempSync, mkdirSync, rmSync, symlinkSync, writeFileSync, realpathSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const policyUrl = pathToFileURL(join(root, 'lib/policy.mjs')).href

const { assertWritable, isProtected } = await import(policyUrl)

function fail(msg) {
  console.error('FAIL', msg)
  process.exitCode = 1
}

function pass(msg) {
  console.log('PASS', msg)
}

const install = mkdtempSync(join(tmpdir(), 'ys-install-'))
const work = mkdtempSync(join(tmpdir(), 'ys-work-'))
const templates = join(install, 'templates')
const backup = join(install, 'templates-backup')
mkdirSync(templates, { recursive: true })
mkdirSync(backup, { recursive: true })
writeFileSync(join(templates, 'a.docx'), 'tpl')
writeFileSync(join(work, 'out.docx'), 'ok')

const config = {
  installRoot: install,
  workspaceRoot: work,
  pythonBin: 'python',
  engineRoot: '',
  activeProject: work,
  protectedPaths: ['templates', 'templates-backup', 'templates_原始备份'],
  allowWriteToTemplates: false,
  engineTimeoutMs: 600000,
}

try {
  if (isProtected(join(templates, 'a.docx'), config)) pass('direct templates path is protected')
  else fail('direct templates path should be protected')

  if (isProtected(join(work, 'out.docx'), config)) fail('workspace file must not be protected')
  else pass('workspace file is writable')

  let threw = false
  try {
    assertWritable(join(templates, 'a.docx'), config)
  } catch (err) {
    threw = err instanceof Error && err.name === 'TemplateProtectionError'
    if (threw && String(err.message).includes('TemplateProtectionError')) {
      pass('assertWritable throws TemplateProtectionError')
    } else {
      fail(`wrong error: ${err}`)
    }
  }
  if (!threw) fail('assertWritable should throw')

  // relative path against installRoot
  if (isProtected('templates/a.docx', config)) pass('relative templates path is protected')
  else fail('relative templates path should be protected')

  // symlink / junction bypass
  const sneak = join(work, 'sneak-templates')
  try {
    symlinkSync(templates, sneak)
    const viaLink = join(sneak, 'a.docx')
    const real = realpathSync(viaLink)
    if (!real.includes('templates')) {
      fail(`realpath did not land in templates: ${real}`)
    }
    if (isProtected(viaLink, config)) pass('symlink into templates is protected')
    else fail('symlink into templates should be protected')
  } catch (err) {
    if (process.platform === 'win32') {
      console.log('SKIP symlink test:', err)
    } else {
      fail(`symlink test: ${err}`)
    }
  }

  const open = { ...config, allowWriteToTemplates: true }
  if (isProtected(join(templates, 'a.docx'), open)) fail('escape hatch should allow writes')
  else pass('allowWriteToTemplates bypasses protection')
} finally {
  rmSync(install, { recursive: true, force: true })
  rmSync(work, { recursive: true, force: true })
}

if (process.exitCode) {
  console.error('policy tests failed')
  process.exit(process.exitCode)
}
console.log('policy tests ok')
