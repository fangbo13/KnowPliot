/**
 * Token Batch Renderer — V3.5 HIGH-005 fix
 *
 * requestAnimationFrame-based token buffer that batches SSE token updates
 * to reduce React re-render frequency.
 *
 * Without batching: each SSE token triggers `set({ streamContent })` → Zustand update →
 * React re-render → ReactMarkdown parse of entire accumulated content.
 * 500 tokens = 500 full ReactMarkdown parse+render cycles → FPS < 20.
 *
 * With batching: tokens accumulate between rAF frames (~16ms). Only one state update
 * per frame. 500 tokens → ~16-20 batched updates per second → FPS > 30.
 *
 * The batcher passes the FULL accumulated content string on each flush (not just
 * the incremental tokens), so `updateStreamContent` remains a simple `set({ streamContent })`.
 */

let accumulatedContent: string = '';
let rafId: number | null = null;
let batchCallback: ((content: string) => void) | null = null;

/**
 * Initialize the token batcher with a callback that receives the full
 * accumulated content on each rAF flush.
 * Called at the start of sendMessage, before streaming begins.
 */
export function initTokenBatcher(callback: (content: string) => void): void {
  // Reset any previous state
  accumulatedContent = '';
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  batchCallback = callback;
}

/**
 * Append a token to the accumulator and schedule a rAF flush if not already scheduled.
 * Called on each SSE 'token' event — replaces direct `updateStreamContent` call.
 */
export function appendToken(token: string): void {
  accumulatedContent += token;
  if (!rafId) {
    rafId = requestAnimationFrame(flushBatch);
  }
}

/**
 * Force immediate flush of all accumulated tokens.
 * Called on 'done' event, 'error' event, and abort — ensures the final state
 * is fully rendered before cleanup.
 */
export function flushImmediate(): void {
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  if (batchCallback && accumulatedContent) {
    batchCallback(accumulatedContent);
    // Do NOT clear accumulatedContent — it stays as the full string
    // (the callback replaces streamContent with the full string each time)
  }
}

/**
 * Reset the batcher — clear all accumulated tokens and cancel pending rAF.
 * Called when session switches, resets, or on abort cleanup.
 */
export function resetTokenBatcher(): void {
  accumulatedContent = '';
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = null;
  }
  batchCallback = null;
}

/**
 * Internal: rAF flush function. Passes the full accumulated content
 * to the callback. The callback (updateStreamContent) replaces streamContent
 * with the complete string, so we do NOT need to track "pending vs flushed" tokens.
 */
function flushBatch(): void {
  if (batchCallback && accumulatedContent) {
    batchCallback(accumulatedContent);
  }
  rafId = null;
  // Note: we do NOT clear accumulatedContent here.
  // The next flush will pass the same string (with any new tokens appended).
  // This is correct because updateStreamContent does `set({ streamContent: content })`,
  // which always sets the complete string, not an increment.
}
