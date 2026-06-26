/**
 * Stream Lifecycle Manager — V3.5 CRIT-001/CRIT-002 fix
 *
 * Module-level singleton for managing SSE stream AbortController lifecycle.
 * NOT stored in Zustand (AbortController is not serializable and should
 * not be part of immutable state model).
 *
 * Key responsibilities:
 * 1. Create AbortController per stream, abort any previous stream before starting new one
 * 2. Track which session owns the active stream (session ID verification in finishStreamingMessage)
 * 3. Provide abort function for session switch / delete / reset scenarios
 * 4. Clean up references when stream completes naturally
 *
 * ─── V4.0 DEFECT-006 DESIGN NOTE — Architectural constraints of module-level state ───
 *
 * activeAbortController and activeStreamSessionId are module-level singleton
 * variables, NOT stored in Zustand (AbortController is not serializable).
 * This creates three implications documented here:
 *
 * 1. CROSS-TAB ISOLATION: Each browser tab has its own JS context with its own
 *    module-level variables. If Tab A is streaming and Tab B switches sessions,
 *    Tab B's abortActiveStream() does NOT affect Tab A's stream.
 *    Mitigation: BroadcastChannel (see DEFECT-008 / crossTabSync.ts).
 *
 * 2. DUAL-STATE MANAGEMENT: streamPhase/isSendLocked (Zustand) and
 *    activeAbortController/activeStreamSessionId (module-level) are managed
 *    by different mechanisms. Zustand's set() is synchronous, but React
 *    component re-renders are batched (async). The sendMessage function reads
 *    Zustand internal state via get(), so the send lock is effective despite
 *    React batching delay.
 *
 * 3. JS SINGLE-THREAD SAFETY: createStreamAbortController() calls
 *    abortActiveStream() → new AbortController() → assigns module variables,
 *    all in one synchronous function. JS event loop guarantees no interleaving
 *    of these steps. There is no real TOCTOU race condition.
 *
 * [Source: V4.0/deep_sys_defect_list.md §DEFECT-006]
 * [Source: V3.4/bug_list.md §CRIT-001] + [Source: V3.5/reports/综合审计报告.md §streamPhase修复]
 */

let activeAbortController: AbortController | null = null;
let activeStreamSessionId: string | null = null;

/**
 * Create a new AbortController for a stream, aborting any previously active stream.
 * Called at the start of sendMessage and on each retry attempt.
 */
export function createStreamAbortController(sessionId: string): AbortController {
  // Abort any previous stream before starting new one
  abortActiveStream();

  const controller = new AbortController();
  activeAbortController = controller;
  activeStreamSessionId = sessionId;
  return controller;
}

/**
 * Abort the currently active SSE stream and clear references.
 * Called on session switch, session delete, new chat reset, and any scenario
 * where the old stream must be killed to prevent data pollution.
 */
export function abortActiveStream(): void {
  if (activeAbortController) {
    activeAbortController.abort();
    activeAbortController = null;
    activeStreamSessionId = null;
  }
}

/**
 * Get the session ID that owns the currently active stream.
 * Used in finishStreamingMessage to verify that completing stream
 * belongs to the currently active session (prevents cross-session data pollution).
 */
export function getActiveStreamSessionId(): string | null {
  return activeStreamSessionId;
}

/**
 * Clear references after stream completes naturally (done event).
 * Does NOT abort — the stream is already finished.
 */
export function clearStreamOnComplete(): void {
  activeAbortController = null;
  activeStreamSessionId = null;
}

/**
 * Check if there is an active stream running.
 */
export function hasActiveStream(): boolean {
  return activeAbortController !== null;
}
