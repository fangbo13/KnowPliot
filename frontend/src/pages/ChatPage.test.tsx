// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ChatPage from './ChatPage';

const mocks = vi.hoisted(() => ({
  chatState: {} as Record<string, unknown>,
  cleanupTokenBatcher: vi.fn(),
  canShare: false,
  canDeep: false,
  composerProps: {} as Record<string, unknown>,
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

vi.mock('../auth/CapabilityProvider', () => ({
  useAuthorization: () => ({
    enabled: true,
    has: (capability: string) => (
      (capability === 'chat.share' && mocks.canShare)
      || (capability === 'chat.deep' && mocks.canDeep)
    ),
  }),
}));

vi.mock('../auth/authorization', () => ({
  DEEP_ANSWER_MODE_ENABLED: true,
}));

vi.mock('../stream/TokenBatchRenderer', () => ({
  cleanupTokenBatcher: mocks.cleanupTokenBatcher,
}));

vi.mock('../components/chat/WelcomeScreen', () => ({
  default: () => <div data-testid="welcome" />,
}));

vi.mock('../components/chat/VirtualizedMessageList', () => ({
  default: ({ isStreaming, streamContent, canShare }: { isStreaming: boolean; streamContent: string; canShare?: boolean }) => (
    <div data-testid="message-list" data-streaming={String(isStreaming)} data-can-share={String(canShare)}>{streamContent}</div>
  ),
}));

vi.mock('../components/chat/ChatComposer', () => ({
  default: (props: { isStreaming: boolean; disabled: boolean }) => {
    mocks.composerProps = props;
    return <div data-testid="composer" data-streaming={String(props.isStreaming)} data-disabled={String(props.disabled)} />;
  },
}));

describe('ChatPage stream ownership gating', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.canShare = false;
    mocks.canDeep = false;
    mocks.composerProps = {};
    Object.defineProperty(window.navigator, 'onLine', { configurable: true, value: true });
    mocks.chatState = {
      sessions: [{ id: 'session-b', title: 'Session B' }],
      messages: [{ id: 'message-b', role: 'user', content: 'B question', createdAt: '2026-07-16T00:00:00Z' }],
      streamContent: 'private partial from A',
      citations: [],
      turnsBySession: {
        'session-a': {
          phase: 'streaming',
          isLocked: true,
          content: 'private partial from A',
          citations: [],
          quality: null,
          error: null,
          aiStatusText: 'Generating',
          generationId: 'generation-a',
        },
      },
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

  it('does not expose or lock session A stream while session B is active', async () => {
    render(<ChatPage />);

    const messageList = await screen.findByTestId('message-list');
    expect(messageList.getAttribute('data-streaming')).toBe('false');
    expect(messageList.textContent).not.toContain('private partial from A');
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

  it('passes the exact chat.share decision to message rendering', async () => {
    const view = render(<ChatPage />);
    expect((await screen.findByTestId('message-list')).getAttribute('data-can-share')).toBe('false');

    mocks.canShare = true;
    view.rerender(<ChatPage />);
    expect(screen.getByTestId('message-list').getAttribute('data-can-share')).toBe('true');
  });

  it('renders only safe application phases, timings, and citation-derived basis', async () => {
    mocks.chatState.turnsBySession = {
      'session-b': {
        phase: 'streaming',
        safePhase: 'generating',
        isLocked: true,
        answerMode: 'deep',
        content: 'answer',
        citations: [{
          document_id: 'doc-1',
          document_title: 'Employee handbook',
          score: 0.9,
          quoted_text: 'permitted citation excerpt',
        }],
        timings: { connectionMs: 120, firstAnswerMs: 800 },
        quality: null,
        error: null,
        aiStatusText: null,
        generationId: 'generation-b',
        rawReasoning: 'private chain of thought',
      },
    };

    render(<ChatPage />);

    expect(await screen.findByRole('button', { name: 'processing_panel_toggle' })).not.toBeNull();
    expect(await screen.findByText('Employee handbook')).not.toBeNull();
    expect(screen.queryByText('private chain of thought')).toBeNull();
    expect(screen.queryByText('permitted citation excerpt')).toBeNull();
  });

  it('submits the explicitly selected governed mode with the current eligibility decision', () => {
    mocks.canDeep = true;
    render(<ChatPage />);

    act(() => (mocks.composerProps.onChange as (value: string) => void)('Question'));
    act(() => (mocks.composerProps.onAnswerModeChange as (mode: string) => void)('deep'));
    act(() => (mocks.composerProps.onSubmit as () => void)());

    expect(mocks.chatState.sendMessage).toHaveBeenCalledWith('Question', {
      answerMode: 'deep',
      canUseDeep: true,
    });
  });

  it('returns to fast with an actionable notice when deep eligibility is revoked', async () => {
    mocks.canDeep = true;
    const view = render(<ChatPage />);
    act(() => (mocks.composerProps.onAnswerModeChange as (mode: string) => void)('deep'));

    mocks.canDeep = false;
    view.rerender(<ChatPage />);

    await waitFor(() => expect(mocks.composerProps.answerMode).toBe('fast'));
    expect(screen.getByRole('alert').textContent).toContain('error_deep_unavailable');
    expect(mocks.chatState.sendMessage).not.toHaveBeenCalled();
  });

  it('reuses a failed deep Turn identity only after the user clicks fast retry', () => {
    mocks.chatState.turnsBySession = {
      'session-b': {
        phase: 'error',
        safePhase: 'generating',
        isLocked: false,
        answerMode: 'deep',
        content: '',
        citations: [],
        timings: {},
        quality: null,
        error: 'error_generic',
        aiStatusText: null,
        generationId: 'generation-b',
        clientRequestId: '10000000-0000-4000-8000-000000000001',
        turnId: '33333333-3333-4333-8333-333333333333',
        recoveryState: 'failed',
      },
    };

    render(<ChatPage />);
    act(() => screen.getByText('error_retry').click());

    expect(mocks.chatState.sendMessage).toHaveBeenCalledOnce();
    expect(mocks.chatState.sendMessage).toHaveBeenCalledWith('B question', {
      answerMode: 'fast',
      retryClientRequestId: '10000000-0000-4000-8000-000000000001',
    });
    expect(mocks.chatState.setSendError).not.toHaveBeenCalled();
  });
});
