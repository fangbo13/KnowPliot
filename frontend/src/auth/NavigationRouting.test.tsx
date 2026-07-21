// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { CapabilitySnapshot } from '../api/capabilities';
import {
  NavigationModeBoundary,
  resolvePostAuthDestination,
} from './NavigationRouting';
import { useCapabilities } from './CapabilityProvider';

vi.mock('./CapabilityProvider', () => ({
  useCapabilities: vi.fn(),
}));

const snapshot = (overrides: Partial<CapabilitySnapshot> = {}): CapabilitySnapshot => ({
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
    platform: true,
    organization_ids: [],
    business_line_ids: [],
    space_ids: ['space-1'],
  },
  capabilities: ['chat.ask', 'platform.access', 'platform.users.manage', 'workspace.manage'],
  default_console: '/platform-admin',
  ...overrides,
});

describe('resolvePostAuthDestination', () => {
  it('uses an authorized same-origin next path before the server default', () => {
    expect(resolvePostAuthDestination({
      next: '/platform-admin/users?filter=active#results',
      snapshot: snapshot(),
      origin: 'https://knowpilot.example',
    })).toBe('/platform-admin/users?filter=active#results');
  });

  it.each([
    'https://evil.example/platform-admin',
    '//evil.example/platform-admin',
    'javascript:alert(1)',
    '/login',
  ])('rejects unsafe or looping next target %s and uses the capability default', (next) => {
    expect(resolvePostAuthDestination({
      next,
      snapshot: snapshot(),
      origin: 'https://knowpilot.example',
    })).toBe('/platform-admin');
  });

  it('rejects a stale workspace next path without role-name inference', () => {
    expect(resolvePostAuthDestination({
      next: '/workspace/stale/manage/members',
      snapshot: snapshot({ default_console: '/workspace/space-1/manage' }),
      origin: 'https://knowpilot.example',
    })).toBe('/workspace/space-1/manage');
  });

  it('falls back to chat when both next and default console are unsafe or unauthorized', () => {
    expect(resolvePostAuthDestination({
      next: '/platform-admin/users',
      snapshot: snapshot({
        capabilities: ['chat.ask'],
        default_console: '//evil.example',
      }),
      origin: 'https://knowpilot.example',
    })).toBe('/chat');
  });

  it('accepts legacy routes only for a paired legacy response', () => {
    const legacy = snapshot({
      navigation_mode: 'legacy',
      capabilities: ['platform.access'],
      default_console: '/admin',
    });
    expect(resolvePostAuthDestination({
      next: '/admin/dashboard',
      snapshot: legacy,
      origin: 'https://knowpilot.example',
    })).toBe('/admin/dashboard');
    expect(resolvePostAuthDestination({
      next: '/platform-admin',
      snapshot: legacy,
      origin: 'https://knowpilot.example',
    })).toBe('/admin');
  });
});

describe('NavigationModeBoundary', () => {
  afterEach(cleanup);

  it('renders a bounded safe-chat escape and never mounts children on mismatch', () => {
    vi.mocked(useCapabilities).mockReturnValue({
      enabled: true,
      status: 'mismatch',
      snapshot: { ...snapshot(), navigation_mode: 'legacy' },
      errorCode: 'navigation_mode_mismatch',
      resolvedUserId: 'user-1',
      resolvedSpaceId: null,
      expectedNavigationMode: 'capability',
      refresh: vi.fn(),
    });

    render(
      <MemoryRouter>
        <NavigationModeBoundary expected="capability">
          <div>Capability console data</div>
        </NavigationModeBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Navigation unavailable' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Continue to chat' }).getAttribute('href')).toBe('/chat');
    expect(screen.queryByText('Capability console data')).toBeNull();
  });
});
