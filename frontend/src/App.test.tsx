// @vitest-environment jsdom

import { render, screen } from '@testing-library/react';
import { MemoryRouter, Outlet } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import App from './App';

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
  default: () => <Outlet />,
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
vi.mock('./pages/admin/AdminUsersPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminCodesPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminAnnouncementsPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminBusinessLinesPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminAuditPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminTemplatesPage', () => ({ default: () => <div /> }));
vi.mock('./pages/admin/AdminQualityPage', () => ({ default: () => <div /> }));

vi.mock('./i18n', () => ({
  default: {
    language: 'en',
    changeLanguage: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}));

describe('App history routing', () => {
  it('renders the existing History page at /history', () => {
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
});
