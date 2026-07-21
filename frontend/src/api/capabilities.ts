/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { coalescedGet } from './client';

export type Capability =
  | 'chat.ask'
  | 'chat.deep'
  | 'chat.thinking'
  | 'chat.export'
  | 'chat.history'
  | 'chat.share'
  | 'platform.access'
  | 'platform.organizations.manage'
  | 'platform.users.manage'
  | 'platform.users.offboard'
  | 'platform.roles.manage'
  | 'platform.models.manage'
  | 'platform.metrics.read'
  | 'platform.audit.read'
  | 'platform.knowledge.read'
  | 'platform.taxonomy.manage'
  | 'platform.templates.manage'
  | 'platform.workspace_creation_policies.manage'
  | 'platform.workspace_creation_requests.manage'
  | 'governance.access'
  | 'governance.organization.settings.manage'
  | 'governance.business_lines.manage'
  | 'governance.spaces.manage'
  | 'governance.users.manage'
  | 'governance.admin_succession.manage'
  | 'governance.users.suspend'
  | 'governance.templates.manage'
  | 'governance.metrics.read'
  | 'governance.audit.read'
  | 'governance.models.bind'
  | 'governance.taxonomy.manage'
  | 'workspace.creation.request'
  | 'workspace.manage'
  | 'workspace.members.manage'
  | 'workspace.invites.manage'
  | 'workspace.access_requests.manage'
  | 'workspace.settings.manage'
  | 'workspace.lifecycle.manage'
  | 'workspace.delete.permanent'
  | 'workspace.ownership.read'
  | 'workspace.ownership.transfer.request'
  | 'workspace.ownership.transfer.accept'
  | 'workspace.ownership.transfer.force'
  | 'knowledge.read'
  | 'knowledge.manage'
  | 'knowledge.index'
  | 'knowledge.download'
  | 'quality.read'
  | 'quality.review'
  | 'audit.read';

export interface CapabilityScopes {
  platform: boolean;
  organization_ids: string[];
  business_line_ids: string[];
  space_ids: string[];
}

export type NavigationMode = 'legacy' | 'capability';

export interface FeatureAvailability {
  deep: boolean;
  thinking: boolean;
  workspace_creation_approval: boolean;
  workspace_join_v2: boolean;
  workspace_permanent_delete: boolean;
}

export interface CapabilitySnapshot {
  navigation_mode: NavigationMode;
  configuration_revision: string;
  feature_availability: FeatureAvailability;
  scopes: CapabilityScopes;
  capabilities: Capability[];
  default_console: string;
}

export const CAPABILITY_CONTRACT_VERSION = 2;

const FEATURE_KEYS = [
  'deep',
  'thinking',
  'workspace_creation_approval',
  'workspace_join_v2',
  'workspace_permanent_delete',
] as const satisfies readonly (keyof FeatureAvailability)[];

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

export function isCapabilitySnapshot(value: unknown): value is CapabilitySnapshot {
  if (!isRecord(value)) return false;
  if (value.navigation_mode !== 'legacy' && value.navigation_mode !== 'capability') return false;
  if (typeof value.configuration_revision !== 'string' || !value.configuration_revision) return false;
  if (typeof value.default_console !== 'string' || !isStringArray(value.capabilities)) return false;

  const features = value.feature_availability;
  if (!isRecord(features) || FEATURE_KEYS.some((key) => typeof features[key] !== 'boolean')) {
    return false;
  }

  const scopes = value.scopes;
  return isRecord(scopes)
    && typeof scopes.platform === 'boolean'
    && isStringArray(scopes.organization_ids)
    && isStringArray(scopes.business_line_ids)
    && isStringArray(scopes.space_ids);
}

export const capabilitiesApi = {
  async me(
    spaceId?: string | null,
    signal?: AbortSignal,
  ): Promise<CapabilitySnapshot> {
    const config = {
      params: {
        contract_version: CAPABILITY_CONTRACT_VERSION,
        ...(spaceId ? { space_id: spaceId } : {}),
      },
      signal,
    };
    // Preserve the caller-owned signal for this bootstrap contract while still
    // coalescing duplicate reads made during one route mount.
    const { data } = await coalescedGet<unknown>(
      '/rbac/me/capabilities/',
      config,
      { preserveSignal: true },
    );
    if (!isCapabilitySnapshot(data)) {
      throw new Error('invalid_capability_contract');
    }
    return data;
  },
};
