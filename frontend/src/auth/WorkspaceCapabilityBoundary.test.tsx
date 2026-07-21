// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { capabilitiesApi, type CapabilitySnapshot } from '../api/capabilities';
import { useSpaceStore } from '../store/spaceStore';
import { CapabilityProvider } from './CapabilityProvider';
import { WorkspaceCapabilityBoundary } from './WorkspaceCapabilityBoundary';

const setActiveSpace = vi.fn(async (spaceId: string) => {
  useSpaceStore.setState({ activeSpaceId: spaceId });
});

vi.mock('./AuthProvider', () => ({
  useAuth: () => ({ user: { id: 'user-1' } }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

const workspace = (spaceId: string): CapabilitySnapshot => ({
  navigation_mode: 'capability',
  configuration_revision: 'config-v3',
  feature_availability: {
    deep: true,
    thinking: false,
    workspace_creation_approval: true,
    workspace_join_v2: true,
    workspace_permanent_delete: false,
  },
  scopes: {
    platform: false,
    organization_ids: [],
    business_line_ids: [],
    space_ids: ['space-a', 'space-b'],
  },
  capabilities: ['workspace.manage'],
  default_console: `/workspace/${spaceId}/manage`,
});

describe('WorkspaceCapabilityBoundary', () => {
  beforeEach(() => {
    useSpaceStore.setState({
      activeSpaceId: 'space-a',
      spaces: [],
      setActiveSpace,
    });
    setActiveSpace.mockClear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('converges a direct workspace B route before mounting content authorized for A', async () => {
    const a = deferred<CapabilitySnapshot>();
    const b = deferred<CapabilitySnapshot>();
    const me = vi.spyOn(capabilitiesApi, 'me').mockImplementation((spaceId) => {
      if (spaceId === 'space-b') return b.promise;
      return a.promise;
    });

    render(
      <MemoryRouter
        initialEntries={['/workspace/space-b/manage']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <CapabilityProvider enabled>
          <Routes>
            <Route
              path="/workspace/:spaceId/manage"
              element={(
                <WorkspaceCapabilityBoundary>
                  <div>Workspace B content</div>
                </WorkspaceCapabilityBoundary>
              )}
            />
          </Routes>
        </CapabilityProvider>
      </MemoryRouter>,
    );

    expect(screen.queryByText('Workspace B content')).toBeNull();
    await waitFor(() => {
      expect(me).toHaveBeenCalledWith('space-b', expect.any(AbortSignal));
    });
    expect(setActiveSpace).not.toHaveBeenCalled();

    await act(async () => a.resolve(workspace('space-a')));
    expect(screen.queryByText('Workspace B content')).toBeNull();

    await act(async () => b.resolve(workspace('space-b')));
    await waitFor(() => expect(screen.getByText('Workspace B content')).toBeTruthy());
    expect(setActiveSpace).toHaveBeenCalledWith('space-b');
    expect(me.mock.calls[me.mock.calls.length - 1]?.[0]).toBe('space-b');
  });

  it('does not switch or persist an inaccessible workspace URL', async () => {
    vi.spyOn(capabilitiesApi, 'me').mockImplementation((spaceId) => {
      if (spaceId === 'revoked-space') {
        return Promise.reject({ response: { status: 404 } });
      }
      return Promise.resolve(workspace('space-a'));
    });

    render(
      <MemoryRouter
        initialEntries={['/workspace/revoked-space/manage']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <CapabilityProvider enabled>
          <Routes>
            <Route
              path="/workspace/:spaceId/manage"
              element={(
                <WorkspaceCapabilityBoundary>
                  <div>Revoked content</div>
                </WorkspaceCapabilityBoundary>
              )}
            />
          </Routes>
        </CapabilityProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Access denied' })).toBeTruthy();
    });
    expect(setActiveSpace).not.toHaveBeenCalled();
    expect(useSpaceStore.getState().activeSpaceId).toBe('space-a');
    expect(screen.queryByText('Revoked content')).toBeNull();
  });
});
