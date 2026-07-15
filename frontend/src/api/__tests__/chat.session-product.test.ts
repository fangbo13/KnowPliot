import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { chatApi } from '../chat';


describe('session product closure client', () => {
  afterEach(() => vi.restoreAllMocks());

  it('preserves the session cursor envelope', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        results: [{
          id: 'session-id',
          title: 'Cursor page',
          is_active: true,
          is_pinned: false,
          updated_at: '2026-07-16T00:00:00Z',
        }],
        next: '/chat/sessions/?cursor=next',
        previous: null,
      },
    });

    await expect(chatApi.getSessions()).resolves.toEqual({
      results: [{
        id: 'session-id',
        title: 'Cursor page',
        is_active: true,
        isPinned: false,
        updatedAt: '2026-07-16T00:00:00Z',
      }],
      next: '/chat/sessions/?cursor=next',
      previous: null,
    });
  });

  it('requests a session page by cursor', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });

    await chatApi.getSessions({ cursor: 'session-next' });

    expect(get).toHaveBeenCalledWith('/chat/sessions/', {
      params: { cursor: 'session-next' },
    });
  });

  it('extracts an opaque cursor token from a next-page URL', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });

    await chatApi.getSessions({
      cursor: 'https://api.example.test/chat/sessions/?cursor=encoded%3Dtoken',
    });

    expect(get).toHaveBeenCalledWith('/chat/sessions/', {
      params: { cursor: 'encoded=token' },
    });
  });

  it('normalizes a plain session array as a page with null cursors', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: [{
        id: 'session-id',
        title: 'Compatibility',
        is_active: true,
        is_pinned: false,
        updated_at: '2026-07-16T00:00:00Z',
      }],
    });

    const page = await chatApi.getSessions();

    expect(page.results.map((session) => session.id)).toEqual(['session-id']);
    expect(page.next).toBeNull();
    expect(page.previous).toBeNull();
  });

  it('preserves the message cursor envelope', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        results: [{
          id: 'message-id',
          role: 'assistant',
          content: 'paged answer',
          created_at: '2026-07-16T00:00:00Z',
        }],
        next: '/chat/sessions/session-id/messages/?cursor=older',
        previous: '/chat/sessions/session-id/messages/?cursor=newer',
      },
    });

    await expect(chatApi.getMessages('session-id')).resolves.toEqual({
      results: [{
        id: 'message-id',
        role: 'assistant',
        content: 'paged answer',
        created_at: '2026-07-16T00:00:00Z',
      }],
      next: '/chat/sessions/session-id/messages/?cursor=older',
      previous: '/chat/sessions/session-id/messages/?cursor=newer',
    });
  });

  it('requests a message page with cursor and abort signal', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });
    const controller = new AbortController();

    await chatApi.getMessages('session-id', {
      cursor: 'message-next',
      signal: controller.signal,
    });

    expect(get).toHaveBeenCalledWith('/chat/sessions/session-id/messages/', {
      params: { cursor: 'message-next' },
      signal: controller.signal,
    });
  });

  it('normalizes a plain message array as a page with null cursors', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: [{ id: 'message-id', role: 'user', content: 'Compatibility' }],
    });

    const page = await chatApi.getMessages('session-id');

    expect(page.results.map((message) => message.id)).toEqual(['message-id']);
    expect(page.next).toBeNull();
    expect(page.previous).toBeNull();
  });

  it('maps and updates pinned state', async () => {
    const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      data: {
        id: 'session-id',
        title: 'Pinned',
        is_active: true,
        is_pinned: true,
        updated_at: '2026-07-03T00:00:00Z',
      },
    });

    const session = await chatApi.pinSession('session-id', true);

    expect(patch).toHaveBeenCalledWith('/chat/sessions/session-id/', {
      is_pinned: true,
    });
    expect(session.isPinned).toBe(true);
  });

  it('downloads an authorized export as a blob', async () => {
    const blob = new Blob(['# Conversation'], { type: 'text/markdown' });
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: blob });

    await expect(chatApi.exportSession('session-id', 'markdown')).resolves.toBe(blob);
    expect(get).toHaveBeenCalledWith(
      '/chat/sessions/session-id/export/',
      { params: { format: 'markdown' }, responseType: 'blob' },
    );
  });
});
