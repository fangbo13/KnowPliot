import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  abortActiveStream: vi.fn(),
  getActiveStreamSessionId: vi.fn(),
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
  abortActiveStream: mocks.abortActiveStream,
  getActiveStreamSessionId: mocks.getActiveStreamSessionId,
}));

vi.mock('../stream/TokenBatchRenderer', () => ({
  resetTokenBatcher: mocks.resetTokenBatcher,
}));

vi.mock('../store/chatStore', () => ({
  useChatStore: Object.assign(vi.fn(), {
    getState: () => ({
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
    mocks.getActiveStreamSessionId.mockReturnValue('session-a');
    initCrossTabSync();
  });

  it('does not abort or reset this tab stream when another tab switches sessions', async () => {
    await receive({ type: 'session-switch', sessionId: 'session-b' });

    expect(mocks.abortActiveStream).not.toHaveBeenCalled();
    expect(mocks.resetTokenBatcher).not.toHaveBeenCalled();
    expect(mocks.setStreamPhase).not.toHaveBeenCalled();
    expect(mocks.unlockSend).not.toHaveBeenCalled();
  });

  it('still safely resets and refreshes when another tab deletes the owning session', async () => {
    await receive({ type: 'session-delete', sessionId: 'session-a' });

    expect(mocks.abortActiveStream).toHaveBeenCalledOnce();
    expect(mocks.resetTokenBatcher).toHaveBeenCalledOnce();
    expect(mocks.resetSession).toHaveBeenCalledOnce();
    expect(mocks.loadSessions).toHaveBeenCalledOnce();
  });
});
