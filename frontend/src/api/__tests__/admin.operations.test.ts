import { beforeEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import { adminApi } from '../admin';


vi.mock('../client', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

describe('admin operations API', () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
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

  it('loads scoped ingestion jobs and safely retries by job id', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { results: [] } });
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 'retry-1' } });

    await adminApi.ingestionJobs({ status: 'failed' });
    await adminApi.retryIngestionJob('failed-1');

    expect(apiClient.get).toHaveBeenCalledWith('/admin/ingestion-jobs/', {
      params: { status: 'failed' },
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      '/admin/ingestion-jobs/failed-1/retry/',
      {},
    );
  });

  it('loads document quality drill-down', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: { results: [] } });

    await adminApi.documentQuality({ flag: 'unused' });

    expect(apiClient.get).toHaveBeenCalledWith('/admin/quality/documents/', {
      params: { flag: 'unused' },
    });
  });
});
