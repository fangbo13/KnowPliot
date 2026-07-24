/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { type ReactNode, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { capabilitiesApi } from '../api/capabilities';
import { useSpaceStore } from '../store/spaceStore';
import { ForbiddenPage } from './CapabilityGate';

/** Any capability that grants access to at least one section of the workspace console. */
const WORKSPACE_CONSOLE_CAPABILITIES = new Set<string>([
  'workspace.manage',
  'workspace.members.manage',
  'workspace.invites.manage',
  'workspace.access_requests.manage',
  'workspace.settings.manage',
  'workspace.lifecycle.manage',
  'workspace.delete.permanent',
  'workspace.ownership.read',
  'workspace.ownership.transfer.request',
  'workspace.ownership.transfer.accept',
  'knowledge.read',
  'quality.read',
  'audit.read',
]);

/**
 * A workspace URL is itself a scope selection. Converge the active scope first;
 * the provider then fetches capabilities for that exact id. Children remain
 * unmounted throughout both transitions, so space A authority cannot flash on B.
 */
export function WorkspaceCapabilityBoundary({ children }: { children: ReactNode }) {
  const { spaceId } = useParams<{ spaceId: string }>();
  const activeSpaceId = useSpaceStore((state) => state.activeSpaceId);
  const setActiveSpace = useSpaceStore((state) => state.setActiveSpace);
  const [deniedSpaceId, setDeniedSpaceId] = useState<string | null>(null);

  useEffect(() => {
    if (!spaceId || spaceId === activeSpaceId) return;
    const controller = new AbortController();
    setDeniedSpaceId(null);
    void capabilitiesApi.me(spaceId, controller.signal).then(
      async (snapshot) => {
        const hasConsoleAccess = snapshot.capabilities.some(
          (cap) => WORKSPACE_CONSOLE_CAPABILITIES.has(cap),
        );
        const isScoped = snapshot.scopes.space_ids.includes(spaceId);
        if (!hasConsoleAccess || !isScoped) {
          if (!controller.signal.aborted) setDeniedSpaceId(spaceId);
          return;
        }
        try {
          await setActiveSpace(spaceId);
        } catch {
          if (!controller.signal.aborted) setDeniedSpaceId(spaceId);
        }
      },
      () => {
        if (!controller.signal.aborted) setDeniedSpaceId(spaceId);
      },
    );
    return () => controller.abort();
  }, [activeSpaceId, setActiveSpace, spaceId]);

  if (!spaceId || deniedSpaceId === spaceId) return <ForbiddenPage />;
  if (activeSpaceId !== spaceId) {
    return (
      <div role="status" style={{ display: 'grid', minHeight: '40vh', placeItems: 'center' }}>
        Switching workspace…
      </div>
    );
  }

  return <>{children}</>;
}
