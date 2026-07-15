import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  hasActiveStream: vi.fn(),
  abortSessionStream: vi.fn(),
  removeSessionState: vi.fn(),
  resetTokenBatcher: vi.fn(),
  resetSession: vi.fn(),
  loadSessions: vi.fn(),
  setStreamPhase: vi.fn(),
  unlockSend: vi.fn(),
  info: vi.fn(),
}));

class MockBroadcastChannel {
  static instance: MockBroadcastChannel;
  onmessage: ((event: MessageEvent) => void) | null = null;

  constructor(_name: string) {
    MockBroadcastChannel.instance = this;
  }

  postMessage() {}
}

vi.stubGlobal('BroadcastChannel', MockBroadcastChannel);

vi.mock('../stream/StreamLifecycleManager', () => ({
  hasActiveStream: mocks.hasActiveStream,
}));

vi.mock('../stream/TokenBatchRenderer', () => ({
  resetTokenBatcher: mocks.resetTokenBatcher,
}));

vi.mock('../store/chatStore', () => ({
  useChatStore: Object.assign(vi.fn(), {
    getState: () => ({
      activeSessionId: 'session-a',
      turnsBySession: { 'session-a': { isLocked: true } },
      abortSessionStream: mocks.abortSessionStream,
      removeSessionState: mocks.removeSessionState,
      resetSession: mocks.resetSession,
      loadSessions: mocks.loadSessions,
      setStreamPhase: mocks.setStreamPhase,
      unlockSend: mocks.unlockSend,
    }),
    setState: vi.fn(),
  }),
}));

vi.mock('antd', () => ({
  message: { info: mocks.info },
}));

const { initCrossTabSync } = await import('./crossTabSync');

async function receive(data: { type: string; sessionId: string }) {
  MockBroadcastChannel.instance.onmessage?.({ data } as MessageEvent);
  await vi.waitFor(() => expect(mocks.info).toHaveBeenCalled());
}

describe('cross-tab stream isolation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.hasActiveStream.mockImplementation((sessionId: string) => sessionId === 'session-a');
    initCrossTabSync();
  });

  it('does not abort or reset this tab stream when another tab switches sessions', async () => {
    await receive({ type: 'session-switch', sessionId: 'session-b' });

    expect(mocks.abortSessionStream).not.toHaveBeenCalled();
    expect(mocks.resetTokenBatcher).not.toHaveBeenCalled();
    expect(mocks.setStreamPhase).not.toHaveBeenCalled();
    expect(mocks.unlockSend).not.toHaveBeenCalled();
  });

  it('still safely resets and refreshes when another tab deletes the owning session', async () => {
    await receive({ type: 'session-delete', sessionId: 'session-a' });

    expect(mocks.removeSessionState).toHaveBeenCalledWith('session-a');
    expect(mocks.loadSessions).toHaveBeenCalledOnce();
  });

  it('does not abort the owning stream when another session is deleted', async () => {
    MockBroadcastChannel.instance.onmessage?.({
      data: { type: 'session-delete', sessionId: 'session-b' },
    } as MessageEvent);
    await vi.waitFor(() => expect(mocks.loadSessions).toHaveBeenCalledOnce());

    expect(mocks.abortSessionStream).not.toHaveBeenCalled();
    expect(mocks.resetTokenBatcher).not.toHaveBeenCalled();
    expect(mocks.resetSession).not.toHaveBeenCalled();
    expect(mocks.removeSessionState).toHaveBeenCalledWith('session-b');
  });
});
