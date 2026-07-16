/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';

import type { Capability } from '../api/capabilities';
import { safeConsolePath } from './authorization';
import { useAuthorization, useCapabilities } from './CapabilityProvider';

export function ForbiddenPage() {
  return (
    <main className="page" style={{ display: 'grid', minHeight: '100dvh', placeItems: 'center' }}>
      <section style={{ maxWidth: 480, padding: 32, textAlign: 'center' }}>
        <div aria-hidden="true" style={{ fontSize: 42, color: 'var(--accent)' }}>403</div>
        <h1 className="page-title">Access denied</h1>
        <p style={{ color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
          You do not have the capability required for this workspace.
        </p>
      </section>
    </main>
  );
}

function CapabilityLoading() {
  return (
    <div
      role="status"
      style={{ display: 'grid', minHeight: '40vh', placeItems: 'center', color: 'var(--color-text-secondary)' }}
    >
      Checking access…
    </div>
  );
}

function CapabilityError({ retry }: { retry: () => void }) {
  return (
    <main className="page" style={{ display: 'grid', minHeight: '100dvh', placeItems: 'center' }}>
      <section style={{ maxWidth: 480, padding: 32, textAlign: 'center' }}>
        <h1 className="page-title">Access check unavailable</h1>
        <p style={{ color: 'var(--color-text-secondary)' }}>
          We could not verify your permissions. No management data has been loaded.
        </p>
        <button className="new-chat-btn" type="button" onClick={retry}>Try again</button>
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

  if (access.enabled && access.status === 'loading') return <CapabilityLoading />;
  if (access.enabled && access.status === 'error') {
    return <CapabilityError retry={capabilityState.refresh} />;
  }
  if (access.enabled && access.status === 'denied') return <ForbiddenPage />;

  const scopeAllowed =
    !spaceId ||
    !access.enabled ||
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
  if (access.status === 'error') return <CapabilityError retry={capabilityState.refresh} />;
  if (access.status === 'denied') return <ForbiddenPage />;
  return <Navigate to={safeConsolePath(access.defaultConsole)} replace />;
}
