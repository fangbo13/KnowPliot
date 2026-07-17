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

  it('sends history search, time, recovery status, cursor, and abort signal to the server', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });
    const controller = new AbortController();

    await chatApi.getSessions({
      query: 'alpha',
      time: 'today',
      status: 'recovering',
      cursor: 'history-next',
      signal: controller.signal,
    });

    expect(get).toHaveBeenCalledWith('/chat/sessions/', {
      params: {
        q: 'alpha',
        time: 'today',
        status: 'recovering',
        cursor: 'history-next',
      },
      signal: controller.signal,
    });
  });

  it('maps the durable recovery state returned for a session', async () => {
    vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: [{
        id: 'recovering-session',
        title: 'Recovering',
        is_active: true,
        is_pinned: false,
        recovery_state: 'recovering',
        updated_at: '2026-07-17T00:00:00Z',
      }],
    });

    const page = await chatApi.getSessions();

    expect(page.results[0].recoveryState).toBe('recovering');
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

  it('creates an idempotent conversation branch through a selected message', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: {
        id: 'branch-session',
        title: 'Decision branch',
        is_active: true,
        is_pinned: false,
        updated_at: '2026-07-17T00:00:00Z',
      },
    });

    const branch = await chatApi.branchMessage('assistant-id', {
      clientRequestId: 'branch-request',
      title: 'Decision branch',
    });

    expect(post).toHaveBeenCalledWith('/chat/messages/assistant-id/branch/', {
      client_request_id: 'branch-request',
      title: 'Decision branch',
    });
    expect(branch.id).toBe('branch-session');
  });

  it('creates and revokes a durable conversation share', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { id: 'share-id', token: 'opaque-token', expires_at: '2026-07-24T00:00:00Z' },
    });
    const remove = vi.spyOn(apiClient, 'delete').mockResolvedValue({ data: null });

    const share = await chatApi.createShare('session-id', 'share-request');
    await chatApi.revokeShare(share.id);

    expect(post).toHaveBeenCalledWith('/chat/sessions/session-id/shares/', {
      client_request_id: 'share-request',
    });
    expect(remove).toHaveBeenCalledWith('/chat/shares/share-id/');
    expect(share.token).toBe('opaque-token');
  });
});
