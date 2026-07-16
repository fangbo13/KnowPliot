// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { spacesApi } from '../api/spaces';
import { useAuthorization } from '../auth/CapabilityProvider';
import SpaceManagementPage from './SpaceManagementPage';

const activeSpace = {
  id: 'space-1',
  name: 'Workspace One',
  code: 'one',
  description: '',
  icon: '',
  language: 'en',
  visibility: 'private' as const,
  status: 'active' as const,
  organization: 'org-1',
  organization_name: 'Org',
  business_line: null,
  business_line_name: null,
  my_role: 'owner' as const,
  member_count: 1,
  created_at: '',
  updated_at: '',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../auth/CapabilityProvider', () => ({ useAuthorization: vi.fn() }));

vi.mock('../store/spaceStore', () => ({
  useSpaceStore: () => ({
    activeSpaceId: 'space-1',
    getActiveSpace: () => activeSpace,
    loadSpaces: vi.fn(),
  }),
}));

vi.mock('../api/spaces', async () => {
  const actual = await vi.importActual('../api/spaces');
  return {
    ...actual,
    spacesApi: {
      members: vi.fn(),
      listInvites: vi.fn(),
      update: vi.fn(),
      createInvite: vi.fn(),
      revokeInvite: vi.fn(),
      addMember: vi.fn(),
      updateMember: vi.fn(),
      removeMember: vi.fn(),
    },
  };
});

describe('SpaceManagementPage capability actions', () => {
  beforeAll(() => {
    const getComputedStyle = window.getComputedStyle;
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element) => getComputedStyle(element));
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addListener: vi.fn(),
        removeListener: vi.fn(),
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

  beforeEach(() => {
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: null,
      has: (capability) => capability === 'workspace.manage',
      hasAny: (capabilities) => capabilities.includes('workspace.manage'),
      hasAll: (capabilities) => capabilities.every((capability) => capability === 'workspace.manage'),
      defaultConsole: '/workspace/space-1/manage',
    });
    vi.mocked(spacesApi.members).mockReset().mockResolvedValue([]);
    vi.mocked(spacesApi.listInvites).mockReset().mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('does not inherit owner actions when fine-grained capabilities are absent', async () => {
    render(<SpaceManagementPage />);

    await waitFor(() => expect(screen.getByRole('heading', { name: /space_management/ })).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'save' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'add_member' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'generate_code' })).toBeNull();
    expect(spacesApi.members).not.toHaveBeenCalled();
    expect(spacesApi.listInvites).not.toHaveBeenCalled();
  });
});
