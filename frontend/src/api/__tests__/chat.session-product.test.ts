import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { chatApi } from '../chat';


describe('session product closure client', () => {
  afterEach(() => vi.restoreAllMocks());

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
