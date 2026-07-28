// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, useLocation } from 'react-router-dom';

import type { AuthorizationAdapter } from './authorization';
import { CapabilityGate, LegacyAdminRedirect } from './CapabilityGate';
import { useAuthorization, useCapabilities } from './CapabilityProvider';

vi.mock('./CapabilityProvider', () => ({
  useAuthorization: vi.fn(),
  useCapabilities: vi.fn(),
}));

const makeAccess = (overrides: Partial<AuthorizationAdapter> = {}): AuthorizationAdapter => ({
  enabled: true,
  status: 'ready',
  snapshot: {
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
      space_ids: ['space-1'],
    },
    capabilities: ['workspace.manage'],
    default_console: '/workspace/space-1/manage',
  },
  has: (capability) => capability === 'workspace.manage',
  hasAny: (capabilities) => capabilities.includes('workspace.manage'),
  hasAll: (capabilities) => capabilities.every((capability) => capability === 'workspace.manage'),
  defaultConsole: '/workspace/space-1/manage',
  ...overrides,
});

function LocationProbe() {
  return <span data-testid="location">{useLocation().pathname}</span>;
}

describe('CapabilityGate', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(useCapabilities).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: makeAccess().snapshot,
      errorCode: null,
      resolvedUserId: 'user-1',
      resolvedSpaceId: null,
      expectedNavigationMode: 'capability',
      refresh: vi.fn(),
    });
  });

  it('renders an allowed console route', () => {
    vi.mocked(useAuthorization).mockReturnValue(makeAccess());
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CapabilityGate required="workspace.manage">
          <div>Workspace console</div>
        </CapabilityGate>
      </MemoryRouter>,
    );

    expect(screen.getByText('Workspace console')).toBeTruthy();
  });

  it('renders a visible forbidden state for denied direct navigation', () => {
    vi.mocked(useAuthorization).mockReturnValue(
      makeAccess({ has: () => false, hasAny: () => false, hasAll: () => false }),
    );
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CapabilityGate required="platform.access">
          <div>Platform secrets</div>
        </CapabilityGate>
      </MemoryRouter>,
    );

    // ForbiddenPage renders i18n keys in the test environment (no i18next instance).
    expect(screen.getByRole('heading', { name: 'forbidden_title' })).toBeTruthy();
    expect(screen.queryByText('Platform secrets')).toBeNull();
  });

  it('does not render protected children while capabilities are loading', () => {
    vi.mocked(useAuthorization).mockReturnValue(makeAccess({ status: 'loading' }));
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CapabilityGate required="workspace.manage">
          <div>Workspace console</div>
        </CapabilityGate>
      </MemoryRouter>,
    );

    expect(screen.getByRole('status').textContent).toContain('Checking access');
    expect(screen.queryByText('Workspace console')).toBeNull();
  });
});

describe('LegacyAdminRedirect', () => {
  afterEach(cleanup);

  it('redirects to the server-selected console without rendering an admin page first', () => {
    vi.mocked(useAuthorization).mockReturnValue(makeAccess());
    vi.mocked(useCapabilities).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: makeAccess().snapshot,
      errorCode: null,
      resolvedUserId: 'user-1',
      resolvedSpaceId: null,
      expectedNavigationMode: 'capability',
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter
        initialEntries={['/admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <LegacyAdminRedirect />
        <LocationProbe />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('location').textContent).toBe('/workspace/space-1/manage');
    expect(screen.queryByText('Legacy admin')).toBeNull();
  });
});
