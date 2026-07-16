/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { type ReactNode, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { useSpaceStore } from '../store/spaceStore';
import { CapabilityGate, ForbiddenPage } from './CapabilityGate';

/**
 * A workspace URL is itself a scope selection. Converge the active scope first;
 * the provider then fetches capabilities for that exact id. Children remain
 * unmounted throughout both transitions, so space A authority cannot flash on B.
 */
export function WorkspaceCapabilityBoundary({ children }: { children: ReactNode }) {
  const { spaceId } = useParams<{ spaceId: string }>();
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);
  const setActiveSpace = useSpaceStore((state) => state.setActiveSpace);
  const [scopeError, setScopeError] = useState(false);

  useEffect(() => {
    if (!spaceId || spaceId === activeSpaceId) return;
    let cancelled = false;
    setScopeError(false);
    void setActiveSpace(spaceId).catch(() => {
      if (!cancelled) setScopeError(true);
    });
    return () => {
      cancelled = true;
    };
  }, [activeSpaceId, setActiveSpace, spaceId]);

  if (!spaceId || scopeError) return <ForbiddenPage />;
  if (activeSpaceId !== spaceId) {
    return (
      <div role="status" style={{ display: 'grid', minHeight: '40vh', placeItems: 'center' }}>
        Switching workspace…
      </div>
    );
  }

  return (
    <CapabilityGate required="workspace.manage" spaceId={spaceId}>
      {children}
    </CapabilityGate>
  );
}
