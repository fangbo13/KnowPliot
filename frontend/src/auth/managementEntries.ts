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
  // The knowledge base is a standalone workspace-scoped route, separated
  // from the workspace management console. In legacy mode it falls back to
  // the admin knowledge page.
  if (activeSpaceId && access.has('knowledge.read')) {
    entries.push({
      id: 'knowledge',
      label: t?.('knowledge_base') || 'Knowledge base',
      to: access.enabled
        ? `/workspace/${activeSpaceId}/knowledge`
        : '/admin/knowledge',
    });
  }
  return entries;
}
