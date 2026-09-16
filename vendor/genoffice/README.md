# Vendored GenOffice source pin

Upstream: [genspark-ai/genoffice](https://github.com/genspark-ai/genoffice) (Apache-2.0).

`@genoffice/docx-engine` and the repo root are `"private": true` and **not published to npm**. `pnpm add @genoffice/docx-engine` 404 is expected. This tree is the product path: source, pinned, rebuildable offline after `npm install`.

Pinned commit: see [`PIN.json`](PIN.json).

## Why this boundary

`packages/docx-engine` is a **parse / OOXML patch-save engine**, not a complete editor. The official Word surface is `apps/docs` (TipTap + `convert.ts` `blocksToPmDoc` / `pmDocToSavePlan`), tightly coupled to that Electron app.

This product vendors:

1. `docx-engine` (required for fidelity-preserving save)
2. `pptx-engine/custgeom` (the only workspace import from `parse.ts`)
3. Apache-2.0 LICENSE / NOTICE / emf-converter

It does **not** vendor `apps/docs`. There is no exported `<DocxEditor />`. Pulling the docs renderer would lock Electron 43, React 19, TipTap, AI, and ~240 renderer files.

The shell instead renders the engine `Block[]` model (paragraphs, tables, runs, images) as an editable HTML surface and writes back through `saveDocx` — the same save contract the official editor uses for body/table text.

## Refresh

```bash
git clone --depth 1 https://github.com/genspark-ai/genoffice /tmp/genoffice
# copy packages/docx-engine/src and pptx-engine/src/custgeom.ts
# update PIN.json
```

Do not add AGPL editors (OnlyOffice / SuperDoc / Collabora) here.
