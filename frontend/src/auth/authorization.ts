/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { Capability, CapabilitySnapshot, NavigationMode } from '../api/capabilities';
import type { SpaceRole } from '../api/spaces';

/** Build-time rollout switch. It is deliberately off unless set to literal `true`. */
export const CAPABILITY_NAV_ENABLED =
  (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_CAPABILITY_NAV === 'true';

export function isDeepAnswerModeEnabled(
  env: Record<string, string | undefined> =
    (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {},
): boolean {
  return env.VITE_DEEP_ANSWER_MODE === 'true';
}

/** Deep rollout is deliberately independent and default-off. */
export const DEEP_ANSWER_MODE_ENABLED = isDeepAnswerModeEnabled();

/**
 * Thinking is a separate build-time rollout from the deep answer tier.  The
 * flag only controls whether the browser may render the preference; the
 * server capability and policy remain authoritative for execution.
 */
export function isThinkingModeEnabled(
  env: Record<string, string | undefined> =
    (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {},
): boolean {
  return env.VITE_THINKING_MODE === 'true';
}

export const THINKING_MODE_ENABLED = isThinkingModeEnabled();

export type CapabilityStateStatus = 'loading' | 'ready' | 'denied' | 'error' | 'mismatch';

/**
 * Legacy identity fields live only at this compatibility boundary. Active UI
 * code asks this adapter about capabilities and never interprets roles itself.
 */
export interface LegacyAuthorizationUser {
  is_superuser?: boolean;
  is_super_admin?: boolean;
  is_org_admin?: boolean;
  is_business_admin?: boolean;
  is_hr_admin?: boolean;
  roles?: string[];
  permissions?: string[];
}

export interface AuthorizationAdapter {
  enabled: boolean;
  status: CapabilityStateStatus;
  snapshot: CapabilitySnapshot | null;
  has: (capability: Capability) => boolean;
  hasAny: (capabilities: readonly Capability[]) => boolean;
  hasAll: (capabilities: readonly Capability[]) => boolean;
  defaultConsole: string;
}

interface AuthorizationAdapterInput {
  capabilityNavigationEnabled?: boolean;
  status: CapabilityStateStatus;
  snapshot: CapabilitySnapshot | null;
  legacyUser?: LegacyAuthorizationUser | null;
  activeSpaceRole?: SpaceRole | null;
  activeSpaceId?: string | null;
}

function isWorkspaceBoundCapability(capability: Capability): boolean {
  return capability.startsWith('chat.') ||
    capability.startsWith('workspace.') ||
    capability.startsWith('knowledge.') ||
    capability.startsWith('quality.') ||
    capability === 'audit.read';
}

export function safeConsolePath(
  path: string,
  navigationMode: NavigationMode = 'capability',
): string {
  if (path === '/chat') return path;
  if (navigationMode === 'legacy') {
    if (path === '/admin' || path === '/spaces/manage') return path;
    return '/chat';
  }
  if (path === '/platform-admin' || path === '/governance') return path;
  if (/^\/workspace\/[^/]+\/manage$/.test(path)) return path;
  return '/chat';
}

export function createAuthorizationAdapter({
  capabilityNavigationEnabled = CAPABILITY_NAV_ENABLED,
  status,
  snapshot,
  activeSpaceId,
}: AuthorizationAdapterInput): AuthorizationAdapter {
  const capabilitySet = new Set(snapshot?.capabilities ?? []);
  const has = (capability: Capability): boolean => {
    if (status !== 'ready' || !snapshot || !capabilitySet.has(capability)) return false;
    const activeWorkspaceIsScoped = Boolean(
      activeSpaceId && snapshot.scopes.space_ids.includes(activeSpaceId),
    );
    return !isWorkspaceBoundCapability(capability) || activeWorkspaceIsScoped;
  };

  const defaultConsole = status === 'ready' && snapshot
    ? safeConsolePath(snapshot.default_console, snapshot.navigation_mode)
    : '/chat';

  return {
    enabled: capabilityNavigationEnabled,
    status,
    snapshot,
    has,
    hasAny: (capabilities) => capabilities.some(has),
    hasAll: (capabilities) => capabilities.every(has),
    defaultConsole,
  };
}
