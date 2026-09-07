declare module 'pizzip' {
  export default class PizZip {
    constructor(data?: Buffer | Uint8Array | string)
    file(name: string): { asText: () => string; asNodeBuffer: () => Buffer } | null
    file(name: string, data: Buffer | string): this
    files: Record<string, unknown>
    generate(options: { type: 'nodebuffer' | 'uint8array' | 'string'; compression?: string }): Buffer | Uint8Array | string
  }
}
