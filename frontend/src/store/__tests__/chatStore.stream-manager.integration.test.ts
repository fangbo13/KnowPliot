import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

import { useChatStore } from '../chatStore';
import {
  abortActiveStream,
  createStreamAbortController,
  getActiveStreamGenerationId,
  hasActiveStream,
} from '../../stream/StreamLifecycleManager';

const SESSION_A = '11111111-1111-4111-8111-111111111111';
const SESSION_B = '22222222-2222-4222-8222-222222222222';

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal('requestAnimationFrame', () => 1);
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  const uuids = [
    'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'aaaaaaab-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
    'bbbbbbbc-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  ];
  vi.stubGlobal('crypto', { randomUUID: vi.fn(() => uuids.shift() ?? 'cccccccc-cccc-4ccc-8ccc-cccccccccccc') });
  abortActiveStream(SESSION_A);
  abortActiveStream(SESSION_B);
  useChatStore.setState({
    activeSessionId: SESSION_A,
    messages: [],
    allMessages: [],
    turnsBySession: {},
    localPartialsBySession: {},
    messageCacheBySession: {},
    streamPhase: 'idle',
    streamingSessionId: null,
    streamContent: '',
    citations: [],
    streamQuality: null,
    sendError: null,
    isSendLocked: false,
    _pendingSessionRefresh: false,
  });
});

afterEach(() => {
  abortActiveStream(SESSION_A);
  abortActiveStream(SESSION_B);
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('chatStore with the actual keyed StreamLifecycleManager', () => {
  it('keeps A registered when B starts and is stopped', async () => {
    const aReadStarted = deferred<void>();
    const bReadStarted = deferred<void>();
    vi.stubGlobal('fetch', vi.fn(async (url, init?: RequestInit) => {
      const sessionId = String(url).includes(SESSION_B) ? SESSION_B : SESSION_A;
      const signal = init?.signal as AbortSignal;
      return {
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: vi.fn(() => {
              (sessionId === SESSION_A ? aReadStarted : bReadStarted).resolve();
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
    }));

    const sendA = useChatStore.getState().sendMessage('question A');
    await aReadStarted.promise;
    useChatStore.getState().setActiveSession(SESSION_B);
    const sendB = useChatStore.getState().sendMessage('question B');
    await bReadStarted.promise;

    const generationA = getActiveStreamGenerationId(SESSION_A);
    const generationB = getActiveStreamGenerationId(SESSION_B);
    expect(generationA).not.toBeNull();
    expect(generationB).not.toBeNull();
    expect(hasActiveStream(SESSION_A)).toBe(true);
    expect(hasActiveStream(SESSION_B)).toBe(true);

    abortActiveStream(SESSION_B, generationB!);
    await sendB;
    expect(hasActiveStream(SESSION_A)).toBe(true);

    abortActiveStream(SESSION_A, generationA!);
    await sendA;
  });

  it('lets a real stale connection timer fire without aborting the replacement generation', async () => {
    const pendingFetch = deferred<{
      ok: boolean;
      status: number;
      body: { getReader: () => { read: () => Promise<{ done: true; value: undefined }> } };
    }>();
    vi.stubGlobal('fetch', vi.fn(() => pendingFetch.promise));

    const oldSend = useChatStore.getState().sendMessage('old generation');
    await Promise.resolve();
    const oldTurn = useChatStore.getState().turnsBySession[SESSION_A];
    expect(oldTurn?.generationId).not.toBeNull();

    const replacementGeneration = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
    useChatStore.setState((state) => ({
      turnsBySession: {
        ...state.turnsBySession,
        [SESSION_A]: { ...state.turnsBySession[SESSION_A], generationId: replacementGeneration },
      },
    }));
    const replacementController = createStreamAbortController(SESSION_A, replacementGeneration);

    await vi.advanceTimersByTimeAsync(30_001);

    expect(replacementController.signal.aborted).toBe(false);
    expect(getActiveStreamGenerationId(SESSION_A)).toBe(replacementGeneration);

    pendingFetch.resolve({
      ok: true,
      status: 200,
      body: { getReader: () => ({ read: async () => ({ done: true, value: undefined }) }) },
    });
    await oldSend;
  });
});
