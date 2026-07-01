// @vitest-environment jsdom

import { render, waitFor } from '@testing-library/react';
import { message } from 'antd';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { adminApi } from '../../api/admin';
import AdminAuditPage from './AdminAuditPage';


vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../../api/admin', () => ({
  adminApi: {
    auditLogs: vi.fn(),
  },
}));

describe('AdminAuditPage', () => {
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
    vi.mocked(adminApi.auditLogs).mockReset();
  });

  it('shows a visible error when audit logs cannot be loaded', async () => {
    vi.mocked(adminApi.auditLogs).mockRejectedValue(new Error('network'));
    const error = vi.spyOn(message, 'error').mockImplementation(() => undefined as never);

    render(<AdminAuditPage />);

    await waitFor(() => expect(error).toHaveBeenCalled());
    error.mockRestore();
  });
});
