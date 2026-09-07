/** Minimal OOXML helpers: extract w:tbl / w:tr / w:tc / w:p / w:t without a full DOM. */

export interface XmlElement {
  name: string
  start: number
  end: number
  openEnd: number
  inner: string
  full: string
}

function isNameBoundary(ch: string | undefined): boolean {
  return ch === ' ' || ch === '/' || ch === '>' || ch === '\n' || ch === '\t' || ch === '\r'
}

export function extractElements(xml: string, name: string, from = 0, to = xml.length): XmlElement[] {
  const results: XmlElement[] = []
  const openNeedle = `<${name}`
  const closeNeedle = `</${name}>`
  let i = from
  while (i < to) {
    const start = xml.indexOf(openNeedle, i)
    if (start < 0 || start >= to) break
    if (!isNameBoundary(xml[start + openNeedle.length])) {
      i = start + 1
      continue
    }
    const gt = xml.indexOf('>', start)
    if (gt < 0 || gt >= to) break
    const openTag = xml.slice(start, gt + 1)
    if (openTag.endsWith('/>')) {
      results.push({ name, start, end: gt + 1, openEnd: gt + 1, inner: '', full: openTag })
      i = gt + 1
      continue
    }
    let depth = 1
    let search = gt + 1
    let end = -1
    while (search < xml.length) {
      const nextOpen = xml.indexOf(openNeedle, search)
      const nextClose = xml.indexOf(closeNeedle, search)
      if (nextClose < 0) break
      if (nextOpen >= 0 && nextOpen < nextClose && isNameBoundary(xml[nextOpen + openNeedle.length])) {
        const ogt = xml.indexOf('>', nextOpen)
        if (ogt < 0) break
        const nestedOpen = xml.slice(nextOpen, ogt + 1)
        if (!nestedOpen.endsWith('/>')) depth += 1
        search = ogt + 1
        continue
      }
      depth -= 1
      if (depth === 0) {
        end = nextClose + closeNeedle.length
        break
      }
      search = nextClose + closeNeedle.length
    }
    if (end < 0) break
    results.push({
      name,
      start,
      end,
      openEnd: gt + 1,
      inner: xml.slice(gt + 1, end - closeNeedle.length),
      full: xml.slice(start, end)
    })
    i = end
  }
  return results
}

function parseOpenName(xml: string, lt: number, gt: number): string {
  const raw = xml.slice(lt + 1, gt)
  const m = raw.match(/^([A-Za-z0-9:]+)/)
  return m ? m[1] : ''
}

/** Direct child elements of `parent` named `childName`, offsets relative to `parent.full`. */
export function extractDirectChildren(parent: XmlElement, childName: string): XmlElement[] {
  const xml = parent.inner
  const innerBase = parent.openEnd - parent.start
  const results: XmlElement[] = []
  let i = 0
  while (i < xml.length) {
    const lt = xml.indexOf('<', i)
    if (lt < 0) break
    if (xml.startsWith('<!--', lt)) {
      const endc = xml.indexOf('-->', lt)
      i = endc < 0 ? xml.length : endc + 3
      continue
    }
    if (xml.startsWith('</', lt)) break
    const gt = xml.indexOf('>', lt)
    if (gt < 0) break
    const name = parseOpenName(xml, lt, gt)
    if (!name) {
      i = gt + 1
      continue
    }
    const openTag = xml.slice(lt, gt + 1)
    if (openTag.endsWith('/>')) {
      if (name === childName) {
        const start = parent.start + innerBase + lt
        const end = parent.start + innerBase + gt + 1
        results.push({
          name,
          start,
          end,
          openEnd: end,
          inner: '',
          full: openTag
        })
      }
      i = gt + 1
      continue
    }
    const nested = extractElements(xml, name, lt)
    const el = nested[0]
    if (!el) {
      i = gt + 1
      continue
    }
    if (name === childName) {
      results.push({
        name,
        start: parent.start + innerBase + el.start,
        end: parent.start + innerBase + el.end,
        openEnd: parent.start + innerBase + el.openEnd,
        inner: el.inner,
        full: el.full
      })
    }
    i = el.end
  }
  return results
}

export function getText(xml: string): string {
  return extractElements(xml, 'w:t')
    .map((t) => decodeXml(t.inner))
    .join('')
}

export function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function decodeXml(s: string): string {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&')
}

export function firstChild(parent: XmlElement, name: string): XmlElement | undefined {
  return extractDirectChildren(parent, name)[0]
}
