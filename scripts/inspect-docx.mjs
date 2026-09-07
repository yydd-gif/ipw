#!/usr/bin/env node
/** Dump body paragraphs and table cell text from a .docx (for CellPatch coordinates). */
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const PizZip = require('pizzip')

const file = process.argv[2]
if (!file) {
  console.error('usage: node scripts/inspect-docx.mjs <file.docx>')
  process.exit(1)
}

const zip = new PizZip(fs.readFileSync(path.resolve(file)))
const xml = zip.file('word/document.xml')?.asText() ?? ''

function texts(fragment) {
  const out = []
  const re = /<w:t(?:\s[^>]*)?>([^<]*)<\/w:t>/g
  let m
  while ((m = re.exec(fragment))) out.push(m[1])
  return out.join('')
}

const paras = [...xml.matchAll(/<w:p[\s>][\s\S]*?<\/w:p>/g)]
console.log('--- body-level scan is approximate; tables contain nested w:p ---')
const tables = [...xml.matchAll(/<w:tbl[\s>][\s\S]*?<\/w:tbl>/g)]
console.log('tables', tables.length)

tables.forEach((t, ti) => {
  const rows = [...t[0].matchAll(/<w:tr[\s>][\s\S]*?<\/w:tr>/g)]
  console.log(`\nTABLE ${ti} rows=${rows.length}`)
  rows.forEach((r, ri) => {
    const cells = [...r[0].matchAll(/<w:tc[\s>][\s\S]*?<\/w:tc>/g)]
    const bits = cells.map((c, ci) => `C${ci}=${JSON.stringify(texts(c[0]))}`)
    console.log(`  R${ri} (${cells.length} tc) ${bits.join(' | ')}`)
  })
})
