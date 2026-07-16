/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import apiClient from './client';

export type Capability =
  | 'chat.ask'
  | 'chat.export'
  | 'chat.history'
  | 'chat.share'
  | 'platform.access'
  | 'platform.organizations.manage'
  | 'platform.users.manage'
  | 'platform.roles.manage'
  | 'platform.models.manage'
  | 'platform.metrics.read'
  | 'platform.audit.read'
  | 'governance.access'
  | 'governance.organization.settings.manage'
  | 'governance.business_lines.manage'
  | 'governance.spaces.manage'
  | 'governance.users.manage'
  | 'governance.templates.manage'
  | 'governance.metrics.read'
  | 'governance.audit.read'
  | 'governance.models.bind'
  | 'workspace.manage'
  | 'workspace.members.manage'
  | 'workspace.invites.manage'
  | 'workspace.access_requests.manage'
  | 'workspace.settings.manage'
  | 'workspace.lifecycle.manage'
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

export interface CapabilitySnapshot {
  scopes: CapabilityScopes;
  capabilities: Capability[];
  default_console: string;
}

export const capabilitiesApi = {
  async me(
    spaceId?: string | null,
    signal?: AbortSignal,
  ): Promise<CapabilitySnapshot> {
    const { data } = await apiClient.get('/rbac/me/capabilities/', {
      params: spaceId ? { space_id: spaceId } : {},
      signal,
    });
    return data;
  },
};
