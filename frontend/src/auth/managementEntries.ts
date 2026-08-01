/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { AuthorizationAdapter } from './authorization';

export interface ManagementEntry {
  id: 'knowledge' | 'reference-libraries';
  label: string;
  to: string;
}

export function buildManagementEntries(
  access: AuthorizationAdapter,
  activeSpaceId: string | null,
  t?: (key: string) => string,
): ManagementEntry[] {
  const entries: ManagementEntry[] = [];
  // The knowledge base is a standalone high-frequency shortcut that opens
  // the space-selection landing page (new RBAC §3).
  if (activeSpaceId && access.has('knowledge.read')) {
    entries.push({
      id: 'knowledge',
      label: t?.('knowledge_base') || 'Knowledge base',
      to: '/knowledge',
    });
  }
  // Reference libraries shortcut — available to any user who can ask.
  if (access.has('chat.ask')) {
    entries.push({
      id: 'reference-libraries',
      label: t?.('nav_reference_libraries') || 'Reference libraries',
      to: '/reference-libraries',
    });
  }
  return entries;
}
