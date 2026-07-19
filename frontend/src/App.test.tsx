// @vitest-environment jsdom

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Outlet } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';

const { accessState, adminLayoutSpy, authState } = vi.hoisted(() => ({
  accessState: {
    allowed: new Set<string>(),
    status: 'ready' as 'loading' | 'ready' | 'denied' | 'error' | 'mismatch',
    defaultConsole: '/governance',
    navigationMode: 'capability' as 'legacy' | 'capability',
  },
  adminLayoutSpy: vi.fn(),
  authState: { isAuthenticated: true },
}));

vi.mock('./auth/AuthProvider', () => ({
  useAuth: () => authState,
}));

vi.mock('./auth/ProtectedRoute', () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('./components/ErrorBoundary', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('./layout/AppLayout', () => ({
  default: () => <Outlet />,
}));

vi.mock('./layout/AdminLayout', () => ({
  default: () => {
    adminLayoutSpy();
    return <Outlet />;
  },
}));

vi.mock('./layout/ScopedConsoleLayout', () => ({
  default: () => <Outlet />,
}));

vi.mock('./auth/CapabilityProvider', () => ({
  useAuthorization: () => ({
    enabled: true,
    status: accessState.status,
    snapshot: {
      navigation_mode: accessState.navigationMode,
      configuration_revision: 'config-v3',
      feature_availability: {
        deep: true,
        thinking: false,
        workspace_creation_approval: true,
        workspace_join_v2: true,
        workspace_permanent_delete: false,
      },
      scopes: { platform: false, organization_ids: [], business_line_ids: [], space_ids: ['space-1'] },
      capabilities: [...accessState.allowed],
      default_console: accessState.defaultConsole,
    },
    has: (capability: string) => accessState.allowed.has(capability),
    hasAny: (capabilities: string[]) => capabilities.some((capability) => accessState.allowed.has(capability)),
    hasAll: (capabilities: string[]) => capabilities.every((capability) => accessState.allowed.has(capability)),
    defaultConsole: accessState.defaultConsole,
  }),
  useCapabilities: () => ({
    enabled: true,
    status: accessState.status,
    snapshot: {
      navigation_mode: accessState.navigationMode,
      configuration_revision: 'config-v3',
      feature_availability: {
        deep: true,
        thinking: false,
        workspace_creation_approval: true,
        workspace_join_v2: true,
        workspace_permanent_delete: false,
      },
      scopes: { platform: false, organization_ids: [], business_line_ids: [], space_ids: ['space-1'] },
      capabilities: [...accessState.allowed],
      default_console: accessState.defaultConsole,
    },
    errorCode: accessState.status === 'mismatch' ? 'navigation_mode_mismatch' : null,
    resolvedUserId: 'user-1',
    resolvedSpaceId: 'space-1',
    expectedNavigationMode: 'capability',
    refresh: vi.fn(),
  }),
}));

vi.mock('./pages/HistoryPage', () => ({
  default: () => <div>History route content</div>,
}));

vi.mock('./pages/ChatPage', () => ({ default: () => <div>Chat</div> }));
vi.mock('./pages/ProfilePage', () => ({ default: () => <div>Profile</div> }));
vi.mock('./pages/SpaceManagementPage', () => ({ default: () => <div>Spaces</div> }));
vi.mock('./auth/LoginPage', () => ({ default: () => <div>Login</div> }));
vi.mock('./auth/ResetPasswordPage', () => ({ default: () => <div>Reset</div> }));
vi.mock('./pages/admin/KnowledgeBasePage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminDashboardPage', () => ({ default: () => <div>Admin dashboard</div> }));
vi.mock('./pages/admin/AdminUsersPage', () => ({ default: () => <div>Platform users</div> }));
vi.mock('./pages/admin/AdminCodesPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminAnnouncementsPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminBusinessLinesPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminAuditPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminTemplatesPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminQualityPage', () => ({ default: () => <div /> }));
vi.mock('./pages/console/ScopedUsersPage', () => ({ default: () => <div>Governance users</div> }));
vi.mock('./pages/console/ScopedMetricsPage', () => ({ default: () => <div>Scoped metrics</div> }));
vi.mock('./pages/console/ScopedAuditPage', () => ({ default: () => <div>Scoped audit</div> }));
vi.mock('./pages/console/AccessRequestsPage', () => ({ default: () => <div>Access requests</div> }));
vi.mock('./pages/console/ConsoleOverviewPage', () => ({ default: ({ title }: { title: string }) => <div>{title}</div> }));
vi.mock('./pages/console/ConsolePlaceholderPage', () => ({ default: ({ title }: { title: string }) => <div>{title}</div> }));
vi.mock('./auth/WorkspaceCapabilityBoundary', () => ({
  WorkspaceCapabilityBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('./i18n', () => ({
  default: {
    language: 'en',
    changeLanguage: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}));

describe('App history routing', () => {
  beforeEach(() => {
    accessState.allowed = new Set();
    accessState.status = 'ready';
    accessState.defaultConsole = '/governance';
    accessState.navigationMode = 'capability';
    authState.isAuthenticated = true;
    adminLayoutSpy.mockReset();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders the existing History page at /history', async () => {
    accessState.allowed = new Set(['chat.history']);
    render(
      <MemoryRouter
        initialEntries={['/history']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByText('History route content')).toBeTruthy();
  });

  it('denies direct chat and history routes when their capabilities are missing', () => {
    const { rerender } = render(
      <MemoryRouter
        initialEntries={['/history']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeTruthy();
    expect(screen.queryByText('History route content')).toBeNull();

    rerender(
      <MemoryRouter
        initialEntries={['/chat']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeTruthy();
    expect(screen.queryByText('Chat')).toBeNull();
  });

  it('keeps the old admin layout while the paired legacy mode is selected', async () => {
    accessState.navigationMode = 'legacy';
    render(
      <MemoryRouter
        initialEntries={['/admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled={false} />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Platform users')).toBeTruthy();
    expect(adminLayoutSpy).toHaveBeenCalled();
  });

  it('keeps legacy workspace management available in paired legacy mode', async () => {
    accessState.navigationMode = 'legacy';
    render(
      <MemoryRouter
        initialEntries={['/spaces/manage']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled={false} />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Spaces')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Access denied' })).toBeNull();
  });

  it('keeps new console URLs behind paired legacy navigation', async () => {
    accessState.navigationMode = 'legacy';
    accessState.allowed = new Set(['platform.access', 'platform.users.manage']);
    render(
      <MemoryRouter
        initialEntries={['/platform-admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled={false} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(adminLayoutSpy).toHaveBeenCalled());
    expect(screen.queryByText('Platform users')).toBeNull();
  });

  it('redirects old admin URLs to default_console without mounting AdminLayout', async () => {
    accessState.allowed = new Set(['governance.access']);
    accessState.defaultConsole = '/governance';

    render(
      <MemoryRouter
        initialEntries={['/admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Governance')).toBeTruthy();
    expect(adminLayoutSpy).not.toHaveBeenCalled();
    expect(screen.queryByText('Platform users')).toBeNull();
  });

  it('renders forbidden for direct platform navigation without platform capability', () => {
    render(
      <MemoryRouter
        initialEntries={['/platform-admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Access denied' })).toBeTruthy();
    expect(screen.queryByText('Platform users')).toBeNull();
  });

  it('routes platform users only after both console and page capabilities pass', async () => {
    accessState.allowed = new Set(['platform.access', 'platform.users.manage']);
    accessState.defaultConsole = '/platform-admin';

    render(
      <MemoryRouter
        initialEntries={['/platform-admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Platform users')).toBeTruthy();
  });

  it('uses an authorized same-origin next path for an already-authenticated login route', async () => {
    accessState.allowed = new Set(['platform.access', 'platform.users.manage']);
    accessState.defaultConsole = '/platform-admin';

    render(
      <MemoryRouter
        initialEntries={['/login?next=%2Fplatform-admin%2Fusers']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Platform users')).toBeTruthy();
  });

  it('uses default_console for root entry without consulting role names', async () => {
    accessState.allowed = new Set(['platform.access']);
    accessState.defaultConsole = '/platform-admin';

    render(
      <MemoryRouter
        initialEntries={['/']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Admin dashboard')).toBeTruthy();
  });

  it('shows one bounded mismatch state without mounting either console tree', () => {
    accessState.status = 'mismatch';
    accessState.navigationMode = 'legacy';
    accessState.allowed = new Set(['platform.access', 'platform.users.manage']);

    render(
      <MemoryRouter
        initialEntries={['/platform-admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Navigation unavailable' })).toBeTruthy();
    expect(adminLayoutSpy).not.toHaveBeenCalled();
    expect(screen.queryByText('Platform users')).toBeNull();
  });
});
