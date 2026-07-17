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

const SESSION_A = '11111111-1111-4111-8111-111111111111';
const SESSION_B = '44444444-4444-4444-8444-444444444444';
const TURN_ID = '33333333-3333-4333-8333-333333333333';
const FIRST_CLIENT_ID = '10000000-0000-4000-8000-000000000001';
const encoder = new TextEncoder();

function completedResponse(sessionId: string) {
  let read = false;
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    body: {
      getReader: () => ({
        read: vi.fn(async () => {
          if (read) return { done: true, value: undefined };
          read = true;
          return {
            done: false,
            value: encoder.encode(
              `event: token\ndata: {"token":"answer"}\nevent: done\ndata: {"message_id":"55555555-5555-4555-8555-555555555555","session_id":"${sessionId}"}\n`,
            ),
          };
        }),
      }),
    },
  };
}

beforeEach(() => {
  vi.stubGlobal('fetch', mocks.fetch);
  const ids = [
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000003',
    '20000000-0000-4000-8000-000000000001',
    '20000000-0000-4000-8000-000000000002',
    '20000000-0000-4000-8000-000000000003',
  ];
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => ids.shift()) });
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.spyOn(console, 'error').mockImplementation(() => {});
  mocks.fetch.mockReset();
  mocks.controllers.clear();
  useChatStore.setState({
    sessions: [],
    sessionNextCursor: null,
    activeSessionId: SESSION_A,
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

describe('per-Turn answer mode', () => {
  it('submits deep only with an explicit eligibility decision and keeps it on the owning Turn', async () => {
    mocks.fetch.mockResolvedValue(completedResponse(SESSION_A));

    await (useChatStore.getState().sendMessage as any)('deep question', {
      answerMode: 'deep',
      canUseDeep: true,
    });

    const body = JSON.parse(String((mocks.fetch.mock.calls[0]?.[1] as RequestInit).body));
    expect(body.answer_mode).toBe('deep');
    expect(useChatStore.getState().turnsBySession[SESSION_A]?.answerMode).toBe('deep');
  });

  it('fails closed without a deep eligibility decision and never starts a POST', async () => {
    mocks.fetch.mockResolvedValue(completedResponse(SESSION_A));

    await (useChatStore.getState().sendMessage as any)('forged deep question', {
      answerMode: 'deep',
    });

    expect(mocks.fetch).not.toHaveBeenCalled();
    expect(useChatStore.getState().sendError).toBe('error_deep_unavailable');
    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it('does not relabel an earlier session Turn when a later session uses fast', async () => {
    mocks.fetch
      .mockResolvedValueOnce({ ok: false, status: 500, headers: new Headers() })
      .mockResolvedValueOnce(completedResponse(SESSION_B));

    await (useChatStore.getState().sendMessage as any)('deep A', {
      answerMode: 'deep',
      canUseDeep: true,
    });
    useChatStore.getState().setActiveSession(SESSION_B);
    await (useChatStore.getState().sendMessage as any)('fast B', { answerMode: 'fast' });

    expect(useChatStore.getState().turnsBySession[SESSION_A]?.answerMode).toBe('deep');
    expect(useChatStore.getState().turnsBySession[SESSION_B]?.answerMode).toBe('fast');
  });

  it.each([403, 409])(
    'surfaces a stable deep-unavailable error for HTTP %s without resubmitting the POST',
    async (status) => {
      mocks.fetch.mockResolvedValue({ ok: false, status, headers: new Headers() });

      await (useChatStore.getState().sendMessage as any)('deep denied', {
        answerMode: 'deep',
        canUseDeep: true,
      });

      expect(mocks.fetch).toHaveBeenCalledOnce();
      expect(useChatStore.getState().sendError).toBe('error_deep_unavailable');
    },
  );

  it('reuses the failed deep Turn for an explicit fast retry without appending a second question', async () => {
    const deepFailure = completedResponse(SESSION_A);
    deepFailure.headers = new Headers({
      'X-Chat-Turn-Id': TURN_ID,
      'X-Chat-Client-Request-Id': FIRST_CLIENT_ID,
    });
    let firstRead = false;
    deepFailure.body.getReader = () => ({
      read: vi.fn(async () => {
        if (firstRead) return { done: true, value: undefined };
        firstRead = true;
        return {
          done: false,
          value: encoder.encode(
            `id: 1\nevent: meta\ndata: {"turn_id":"${TURN_ID}","session_id":"${SESSION_A}","client_request_id":"${FIRST_CLIENT_ID}","protocol_version":2}\n\n`
            + 'id: 2\nevent: error\ndata: {"code":"provider_unavailable","retryable":true}\n\n',
          ),
        };
      }),
    });

    let secondRead = false;
    const fastSuccess = completedResponse(SESSION_A);
    fastSuccess.headers = new Headers({
      'X-Chat-Turn-Id': TURN_ID,
      'X-Chat-Client-Request-Id': FIRST_CLIENT_ID,
    });
    fastSuccess.body.getReader = () => ({
      read: vi.fn(async () => {
        if (secondRead) return { done: true, value: undefined };
        secondRead = true;
        return {
          done: false,
          value: encoder.encode(
            `id: 3\nevent: meta\ndata: {"turn_id":"${TURN_ID}","session_id":"${SESSION_A}","client_request_id":"${FIRST_CLIENT_ID}","protocol_version":2}\n\n`
            + 'id: 4\nevent: answer_delta\ndata: {"text":"fast answer"}\n\n'
            + `id: 5\nevent: done\ndata: {"message_id":"55555555-5555-4555-8555-555555555555","session_id":"${SESSION_A}","turn_id":"${TURN_ID}","client_request_id":"${FIRST_CLIENT_ID}"}\n\n`,
          ),
        };
      }),
    });
    mocks.fetch.mockResolvedValueOnce(deepFailure).mockResolvedValueOnce(fastSuccess);

    await (useChatStore.getState().sendMessage as any)('one question', {
      answerMode: 'deep',
      canUseDeep: true,
    });
    await (useChatStore.getState().sendMessage as any)('one question', {
      answerMode: 'fast',
      retryClientRequestId: FIRST_CLIENT_ID,
    });

    const bodies = mocks.fetch.mock.calls.map((call) => JSON.parse(String((call[1] as RequestInit).body)));
    expect(bodies).toHaveLength(2);
    expect(bodies.map((body) => body.client_request_id)).toEqual([FIRST_CLIENT_ID, FIRST_CLIENT_ID]);
    expect(bodies.map((body) => body.answer_mode)).toEqual(['deep', 'fast']);
    expect(useChatStore.getState().messages.filter((message) => message.role === 'user')).toHaveLength(1);
    expect(useChatStore.getState().turnsBySession[SESSION_A]).toMatchObject({
      answerMode: 'fast',
      clientRequestId: FIRST_CLIENT_ID,
      turnId: TURN_ID,
    });
  });

  it('regenerates a persisted assistant version without duplicating the question', async () => {
    const assistantId = '66666666-6666-4666-8666-666666666666';
    const existingMessages = [
      { id: '77777777-7777-4777-8777-777777777777', role: 'user' as const, content: 'one question', createdAt: '2026-07-17T01:00:00Z' },
      { id: assistantId, role: 'assistant' as const, content: 'old answer', createdAt: '2026-07-17T01:00:01Z' },
    ];
    useChatStore.setState({
      messages: existingMessages,
      allMessages: existingMessages,
      messageCacheBySession: { [SESSION_A]: existingMessages },
      totalRoundCount: 1,
    });
    mocks.fetch.mockResolvedValue(completedResponse(SESSION_A));

    await useChatStore.getState().sendMessage('one question', {
      answerMode: 'fast',
      regenerateMessageId: assistantId,
    });

    expect(mocks.fetch.mock.calls[0]?.[0]).toBe(`/api/v1/chat/messages/${assistantId}/regenerate/`);
    expect(useChatStore.getState().messages.filter((message) => message.role === 'user')).toHaveLength(1);
    expect(useChatStore.getState().messages.some((message) => message.id === assistantId)).toBe(false);
    expect(useChatStore.getState().messages.some((message) => message.content === 'answer')).toBe(true);
  });
});
