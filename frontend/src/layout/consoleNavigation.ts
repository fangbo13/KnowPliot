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
  /** English fallback label (kept for tests/back-compat). */
  label: string;
  /** Dark/i18n/Layout spec §B1: i18n key — render with t(labelKey, label). */
  labelKey: string;
  capability: Capability;
  to: string;
}

const DEFINITIONS: Record<ConsoleKind, Array<Omit<ConsoleNavigationItem, 'to'>>> = {
  platform: [
    { segment: 'dashboard', label: 'Dashboard', labelKey: 'console_nav_dashboard', capability: 'platform.access' },
    { segment: 'users', label: 'Users', labelKey: 'console_nav_users', capability: 'platform.users.manage' },
    { segment: 'business-lines', label: 'Organizations & business lines', labelKey: 'console_nav_orgs_business_lines', capability: 'platform.organizations.manage' },
    { segment: 'templates', label: 'Templates', labelKey: 'console_nav_templates', capability: 'platform.templates.manage' },
    { segment: 'creation-requests', label: 'Creation requests', labelKey: 'console_nav_creation_requests', capability: 'platform.workspace_creation_requests.manage' },
    { segment: 'knowledge', label: 'Knowledge metadata', labelKey: 'console_nav_knowledge_metadata', capability: 'platform.knowledge.read' },
    { segment: 'metrics', label: 'Metrics', labelKey: 'console_nav_metrics', capability: 'platform.metrics.read' },
    { segment: 'audit', label: 'Audit', labelKey: 'console_nav_audit', capability: 'platform.audit.read' },
    { segment: 'spaces', label: 'Workspaces', labelKey: 'console_nav_workspaces', capability: 'platform.access' },
    { segment: 'model', label: 'Models', labelKey: 'console_nav_models', capability: 'platform.models.manage' },
  ],
  governance: [
    { segment: 'dashboard', label: 'Dashboard', labelKey: 'console_nav_dashboard', capability: 'governance.access' },
    { segment: 'users', label: 'Users', labelKey: 'console_nav_users', capability: 'governance.users.manage' },
    { segment: 'business-lines', label: 'Business lines', labelKey: 'console_nav_business_lines', capability: 'governance.business_lines.manage' },
    { segment: 'templates', label: 'Templates', labelKey: 'console_nav_templates', capability: 'governance.templates.manage' },
    { segment: 'metrics', label: 'Metrics', labelKey: 'console_nav_metrics', capability: 'governance.metrics.read' },
    { segment: 'audit', label: 'Audit', labelKey: 'console_nav_audit', capability: 'governance.audit.read' },
    { segment: 'model', label: 'Model binding', labelKey: 'console_nav_model_binding', capability: 'governance.models.bind' },
  ],
  workspace: [
    { segment: 'dashboard', label: 'Workspace', labelKey: 'console_nav_workspace', capability: 'workspace.manage' },
    { segment: 'members', label: 'Members', labelKey: 'console_nav_members', capability: 'workspace.members.manage' },
    { segment: 'invites', label: 'Invitations', labelKey: 'console_nav_invitations', capability: 'workspace.invites.manage' },
    { segment: 'access', label: 'Access requests', labelKey: 'console_nav_access_requests', capability: 'workspace.access_requests.manage' },
    { segment: 'quality', label: 'Quality', labelKey: 'console_nav_quality', capability: 'quality.read' },
    { segment: 'audit', label: 'Audit', labelKey: 'console_nav_audit', capability: 'audit.read' },
    { segment: 'settings', label: 'Settings', labelKey: 'console_nav_settings', capability: 'workspace.settings.manage' },
    { segment: 'lifecycle', label: 'Lifecycle', labelKey: 'console_nav_lifecycle', capability: 'workspace.lifecycle.manage' },
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
