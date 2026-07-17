import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { capabilitiesApi } from '../capabilities';

describe('capabilities api', () => {
  afterEach(() => vi.restoreAllMocks());

  it('requests the effective capability contract for the selected space', async () => {
    const signal = new AbortController().signal;
    const payload = {
      scopes: {
        platform: false,
        organization_ids: ['org-1'],
        business_line_ids: [],
        space_ids: ['space-1'],
      },
      capabilities: ['chat.ask', 'workspace.manage'],
      default_console: '/workspace/space-1/manage',
    };
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: payload } as any);

    await expect(capabilitiesApi.me('space-1', signal)).resolves.toEqual(payload);
    expect(get).toHaveBeenCalledWith('/rbac/me/capabilities/', {
      params: { space_id: 'space-1' },
      signal,
    });
  });

  it('omits space_id when no space is selected', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        scopes: { platform: false, organization_ids: [], business_line_ids: [], space_ids: [] },
        capabilities: ['chat.ask'],
        default_console: '/chat',
      },
    } as any);

    await capabilitiesApi.me(null);

    expect(get).toHaveBeenCalledWith('/rbac/me/capabilities/', {
      params: {},
      signal: undefined,
    });
  });
});
