/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { ReactNode } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import type { Capability } from '../api/capabilities';
import { safeConsolePath } from './authorization';
import { useAuthorization, useCapabilities } from './CapabilityProvider';

export function ForbiddenPage() {
  const { t } = useTranslation('common');
  return (
    <main className="page" style={{ display: 'grid', minHeight: '100dvh', placeItems: 'center' }}>
      <section style={{ maxWidth: 480, padding: 32, textAlign: 'center' }}>
        <div aria-hidden="true" style={{ fontSize: 42, color: 'var(--accent)' }}>403</div>
        <h1 className="page-title">{t('forbidden_title')}</h1>
        <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
          {t('forbidden_description')}
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 24 }}>
          <Link className="new-chat-btn" to="/chat">{t('forbidden_go_chat')}</Link>
          <Link className="new-chat-btn" to="/spaces/discover">{t('space_discovery')}</Link>
        </div>
      </section>
    </main>
  );
}

export function CapabilityLoading() {
  return (
    <div
      role="status"
      style={{ display: 'grid', minHeight: '40vh', placeItems: 'center', color: 'var(--color-text-secondary)' }}
    >
      Checking access…
    </div>
  );
}

export function CapabilityError({ retry, retryAfterSeconds }: { retry: () => void; retryAfterSeconds?: number | null }) {
  return (
    <main className="page" style={{ display: 'grid', minHeight: '100dvh', placeItems: 'center' }}>
      <section style={{ maxWidth: 480, padding: 32, textAlign: 'center' }}>
        <h1 className="page-title">Access check unavailable</h1>
        <p style={{ color: 'var(--color-text-secondary)' }}>
          {retryAfterSeconds == null
            ? 'We could not verify your permissions. No management data has been loaded.'
            : `Too many access checks. Retry in ${retryAfterSeconds}s. No management data has been loaded.`}
        </p>
        <button className="new-chat-btn" type="button" onClick={retry}>Try again</button>
      </section>
    </main>
  );
}

export function NavigationUnavailablePage({ retry }: { retry?: () => void }) {
  return (
    <main className="page" style={{ display: 'grid', minHeight: '100dvh', placeItems: 'center' }}>
      <section style={{ maxWidth: 520, padding: 32, textAlign: 'center' }}>
        <h1 className="page-title">Navigation unavailable</h1>
        <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
          This frontend and the server are using different navigation contracts. No management console has been loaded.
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 12 }}>
          {retry ? <button className="new-chat-btn" type="button" onClick={retry}>Try again</button> : null}
          <a className="new-chat-btn" href="/chat">Continue to chat</a>
        </div>
      </section>
    </main>
  );
}

export function CapabilityGate({
  required,
  requiredAny,
  spaceId,
  children,
}: {
  required?: Capability;
  requiredAny?: readonly Capability[];
  spaceId?: string | null;
  children: ReactNode;
}) {
  const access = useAuthorization();
  const capabilityState = useCapabilities();

  if (access.status === 'loading') return <CapabilityLoading />;
  if (access.status === 'mismatch') {
    return <NavigationUnavailablePage retry={capabilityState.refresh} />;
  }
  if (access.status === 'error') {
    return <CapabilityError retry={capabilityState.refresh} retryAfterSeconds={capabilityState.retryAfterSeconds} />;
  }
  if (access.status === 'denied') return <ForbiddenPage />;

  const scopeAllowed =
    !spaceId ||
    Boolean(access.snapshot?.scopes.space_ids.includes(spaceId));
  const capabilityAllowed = required
    ? access.has(required)
    : requiredAny
      ? access.hasAny(requiredAny)
      : true;

  if (!scopeAllowed || !capabilityAllowed) return <ForbiddenPage />;
  return <>{children}</>;
}

/** Compatibility-only route. It never mounts a legacy admin page. */
export function LegacyAdminRedirect() {
  const access = useAuthorization();
  const capabilityState = useCapabilities();

  if (access.status === 'loading') return <CapabilityLoading />;
  if (access.status === 'mismatch') return <NavigationUnavailablePage retry={capabilityState.refresh} />;
  if (access.status === 'error') return <CapabilityError retry={capabilityState.refresh} retryAfterSeconds={capabilityState.retryAfterSeconds} />;
  if (access.status === 'denied') return <ForbiddenPage />;
  return <Navigate to={safeConsolePath(access.defaultConsole)} replace />;
}
