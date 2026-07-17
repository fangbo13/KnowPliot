import { describe, expect, it } from 'vitest';

import type { AuthorizationAdapter } from '../auth/authorization';
import { visibleConsoleNavigation } from './consoleNavigation';

const access = (allowed: string[]): AuthorizationAdapter => ({
  enabled: true,
  status: 'ready',
  snapshot: null,
  has: (capability) => allowed.includes(capability),
  hasAny: (capabilities) => capabilities.some((capability) => allowed.includes(capability)),
  hasAll: (capabilities) => capabilities.every((capability) => allowed.includes(capability)),
  defaultConsole: '/chat',
});

describe('console navigation capability filtering', () => {
  it('shows only platform workbench destinations backed by platform capabilities', () => {
    const items = visibleConsoleNavigation(
      'platform',
      access(['platform.access', 'platform.users.manage', 'platform.metrics.read']),
      '/platform-admin',
    );

    expect(items.map((item) => item.segment)).toEqual(['dashboard', 'users', 'metrics']);
  });

  it('keeps organization-only governance destinations away from business-line admins', () => {
    const items = visibleConsoleNavigation(
      'governance',
      access([
        'governance.access',
        'governance.users.manage',
        'governance.templates.manage',
        'governance.metrics.read',
        'governance.audit.read',
      ]),
      '/governance',
    );

    expect(items.map((item) => item.segment)).toEqual([
      'dashboard',
      'users',
      'templates',
      'metrics',
      'audit',
    ]);
    expect(items.some((item) => item.segment === 'business-lines')).toBe(false);
    expect(items.some((item) => item.segment === 'model')).toBe(false);
  });

  it('limits reviewer workspace navigation to quality and read-only audit', () => {
    const items = visibleConsoleNavigation(
      'workspace',
      access(['workspace.manage', 'quality.read', 'quality.review', 'audit.read']),
      '/workspace/space-1/manage',
    );

    expect(items.map((item) => item.segment)).toEqual(['dashboard', 'quality', 'audit']);
    expect(items.every((item) => item.to.startsWith('/workspace/space-1/manage'))).toBe(true);
  });
});
