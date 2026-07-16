/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { Capability, CapabilitySnapshot } from '../api/capabilities';
import type { SpaceRole } from '../api/spaces';

/** Build-time rollout switch. It is deliberately off unless set to literal `true`. */
export const CAPABILITY_NAV_ENABLED =
  (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_CAPABILITY_NAV === 'true';

export type CapabilityStateStatus = 'loading' | 'ready' | 'denied' | 'error';

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

const PLATFORM_CAPABILITIES = new Set<Capability>([
  'platform.access',
  'platform.organizations.manage',
  'platform.users.manage',
  'platform.roles.manage',
  'platform.models.manage',
  'platform.metrics.read',
  'platform.audit.read',
]);

const GOVERNANCE_CAPABILITIES = new Set<Capability>([
  'governance.access',
  'governance.organization.settings.manage',
  'governance.business_lines.manage',
  'governance.spaces.manage',
  'governance.users.manage',
  'governance.templates.manage',
  'governance.metrics.read',
  'governance.audit.read',
  'governance.models.bind',
]);

const WORKSPACE_MANAGE_ROLES = new Set<SpaceRole>([
  'owner',
  'super_admin',
  'org_admin',
  'business_admin',
]);

export function safeConsolePath(path: string): string {
  if (path === '/chat' || path === '/platform-admin' || path === '/governance') return path;
  if (/^\/workspace\/[^/]+\/manage$/.test(path)) return path;
  return '/chat';
}

function legacyAdmin(user?: LegacyAuthorizationUser | null): boolean {
  return Boolean(
    user?.is_superuser ||
      user?.is_super_admin ||
      user?.is_org_admin ||
      user?.is_business_admin ||
      user?.roles?.includes('admin'),
  );
}

function legacyPlatformAdmin(user?: LegacyAuthorizationUser | null): boolean {
  return Boolean(
    user?.is_superuser ||
      user?.is_super_admin ||
      user?.roles?.includes('admin'),
  );
}

function legacyHas(
  capability: Capability,
  user?: LegacyAuthorizationUser | null,
  activeSpaceRole?: SpaceRole | null,
): boolean {
  if (capability.startsWith('chat.')) return true;
  if (PLATFORM_CAPABILITIES.has(capability)) return legacyPlatformAdmin(user);
  if (GOVERNANCE_CAPABILITIES.has(capability)) return legacyAdmin(user);

  const managesWorkspace = Boolean(
    activeSpaceRole && WORKSPACE_MANAGE_ROLES.has(activeSpaceRole),
  );
  if (capability.startsWith('workspace.')) return managesWorkspace;

  const legacyKnowledgeAdmin = Boolean(
    managesWorkspace ||
      activeSpaceRole === 'knowledge_admin' ||
      user?.is_hr_admin ||
      user?.roles?.includes('hr'),
  );
  if (capability.startsWith('knowledge.')) return legacyKnowledgeAdmin;
  if (capability.startsWith('quality.')) {
    return legacyKnowledgeAdmin || activeSpaceRole === 'reviewer';
  }
  if (capability === 'audit.read') {
    return managesWorkspace || activeSpaceRole === 'reviewer';
  }
  return false;
}

export function createAuthorizationAdapter({
  capabilityNavigationEnabled = CAPABILITY_NAV_ENABLED,
  status,
  snapshot,
  legacyUser,
  activeSpaceRole,
  activeSpaceId,
}: AuthorizationAdapterInput): AuthorizationAdapter {
  const capabilitySet = new Set(snapshot?.capabilities ?? []);
  const has = (capability: Capability): boolean => {
    if (capabilityNavigationEnabled) {
      return status === 'ready' && capabilitySet.has(capability);
    }
    return legacyHas(capability, legacyUser, activeSpaceRole);
  };

  let defaultConsole = '/chat';
  if (capabilityNavigationEnabled) {
    if (status === 'ready' && snapshot) {
      defaultConsole = safeConsolePath(snapshot.default_console);
    }
  } else if (legacyAdmin(legacyUser)) {
    defaultConsole = '/admin';
  } else if (activeSpaceId && activeSpaceRole && WORKSPACE_MANAGE_ROLES.has(activeSpaceRole)) {
    defaultConsole = '/spaces/manage';
  }

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
