// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '../../store/chatStore';
import { MessageBubbleRaw } from './MessageBubble';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('antd', () => ({
  message: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../api/chat', () => ({ chatApi: {} }));

vi.mock('./markdown', () => ({ MarkdownView: ({ children }: { children: string }) => <>{children}</> }));
vi.mock('./StreamingMarkdown', () => ({ default: ({ content }: { content: string }) => <>{content}</> }));
vi.mock('../ErrorBoundary', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }));

const message: Message = {
  id: 'temporary-message',
  role: 'assistant',
  content: 'Answer',
  createdAt: '2026-07-17T00:00:00Z',
};

describe('MessageBubble share capability', () => {
  afterEach(cleanup);

  it('hides share when chat.share is denied', () => {
    render(<MessageBubbleRaw message={message} canShare={false} />);
    expect(screen.queryByRole('button', { name: 'share_message' })).toBeNull();
  });

  it('shows share when chat.share is allowed', () => {
    render(<MessageBubbleRaw message={message} canShare />);
    expect(screen.getByRole('button', { name: 'share_message' })).toBeTruthy();
  });
});
