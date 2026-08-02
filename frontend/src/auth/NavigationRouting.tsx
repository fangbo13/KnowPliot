/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import type { Capability, CapabilitySnapshot, NavigationMode } from '../api/capabilities';
import {
  CapabilityError,
  CapabilityLoading,
  ForbiddenPage,
  NavigationUnavailablePage,
} from './CapabilityGate';
import { useCapabilities } from './CapabilityProvider';

const MAX_NEXT_LENGTH = 2048;
const CONTROL_OR_BACKSLASH = /[\\\u0000-\u001f\u007f]/;

function targetPath(candidate: string | null | undefined, origin: string): string | null {
  if (!candidate || candidate.length > MAX_NEXT_LENGTH || CONTROL_OR_BACKSLASH.test(candidate)) {
    return null;
  }
  try {
    const base = new URL(origin);
    const target = new URL(candidate, base);
    if (target.origin !== base.origin || target.username || target.password) return null;
    return `${target.pathname}${target.search}${target.hash}`;
  } catch {
    return null;
  }
}

function has(snapshot: CapabilitySnapshot, capability: Capability): boolean {
  return snapshot.capabilities.includes(capability);
}

function hasAny(snapshot: CapabilitySnapshot, capabilities: readonly Capability[]): boolean {
  return capabilities.some((capability) => has(snapshot, capability));
}

function capabilityRouteAllowed(pathname: string, snapshot: CapabilitySnapshot): boolean {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname;

  if (path === '/chat') return has(snapshot, 'chat.ask');
  if (path === '/history') return has(snapshot, 'chat.history');
  if (path === '/profile' || path === '/spaces/discover') return true;
  if (path === '/spaces/create') return has(snapshot, 'workspace.creation.request');
  if (path === '/ownership-transfers') {
    return has(snapshot, 'workspace.ownership.transfer.accept');
  }
  if (/^\/shared\/[^/]+$/.test(path)) return true;

  if (snapshot.navigation_mode === 'legacy') {
    if (path === '/spaces/manage') return has(snapshot, 'workspace.manage');
    if (path === '/admin' || path === '/admin/dashboard') {
      return hasAny(snapshot, ['platform.access', 'governance.access', 'workspace.manage']);
    }
    if (path === '/admin/users') {
      return hasAny(snapshot, ['platform.users.manage', 'governance.users.manage']);
    }
    if (path === '/admin/business-lines') {
      return hasAny(snapshot, ['platform.organizations.manage', 'governance.business_lines.manage']);
    }
    if (path === '/admin/templates') {
      return hasAny(snapshot, ['platform.organizations.manage', 'governance.templates.manage']);
    }
    if (path === '/admin/knowledge') return has(snapshot, 'knowledge.read');
    if (path === '/admin/quality') return has(snapshot, 'quality.read');
    if (path === '/admin/audit') {
      return hasAny(snapshot, ['platform.audit.read', 'governance.audit.read', 'audit.read']);
    }
    if (path === '/admin/codes' || path === '/admin/announcements') {
      return hasAny(snapshot, ['platform.access', 'governance.access']);
    }
    return false;
  }

  if (path === '/platform-admin' || path === '/platform-admin/dashboard') {
    return has(snapshot, 'platform.access');
  }
  // Management center merged into knowledge base — /console redirects to /knowledge.
  // Knowledge spaces page is accessible to all authenticated users.
  if (path === '/console' || path === '/knowledge') return true;
  if (path === '/platform-admin/users') return has(snapshot, 'platform.users.manage');
  if (path === '/platform-admin/business-lines') {
    return has(snapshot, 'platform.organizations.manage');
  }
  if (path === '/platform-admin/templates') return has(snapshot, 'platform.templates.manage');
  if (path === '/platform-admin/knowledge') return has(snapshot, 'platform.knowledge.read');
  if (path === '/platform-admin/metrics') return has(snapshot, 'platform.metrics.read');
  if (path === '/platform-admin/audit') return has(snapshot, 'platform.audit.read');
  if (path === '/platform-admin/model') return has(snapshot, 'platform.models.manage');
  if (path === '/platform-admin/creation-requests') {
    return has(snapshot, 'platform.workspace_creation_requests.manage');
  }

  if (path === '/governance' || path === '/governance/dashboard') {
    return has(snapshot, 'governance.access');
  }
  if (path === '/governance/users') return has(snapshot, 'governance.users.manage');
  if (path === '/governance/business-lines') return has(snapshot, 'governance.business_lines.manage');
  if (path === '/governance/templates') return has(snapshot, 'governance.templates.manage');
  if (path === '/governance/metrics') return has(snapshot, 'governance.metrics.read');
  if (path === '/governance/audit') return has(snapshot, 'governance.audit.read');
  if (path === '/governance/model') return has(snapshot, 'governance.models.bind');

  // Standalone knowledge route — separated from workspace management console
  const knowledge = path.match(/^\/workspace\/([^/]+)\/knowledge$/);
  if (knowledge) {
    if (!snapshot.scopes.space_ids.includes(knowledge[1])) return false;
    return has(snapshot, 'knowledge.read');
  }

  const workspace = path.match(/^\/workspace\/([^/]+)\/manage(?:\/(dashboard|members|invites|access|quality|audit|settings|lifecycle))?$/);
  if (!workspace || !snapshot.scopes.space_ids.includes(workspace[1])) return false;
  const requiredByPage: Record<string, Capability> = {
    dashboard: 'workspace.manage',
    members: 'workspace.members.manage',
    invites: 'workspace.invites.manage',
    access: 'workspace.access_requests.manage',
    quality: 'quality.read',
    audit: 'audit.read',
    settings: 'workspace.settings.manage',
    lifecycle: 'workspace.lifecycle.manage',
  };
  return has(snapshot, requiredByPage[workspace[2] ?? 'dashboard']);
}

function allowedTarget(
  candidate: string | null | undefined,
  snapshot: CapabilitySnapshot,
  origin: string,
): string | null {
  const path = targetPath(candidate, origin);
  if (!path) return null;
  const pathname = new URL(path, origin).pathname;
  if (pathname === '/' || pathname === '/login' || pathname === '/reset-password') return null;
  return capabilityRouteAllowed(pathname, snapshot) ? path : null;
}

export function resolvePostAuthDestination({
  next,
  snapshot,
  origin = typeof window === 'undefined' ? 'http://localhost' : window.location.origin,
}: {
  next?: string | null;
  snapshot: CapabilitySnapshot;
  origin?: string;
}): string {
  return allowedTarget(next, snapshot, origin)
    ?? allowedTarget(snapshot.default_console, snapshot, origin)
    ?? '/chat';
}

export function NavigationModeBoundary({
  expected,
  children,
}: {
  expected: NavigationMode;
  children: ReactNode;
}) {
  const state = useCapabilities();
  if (state.status === 'loading') return <CapabilityLoading />;
  if (
    state.status === 'mismatch'
    || (state.snapshot && state.snapshot.navigation_mode !== expected)
  ) {
    return <NavigationUnavailablePage retry={state.refresh} />;
  }
  if (state.status === 'error') {
    return <CapabilityError retry={state.refresh} retryAfterSeconds={state.retryAfterSeconds} />;
  }
  if (state.status === 'denied' || !state.snapshot) return <ForbiddenPage />;
  return <>{children}</>;
}

export function AuthenticatedEntryRedirect() {
  const state = useCapabilities();
  const location = useLocation();

  if (state.status === 'loading') return <CapabilityLoading />;
  if (state.status === 'mismatch') return <NavigationUnavailablePage retry={state.refresh} />;
  if (state.status === 'error') {
    return <CapabilityError retry={state.refresh} retryAfterSeconds={state.retryAfterSeconds} />;
  }
  if (state.status !== 'ready' || !state.snapshot) return <Navigate to="/chat" replace />;

  const next = new URLSearchParams(location.search).get('next');
  return (
    <Navigate
      to={resolvePostAuthDestination({ next, snapshot: state.snapshot })}
      replace
    />
  );
}
