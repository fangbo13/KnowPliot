// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { MemoryRouter, Outlet } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';

const { accessState, adminLayoutSpy } = vi.hoisted(() => ({
  accessState: {
    allowed: new Set<string>(),
    status: 'ready' as 'loading' | 'ready' | 'denied' | 'error',
    defaultConsole: '/governance',
  },
  adminLayoutSpy: vi.fn(),
}));

vi.mock('./auth/AuthProvider', () => ({
  useAuth: () => ({ isAuthenticated: true }),
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
    snapshot: null,
    errorCode: null,
    resolvedUserId: 'user-1',
    resolvedSpaceId: 'space-1',
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
vi.mock('./pages/admin/AdminDashboardPage', () => ({ default: () => <div /> }));
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
    adminLayoutSpy.mockReset();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders the existing History page at /history', () => {
    accessState.allowed = new Set(['chat.history']);
    render(
      <MemoryRouter
        initialEntries={['/history']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText('History route content')).toBeTruthy();
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

  it('keeps the old admin layout while the capability flag is disabled', () => {
    render(
      <MemoryRouter
        initialEntries={['/admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled={false} />
      </MemoryRouter>,
    );

    expect(screen.getByText('Platform users')).toBeTruthy();
    expect(adminLayoutSpy).toHaveBeenCalled();
  });

  it('keeps legacy workspace management available to authenticated users while disabled', () => {
    render(
      <MemoryRouter
        initialEntries={['/spaces/manage']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled={false} />
      </MemoryRouter>,
    );

    expect(screen.getByText('Spaces')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Access denied' })).toBeNull();
  });

  it('keeps new console URLs behind the disabled rollout flag', () => {
    accessState.allowed = new Set(['platform.access', 'platform.users.manage']);
    render(
      <MemoryRouter
        initialEntries={['/platform-admin/users']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App capabilityNavigationEnabled={false} />
      </MemoryRouter>,
    );

    expect(adminLayoutSpy).toHaveBeenCalled();
    expect(screen.queryByText('Platform users')).toBeNull();
  });

  it('redirects old admin URLs to default_console without mounting AdminLayout', () => {
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

    expect(screen.getByText('Governance')).toBeTruthy();
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

  it('routes platform users only after both console and page capabilities pass', () => {
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

    expect(screen.getByText('Platform users')).toBeTruthy();
  });
});
