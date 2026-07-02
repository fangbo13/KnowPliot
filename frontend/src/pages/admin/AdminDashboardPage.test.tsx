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
}));

vi.mock('../../api/admin', () => ({
  adminApi: {
    health: vi.fn(),
    metrics: vi.fn(),
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
      security: { permission_denied: 0 },
    });

    render(<AdminDashboardPage />);

    await waitFor(() => expect(adminApi.health).toHaveBeenCalledTimes(1));
    expect(adminApi.metrics).toHaveBeenCalledTimes(1);
    expect(apiClient.get).not.toHaveBeenCalledWith(
      '/audit/logs/',
      expect.anything(),
    );
  });
});
