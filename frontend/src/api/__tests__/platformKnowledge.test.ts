import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { platformKnowledgeApi } from '../platformKnowledge';

describe('platform Knowledge metadata API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('uses only allowlisted metadata filters and preserves the cursor', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { results: [], next_cursor: 'next-1' } });

    const page = await platformKnowledgeApi.list({
      q: 'policy',
      space_id: 'space-1',
      status: 'active',
      cursor: 'cursor-1',
    });

    expect(page.next_cursor).toBe('next-1');
    expect(get).toHaveBeenCalledWith('/admin/documents/', {
      params: { q: 'policy', space_id: 'space-1', status: 'active', cursor: 'cursor-1' },
    });
  });
});
