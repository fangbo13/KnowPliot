// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { useAuthorization } from '../auth/CapabilityProvider';
import SpaceSwitcher from './SpaceSwitcher';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({ user: { is_superuser: true, roles: ['admin'] } }),
}));

vi.mock('../auth/CapabilityProvider', () => ({ useAuthorization: vi.fn() }));

vi.mock('../store/spaceStore', () => ({
  useSpaceStore: () => ({
    spaces: [{
      id: 'space-1', name: 'One', status: 'active', my_role: 'member',
    }],
    activeSpaceId: 'space-1',
    setActiveSpace: vi.fn(),
    joinByCode: vi.fn(),
    createSpace: vi.fn(),
  }),
}));

describe('SpaceSwitcher capability actions', () => {
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
  });

  afterEach(cleanup);

  it('hides create-space even for a legacy admin when enabled capabilities deny it', async () => {
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: null,
      has: () => false,
      hasAny: () => false,
      hasAll: () => false,
      defaultConsole: '/chat',
    });

    render(<SpaceSwitcher />);
    fireEvent.click(screen.getByRole('button', { name: 'switch_space' }));

    await waitFor(() => expect(screen.getByText('join_space')).toBeTruthy());
    expect(screen.queryByText('create_space')).toBeNull();
  });
});
