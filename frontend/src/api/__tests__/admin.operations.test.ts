import { beforeEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { adminApi } from '../admin';


vi.mock('../client', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('admin operations API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
  });

  it('loads health from the real admin health endpoint', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { overall: 'up', services: {} },
    });

    await adminApi.health();

    expect(apiClient.get).toHaveBeenCalledWith('/admin/health/');
  });

  it('loads scoped metrics from the real admin metrics endpoint', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { users: {}, usage: {}, documents: {}, quality: {}, security: {} },
    });

    await adminApi.metrics();

    expect(apiClient.get).toHaveBeenCalledWith('/admin/metrics/');
  });
});
