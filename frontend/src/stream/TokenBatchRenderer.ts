/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

export type TokenBatchUpdate = { appendTokens: string } | { fullContent: string };

interface TokenBatcher {
  generationId: string;
  accumulatedContent: string;
  pendingTokens: string;
  rafId: number | null;
  callback: ((update: TokenBatchUpdate) => void) | null;
}

const batchers = new Map<string, TokenBatcher>();

function matchingBatcher(sessionId: string, generationId: string): TokenBatcher | null {
  const batcher = batchers.get(sessionId);
  return batcher?.generationId === generationId ? batcher : null;
}

export function initTokenBatcher(
  sessionId: string,
  generationId: string,
  callback: (update: TokenBatchUpdate) => void,
): void {
  resetTokenBatcher(sessionId);
  batchers.set(sessionId, {
    generationId,
    accumulatedContent: '',
    pendingTokens: '',
    rafId: null,
    callback,
  });
}

export function appendToken(sessionId: string, generationId: string, token: string): boolean {
  const batcher = matchingBatcher(sessionId, generationId);
  if (!batcher) return false;
  batcher.accumulatedContent += token;
  batcher.pendingTokens += token;
  if (batcher.rafId === null) {
    batcher.rafId = requestAnimationFrame(() => flushBatch(sessionId, generationId));
  }
  return true;
}

export function flushImmediate(sessionId: string, generationId: string): string | null {
  const batcher = matchingBatcher(sessionId, generationId);
  if (!batcher) return null;
  if (batcher.rafId !== null) {
    cancelAnimationFrame(batcher.rafId);
    batcher.rafId = null;
  }
  if (batcher.callback && batcher.accumulatedContent) {
    batcher.callback({ fullContent: batcher.accumulatedContent });
    batcher.pendingTokens = '';
  }
  return batcher.accumulatedContent;
}

export function resetTokenBatcher(sessionId: string, generationId?: string): boolean {
  const batcher = batchers.get(sessionId);
  if (!batcher || (generationId && batcher.generationId !== generationId)) return false;
  if (batcher.rafId !== null) cancelAnimationFrame(batcher.rafId);
  batchers.delete(sessionId);
  return true;
}

export function cleanupTokenBatcher(sessionId: string, generationId?: string): boolean {
  const batcher = batchers.get(sessionId);
  if (!batcher || (generationId && batcher.generationId !== generationId)) return false;
  if (batcher.rafId !== null) {
    cancelAnimationFrame(batcher.rafId);
    batcher.rafId = null;
  }
  batcher.callback = null;
  return true;
}

export function hasTokenBatcher(sessionId: string, generationId?: string): boolean {
  const batcher = batchers.get(sessionId);
  return Boolean(batcher && (!generationId || batcher.generationId === generationId));
}

function flushBatch(sessionId: string, generationId: string): void {
  const batcher = matchingBatcher(sessionId, generationId);
  if (!batcher) return;
  if (batcher.callback && batcher.pendingTokens) {
    batcher.callback({ appendTokens: batcher.pendingTokens });
    batcher.pendingTokens = '';
  }
  batcher.rafId = null;
}
