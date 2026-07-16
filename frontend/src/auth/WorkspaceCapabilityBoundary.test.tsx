// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { capabilitiesApi, type CapabilitySnapshot } from '../api/capabilities';
import { useSpaceStore } from '../store/spaceStore';
import { CapabilityProvider } from './CapabilityProvider';
import { WorkspaceCapabilityBoundary } from './WorkspaceCapabilityBoundary';

vi.mock('./AuthProvider', () => ({
  useAuth: () => ({ user: { id: 'user-1' } }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

const workspace = (spaceId: string): CapabilitySnapshot => ({
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
      setActiveSpace: async (spaceId: string) => {
        useSpaceStore.setState({ activeSpaceId: spaceId });
      },
    });
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

    await act(async () => a.resolve(workspace('space-a')));
    expect(screen.queryByText('Workspace B content')).toBeNull();

    await act(async () => b.resolve(workspace('space-b')));
    await waitFor(() => expect(screen.getByText('Workspace B content')).toBeTruthy());
    expect(me.mock.calls[me.mock.calls.length - 1]?.[0]).toBe('space-b');
  });
});
