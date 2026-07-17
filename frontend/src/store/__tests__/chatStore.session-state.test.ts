import { describe, expect, it, vi } from 'vitest';

vi.mock('../../sync/crossTabSync', () => ({
  broadcastSessionSwitch: vi.fn(),
}));

import { useChatStore } from '../chatStore';

const turn = {
  phase: 'error' as const,
  isLocked: false,
  content: '',
  citations: [],
  quality: null,
  error: 'error_network',
  aiStatusText: null,
  generationId: 'generation-b',
};

describe('session-owned state cleanup', () => {
  it('removes only the deleted session turn, cache, and local partials', () => {
    const messageA = {
      id: 'message-a', role: 'user' as const, content: 'A', createdAt: '2026-07-16T00:00:00Z',
    };
    const messageB = {
      id: 'local-b', role: 'assistant' as const, content: 'B partial', createdAt: '2026-07-16T00:01:00Z',
    };
    useChatStore.setState({
      activeSessionId: 'session-a',
      messages: [messageA],
      allMessages: [messageA],
      turnsBySession: { 'session-a': { ...turn, error: null, generationId: 'generation-a' }, 'session-b': turn },
      messageCacheBySession: { 'session-a': [messageA], 'session-b': [messageB] },
      localPartialsBySession: { 'session-b': [messageB] },
    });

    const removeSessionState = useChatStore.getState().removeSessionState;
    expect(removeSessionState).toBeTypeOf('function');
    removeSessionState('session-b');

    const state = useChatStore.getState();
    expect(state.turnsBySession['session-b']).toBeUndefined();
    expect(state.messageCacheBySession['session-b']).toBeUndefined();
    expect(state.localPartialsBySession['session-b']).toBeUndefined();
    expect(state.activeSessionId).toBe('session-a');
    expect(state.messages).toEqual([messageA]);
  });
});
