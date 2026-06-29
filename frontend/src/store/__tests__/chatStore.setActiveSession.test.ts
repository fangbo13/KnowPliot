/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

/**
 * Regression test for the V4.6 "keep streaming when switching conversations" fix.
 *
 * Bug (reported): switching conversations mid-stream stopped the AI's streaming output.
 * Root cause: setActiveSession() called resetTokenBatcher(), which nulled the
 * token-batch callback and wiped the buffer. The background SSE stream kept running
 * (setActiveSession does not abort it), but appendToken→flushBatch then found
 * batchCallback === null and silently dropped every token, so streamContent froze at
 * the switch point and the answer appeared stopped/truncated.
 *
 * Fix: setActiveSession() no longer tears the token batcher down. Only resetSession()
 * (new chat) and explicit aborts do. Display is still scoped per-session via
 * streamingSessionId === activeSessionId.
 *
 * Runs in vitest's default Node environment (no DOM), so:
 *  - crossTabSync (BroadcastChannel) is mocked out.
 *  - requestAnimationFrame / cancelAnimationFrame are stubbed.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';

// Avoid constructing a real BroadcastChannel at import time (Node env, no DOM).
vi.mock('../../sync/crossTabSync', () => ({
  broadcastSessionSwitch: vi.fn(),
  broadcastSessionDelete: vi.fn(),
  initCrossTabSync: vi.fn(),
}));

import { useChatStore } from '../chatStore';
import {
  initTokenBatcher,
  appendToken,
  flushImmediate,
  resetTokenBatcher,
} from '../../stream/TokenBatchRenderer';

// Register a batch callback (as sendMessage does) and capture everything it emits.
function collectBatcher(): string[] {
  const received: string[] = [];
  initTokenBatcher((update) => {
    received.push('appendTokens' in update ? update.appendTokens : update.fullContent);
  });
  return received;
}

beforeEach(() => {
  // Node test env has no rAF; stub so appendToken() can schedule without throwing.
  (globalThis as any).requestAnimationFrame = (_cb: unknown) => 1;
  (globalThis as any).cancelAnimationFrame = () => {};
  resetTokenBatcher();
  useChatStore.setState({
    activeSessionId: null,
    messages: [],
    allMessages: [],
    streamPhase: 'idle',
    streamContent: '',
    streamingSessionId: null,
    isSendLocked: false,
  });
});

describe('setActiveSession — keeps background stream rendering alive (V4.6)', () => {
  it('does NOT sever the token-batch callback when switching sessions mid-stream', () => {
    const received = collectBatcher();

    // A stream is in progress for session A.
    useChatStore.setState({ streamingSessionId: 'sess-A', streamPhase: 'streaming' });
    appendToken('Hello');

    // User switches to a different conversation while A is still streaming.
    useChatStore.getState().setActiveSession('sess-B');

    // The still-running background stream keeps delivering tokens.
    appendToken(' world');
    flushImmediate();

    // Before the fix this was '' — resetTokenBatcher() nulled the callback + wiped the buffer.
    expect(received.join('')).toContain('Hello world');
  });

  it('preserves streamPhase / streamContent / streamingSessionId across a switch', () => {
    useChatStore.setState({
      streamingSessionId: 'sess-A',
      streamPhase: 'streaming',
      streamContent: 'partial answer',
    });

    useChatStore.getState().setActiveSession('sess-B');

    const s = useChatStore.getState();
    expect(s.activeSessionId).toBe('sess-B');        // the view switched
    expect(s.streamPhase).toBe('streaming');         // the stream keeps running
    expect(s.streamContent).toBe('partial answer');  // partial output not discarded
    expect(s.streamingSessionId).toBe('sess-A');     // stream still owned by A
  });
});

describe('resetSession — still tears the batcher down (new chat)', () => {
  it('drops buffered tokens and detaches the callback', () => {
    const received = collectBatcher();
    appendToken('partial');

    useChatStore.getState().resetSession();

    appendToken(' more');
    flushImmediate();

    expect(received.join('')).toBe('');
    expect(useChatStore.getState().streamPhase).toBe('idle');
    expect(useChatStore.getState().streamingSessionId).toBeNull();
  });
});
