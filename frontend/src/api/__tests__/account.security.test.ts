import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { accountApi } from '../account';

describe('account security api', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses the governed password reset and session endpoints', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} } as any);
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] } as any);
    const del = vi.spyOn(apiClient, 'delete').mockResolvedValue({ data: {} } as any);

    await accountApi.requestPasswordReset('user@example.com');
    await accountApi.sessions();
    await accountApi.revokeSession('session-id');

    expect(post).toHaveBeenCalledWith('/auth/password/reset/request/', {
      email: 'user@example.com',
    });
    expect(get).toHaveBeenCalledWith('/auth/sessions/');
    expect(del).toHaveBeenCalledWith('/auth/sessions/session-id/');
  });

  it('submits MFA challenges without resending the password', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: { access: 'access', refresh: 'refresh', user: { id: '1' } },
    } as any);

    await accountApi.completeMfa('challenge-token', '123456');

    expect(post).toHaveBeenCalledWith('/auth/token/mfa/', {
      challenge: 'challenge-token',
      code: '123456',
    });
  });
});
