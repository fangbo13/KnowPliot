// @vitest-environment jsdom

import { render, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { adminApi } from '../../api/admin';
import apiClient from '../../api/client';
import AdminDashboardPage from './AdminDashboardPage';


vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(),
  },
  getRateLimitDetails: () => null,
  isAbortError: () => false,
  withRequestSignal: (_signal: AbortSignal, callback: () => unknown) => callback(),
}));

vi.mock('../../api/admin', () => ({
  adminApi: {
    health: vi.fn(),
    metrics: vi.fn(),
    ingestionJobs: vi.fn(),
    retryIngestionJob: vi.fn(),
    documentQuality: vi.fn(),
  },
}));

describe('AdminDashboardPage', () => {
  beforeAll(() => {
    const getComputedStyle = window.getComputedStyle;
    vi.spyOn(window, 'getComputedStyle').mockImplementation(
      (element) => getComputedStyle(element),
    );
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  });

  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(adminApi.health).mockReset();
    vi.mocked(adminApi.metrics).mockReset();
    vi.mocked(adminApi.ingestionJobs).mockReset();
    vi.mocked(adminApi.retryIngestionJob).mockReset();
    vi.mocked(adminApi.documentQuality).mockReset();
  });

  it('loads real health and scoped metrics instead of inferring from audit logs', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      data: [
        {
          id: 'user-1',
          email: 'admin@example.com',
          username: 'admin',
          is_hr_admin: false,
          roles: ['admin'],
          is_active: true,
          service_line: null,
          office_location: null,
          role_level: null,
        },
      ],
    });
    vi.mocked(adminApi.health).mockResolvedValue({
      overall: 'up',
      services: {
        backend: { status: 'up' },
        database: { status: 'up' },
        redis: { status: 'up' },
        celery: { status: 'up' },
        vector_db: { status: 'not_configured' },
        llm: { status: 'configured' },
      },
    });
    vi.mocked(adminApi.metrics).mockResolvedValue({
      users: { total: 1, active: 1 },
      usage: { sessions: 0, questions: 0, citations: 0 },
      documents: { total: 0, processing: 0, failed: 0, stale: 0, expiring: 0 },
      quality: {
        average_response_time_ms: null,
        no_evidence_rate: 0,
        citation_coverage_rate: 0,
      },
      model_api: {
        calls: 2,
        failures: 1,
        error_rate: 0.5,
        total_tokens: 120,
        average_tokens: 120,
        by_model: [{ model: 'qwen-plus', calls: 2 }],
      },
      knowledge_quality: {
        unused_documents: 1,
        high_usage_documents: 1,
        stale_cited_documents: 0,
      },
      security: { permission_denied: 0 },
    });
    vi.mocked(adminApi.ingestionJobs).mockResolvedValue([
      {
        id: 'failed-job',
        document: 'doc-1',
        document_title: 'Policy',
        space: 'space-1',
        space_name: 'Advisory',
        requested_by_email: 'admin@example.com',
        trigger: 'upload',
        status: 'failed',
        celery_task_id: 'task-1',
        attempt: 4,
        max_attempts: 4,
        last_error: 'RuntimeError',
        retry_of: null,
        started_at: null,
        completed_at: null,
        created_at: '2026-07-02T08:00:00Z',
      },
    ]);
    vi.mocked(adminApi.documentQuality).mockResolvedValue([
      {
        id: 'doc-1',
        title: 'Policy',
        space: 'space-1',
        status: 'active',
        effective_to: null,
        chunk_count: 2,
        citation_count: 0,
        average_relevance: null,
        last_cited_at: null,
        flags: { unused: true, high_usage: false, stale_source: false },
      },
    ]);

    render(<AdminDashboardPage />);

    await waitFor(() => expect(adminApi.health).toHaveBeenCalledTimes(1));
    expect(adminApi.metrics).toHaveBeenCalledTimes(1);
    expect(adminApi.ingestionJobs).toHaveBeenCalledTimes(1);
    expect(adminApi.documentQuality).toHaveBeenCalledTimes(1);
    expect(apiClient.get).not.toHaveBeenCalledWith(
      '/audit/logs/',
      expect.anything(),
    );
  });
});
