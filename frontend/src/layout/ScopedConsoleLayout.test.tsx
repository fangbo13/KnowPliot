// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { useAuthorization } from '../auth/CapabilityProvider';
import { useBreakpoint } from '../hooks/useBreakpoint';
import ScopedConsoleLayout from './ScopedConsoleLayout';

vi.mock('../auth/CapabilityProvider', () => ({ useAuthorization: vi.fn() }));
vi.mock('../hooks/useBreakpoint', () => ({ useBreakpoint: vi.fn() }));

// The console shell now carries the theme/language top bar; stub its deps.
vi.mock('../hooks/useTheme', () => ({
  useTheme: () => ({ effective: 'light', setThemeMode: vi.fn() }),
}));
vi.mock('../auth/AuthProvider', () => ({
  useAuth: () => ({ user: { email: 'gov@test.ey.com' } }),
}));
vi.mock('../components/NotificationBell', () => ({ default: () => <div /> }));

describe('ScopedConsoleLayout', () => {
  beforeEach(() => {
    vi.mocked(useBreakpoint).mockReturnValue({
      xs: false,
      sm: false,
      md: false,
      lg: false,
      xl: false,
    });
  });

  afterEach(cleanup);

  it('renders governance navigation strictly from capabilities', () => {
    const allowed = new Set([
      'governance.access',
      'governance.users.manage',
      'governance.metrics.read',
    ]);
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: null,
      has: (capability) => allowed.has(capability),
      hasAny: (capabilities) => capabilities.some((capability) => allowed.has(capability)),
      hasAll: (capabilities) => capabilities.every((capability) => allowed.has(capability)),
      defaultConsole: '/governance',
    });

    render(
      <MemoryRouter
        initialEntries={['/governance/dashboard']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/governance" element={<ScopedConsoleLayout kind="governance" />}>
            <Route path="dashboard" element={<div>Overview content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Users' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Metrics' })).toBeTruthy();
    expect(screen.queryByRole('link', { name: 'Business lines' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Model binding' })).toBeNull();
    expect(screen.getByText('Overview content')).toBeTruthy();
  });

  it('uses a dismissible navigation drawer on mobile widths', () => {
    const allowed = new Set(['governance.access']);
    vi.mocked(useBreakpoint).mockReturnValue({
      xs: false,
      sm: true,
      md: true,
      lg: true,
      xl: false,
    });
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: null,
      has: (capability) => allowed.has(capability),
      hasAny: (capabilities) => capabilities.some((capability) => allowed.has(capability)),
      hasAll: (capabilities) => capabilities.every((capability) => allowed.has(capability)),
      defaultConsole: '/governance',
    });

    render(
      <MemoryRouter
        initialEntries={['/governance/dashboard']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/governance" element={<ScopedConsoleLayout kind="governance" />}>
            <Route path="dashboard" element={<div>Overview content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    const menuButton = screen.getByRole('button', { name: 'mobile_menu' });
    expect(menuButton.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(menuButton);
    expect(menuButton.getAttribute('aria-expanded')).toBe('true');
    const navigationDialog = screen.getByRole('dialog', { name: 'console_title_governance navigation' });
    expect(navigationDialog).toBeTruthy();
    expect(document.activeElement).toBe(navigationDialog.querySelector('.kp-workbench-drawer__close'));

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(menuButton.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('dialog', { name: 'console_title_governance navigation' })).toBeNull();
    expect(document.activeElement).toBe(menuButton);
  });
});
