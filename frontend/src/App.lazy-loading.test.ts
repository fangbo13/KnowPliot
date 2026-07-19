import { describe, expect, it } from 'vitest';

import appSource from './App.tsx?raw';

describe('App route-level lazy boundaries', () => {
  it.each([
    './auth/LoginPage',
    './auth/ResetPasswordPage',
    './pages/ChatPage',
    './pages/SpaceDiscoveryPage',
    './pages/admin/KnowledgeBasePage',
    './pages/admin/AdminTemplatesPage',
    './pages/admin/AdminDashboardPage',
    './pages/console/ScopedMetricsPage',
    './pages/console/GovernancePoliciesPage',
  ])('uses a statically analyzable lazy import for %s', (modulePath) => {
    expect(appSource).toContain(`lazy(() => import('${modulePath}'))`);
    expect(appSource).not.toContain(`from '${modulePath}'`);
  });

  it('ships an explicit Suspense route fallback', () => {
    expect(appSource).toContain('<Suspense fallback={<RouteLoading />}');
  });
});
