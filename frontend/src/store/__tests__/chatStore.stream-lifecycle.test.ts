import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  controller: null as AbortController | null,
  controllers: new Map<string, AbortController>(),
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
  createStreamAbortController: (sessionId: string) => {
    mocks.controller = new AbortController();
    mocks.controllers.set(sessionId, mocks.controller);
    return mocks.controller;
  },
  abortActiveStream: (sessionId: string) => {
    mocks.controllers.get(sessionId)?.abort();
    mocks.controllers.delete(sessionId);
  },
  clearStreamOnComplete: (sessionId: string) => {
    const controller = mocks.controllers.get(sessionId);
    mocks.controllers.delete(sessionId);
    if (mocks.controller === controller) mocks.controller = null;
  },
}));

import { useChatStore } from '../chatStore';
import { chatApi } from '../../api/chat';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const SESSION_B = '44444444-4444-4444-8444-444444444444';
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
  vi.mocked(chatApi.getMessages).mockReset();
  mocks.controller = null;
  mocks.controllers.clear();
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
    turnsBySession: {},
    localPartialsBySession: {},
    messageCacheBySession: {},
    streamPhase: 'idle',
    streamingSessionId: null,
    streamContent: '',
    citations: [],
    streamQuality: null,
    isLoadingMessages: false,
    sendError: null,
    isSendLocked: false,
    _pendingSessionRefresh: false,
    aiStatusText: null,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('sendMessage stream lifecycle', () => {
  it('uses a shorter connection budget than the event-idle budget', async () => {
    let pendingSignal!: AbortSignal;
    mocks.fetch.mockImplementation((_url, init?: RequestInit) => {
      pendingSignal = init?.signal as AbortSignal;
      return new Promise((_resolve, reject) => {
        pendingSignal.addEventListener(
          'abort',
          () => reject(new DOMException('aborted', 'AbortError')),
          { once: true },
        );
      });
    });

    const send = useChatStore.getState().sendMessage('connect');
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(20_001);
    const didTimeout = pendingSignal.aborted;
    if (!didTimeout) pendingSignal.dispatchEvent(new Event('abort'));
    if (!didTimeout) mocks.controller?.abort();
    await send;

    expect(didTimeout).toBe(true);
  });

  it('does not spend the connection budget as the idle budget after headers arrive', async () => {
    let markRead!: () => void;
    const readStarted = new Promise<void>((resolve) => { markRead = resolve; });
    mocks.fetch.mockImplementation(async (_url, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal;
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              markRead();
              return new Promise((_resolve, reject) => {
                signal.addEventListener(
                  'abort',
                  () => reject(new DOMException('aborted', 'AbortError')),
                  { once: true },
                );
              });
            }),
          }),
        },
      };
    });

    const send = useChatStore.getState().sendMessage('idle');
    await readStarted;
    const streamController = mocks.controller!;
    await vi.advanceTimersByTimeAsync(30_001);
    const abortedAtConnectionBudget = streamController.signal.aborted;
    await vi.advanceTimersByTimeAsync(15_000);
    const abortedAtIdleBudget = streamController.signal.aborted;
    if (!abortedAtIdleBudget) mocks.controller?.abort();
    await send;

    expect(abortedAtConnectionBudget).toBe(false);
    expect(abortedAtIdleBudget).toBe(true);
  });

  it('enforces a total budget even while keepalive bytes continually reset idle time', async () => {
    let streamSignal!: AbortSignal;
    mocks.fetch.mockImplementation(async (_url, init?: RequestInit) => {
      streamSignal = init?.signal as AbortSignal;
      return {
        ok: true,
        status: 200,
        headers: new Headers(),
        body: {
          getReader: () => ({
            read: vi.fn(() => new Promise((resolve, reject) => {
              const onAbort = () => {
                clearTimeout(timer);
                reject(new DOMException('aborted', 'AbortError'));
              };
              const timer = setTimeout(() => {
                streamSignal.removeEventListener('abort', onAbort);
                resolve({
                  done: false,
                  value: encoder.encode(': keepalive\n\n'),
                });
              }, 10_000);
              streamSignal.addEventListener('abort', onAbort, { once: true });
            })),
          }),
        },
      };
    });

    const send = useChatStore.getState().sendMessage('long running');
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(180_001);
    const didTimeout = streamSignal.aborted;
    if (!didTimeout) mocks.controller?.abort();
    await send;

    expect(didTimeout).toBe(true);
  });

  it('keeps distinct request identities with their owning sessions across error and switch', async () => {
    const ids = [
      '10000000-0000-4000-8000-000000000001',
      '10000000-0000-4000-8000-000000000002',
      '10000000-0000-4000-8000-000000000003',
      '20000000-0000-4000-8000-000000000001',
      '20000000-0000-4000-8000-000000000002',
      '20000000-0000-4000-8000-000000000003',
    ];
    vi.stubGlobal('crypto', { randomUUID: vi.fn(() => ids.shift()) });
    mocks.fetch.mockImplementation(async (url) => {
      if (String(url).includes(SESSION_B)) {
        return streamResponse([
          `event: token\ndata: {"token":"B answer"}\nevent: done\ndata: {"message_id":"55555555-5555-4555-8555-555555555555","session_id":"${SESSION_B}"}\n`,
        ]);
      }
      return { ok: false, status: 500 };
    });

    await useChatStore.getState().sendMessage('question A');
    useChatStore.getState().setActiveSession(SESSION_B);
    await useChatStore.getState().sendMessage('question B');

    const firstBody = JSON.parse(String((mocks.fetch.mock.calls[0]?.[1] as RequestInit).body));
    const secondBody = JSON.parse(String((mocks.fetch.mock.calls[1]?.[1] as RequestInit).body));
    expect(firstBody.client_request_id).toBe('10000000-0000-4000-8000-000000000001');
    expect(secondBody.client_request_id).toBe('20000000-0000-4000-8000-000000000001');
    expect(firstBody.client_request_id).not.toBe(secondBody.client_request_id);
    expect(mocks.fetch).toHaveBeenCalledTimes(2);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      phase: 'error',
      clientRequestId: firstBody.client_request_id,
    });
    expect(useChatStore.getState().turnsBySession[SESSION_B]).toMatchObject({
      phase: 'idle',
      clientRequestId: secondBody.client_request_id,
    });
  });

  it('ignores a terminal callback from a stale generation', () => {
    useChatStore.setState({
      turnsBySession: {
        [SESSION_ID]: {
          phase: 'streaming',
          isLocked: true,
          content: 'new generation',
          citations: [],
          quality: null,
          error: null,
          aiStatusText: null,
          generationId: 'generation-new',
        },
      },
    });

    useChatStore.getState().finishStreamingMessage('message-old', SESSION_ID, 'generation-old');

    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      phase: 'streaming',
      isLocked: true,
      content: 'new generation',
      generationId: 'generation-new',
    });
    expect(useChatStore.getState().messages.some((message) => message.id === 'message-old')).toBe(false);
  });

  it('actually submits from session B while session A is still streaming', async () => {
    let markReaderStalled!: () => void;
    const readerStalled = new Promise<void>((resolve) => { markReaderStalled = resolve; });
    mocks.fetch.mockImplementation(async (url, init?: RequestInit) => {
      if (String(url).includes(SESSION_B)) {
        return streamResponse([
          `event: token\ndata: {"token":"B answer"}\nevent: done\ndata: {"message_id":"55555555-5555-4555-8555-555555555555","session_id":"${SESSION_B}"}\n`,
        ]);
      }
      const signal = init?.signal as AbortSignal;
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              markReaderStalled();
              return new Promise((_resolve, reject) => {
                signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
              });
            }),
          }),
        },
      };
    });

    const sendA = useChatStore.getState().sendMessage('question A');
    await readerStalled;
    useChatStore.getState().setActiveSession(SESSION_B);
    await useChatStore.getState().sendMessage('question B');
    const postCount = mocks.fetch.mock.calls.length;
    mocks.controllers.get(SESSION_ID)?.abort();
    await sendA;

    expect(postCount).toBe(2);
  });

  it('keeps session A terminal error out of B and restores its partial after remount', async () => {
    let releaseA!: () => void;
    let markAWaiting!: () => void;
    const aWaiting = new Promise<void>((resolve) => { markAWaiting = resolve; });
    mocks.fetch.mockImplementation(async (url) => {
      if (String(url).includes(SESSION_B)) {
        return streamResponse([
          `event: token\ndata: {"token":"B answer"}\nevent: done\ndata: {"message_id":"55555555-5555-4555-8555-555555555555","session_id":"${SESSION_B}"}\n`,
        ]);
      }
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
                  value: encoder.encode('event: token\ndata: {"token":"A partial"}\n'),
                });
              }
              if (readCount === 2) {
                markAWaiting();
                return new Promise((resolve) => {
                  releaseA = () => resolve({
                    done: false,
                    value: encoder.encode('event: token\ndata: not-json\n'),
                  });
                });
              }
              return Promise.resolve({ done: true, value: undefined });
            }),
          }),
        },
      };
    });

    const sendA = useChatStore.getState().sendMessage('question A');
    await aWaiting;
    useChatStore.getState().setActiveSession(SESSION_B);
    await useChatStore.getState().sendMessage('question B');
    const bMessagesBeforeAError = useChatStore.getState().messages.map((message) => message.content);
    releaseA();
    await sendA;

    const state = useChatStore.getState();
    expect(state.turnsBySession[SESSION_B]).toMatchObject({ phase: 'idle', isLocked: false, error: null });
    expect(state.messages.map((message) => message.content)).toEqual(bMessagesBeforeAError);
    expect(state.messages.some((message) => message.content === 'A partial')).toBe(false);
    expect(state.turnsBySession[SESSION_ID]).toMatchObject({ phase: 'error', isLocked: false, error: 'error_generic' });
    expect(state.localPartialsBySession[SESSION_ID]?.map((message) => message.content)).toContain('A partial');

    vi.mocked(chatApi.getMessages).mockResolvedValue({
      results: [],
      next: null,
      previous: null,
    });
    useChatStore.getState().setActiveSession(SESSION_ID);
    await useChatStore.getState().loadMessages(SESSION_ID);

    expect(useChatStore.getState().messages.map((message) => message.content)).toContain('A partial');
  });

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

  it('times out while the initial fetch is still pending', async () => {
    let pendingSignal!: AbortSignal;
    mocks.fetch.mockImplementation((_url, init?: RequestInit) => {
      pendingSignal = init?.signal as AbortSignal;
      return new Promise((_resolve, reject) => {
        pendingSignal.addEventListener(
          'abort',
          () => reject(new DOMException('aborted', 'AbortError')),
          { once: true },
        );
      });
    });

    const send = useChatStore.getState().sendMessage('hello');
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(30_001);
    const didTimeout = pendingSignal.aborted;
    if (!didTimeout) mocks.controller?.abort();
    await send;

    expect(didTimeout).toBe(true);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      phase: 'error',
      isLocked: false,
      error: 'error_timeout',
    });
  });

  it('arms the idle watchdog before the first reader read resolves', async () => {
    let markFirstRead!: () => void;
    const firstRead = new Promise<void>((resolve) => { markFirstRead = resolve; });
    mocks.fetch.mockImplementation(async (_url, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal;
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              markFirstRead();
              return new Promise((_resolve, reject) => {
                signal.addEventListener(
                  'abort',
                  () => reject(new DOMException('aborted', 'AbortError')),
                  { once: true },
                );
              });
            }),
          }),
        },
      };
    });

    const send = useChatStore.getState().sendMessage('hello');
    await firstRead;
    const streamSignal = mocks.controller!.signal;
    await vi.advanceTimersByTimeAsync(45_001);
    const didTimeout = streamSignal.aborted;
    if (!didTimeout) mocks.controller?.abort();
    await send;

    expect(didTimeout).toBe(true);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      phase: 'error',
      isLocked: false,
      error: 'error_timeout',
    });
  });

  it('does not let a prior generation watchdog abort a newer generation', async () => {
    vi.mocked(crypto.randomUUID)
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222221')
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222222')
      .mockReturnValueOnce('22222222-2222-4222-8222-222222222223');
    let secondSignal!: AbortSignal;
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([
        `event: done\ndata: {"message_id":"33333333-3333-4333-8333-333333333333","session_id":"${SESSION_ID}"}\n`,
      ]))
      .mockImplementationOnce((_url, init?: RequestInit) => {
        secondSignal = init?.signal as AbortSignal;
        return new Promise((_resolve, reject) => {
          secondSignal.addEventListener(
            'abort',
            () => reject(new DOMException('aborted', 'AbortError')),
            { once: true },
          );
        });
      });

    await useChatStore.getState().sendMessage('first');
    await vi.advanceTimersByTimeAsync(20_000);
    const secondSend = useChatStore.getState().sendMessage('second');
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(10_001);

    const staleTimerAbortedNewGeneration = secondSignal.aborted;
    mocks.controllers.get(SESSION_ID)?.abort();
    await secondSend;
    expect(staleTimerAbortedNewGeneration).toBe(false);
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

    useChatStore.getState().setActiveSession(SESSION_B);
    useChatStore.getState().setActiveSession(SESSION_ID);
    expect(useChatStore.getState().messages.map((message) => message.content)).toContain('partial answer');

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
                  value: encoder.encode('event: token\ndata: {"token":"partial answer"}\n\n'),
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
    await vi.advanceTimersByTimeAsync(45_001);
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
                  value: encoder.encode('event: token\ndata: {"token":"partial answer"}\n\n'),
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

  it('flushes and stores the owner partial before resetting to a new chat', async () => {
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
                  value: encoder.encode('event: token\ndata: {"token":"partial before new chat"}\n\n'),
                });
              }
              markReaderStalled();
              return new Promise((_resolve, reject) => {
                signal.addEventListener(
                  'abort',
                  () => reject(new DOMException('aborted', 'AbortError')),
                  { once: true },
                );
              });
            }),
          }),
        },
      };
    });

    const send = useChatStore.getState().sendMessage('question before reset');
    await readerStalled;
    useChatStore.getState().resetSession();
    await send;

    expect((useChatStore.getState().localPartialsBySession[SESSION_ID] ?? []).map(
      (message) => message.content,
    )).toContain('partial before new chat');
    useChatStore.getState().setActiveSession(SESSION_ID);
    expect(useChatStore.getState().messages.map((message) => message.content)).toEqual(
      expect.arrayContaining(['question before reset', 'partial before new chat']),
    );
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

    useChatStore.getState().setActiveSession(SESSION_B);
    useChatStore.getState().setActiveSession(SESSION_ID);
    expect(useChatStore.getState().messages.some(
      (message) => message.id === '33333333-3333-4333-8333-333333333333',
    )).toBe(true);
  });

  it('flushes and parses a complete final SSE data line at EOF', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      `event: token\ndata: {"token":"tail answer"}\nevent: done\ndata: {"message_id":"33333333-3333-4333-8333-333333333333","session_id":"${SESSION_ID}"}`,
    ]));

    await useChatStore.getState().sendMessage('hello');

    const state = useChatStore.getState();
    expect(state.messages[state.messages.length - 1]).toMatchObject({
      id: '33333333-3333-4333-8333-333333333333',
      content: 'tail answer',
    });
    expect(state.turnsBySession[SESSION_ID]).toMatchObject({ phase: 'idle', error: null });
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
