import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
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
  getActiveSpaceId: () => 'space-1',
}));

vi.mock('../../sync/crossTabSync', () => ({ broadcastSessionSwitch: vi.fn() }));

vi.mock('../../stream/StreamLifecycleManager', () => ({
  createStreamAbortController: (sessionId: string) => {
    const controller = new AbortController();
    mocks.controllers.set(sessionId, controller);
    return controller;
  },
  abortActiveStream: (sessionId: string) => {
    mocks.controllers.get(sessionId)?.abort();
    mocks.controllers.delete(sessionId);
  },
  clearStreamOnComplete: (sessionId: string) => {
    mocks.controllers.delete(sessionId);
  },
  hasActiveStream: (sessionId?: string) => (
    sessionId ? mocks.controllers.has(sessionId) : mocks.controllers.size > 0
  ),
}));

import { useChatStore } from '../chatStore';

const SESSION_ID = '11111111-1111-4111-8111-111111111111';
const SESSION_B = '44444444-4444-4444-8444-444444444444';
const TURN_ID = '33333333-3333-4333-8333-333333333333';
const CLIENT_ID = '22222222-2222-4222-8222-222222222221';
const GENERATION_ID = '22222222-2222-4222-8222-222222222222';
const USER_MESSAGE_ID = '22222222-2222-4222-8222-222222222223';
const ASSISTANT_ID = '55555555-5555-4555-8555-555555555555';
const encoder = new TextEncoder();

function streamResponse(chunks: string[], headers: Record<string, string> = {}) {
  let index = 0;
  return {
    ok: true,
    status: 200,
    headers: new Headers(headers),
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
  vi.stubGlobal('fetch', mocks.fetch);
  const ids = [CLIENT_ID, GENERATION_ID, USER_MESSAGE_ID];
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => ids.shift() ?? USER_MESSAGE_ID) });
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.spyOn(console, 'error').mockImplementation(() => {});
  mocks.fetch.mockReset();
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
  vi.unstubAllGlobals();
});

describe('chat stream v2 and recovery', () => {
  it('keeps legacy v1 token and done events compatible', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      `event: token\ndata: {"token":"legacy answer"}\nevent: done\ndata: {"message_id":"${ASSISTANT_ID}","session_id":"${SESSION_ID}"}\n`,
    ]));

    await useChatStore.getState().sendMessage('hello');

    expect(useChatStore.getState().messages[useChatStore.getState().messages.length - 1]).toMatchObject({
      id: ASSISTANT_ID,
      content: 'legacy answer',
    });
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      protocolVersion: 1,
      phase: 'idle',
      error: null,
    });
  });

  it('captures matching header/meta identity and commits a v2 answer', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      `id: 1\r\nevent: meta\r\ndata: {"turn_id":"${TURN_ID}","session_id":"${SESSION_ID}","client_request_id":"${CLIENT_ID}","protocol_version":2}\r\n\r\n`,
      'id: 2\nevent: phase\ndata: {"phase":"retrieving"}\n\n',
      'id: 3\nevent: answer_delta\ndata: {"text":"complete answer"}\n\n',
      `id: 4\nevent: done\ndata: {"message_id":"${ASSISTANT_ID}","session_id":"${SESSION_ID}","turn_id":"${TURN_ID}","client_request_id":"${CLIENT_ID}"}`,
    ], {
      'X-Chat-Turn-Id': TURN_ID,
      'X-Chat-Client-Request-Id': CLIENT_ID,
    }));

    await useChatStore.getState().sendMessage('hello');

    expect(useChatStore.getState().messages[useChatStore.getState().messages.length - 1]).toMatchObject({
      id: ASSISTANT_ID,
      role: 'assistant',
      content: 'complete answer',
    });
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      turnId: TURN_ID,
      clientRequestId: CLIENT_ID,
      lastEventSeq: 4,
      protocolVersion: 2,
      recoveryState: 'idle',
      phase: 'idle',
      error: null,
    });
  });

  it('rejects a response whose header and meta identities disagree', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([
      `id: 1\nevent: meta\ndata: {"turn_id":"${TURN_ID}","session_id":"${SESSION_ID}","client_request_id":"${CLIENT_ID}","protocol_version":2}\n\n`,
    ], {
      'X-Chat-Turn-Id': '66666666-6666-4666-8666-666666666666',
      'X-Chat-Client-Request-Id': CLIENT_ID,
    }));

    await useChatStore.getState().sendMessage('hello');

    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      phase: 'error',
      isLocked: false,
      error: 'error_generic',
    });
    expect(useChatStore.getState().messages.some((message) => message.role === 'assistant')).toBe(false);
  });

  it('rejects a meta event for another session or client request', async () => {
    const otherSession = '77777777-7777-4777-8777-777777777777';
    mocks.fetch.mockResolvedValue(streamResponse([
      `id: 1\nevent: meta\ndata: {"turn_id":"${TURN_ID}","session_id":"${otherSession}","client_request_id":"${CLIENT_ID}","protocol_version":2}\n\n`,
    ], {
      'X-Chat-Turn-Id': TURN_ID,
      'X-Chat-Client-Request-Id': CLIENT_ID,
    }));

    await useChatStore.getState().sendMessage('hello');

    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      phase: 'error',
      error: 'error_generic',
    });
  });

  it('retains the client request identity when no server turn identity was received', async () => {
    mocks.fetch.mockResolvedValue(streamResponse([]));

    await useChatStore.getState().sendMessage('hello');

    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      clientRequestId: CLIENT_ID,
      turnId: null,
      recoveryState: 'failed',
      phase: 'error',
      error: 'error_network',
    });
  });

  it('recovers an interrupted stream with GET only and ignores replayed event ids', async () => {
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([
        `id: 1\nevent: meta\ndata: {"turn_id":"${TURN_ID}","session_id":"${SESSION_ID}","client_request_id":"${CLIENT_ID}","protocol_version":2}\n\n`,
        'id: 2\nevent: answer_delta\ndata: {"text":"part"}\n\n',
      ], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockResolvedValueOnce(streamResponse([
        'id: 2\nevent: answer_delta\ndata: {"text":"part"}\n\n',
        'id: 3\nevent: answer_delta\ndata: {"text":"ial"}\n\n',
        `id: 4\nevent: done\ndata: {"message_id":"${ASSISTANT_ID}","session_id":"${SESSION_ID}","turn_id":"${TURN_ID}","client_request_id":"${CLIENT_ID}"}\n\n`,
        `id: 4\nevent: done\ndata: {"message_id":"${ASSISTANT_ID}","session_id":"${SESSION_ID}","turn_id":"${TURN_ID}","client_request_id":"${CLIENT_ID}"}\n\n`,
      ], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
        'X-Chat-Turn-Status': 'completed',
      }));

    await useChatStore.getState().sendMessage('hello');

    expect(mocks.fetch).toHaveBeenCalledTimes(2);
    expect(mocks.fetch.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    expect(String(mocks.fetch.mock.calls[1][0])).toBe(
      `/api/v1/chat/turns/${TURN_ID}/events/?after=2`,
    );
    expect(mocks.fetch.mock.calls[1][1]).toMatchObject({ method: 'GET' });
    expect(useChatStore.getState().messages[useChatStore.getState().messages.length - 1]).toMatchObject({
      id: ASSISTANT_ID,
      content: 'partial',
    });
    expect(useChatStore.getState().messages.filter((message) => message.id === ASSISTANT_ID)).toHaveLength(1);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      lastEventSeq: 4,
      recoveryState: 'recovered',
      phase: 'idle',
      error: null,
    });
  });

  it('uses the same GET-only recovery path after a reader network failure', async () => {
    let readCount = 0;
    mocks.fetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({
          'X-Chat-Turn-Id': TURN_ID,
          'X-Chat-Client-Request-Id': CLIENT_ID,
        }),
        body: {
          getReader: () => ({
            read: vi.fn(async () => {
              if (readCount++ === 0) {
                return {
                  done: false,
                  value: encoder.encode(
                    `id: 1\nevent: meta\ndata: {"turn_id":"${TURN_ID}","session_id":"${SESSION_ID}","client_request_id":"${CLIENT_ID}","protocol_version":2}\n\n`,
                  ),
                };
              }
              throw new TypeError('NetworkError while reading');
            }),
          }),
        },
      })
      .mockResolvedValueOnce(streamResponse([
        `id: 2\nevent: done\ndata: {"message_id":"${ASSISTANT_ID}","session_id":"${SESSION_ID}","turn_id":"${TURN_ID}","client_request_id":"${CLIENT_ID}"}\n\n`,
      ], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }));

    await useChatStore.getState().sendMessage('hello');

    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'GET')).toHaveLength(1);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      recoveryState: 'recovered',
      phase: 'idle',
      error: null,
    });
  });

  it('does not advance the replay cursor past a malformed event', async () => {
    vi.useFakeTimers();
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockResolvedValueOnce(streamResponse([
        'id: 5\nevent: answer_delta\ndata: not-json\n\n',
      ], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockResolvedValueOnce(streamResponse([
        'id: 5\nevent: answer_delta\ndata: {"text":"kept"}\n\n',
        `id: 6\nevent: done\ndata: {"message_id":"${ASSISTANT_ID}","session_id":"${SESSION_ID}","turn_id":"${TURN_ID}","client_request_id":"${CLIENT_ID}"}\n\n`,
      ], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }));

    const send = useChatStore.getState().sendMessage('hello');
    await vi.runAllTimersAsync();
    await send;

    expect(String(mocks.fetch.mock.calls[2][0])).toContain('after=0');
    expect(useChatStore.getState().messages[useChatStore.getState().messages.length - 1]).toMatchObject({
      id: ASSISTANT_ID,
      content: 'kept',
    });
    vi.useRealTimers();
  });

  it('converges a replayed terminal error without retrying the POST', async () => {
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockResolvedValueOnce(streamResponse([
        'id: 8\nevent: error\ndata: {"code":"worker_lost","retryable":true}\n\n',
      ], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
        'X-Chat-Turn-Status': 'failed',
      }));

    await useChatStore.getState().sendMessage('hello');

    expect(mocks.fetch).toHaveBeenCalledTimes(2);
    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      lastEventSeq: 8,
      recoveryState: 'failed',
      phase: 'error',
      error: 'error_generic',
    });
  });

  it('uses the status answer when the replay buffer is empty but the turn completed', async () => {
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
        'X-Chat-Turn-Status': 'completed',
      }))
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: vi.fn(async () => ({
          id: TURN_ID,
          client_request_id: CLIENT_ID,
          session: SESSION_ID,
          status: 'completed',
          last_event_seq: 12,
          answer: {
            id: ASSISTANT_ID,
            role: 'assistant',
            content: 'answer from status',
            citations: [],
            confidence_score: 0.9,
            confidence_label: 'high',
            needs_human_review: false,
            retrieval_mode: 'hybrid',
            retrieval_latency_ms: 42,
            created_at: '2026-07-16T00:00:00Z',
          },
        })),
      });

    await useChatStore.getState().sendMessage('hello');

    expect(mocks.fetch).toHaveBeenCalledTimes(3);
    expect(String(mocks.fetch.mock.calls[2][0])).toBe(`/api/v1/chat/turns/${TURN_ID}/`);
    expect(mocks.fetch.mock.calls[2][1]).toMatchObject({ method: 'GET' });
    expect(useChatStore.getState().messages[useChatStore.getState().messages.length - 1]).toMatchObject({
      id: ASSISTANT_ID,
      content: 'answer from status',
      confidenceScore: 0.9,
    });
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      lastEventSeq: 12,
      recoveryState: 'recovered',
      phase: 'idle',
      error: null,
    });
  });

  it('stops GET recovery when its owning session is deleted', async () => {
    let getStarted!: () => void;
    const didStartGet = new Promise<void>((resolve) => { getStarted = resolve; });
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockImplementationOnce((_url, init?: RequestInit) => {
        getStarted();
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('aborted', 'AbortError')),
            { once: true },
          );
        });
      });

    const send = useChatStore.getState().sendMessage('hello');
    await didStartGet;
    useChatStore.getState().removeSessionState(SESSION_ID);
    await send;

    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'GET')).toHaveLength(1);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toBeUndefined();
  });

  it('unlocks the owning turn when the user cancels during GET recovery', async () => {
    let getStarted!: () => void;
    const didStartGet = new Promise<void>((resolve) => { getStarted = resolve; });
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockImplementationOnce((_url, init?: RequestInit) => {
        getStarted();
        return new Promise((_resolve, reject) => {
          init?.signal?.addEventListener(
            'abort',
            () => reject(new DOMException('aborted', 'AbortError')),
            { once: true },
          );
        });
      });

    const send = useChatStore.getState().sendMessage('hello');
    await didStartGet;
    useChatStore.getState().abortSessionStream(SESSION_ID);
    await send;

    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      phase: 'idle',
      isLocked: false,
      recoveryState: 'idle',
      error: null,
    });
  });

  it('keeps recovery for session A isolated while session B remains usable', async () => {
    let startRecovery!: () => void;
    let releaseRecovery!: () => void;
    const recoveryStarted = new Promise<void>((resolve) => { startRecovery = resolve; });
    const recoveryResponse = new Promise<ReturnType<typeof streamResponse>>((resolve) => {
      releaseRecovery = () => resolve(streamResponse([
        'id: 1\nevent: answer_delta\ndata: {"text":"A recovered"}\n\n',
        `id: 2\nevent: done\ndata: {"message_id":"${ASSISTANT_ID}","session_id":"${SESSION_ID}","turn_id":"${TURN_ID}","client_request_id":"${CLIENT_ID}"}\n\n`,
      ], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }));
    });
    mocks.fetch.mockImplementation(async (url, init?: RequestInit) => {
      if (init?.method === 'GET') {
        startRecovery();
        return recoveryResponse;
      }
      if (String(url).includes(SESSION_B)) {
        return streamResponse([
          `event: token\ndata: {"token":"B answer"}\nevent: done\ndata: {"message_id":"66666666-6666-4666-8666-666666666666","session_id":"${SESSION_B}"}\n`,
        ]);
      }
      return streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      });
    });

    const sendA = useChatStore.getState().sendMessage('question A');
    await recoveryStarted;
    useChatStore.getState().setActiveSession(SESSION_B);
    await useChatStore.getState().sendMessage('question B');
    const sessionBMessages = useChatStore.getState().messages.map((message) => message.content);
    expect(useChatStore.getState().isSendLocked).toBe(false);

    releaseRecovery();
    await sendA;

    expect(useChatStore.getState().activeSessionId).toBe(SESSION_B);
    expect(useChatStore.getState().messages.map((message) => message.content)).toEqual(sessionBMessages);
    expect(sessionBMessages).toContain('B answer');
    expect(sessionBMessages).not.toContain('A recovered');
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      recoveryState: 'recovered',
      phase: 'idle',
    });
    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
  });

  it('ends in an explicit recoverable timeout after bounded GET failures', async () => {
    vi.useFakeTimers();
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockRejectedValue(new TypeError('Failed to fetch'));

    const send = useChatStore.getState().sendMessage('hello');
    await vi.runAllTimersAsync();
    await send;

    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'GET')).toHaveLength(3);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      recoveryState: 'failed',
      phase: 'error',
      isLocked: false,
      error: 'error_timeout',
      turnId: TURN_ID,
      clientRequestId: CLIENT_ID,
    });
    vi.useRealTimers();
  });

  it('bounds recovery when each GET remains pending', async () => {
    vi.useFakeTimers();
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockImplementation((_url, init?: RequestInit) => new Promise((_resolve, reject) => {
        init?.signal?.addEventListener(
          'abort',
          () => reject(new DOMException('aborted', 'AbortError')),
          { once: true },
        );
      }));

    const send = useChatStore.getState().sendMessage('hello');
    await vi.advanceTimersByTimeAsync(20_000);
    await send;

    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'GET')).toHaveLength(3);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      recoveryState: 'failed',
      phase: 'error',
      error: 'error_timeout',
    });
    vi.useRealTimers();
  });

  it('bounds recovery when GET headers arrive but the replay body stalls', async () => {
    vi.useFakeTimers();
    mocks.fetch
      .mockResolvedValueOnce(streamResponse([], {
        'X-Chat-Turn-Id': TURN_ID,
        'X-Chat-Client-Request-Id': CLIENT_ID,
      }))
      .mockImplementation((_url, init?: RequestInit) => Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({
          'X-Chat-Turn-Id': TURN_ID,
          'X-Chat-Client-Request-Id': CLIENT_ID,
        }),
        body: {
          getReader: () => ({
            read: () => new Promise((_resolve, reject) => {
              init?.signal?.addEventListener(
                'abort',
                () => reject(new DOMException('aborted', 'AbortError')),
                { once: true },
              );
            }),
          }),
        },
      }));

    const send = useChatStore.getState().sendMessage('hello');
    await vi.advanceTimersByTimeAsync(20_000);
    await send;

    expect(mocks.fetch.mock.calls.filter(([, init]) => init?.method === 'GET')).toHaveLength(3);
    expect(useChatStore.getState().turnsBySession[SESSION_ID]).toMatchObject({
      recoveryState: 'failed',
      error: 'error_timeout',
    });
    vi.useRealTimers();
  });
});
