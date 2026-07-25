/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { useEffect, useRef } from 'react';
import { Navigate, useLocation, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from './AuthProvider';
import { useSpaceStore } from '../store/spaceStore';

/** Paths a spaceless user may access without being redirected to the guidance page.
 *  Admin/governance/workspace-management routes are workspace-independent and must
 *  remain accessible to platform/org/business admins who may not have a
 *  default_space.  The CapabilityGate on those routes still enforces authorization. */
const SPACELESS_SAFE_PATHS = [
  '/spaces/discover', '/spaces/create', '/profile', '/ownership-transfers',
  '/platform-admin', '/governance', '/admin', '/workspace',
];

function SpaceGuidancePage() {
  const { t } = useTranslation('common');
  return (
    <main className="page" style={{ display: 'grid', minHeight: '100dvh', placeItems: 'center' }}>
      <section style={{ maxWidth: 480, padding: 32, textAlign: 'center' }}>
        <h1 className="page-title">{t('no_space_guidance_title')}</h1>
        <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6, marginTop: 12 }}>
          {t('no_space_guidance_description')}
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 24 }}>
          <Link className="new-chat-btn" to="/spaces/discover">{t('space_discovery')}</Link>
        </div>
      </section>
    </main>
  );
}

function SpaceCheckingLoader() {
  return (
    <div
      role="status"
      style={{ display: 'grid', minHeight: '100dvh', placeItems: 'center', color: 'var(--color-text-secondary)' }}
    >
      Loading workspace…
    </div>
  );
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();
  const spaces = useSpaceStore((state) => state.spaces);
  const loading = useSpaceStore((state) => state.loading);
  const loadSpaces = useSpaceStore((state) => state.loadSpaces);

  // When the user has no default_space on the auth state (e.g. legacy users
  // whose default_space was never persisted, or registrations that predate
  // the backend fix), trigger a spaceStore load so we can check whether they
  // actually belong to a workspace before showing the guidance page.
  const needsSpaceCheck = isAuthenticated && !user?.default_space;
  const spaceCheckTriggered = useRef(false);

  useEffect(() => {
    if (needsSpaceCheck && !spaceCheckTriggered.current && !loading) {
      spaceCheckTriggered.current = true;
      loadSpaces();
    }
  }, [needsSpaceCheck, loading, loadSpaces]);

  // State 1: unauthenticated → redirect to login.
  if (!isAuthenticated) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    const query = new URLSearchParams({ next }).toString();
    return <Navigate to={`/login?${query}`} replace />;
  }

  // State 2: authenticated but no default_space → check spaceStore.
  if (!user?.default_space) {
    const isSafePath = SPACELESS_SAFE_PATHS.some(
      (p) => location.pathname === p || location.pathname.startsWith(p + '/'),
    );
    if (!isSafePath) {
      // Spaces are already loaded and non-empty → user has a workspace, pass through.
      if (spaces.length > 0) return <>{children}</>;

      // Still loading or about to load → show a loading state.
      if (loading || (needsSpaceCheck && !spaceCheckTriggered.current)) {
        return <SpaceCheckingLoader />;
      }

      // Load completed but no spaces → guidance page.
      return <SpaceGuidancePage />;
    }
  }

  // State 3: authenticated with a space → pass through.
  return <>{children}</>;
}
