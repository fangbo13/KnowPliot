import { afterEach, describe, expect, it, vi } from 'vitest';

import { adminApi } from '../admin';
import apiClient from '../client';
import { scopedConsoleApi } from '../scopedConsole';
import { spacesApi } from '../spaces';

describe('workspace product closure APIs', () => {
  afterEach(() => vi.restoreAllMocks());

  it('discovers spaces and submits an access request with a reason', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { id: 'request-1', status: 'pending' } });

    await spacesApi.discoverable();
    await spacesApi.requestAccess('space-1', { reason: 'Need policy access', role: 'member' });

    expect(get).toHaveBeenCalledWith('/spaces/discoverable/');
    expect(post).toHaveBeenCalledWith('/spaces/space-1/access-requests/', {
      reason: 'Need policy access',
      role: 'member',
    });
  });

  it('uses explicit lifecycle endpoints for restore, clone, and transfers', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });

    await spacesApi.restore('space-1');
    await spacesApi.clone('space-1', { name: 'Clone', code: 'clone', copy_documents: false });
    await spacesApi.transfer('space-1', 'line-2');
    await spacesApi.transferOwner('space-1', 'user-2');

    expect(post.mock.calls.map((call) => call[0])).toEqual([
      '/spaces/space-1/restore/',
      '/spaces/space-1/clone/',
      '/spaces/space-1/transfer/',
      '/spaces/space-1/transfer-owner/',
    ]);
  });

  it('approves access and loads model/governance records through scoped endpoints', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] });
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });

    await scopedConsoleApi.approveAccessRequest('space-1', 'request-1');
    await adminApi.modelProfiles();
    await adminApi.governancePolicies('space-1');

    expect(post).toHaveBeenCalledWith('/admin/spaces/space-1/access-requests/request-1/approve/', {});
    expect(get).toHaveBeenCalledWith('/admin/model-profiles/');
    expect(get).toHaveBeenCalledWith('/admin/governance/policies/', { params: { space: 'space-1' } });
  });
});
