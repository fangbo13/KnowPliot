// @vitest-environment jsdom

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { chatApi } from '../api/chat';
import HistoryPage from './HistoryPage';


const mocks = vi.hoisted(() => ({
  loadSessions: vi.fn(),
  setActiveSession: vi.fn(),
  navigate: vi.fn(),
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
    getMessages: vi.fn(),
  },
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
  default: ({ message }: { message: { content: string } }) => (
    <div data-testid="history-message">{message.content}</div>
  ),
}));

describe('HistoryPage', () => {
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
    mocks.loadSessions.mockResolvedValue(undefined);
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

  it('does not render implementation comments in the history list', async () => {
    render(<HistoryPage />);

    await screen.findByText('Review session');
    expect(screen.queryByText(/V3\.6 HIGH-001/)).toBeNull();
    expect(screen.queryByText(/Same grouping logic/)).toBeNull();
  });
});
