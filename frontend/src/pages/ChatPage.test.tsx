// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ChatPage from './ChatPage';

const mocks = vi.hoisted(() => ({
  chatState: {} as Record<string, unknown>,
  cleanupTokenBatcher: vi.fn(),
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-router-dom', () => ({
  useLocation: () => ({ pathname: '/chat' }),
}));

vi.mock('antd', () => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock('@ant-design/icons', () => ({
  CheckOutlined: () => null,
  CloseOutlined: () => null,
  ArrowDownOutlined: () => null,
  EditOutlined: () => null,
  ReloadOutlined: () => null,
  WarningOutlined: () => null,
}));

vi.mock('../store/chatStore', () => ({
  useChatStore: (selector?: (state: Record<string, unknown>) => unknown) =>
    selector ? selector(mocks.chatState) : mocks.chatState,
}));

vi.mock('../store/spaceStore', () => ({
  useSpaceStore: (selector: (state: { getActiveSpace: () => null }) => unknown) =>
    selector({ getActiveSpace: () => null }),
}));

vi.mock('../stream/TokenBatchRenderer', () => ({
  cleanupTokenBatcher: mocks.cleanupTokenBatcher,
}));

vi.mock('../components/chat/WelcomeScreen', () => ({
  default: () => <div data-testid="welcome" />,
}));

vi.mock('../components/chat/VirtualizedMessageList', () => ({
  default: ({ isStreaming, streamContent }: { isStreaming: boolean; streamContent: string }) => (
    <div data-testid="message-list" data-streaming={String(isStreaming)}>{streamContent}</div>
  ),
}));

vi.mock('../components/chat/ChatComposer', () => ({
  default: ({ isStreaming, disabled }: { isStreaming: boolean; disabled: boolean }) => (
    <div data-testid="composer" data-streaming={String(isStreaming)} data-disabled={String(disabled)} />
  ),
}));

describe('ChatPage stream ownership gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window.navigator, 'onLine', { configurable: true, value: true });
    mocks.chatState = {
      sessions: [{ id: 'session-b', title: 'Session B' }],
      messages: [{ id: 'message-b', role: 'user', content: 'B question', createdAt: '2026-07-16T00:00:00Z' }],
      streamContent: 'private partial from A',
      citations: [],
      activeSessionId: 'session-b',
      streamingSessionId: 'session-a',
      isLoadingMessages: false,
      sendError: null,
      hasOlderMessages: false,
      setSendError: vi.fn(),
      sendMessage: vi.fn(),
      loadSessions: vi.fn(),
      loadMessages: vi.fn().mockResolvedValue(undefined),
      loadOlderRounds: vi.fn(),
      aiStatusText: 'Generating',
      streamPhase: 'streaming',
      isSendLocked: true,
    };
  });

  it('does not expose or lock session A stream while session B is active', () => {
    render(<ChatPage />);

    expect(screen.getByTestId('message-list').getAttribute('data-streaming')).toBe('false');
    expect(screen.getByTestId('message-list').textContent).not.toContain('private partial from A');
    expect(screen.getByTestId('composer').getAttribute('data-streaming')).toBe('false');
    expect(screen.getByTestId('composer').getAttribute('data-disabled')).toBe('false');
    expect(screen.queryByText(/private partial from A/)).toBeNull();
  });

  it('does not tear down the store-owned token batcher on unmount', () => {
    const { unmount } = render(<ChatPage />);

    unmount();

    expect(mocks.cleanupTokenBatcher).not.toHaveBeenCalled();
  });

  it('does not show a background stream status on the new-chat welcome view', () => {
    mocks.chatState.activeSessionId = null;
    mocks.chatState.sessions = [];
    mocks.chatState.messages = [];

    render(<ChatPage />);

    expect(screen.queryByText('Generating')).toBeNull();
  });
});
