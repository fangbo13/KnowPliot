/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

/**
 * Stream Lifecycle Manager — V3.5 CRIT-001/CRIT-002 fix
 *
 * Module-level per-session registry for managing SSE AbortController lifecycles.
 * NOT stored in Zustand (AbortController is not serializable and should
 * not be part of immutable state model).
 *
 * Key responsibilities:
 * 1. Create one AbortController per session without disturbing other sessions
 * 2. Match terminal work by both session ID and generation ID
 * 3. Provide owner-scoped aborts for stop / delete / reset scenarios
 * 4. Clean up references when stream completes naturally
 *
 * ─── V4.0 DEFECT-006 DESIGN NOTE — Architectural constraints of module-level state ───
 *
 * The activeStreams registry is module-level state, NOT stored in Zustand
 * (AbortController is not serializable).
 * This creates three implications documented here:
 *
 * 1. CROSS-TAB ISOLATION: Each browser tab has its own JS context with its own
 *    module-level variables. If Tab A is streaming and Tab B switches sessions,
 *    Tab B's abortActiveStream() does NOT affect Tab A's stream.
 *    Mitigation: BroadcastChannel (see DEFECT-008 / crossTabSync.ts).
 *
 * 2. DUAL-STATE MANAGEMENT: per-session turn state (Zustand) and
 *    AbortControllers (module-level) are managed
 *    by different mechanisms. Zustand's set() is synchronous, but React
 *    component re-renders are batched (async). The sendMessage function reads
 *    Zustand internal state via get(), so the send lock is effective despite
 *    React batching delay.
 *
 * 3. JS SINGLE-THREAD SAFETY: createStreamAbortController() replaces only the
 *    named session's controller and assigns the new registry entry,
 *    all in one synchronous function. JS event loop guarantees no interleaving
 *    of these steps. There is no real TOCTOU race condition.
 *
 * [Source: V4.0/deep_sys_defect_list.md §DEFECT-006]
 * [Source: V3.4/bug_list.md §CRIT-001] + [Source: V3.5/reports/综合审计报告.md §streamPhase修复]
 */

interface ActiveStream {
  generationId: string;
  controller: AbortController;
}

const activeStreams = new Map<string, ActiveStream>();

/**
 * Create a new AbortController, replacing only the same session's prior generation.
 * Called at the start of sendMessage.
 */
export function createStreamAbortController(sessionId: string, generationId = 'legacy'): AbortController {
  abortActiveStream(sessionId);

  const controller = new AbortController();
  activeStreams.set(sessionId, { generationId, controller });
  return controller;
}

/**
 * Abort the named session's SSE stream and clear its registry entry.
 */
export function abortActiveStream(sessionId: string, generationId?: string): boolean {
  const active = activeStreams.get(sessionId);
  if (!active || (generationId && active.generationId !== generationId)) return false;
  active.controller.abort();
  activeStreams.delete(sessionId);
  return true;
}

/**
 * Get the session ID that owns the currently active stream.
 * Used in finishStreamingMessage to verify that completing stream
 * belongs to the currently active session (prevents cross-session data pollution).
 */
export function getActiveStreamSessionId(): string | null {
  if (activeStreams.size !== 1) return null;
  return activeStreams.keys().next().value ?? null;
}

export function getActiveStreamGenerationId(sessionId: string): string | null {
  return activeStreams.get(sessionId)?.generationId ?? null;
}

/**
 * Clear references after stream completes naturally (done event).
 * Does NOT abort — the stream is already finished.
 */
export function clearStreamOnComplete(sessionId: string, generationId?: string): boolean {
  const active = activeStreams.get(sessionId);
  if (!active || (generationId && active.generationId !== generationId)) return false;
  activeStreams.delete(sessionId);
  return true;
}

/**
 * Check if there is an active stream running.
 */
export function hasActiveStream(sessionId?: string): boolean {
  return sessionId ? activeStreams.has(sessionId) : activeStreams.size > 0;
}
