import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/chat', () => ({
  chatApi: {
    getSessions: vi.fn(),
    getMessages: vi.fn(),
  },
}));

vi.mock('../../sync/crossTabSync', () => ({
  broadcastSessionSwitch: vi.fn(),
  broadcastSessionDelete: vi.fn(),
  initCrossTabSync: vi.fn(),
}));

import { chatApi } from '../../api/chat';
import { useChatStore } from '../chatStore';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

type MessagePage = Awaited<ReturnType<typeof chatApi.getMessages>>;

function messagePage(results: MessagePage['results'], next: string | null = null): MessagePage {
  return { results, next, previous: null };
}

beforeEach(() => {
  vi.clearAllMocks();
  useChatStore.setState({
    sessions: [],
    sessionNextCursor: null,
    activeSessionId: null,
    messages: [],
    allMessages: [],
    messageNextCursor: null,
    isLoadingMessages: false,
    sendError: null,
    visibleRoundCount: 10,
    hasOlderMessages: false,
    totalRoundCount: 0,
  });
});

describe('session pagination', () => {
  it('stores the first page results and next cursor', async () => {
    vi.mocked(chatApi.getSessions).mockResolvedValue({
      results: [{
        id: 'session-a',
        title: 'First page',
        is_active: true,
        isPinned: false,
        updatedAt: '2026-07-16T02:00:00Z',
      }],
      next: 'session-next',
      previous: null,
    });

    await useChatStore.getState().loadSessions();

    expect(useChatStore.getState().sessions.map((session) => session.id)).toEqual(['session-a']);
    expect(useChatStore.getState().sessionNextCursor).toBe('session-next');
  });

  it('appends the next page without replacing or duplicating sessions', async () => {
    const existing = {
      id: 'session-a',
      title: 'Existing',
      is_active: true,
      isPinned: false,
      updatedAt: '2026-07-16T02:00:00Z',
    };
    useChatStore.setState({
      sessions: [existing],
      sessionNextCursor: 'session-next',
    });
    vi.mocked(chatApi.getSessions).mockResolvedValue({
      results: [
        { ...existing, title: 'Must not replace existing' },
        {
          id: 'session-b',
          title: 'Older page',
          is_active: true,
          isPinned: false,
          updatedAt: '2026-07-15T02:00:00Z',
        },
      ],
      next: 'session-final',
      previous: null,
    });

    await useChatStore.getState().loadMoreSessions();

    expect(chatApi.getSessions).toHaveBeenCalledWith({ cursor: 'session-next' });
    expect(useChatStore.getState().sessions).toEqual([
      existing,
      expect.objectContaining({ id: 'session-b' }),
    ]);
    expect(useChatStore.getState().sessionNextCursor).toBe('session-final');
  });
});

describe('message loading', () => {
  it('stores the first message page and next cursor', async () => {
    vi.mocked(chatApi.getMessages).mockResolvedValue({
      results: [{
        id: 'message-a',
        role: 'assistant',
        content: 'first page',
        created_at: '2026-07-16T02:00:00Z',
      }],
      next: 'message-next',
      previous: null,
    });

    useChatStore.getState().setActiveSession('session-a');
    await useChatStore.getState().loadMessages('session-a');

    expect(useChatStore.getState().allMessages.map((message) => message.id)).toEqual(['message-a']);
    expect(useChatStore.getState().messageNextCursor).toBe('message-next');
    expect(useChatStore.getState().hasOlderMessages).toBe(true);
  });

  it('appends an older server page without replacing duplicates and sorts chronologically', async () => {
    const existing = {
      id: 'message-existing',
      role: 'assistant' as const,
      content: 'keep existing content',
      createdAt: '2026-07-16T02:00:00Z',
    };
    useChatStore.setState({
      activeSessionId: 'session-a',
      allMessages: [existing],
      messages: [existing],
      messageNextCursor: 'message-next',
    });
    vi.mocked(chatApi.getMessages).mockResolvedValue(messagePage([
      {
        id: 'message-middle',
        role: 'assistant',
        content: 'middle',
        created_at: '2026-07-16T01:00:00Z',
      },
      {
        id: 'message-existing',
        role: 'assistant',
        content: 'must not replace existing content',
        created_at: '2026-07-16T02:00:00Z',
      },
      {
        id: 'message-oldest',
        role: 'user',
        content: 'oldest',
        created_at: '2026-07-16T00:00:00Z',
      },
    ], 'message-final'));

    await useChatStore.getState().loadOlderMessages();

    expect(useChatStore.getState().allMessages.map((message) => message.id)).toEqual([
      'message-oldest',
      'message-middle',
      'message-existing',
    ]);
    expect(useChatStore.getState().allMessages[2]).toBe(existing);
    expect(useChatStore.getState().messageNextCursor).toBe('message-final');
  });

  it('keeps local round reveal separate from server-page loading', () => {
    const messages = [
      {
        id: 'message-user',
        role: 'user' as const,
        content: 'question',
        createdAt: '2026-07-16T00:00:00Z',
      },
      {
        id: 'message-assistant',
        role: 'assistant' as const,
        content: 'answer',
        createdAt: '2026-07-16T00:01:00Z',
      },
    ];
    useChatStore.setState({
      allMessages: messages,
      messages,
      visibleRoundCount: 1,
      totalRoundCount: 1,
      messageNextCursor: 'server-next',
      hasOlderMessages: true,
    });

    useChatStore.getState().loadOlderRounds(1);

    expect(chatApi.getMessages).not.toHaveBeenCalled();
    expect(useChatStore.getState().hasOlderMessages).toBe(true);
  });

  it('aborts the active message request when selecting another session', async () => {
    const pending = deferred<MessagePage>();
    vi.mocked(chatApi.getMessages).mockReturnValueOnce(pending.promise);

    useChatStore.getState().setActiveSession('session-a');
    const load = useChatStore.getState().loadMessages('session-a');
    useChatStore.getState().setActiveSession('session-b');

    expect(vi.mocked(chatApi.getMessages).mock.calls[0]?.[1]?.signal?.aborted).toBe(true);

    pending.resolve(messagePage([]));
    await load;
  });

  it('does not let an earlier request overwrite a later request', async () => {
    const first = deferred<MessagePage>();
    const second = deferred<MessagePage>();
    vi.mocked(chatApi.getMessages)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    useChatStore.getState().setActiveSession('session-a');
    const firstLoad = useChatStore.getState().loadMessages('session-a');
    useChatStore.getState().setActiveSession('session-b');
    const secondLoad = useChatStore.getState().loadMessages('session-b');

    second.resolve(messagePage([{
      id: 'message-b',
      role: 'assistant',
      content: 'new selection',
      created_at: '2026-07-16T02:00:00Z',
    }]));
    await secondLoad;
    first.resolve(messagePage([{
      id: 'message-a',
      role: 'assistant',
      content: 'stale selection',
      created_at: '2026-07-16T01:00:00Z',
    }]));
    await firstLoad;

    expect(useChatStore.getState().activeSessionId).toBe('session-b');
    expect(useChatStore.getState().allMessages.map((message) => message.id)).toEqual(['message-b']);
  });

  it('ignores a success for a session that is no longer selected', async () => {
    const pending = deferred<MessagePage>();
    vi.mocked(chatApi.getMessages).mockReturnValueOnce(pending.promise);

    useChatStore.getState().setActiveSession('session-a');
    const load = useChatStore.getState().loadMessages('session-a');
    useChatStore.getState().setActiveSession('session-b');
    const afterSwitch = useChatStore.getState();

    pending.resolve(messagePage([{
      id: 'message-a',
      role: 'assistant',
      content: 'stale selection',
      created_at: '2026-07-16T01:00:00Z',
    }]));
    await load;

    expect(useChatStore.getState()).toBe(afterSwitch);
  });

  it('ignores a failure for a session that is no longer selected', async () => {
    const pending = deferred<MessagePage>();
    vi.mocked(chatApi.getMessages).mockReturnValueOnce(pending.promise);

    useChatStore.getState().setActiveSession('session-a');
    const load = useChatStore.getState().loadMessages('session-a');
    useChatStore.getState().setActiveSession('session-b');
    const afterSwitch = useChatStore.getState();

    pending.reject(new Error('stale failure'));
    await load;

    expect(useChatStore.getState()).toBe(afterSwitch);
  });
});
