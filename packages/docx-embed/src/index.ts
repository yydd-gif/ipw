/**
 * Product adapter over pinned GenOffice source (docx-engine).
 * Visual chrome of apps/docs is not vendored; save uses the engine SaveBlock contract.
 */
import { parseDocx, type ParsedDocFull } from '@genoffice/docx-engine';
import { renderBlocks, type RenderResult } from './render';
import {
  editsFromPlan,
  planOneCharEdit,
  saveWithEdits,
  type OneCharPlan,
  type TextEdit,
} from './save';

export { renderBlocks, saveWithEdits, planOneCharEdit, editsFromPlan };
export type { RenderResult, TextEdit, OneCharPlan };

export type SourcePin = {
  upstream: string;
  license: string;
  commit: string;
  committedAt: string;
};

/** Mirrors vendor/genoffice/PIN.json (keep in sync when refreshing the pin). */
export function sourcePin(): SourcePin {
  return {
    upstream: 'https://github.com/genspark-ai/genoffice',
    license: 'Apache-2.0',
    commit: '09485f884dc845cf3bf27fb7edfe489f9d457aad',
    committedAt: '2026-09-16 19:21:03 +0800',
  };
}

export function engineStatus(): {
  available: true;
  editorMode: 'genoffice-embed';
  pin: SourcePin;
} {
  return {
    available: true,
    editorMode: 'genoffice-embed',
    pin: sourcePin(),
  };
}

export async function openBytes(bytes: Uint8Array): Promise<{
  parsed: ParsedDocFull;
  render: RenderResult;
}> {
  const parsed = await parseDocx(bytes);
  const render = renderBlocks(parsed.blocks as never);
  if (!render.stats.visible) {
    throw new Error('renderer produced 0 visible blocks');
  }
  return { parsed, render };
}

export async function saveOneCharacter(bytes: Uint8Array): Promise<{
  out: Uint8Array;
  plan: OneCharPlan;
  render: RenderResult;
}> {
  const { parsed, render } = await openBytes(bytes);
  const plan = planOneCharEdit(parsed);
  if (!plan) throw new Error('no editable paragraph or table cell');
  const out = await saveWithEdits(parsed, editsFromPlan(plan));
  return { out, plan, render };
}
