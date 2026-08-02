// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../../api/client';
import { scopedConsoleApi } from '../../api/scopedConsole';
import ScopedUsersPage from './ScopedUsersPage';

const originalGetComputedStyle = window.getComputedStyle;

vi.mock('react-i18next', () => {
  // Stable t reference: the page's load() depends on t, so a fresh function
  // per render would re-trigger the fetch effect and break call-count asserts.
  const t = (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key;
  return { useTranslation: () => ({ t }) };
});

vi.mock('../../api/client', () => ({ default: { get: vi.fn() } }));

vi.mock('../../api/scopedConsole', () => ({
  scopedConsoleApi: { users: vi.fn() },
}));

describe('ScopedUsersPage', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element) => (
      originalGetComputedStyle(element)
    ));
  });

  afterAll(() => vi.restoreAllMocks());

  beforeEach(() => {
    vi.mocked(scopedConsoleApi.users).mockReset().mockResolvedValue([
      { id: 'user-1', email: 'member@example.com', is_active: true },
    ]);
    vi.mocked(apiClient.get).mockReset();
  });

  afterEach(cleanup);

  it('loads governance users from the scoped endpoint and never global RBAC', async () => {
    render(<ScopedUsersPage />);

    await waitFor(() => expect(scopedConsoleApi.users).toHaveBeenCalledWith(''));
    expect(apiClient.get).not.toHaveBeenCalled();

    fireEvent.change(screen.getByRole('searchbox', { name: 'scoped_users_search_aria' }), {
      target: { value: 'member' },
    });
    expect(scopedConsoleApi.users).toHaveBeenCalledTimes(1);
  });
});
