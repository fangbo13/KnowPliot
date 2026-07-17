/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { Capability } from '../api/capabilities';
import type { AuthorizationAdapter } from '../auth/authorization';

export type ConsoleKind = 'platform' | 'governance' | 'workspace';

export interface ConsoleNavigationItem {
  segment: string;
  label: string;
  capability: Capability;
  to: string;
}

const DEFINITIONS: Record<ConsoleKind, Array<Omit<ConsoleNavigationItem, 'to'>>> = {
  platform: [
    { segment: 'dashboard', label: 'Dashboard', capability: 'platform.access' },
    { segment: 'users', label: 'Users', capability: 'platform.users.manage' },
    { segment: 'business-lines', label: 'Organizations & business lines', capability: 'platform.organizations.manage' },
    { segment: 'templates', label: 'Templates', capability: 'platform.organizations.manage' },
    { segment: 'metrics', label: 'Metrics', capability: 'platform.metrics.read' },
    { segment: 'audit', label: 'Audit', capability: 'platform.audit.read' },
    { segment: 'model', label: 'Models', capability: 'platform.models.manage' },
  ],
  governance: [
    { segment: 'dashboard', label: 'Dashboard', capability: 'governance.access' },
    { segment: 'users', label: 'Users', capability: 'governance.users.manage' },
    { segment: 'business-lines', label: 'Business lines', capability: 'governance.business_lines.manage' },
    { segment: 'templates', label: 'Templates', capability: 'governance.templates.manage' },
    { segment: 'metrics', label: 'Metrics', capability: 'governance.metrics.read' },
    { segment: 'audit', label: 'Audit', capability: 'governance.audit.read' },
    { segment: 'model', label: 'Model binding', capability: 'governance.models.bind' },
  ],
  workspace: [
    { segment: 'dashboard', label: 'Workspace', capability: 'workspace.manage' },
    { segment: 'members', label: 'Members', capability: 'workspace.members.manage' },
    { segment: 'invites', label: 'Invitations', capability: 'workspace.invites.manage' },
    { segment: 'access', label: 'Access requests', capability: 'workspace.access_requests.manage' },
    { segment: 'knowledge', label: 'Knowledge', capability: 'knowledge.read' },
    { segment: 'quality', label: 'Quality', capability: 'quality.read' },
    { segment: 'audit', label: 'Audit', capability: 'audit.read' },
    { segment: 'settings', label: 'Settings', capability: 'workspace.settings.manage' },
    { segment: 'lifecycle', label: 'Lifecycle', capability: 'workspace.lifecycle.manage' },
  ],
};

export function visibleConsoleNavigation(
  kind: ConsoleKind,
  access: AuthorizationAdapter,
  basePath: string,
): ConsoleNavigationItem[] {
  return DEFINITIONS[kind]
    .filter((item) => access.has(item.capability))
    .map((item) => ({ ...item, to: `${basePath}/${item.segment}` }));
}

export function consoleCapability(kind: ConsoleKind, segment: string): Capability | null {
  return DEFINITIONS[kind].find((item) => item.segment === segment)?.capability ?? null;
}
