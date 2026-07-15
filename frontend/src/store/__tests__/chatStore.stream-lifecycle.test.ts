import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  controller: null as AbortController | null,
}));

vi.mock('../../api/chat', () => ({
  chatApi: {
    createSession: vi.fn(),
    getSessions: vi.fn(),
    getMessages: vi.fn(),
  },
}));

vi.mock('../../api/client', () => ({
  getAuthToken: () => 'test-token',
  getActiveSpaceId: () => null,
}));

vi.mock('../../sync/crossTabSync', () => ({
  broadcastSessionSwitch: vi.fn(),
}));

vi.mock('../../stream/StreamLifecycleManager', () => ({
  createStreamAbortController: () => {
    mocks.controller = new AbortController();
    return mocks.controller;
  },
  abortActiveStream: () => {
    mocks.controller?.abort();
    mocks.controller = null;
  },
  clearStreamOnComplete: () => {
    mocks.controller = null;
  },
}));

import { useChatStore } from '../chatStore';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const encoder = new TextEncoder();

function streamResponse(chunks: string[]) {
  let index = 0;
  return {
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: vi.fn(async () => index < chunks.length
          ? { done: false, value: encoder.encode(chunks[index++]) }
          : { done: true, value: undefined }),
      }),
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-07-16T00:00:00Z'));
  vi.stubGlobal('fetch', mocks.fetch);
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => '22222222-2222-4222-8222-222222222222') });
  vi.stubGlobal('requestAnimationFrame', (_callback: FrameRequestCallback) => 1);
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.spyOn(console, 'log').mockImplementation(() => {});
  mocks.fetch.mockReset();
  mocks.controller = null;
  useChatStore.setState({
    sessions: [],
    sessionNextCursor: null,
    activeSessionId: SESSION_ID,
    messages: [],
    messageNextCursor: null,
    allMessages: [],
    visibleRoundCount: 5,
    hasOlderMessages: false,
    totalRoundCount: 0,
    streamPhase: 'idle',
    streamingSessionId: null,
    streamContent: '',
    citations: [],
    streamQuality: null,
    isLoadingMessages: false,
    sendError: null,
    isSendLocked: false,
    _pendingSessionRefresh: false,
    _isTimeoutAbort: false,
    aiStatusText: null,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('sendMessage stream lifecycle', () => {
  it('issues one POST and exposes a recoverable error when the initial send fails', async () => {
    mocks.fetch.mockResolvedValue({ ok: false, status: 500 });

    const send = useChatStore.getState().sendMessage('hello');
    await vi.runAllTimersAsync();
    await send;

    expect(mocks.fetch).toHaveBeenCalledOnce();
    expect(useChatStore.getState().sendError).toBe('error_server');
    expect(useChatStore.getState().isSendLocked).toBe(false);
    expect(useChatStore.getState().streamingSessionId).toBeNull();
  });

  it('treats EOF without done as recoverable and preserves partial content', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      'event: token\ndata: {"token":"partial answer"}\n',
    ]));

    await useChatStore.getState().sendMessage('hello');

    const state = useChatStore.getState();
    expect(state.messages[state.messages.length - 1]).toMatchObject({ role: 'assistant', content: 'partial answer' });
    expect(state.sendError).toBe('error_network');
    expect(state.isSendLocked).toBe(false);
    expect(state.streamingSessionId).toBeNull();
  });

  it('terminates a parse failure without retrying and preserves partial content', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      'event: token\ndata: {"token":"partial answer"}\nevent: token\ndata: not-json\n',
    ]));

    await useChatStore.getState().sendMessage('hello');

    const state = useChatStore.getState();
    expect(mocks.fetch).toHaveBeenCalledOnce();
    expect(state.messages[state.messages.length - 1]).toMatchObject({ role: 'assistant', content: 'partial answer' });
    expect(state.sendError).toBe('error_generic');
    expect(state.isSendLocked).toBe(false);
    expect(state.streamingSessionId).toBeNull();
  });

  it('times out a stalled stream after partial output and preserves that partial', async () => {
    let markReaderStalled!: () => void;
    const readerStalled = new Promise<void>((resolve) => { markReaderStalled = resolve; });
    mocks.fetch.mockImplementation(async (_url, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal;
      let readCount = 0;
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              if (readCount++ === 0) {
                return Promise.resolve({
                  done: false,
                  value: encoder.encode('event: token\ndata: {"token":"partial answer"}\n'),
                });
              }
              markReaderStalled();
              return new Promise((_resolve, reject) => {
                signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
              });
            }),
          }),
        },
      };
    });

    const send = useChatStore.getState().sendMessage('hello');
    await readerStalled;
    const streamSignal = mocks.controller!.signal;
    await vi.advanceTimersByTimeAsync(33_001);
    const didTimeout = streamSignal.aborted;
    if (!didTimeout) mocks.controller?.abort();
    await send;

    const state = useChatStore.getState();
    expect(didTimeout).toBe(true);
    expect(state.messages[state.messages.length - 1]).toMatchObject({ role: 'assistant', content: 'partial answer' });
    expect(state.sendError).toBe('error_timeout');
    expect(state.isSendLocked).toBe(false);
    expect(state.streamingSessionId).toBeNull();
  });

  it('releases the lock and preserves partial content after a user abort', async () => {
    let markReaderStalled!: () => void;
    const readerStalled = new Promise<void>((resolve) => { markReaderStalled = resolve; });
    mocks.fetch.mockImplementation(async (_url, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal;
      let readCount = 0;
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              if (readCount++ === 0) {
                return Promise.resolve({
                  done: false,
                  value: encoder.encode('event: token\ndata: {"token":"partial answer"}\n'),
                });
              }
              markReaderStalled();
              return new Promise((_resolve, reject) => {
                signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
              });
            }),
          }),
        },
      };
    });

    const send = useChatStore.getState().sendMessage('hello');
    await readerStalled;
    mocks.controller!.abort();
    await send;

    const state = useChatStore.getState();
    expect(state.messages[state.messages.length - 1]).toMatchObject({ role: 'assistant', content: 'partial answer' });
    expect(state.streamPhase).toBe('idle');
    expect(state.sendError).toBeNull();
    expect(state.isSendLocked).toBe(false);
    expect(state.streamingSessionId).toBeNull();
  });

  it('commits an explicit done event as the successful terminal state', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      `event: token\ndata: {"token":"complete answer"}\nevent: done\ndata: {"message_id":"33333333-3333-4333-8333-333333333333","session_id":"${SESSION_ID}"}\n`,
    ]));

    await useChatStore.getState().sendMessage('hello');

    const state = useChatStore.getState();
    expect(state.messages[state.messages.length - 1]).toMatchObject({
      id: '33333333-3333-4333-8333-333333333333',
      role: 'assistant',
      content: 'complete answer',
    });
    expect(state.streamPhase).toBe('idle');
    expect(state.streamContent).toBe('');
    expect(state.sendError).toBeNull();
    expect(state.isSendLocked).toBe(false);
    expect(state.streamingSessionId).toBeNull();
  });

  it('makes an explicit SSE error recoverable and preserves partial content', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      'event: token\ndata: {"token":"partial answer"}\nevent: error\ndata: {"detail":"failed"}\n',
    ]));

    await useChatStore.getState().sendMessage('hello');

    const state = useChatStore.getState();
    expect(state.messages[state.messages.length - 1]).toMatchObject({ role: 'assistant', content: 'partial answer' });
    expect(state.sendError).toBe('error_generic');
    expect(state.isSendLocked).toBe(false);
    expect(state.streamingSessionId).toBeNull();
    expect(mocks.controller).toBeNull();
  });
});
