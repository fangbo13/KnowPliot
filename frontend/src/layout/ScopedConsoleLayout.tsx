/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { Link, NavLink, Outlet, useParams } from 'react-router-dom';

import { useAuthorization } from '../auth/CapabilityProvider';
import {
  type ConsoleKind,
  visibleConsoleNavigation,
} from './consoleNavigation';

const TITLES: Record<ConsoleKind, string> = {
  platform: 'Platform administration',
  governance: 'Governance',
  workspace: 'Workspace management',
};

export default function ScopedConsoleLayout({ kind }: { kind: ConsoleKind }) {
  const access = useAuthorization();
  const { spaceId } = useParams<{ spaceId: string }>();
  const basePath = kind === 'workspace'
    ? `/workspace/${spaceId ?? ''}/manage`
    : kind === 'platform'
      ? '/platform-admin'
      : '/governance';
  const navigation = visibleConsoleNavigation(kind, access, basePath);

  return (
    <div style={{ display: 'flex', minHeight: '100dvh', background: 'var(--color-bg-body)' }}>
      <aside
        style={{
          width: 256,
          flexShrink: 0,
          display: 'flex',
          flexDirection: 'column',
          padding: '20px 14px',
          borderRight: '1px solid var(--color-border-secondary)',
          background: 'var(--color-bg-sunken)',
        }}
      >
        <div style={{ padding: '0 10px 18px' }}>
          <div style={{ fontFamily: 'var(--font-family-display)', fontSize: 19, fontWeight: 600 }}>
            {TITLES[kind]}
          </div>
          <div style={{ marginTop: 5, color: 'var(--color-text-tertiary)', fontSize: 12 }}>
            Capability-scoped console
          </div>
        </div>

        <nav aria-label={`${TITLES[kind]} navigation`} style={{ display: 'grid', gap: 3 }}>
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                padding: '10px 12px',
                borderRadius: 9,
                color: isActive ? 'var(--accent-text)' : 'var(--color-text-secondary)',
                background: isActive ? 'var(--accent-soft)' : 'transparent',
                fontWeight: isActive ? 600 : 500,
                textDecoration: 'none',
              })}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div style={{ flex: 1 }} />
        <Link
          to="/chat"
          style={{ padding: '10px 12px', color: 'var(--color-text-secondary)', textDecoration: 'none' }}
        >
          Back to app
        </Link>
      </aside>

      <main style={{ flex: 1, minWidth: 0, overflow: 'auto' }}>
        <Outlet />
      </main>
    </div>
  );
}
