import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { scopedConsoleApi } from '../scopedConsole';

describe('scoped console data sources', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses the scope-filtered admin user endpoint instead of global RBAC users', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: { results: [{ id: 'user-1', email: 'member@example.com', is_active: true }] },
    } as any);

    await expect(scopedConsoleApi.users('member')).resolves.toHaveLength(1);
    expect(get).toHaveBeenCalledWith('/admin/users/', { params: { q: 'member' } });
    expect(get).not.toHaveBeenCalledWith('/rbac/users/', expect.anything());
  });

  it('uses server-scoped metrics and a workspace-qualified audit query', async () => {
    const get = vi.spyOn(apiClient, 'get')
      .mockResolvedValueOnce({ data: { users: { total: 2, active: 1 } } } as any)
      .mockResolvedValueOnce({ data: { results: [] } } as any);

    await scopedConsoleApi.metrics();
    await scopedConsoleApi.audit({ space: 'space-1' });

    expect(get).toHaveBeenNthCalledWith(1, '/admin/metrics/');
    expect(get).toHaveBeenNthCalledWith(2, '/audit/logs/', {
      params: { space: 'space-1' },
    });
  });

  it('keeps access requests under the selected workspace resource', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: [] } as any);

    await scopedConsoleApi.accessRequests('space-1');

    expect(get).toHaveBeenCalledWith('/admin/spaces/space-1/access-requests/');
  });
});
