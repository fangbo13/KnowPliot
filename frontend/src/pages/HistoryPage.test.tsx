// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { chatApi } from '../api/chat';
import HistoryPage from './HistoryPage';


const mocks = vi.hoisted(() => ({
  loadSessions: vi.fn(),
  setActiveSession: vi.fn(),
  navigate: vi.fn(),
  canShare: false,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock('../i18n', () => ({
  default: { language: 'en' },
}));

vi.mock('../api/chat', () => ({
  chatApi: {
    getSessions: vi.fn(),
    getMessages: vi.fn(),
  },
}));

vi.mock('../auth/CapabilityProvider', () => ({
  useAuthorization: () => ({ has: (capability: string) => capability === 'chat.share' && mocks.canShare }),
}));

vi.mock('../store/chatStore', () => ({
  useChatStore: () => ({
    sessions: [{
      id: 'session-id',
      title: 'Review session',
      is_active: true,
      isPinned: false,
      updatedAt: '2026-07-16T02:00:00Z',
    }],
    loadSessions: mocks.loadSessions,
    setActiveSession: mocks.setActiveSession,
  }),
}));

vi.mock('../components/chat/MessageBubble', () => ({
  default: ({ message, canShare }: { message: { content: string }; canShare?: boolean }) => (
    <div data-testid="history-message" data-can-share={String(canShare)}>{message.content}</div>
  ),
}));

describe('HistoryPage', () => {
  afterEach(cleanup);

  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
    Element.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, '', '/history');
    mocks.canShare = false;
    mocks.loadSessions.mockResolvedValue(undefined);
    vi.mocked(chatApi.getSessions).mockResolvedValue({
      results: [{
        id: 'session-id',
        title: 'Review session',
        is_active: true,
        isPinned: false,
        recoveryState: 'terminal',
        updatedAt: '2026-07-16T02:00:00Z',
      }],
      next: null,
      previous: null,
    });
    vi.mocked(chatApi.getMessages).mockResolvedValue({
      results: [
        {
          id: 'message-newer',
          role: 'assistant',
          content: 'newer',
          created_at: '2026-07-16T02:00:00Z',
        },
        {
          id: 'message-older',
          role: 'user',
          content: 'older',
          created_at: '2026-07-16T01:00:00Z',
        },
      ],
      next: null,
      previous: null,
    });
  });

  it('renders newest-first API messages in chronological order', async () => {
    render(<HistoryPage />);
    fireEvent.click(await screen.findByText('Review session'));

    const messages = await screen.findAllByTestId('history-message');

    expect(messages.map((message) => message.textContent)).toEqual(['older', 'newer']);
  });

  it('loads older message cursor pages without replacing visible content', async () => {
    vi.mocked(chatApi.getMessages)
      .mockResolvedValueOnce({
        results: [{
          id: 'message-newest',
          role: 'assistant',
          content: 'newest page',
          created_at: '2026-07-16T02:00:00Z',
        }],
        next: 'older-cursor',
        previous: null,
      })
      .mockResolvedValueOnce({
        results: [{
          id: 'message-earliest',
          role: 'user',
          content: 'earliest page',
          created_at: '2026-07-15T02:00:00Z',
        }],
        next: null,
        previous: 'newer-cursor',
      });

    render(<HistoryPage />);
    fireEvent.click(await screen.findByText('Review session'));
    fireEvent.click(await screen.findByRole('button', { name: 'load_older_messages' }));

    await waitFor(() => expect(
      screen.getAllByTestId('history-message').map((message) => message.textContent),
    ).toEqual(['earliest page', 'newest page']));
    expect(chatApi.getMessages).toHaveBeenLastCalledWith('session-id', {
      cursor: 'older-cursor',
      signal: expect.any(AbortSignal),
    });
  });

  it('does not render implementation comments in the history list', async () => {
    render(<HistoryPage />);

    await screen.findByText('Review session');
    expect(screen.queryByText(/V3\.6 HIGH-001/)).toBeNull();
    expect(screen.queryByText(/Same grouping logic/)).toBeNull();
  });

  it('passes the exact chat.share decision to history messages', async () => {
    const view = render(<HistoryPage />);
    fireEvent.click(await screen.findByText('Review session'));
    const deniedMessages = await screen.findAllByTestId('history-message');
    expect(deniedMessages.every((message) => message.getAttribute('data-can-share') === 'false')).toBe(true);

    view.unmount();
    mocks.canShare = true;
    render(<HistoryPage />);
    fireEvent.click(await screen.findByText('Review session'));
    const allowedMessages = await screen.findAllByTestId('history-message');
    expect(allowedMessages.every((message) => message.getAttribute('data-can-share') === 'true')).toBe(true);
  });

  it('restores filters from the URL and asks the server for only that cursor page', async () => {
    window.history.replaceState({}, '', '/history?q=alpha&time=today&status=recovering&cursor=opaque-next');

    render(<HistoryPage />);

    await waitFor(() => expect(chatApi.getSessions).toHaveBeenCalledWith(expect.objectContaining({
      query: 'alpha',
      time: 'today',
      status: 'recovering',
      cursor: 'opaque-next',
      signal: expect.any(AbortSignal),
    })));
    expect(mocks.loadSessions).not.toHaveBeenCalled();
  });

  it('renders an explicit retry state when the history page request fails', async () => {
    vi.mocked(chatApi.getSessions).mockRejectedValueOnce(new Error('offline'));

    render(<HistoryPage />);

    expect(await screen.findByText('load_error')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'error_retry' })).toBeTruthy();
  });
});
