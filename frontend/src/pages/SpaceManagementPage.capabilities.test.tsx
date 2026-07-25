// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { spacesApi } from '../api/spaces';
import { useAuthorization } from '../auth/CapabilityProvider';
import { useParams } from 'react-router-dom';
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
  join_policy: 'access_code' as const,
  join_code: null,
  allow_member_invite: false,
  join_code_updated_at: null,
  created_at: '',
  updated_at: '',
};

let mockActiveSpaceId: string | null = 'space-1';
let mockActiveSpace: typeof activeSpace | null = activeSpace;

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../auth/CapabilityProvider', () => ({ useAuthorization: vi.fn() }));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: vi.fn() };
});

vi.mock('../store/spaceStore', () => ({
  useSpaceStore: () => ({
    activeSpaceId: mockActiveSpaceId,
    getActiveSpace: () => mockActiveSpace,
    loadSpaces: vi.fn(),
  }),
}));

vi.mock('../api/spaces', async () => {
  const actual = await vi.importActual('../api/spaces');
  return {
    ...actual,
    spacesApi: {
      members: vi.fn(),
      get: vi.fn(),
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
    mockActiveSpaceId = 'space-1';
    mockActiveSpace = activeSpace;
    vi.mocked(useParams).mockReturnValue({});
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
    vi.mocked(spacesApi.get).mockReset().mockResolvedValue(activeSpace);
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

  it('keeps legacy members readable without exposing mutations while disabled', async () => {
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: false,
      status: 'ready',
      snapshot: null,
      has: () => false,
      hasAny: () => false,
      hasAll: () => false,
      defaultConsole: '/chat',
    });

    render(<SpaceManagementPage />);

    await waitFor(() => expect(spacesApi.members).toHaveBeenCalledWith('space-1'));
    expect(spacesApi.listInvites).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'save' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'add_member' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'generate_code' })).toBeNull();
  });

  it('resolves the route workspace for a direct scoped-console URL', async () => {
    const routeSpace = { ...activeSpace, id: 'route-space', name: 'Route Workspace' };
    mockActiveSpaceId = null;
    mockActiveSpace = null;
    vi.mocked(useParams).mockReturnValue({ spaceId: routeSpace.id });
    vi.mocked(spacesApi.get).mockResolvedValue(routeSpace);
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: null,
      has: (capability) => capability === 'workspace.members.manage',
      hasAny: (capabilities) => capabilities.includes('workspace.members.manage'),
      hasAll: (capabilities) => capabilities.every(
        (capability) => capability === 'workspace.members.manage',
      ),
      defaultConsole: `/workspace/${routeSpace.id}/manage`,
    });

    render(<SpaceManagementPage />);

    await waitFor(() => expect(spacesApi.get).toHaveBeenCalledWith(
      routeSpace.id,
      expect.any(AbortSignal),
    ));
    await waitFor(() => expect(screen.getByRole('heading', {
      name: /Route Workspace/,
    })).toBeTruthy());
    expect(spacesApi.members).toHaveBeenCalledWith(routeSpace.id);
    expect(spacesApi.members).toHaveBeenCalledTimes(1);
    expect(vi.mocked(spacesApi.get).mock.invocationCallOrder[0]).toBeLessThan(
      vi.mocked(spacesApi.members).mock.invocationCallOrder[0],
    );
  });
});
