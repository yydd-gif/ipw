/** Minimal valid PDF fallback when LibreOffice / soffice is not installed. */

function asciiHeading(s: string): string {
  return s
    .replace(/[()\\]/g, ' ')
    .replace(/[^\x20-\x7E]/g, '?')
    .slice(0, 96)
}

export function buildSimplePdf(opts: { title: string; note?: string }): Buffer {
  const title = asciiHeading(opts.title || 'item')
  const note = asciiHeading(opts.note || 'Fallback item PDF export (soffice not found)')
  const stream = `BT /F1 16 Tf 48 780 Td (${title}) Tj T* /F1 11 Tf 0 -22 Td (${note}) Tj ET`
  const objects: string[] = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'
  ]

  let body = '%PDF-1.4\n'
  const offsets = [0]
  for (let i = 0; i < objects.length; i++) {
    offsets.push(Buffer.byteLength(body, 'utf8'))
    body += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`
  }
  const xref = Buffer.byteLength(body, 'utf8')
  let xrefTable = `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`
  for (let i = 1; i <= objects.length; i++) {
    xrefTable += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`
  }
  body += `${xrefTable}trailer << /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(body, 'utf8')
}
