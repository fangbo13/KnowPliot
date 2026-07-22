/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { Navigate, useLocation, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from './AuthProvider';

/** Paths a spaceless user may access without being redirected to the guidance page. */
const SPACELESS_SAFE_PATHS = ['/spaces/discover', '/profile', '/ownership-transfers'];

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

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, user } = useAuth();
  const location = useLocation();

  // State 1: unauthenticated → redirect to login.
  if (!isAuthenticated) {
    const next = `${location.pathname}${location.search}${location.hash}`;
    const query = new URLSearchParams({ next }).toString();
    return <Navigate to={`/login?${query}`} replace />;
  }

  // State 2: authenticated but no default_space → guidance page (unless on a safe path).
  if (!user?.default_space) {
    const isSafePath = SPACELESS_SAFE_PATHS.some(
      (p) => location.pathname === p || location.pathname.startsWith(p + '/'),
    );
    if (!isSafePath) return <SpaceGuidancePage />;
  }

  // State 3: authenticated with a space → pass through.
  return <>{children}</>;
}
