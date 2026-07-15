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
import { broadcastSessionSwitch } from '../../sync/crossTabSync';

// Register a batch callback (as sendMessage does) and capture everything it emits.
function collectBatcher(sessionId = 'sess-A', generationId = 'gen-A'): string[] {
  const received: string[] = [];
  initTokenBatcher(sessionId, generationId, (update) => {
    received.push('appendTokens' in update ? update.appendTokens : update.fullContent);
  });
  return received;
}

beforeEach(() => {
  // Node test env has no rAF; stub so appendToken() can schedule without throwing.
  (globalThis as any).requestAnimationFrame = (_cb: unknown) => 1;
  (globalThis as any).cancelAnimationFrame = () => {};
  resetTokenBatcher('sess-A');
  resetTokenBatcher('sess-B');
  useChatStore.setState({
    activeSessionId: null,
    messages: [],
    allMessages: [],
    turnsBySession: {},
    localPartialsBySession: {},
    streamPhase: 'idle',
    streamContent: '',
    streamingSessionId: null,
    isSendLocked: false,
  });
});

describe('setActiveSession — keeps background stream rendering alive (V4.6)', () => {
  it('is a true no-op when selecting the active session again', () => {
    const message = {
      id: 'message-1',
      role: 'user' as const,
      content: 'keep me',
      createdAt: '2026-07-16T00:00:00Z',
    };
    useChatStore.setState({
      activeSessionId: 'sess-A',
      messages: [message],
      allMessages: [message],
      sessionNextCursor: 'session-next',
      messageNextCursor: 'message-next',
      visibleRoundCount: 7,
      hasOlderMessages: true,
      totalRoundCount: 9,
      isLoadingMessages: true,
      streamPhase: 'streaming',
      streamingSessionId: 'sess-A',
      streamContent: 'partial answer',
      sendError: 'error_network',
      isSendLocked: true,
    });

    const before = useChatStore.getState();
    before.setActiveSession('sess-A');

    expect(useChatStore.getState()).toBe(before);
    expect(broadcastSessionSwitch).not.toHaveBeenCalled();
  });

  it('does NOT sever the token-batch callback when switching sessions mid-stream', () => {
    const received = collectBatcher();

    // A stream is in progress for session A.
    useChatStore.setState({
      activeSessionId: 'sess-A',
      turnsBySession: {
        'sess-A': {
          phase: 'streaming', isLocked: true, content: '', citations: [], quality: null,
          error: null, aiStatusText: null, generationId: 'gen-A',
        },
      },
    });
    appendToken('sess-A', 'gen-A', 'Hello');

    // User switches to a different conversation while A is still streaming.
    useChatStore.getState().setActiveSession('sess-B');

    // The still-running background stream keeps delivering tokens.
    appendToken('sess-A', 'gen-A', ' world');
    flushImmediate('sess-A', 'gen-A');

    // Before the fix this was '' — resetTokenBatcher() nulled the callback + wiped the buffer.
    expect(received.join('')).toContain('Hello world');
  });

  it('preserves session A turn while mirroring idle state for session B', () => {
    useChatStore.setState({
      activeSessionId: 'sess-A',
      turnsBySession: {
        'sess-A': {
          phase: 'streaming', isLocked: true, content: 'partial answer', citations: [], quality: null,
          error: null, aiStatusText: null, generationId: 'gen-A',
        },
      },
      streamingSessionId: 'sess-A',
      streamPhase: 'streaming',
      streamContent: 'partial answer',
    });

    useChatStore.getState().setActiveSession('sess-B');

    const s = useChatStore.getState();
    expect(s.activeSessionId).toBe('sess-B');        // the view switched
    expect(s.streamPhase).toBe('idle');
    expect(s.streamContent).toBe('');
    expect(s.streamingSessionId).toBeNull();
    expect(s.turnsBySession['sess-A']).toMatchObject({
      phase: 'streaming', content: 'partial answer', generationId: 'gen-A',
    });
  });
});

describe('resetSession — still tears the batcher down (new chat)', () => {
  it('drops buffered tokens and detaches the callback', () => {
    const received = collectBatcher();
    useChatStore.setState({ activeSessionId: 'sess-A' });
    appendToken('sess-A', 'gen-A', 'partial');

    useChatStore.getState().resetSession();

    appendToken('sess-A', 'gen-A', ' more');
    flushImmediate('sess-A', 'gen-A');

    expect(received.join('')).toBe('');
    expect(useChatStore.getState().streamPhase).toBe('idle');
    expect(useChatStore.getState().streamingSessionId).toBeNull();
    expect(useChatStore.getState().isSendLocked).toBe(false);
  });
});
