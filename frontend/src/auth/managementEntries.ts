/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { AuthorizationAdapter } from './authorization';

export interface ManagementEntry {
  id: 'console' | 'workspace' | 'knowledge';
  label: string;
  to: string;
}

export function buildManagementEntries(
  access: AuthorizationAdapter,
  activeSpaceId: string | null,
  t?: (key: string) => string,
): ManagementEntry[] {
  const entries: ManagementEntry[] = [];
  if (access.hasAny(['platform.access', 'governance.access'])) {
    entries.push({ id: 'console', label: t?.('management_console') || 'Management console', to: access.defaultConsole });
  }
  if (activeSpaceId && access.has('workspace.manage')) {
    entries.push({
      id: 'workspace',
      label: t?.('workspace_management') || 'Workspace management',
      to: access.enabled
        ? `/workspace/${activeSpaceId}/manage`
        : '/spaces/manage',
    });
  }
  // Knowledge base entry always routes to the workspace-scoped path so that
  // regular users with knowledge permissions don't land in the admin backend.
  if (activeSpaceId && access.has('knowledge.read')) {
    entries.push({
      id: 'knowledge',
      label: t?.('knowledge_base') || 'Knowledge base',
      to: `/workspace/${activeSpaceId}/manage/knowledge`,
    });
  }
  return entries;
}
