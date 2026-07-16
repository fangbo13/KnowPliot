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
): ManagementEntry[] {
  const entries: ManagementEntry[] = [];
  if (access.hasAny(['platform.access', 'governance.access'])) {
    entries.push({ id: 'console', label: 'Management console', to: access.defaultConsole });
  }
  if (activeSpaceId && access.has('workspace.manage')) {
    entries.push({
      id: 'workspace',
      label: 'Workspace management',
      to: access.enabled
        ? `/workspace/${activeSpaceId}/manage`
        : '/spaces/manage',
    });
  }
  if (activeSpaceId && access.has('knowledge.read')) {
    entries.push({
      id: 'knowledge',
      label: 'Knowledge base',
      to: access.enabled
        ? `/workspace/${activeSpaceId}/manage/knowledge`
        : '/admin/knowledge',
    });
  }
  return entries;
}
