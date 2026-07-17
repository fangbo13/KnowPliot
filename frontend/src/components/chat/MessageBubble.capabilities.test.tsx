// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
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

  it('links only server-issued citation source paths', () => {
    render(<MessageBubbleRaw message={{
      ...message,
      citations: [
        {
          source_id: 'source-1',
          source_url: '/api/v1/chat/citations/source-1/source/',
          document_id: 'document-1',
          document_title: 'Safe source',
          score: 0.9,
          snippet: 'Governed excerpt',
          quoted_text: 'Governed excerpt',
        },
        {
          source_id: 'source-2',
          source_url: 'https://untrusted.example/source',
          document_id: 'document-2',
          document_title: 'Untrusted source',
          score: 0.8,
          quoted_text: '',
        },
      ],
    }} />);

    fireEvent.click(screen.getByText('sources_count').closest('button')!);

    expect(screen.getByRole('link', { name: 'Safe source' }).getAttribute('href'))
      .toBe('/api/v1/chat/citations/source-1/source/');
    expect(screen.queryByRole('link', { name: 'Untrusted source' })).toBeNull();
    expect(screen.getByText('Governed excerpt')).toBeTruthy();
  });
});
