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
    <div className="kp-console-layout">
      <aside className="kp-console-sidebar">
        <div className="kp-console-brand">
          <div className="kp-console-title">
            {TITLES[kind]}
          </div>
          <div className="kp-console-scope">
            Capability-scoped console
          </div>
        </div>

        <nav aria-label={`${TITLES[kind]} navigation`} className="kp-console-nav">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `kp-console-nav__item${isActive ? ' is-active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="kp-console-sidebar__spacer" />
        <Link to="/chat" className="kp-console-back">
          Back to app
        </Link>
      </aside>

      <main className="kp-console-main">
        <div className="kp-console-content">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
