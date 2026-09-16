#!/usr/bin/env node
/**
 * Bundle the source-integrated GenOffice adapter for Electron (CJS).
 * Offline after npm install (esbuild + jszip/fast-xml-parser/utif2).
 */
import * as esbuild from 'esbuild';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const vendor = path.join(root, 'vendor/genoffice/packages');

await esbuild.build({
  absWorkingDir: root,
  entryPoints: [path.join(root, 'packages/docx-embed/src/index.ts')],
  outfile: path.join(root, 'src/editor/bundle.cjs'),
  bundle: true,
  platform: 'node',
  format: 'cjs',
  target: 'node20',
  sourcemap: false,
  legalComments: 'none',
  alias: {
    '@genoffice/docx-engine': path.join(vendor, 'docx-engine/src/index.ts'),
    '@genoffice/pptx-engine/custgeom': path.join(vendor, 'pptx-engine/src/custgeom.ts'),
  },
  logLevel: 'info',
});

console.log('wrote src/editor/bundle.cjs');
