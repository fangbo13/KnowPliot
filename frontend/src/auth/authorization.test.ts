import { describe, expect, it } from 'vitest';

import {
  createAuthorizationAdapter,
  isDeepAnswerModeEnabled,
  type LegacyAuthorizationUser,
} from './authorization';
import type { CapabilitySnapshot } from '../api/capabilities';

const legacyAdmin: LegacyAuthorizationUser = {
  is_superuser: true,
  is_super_admin: false,
  is_org_admin: false,
  is_business_admin: false,
  is_hr_admin: true,
  roles: ['admin', 'hr'],
  permissions: ['document.create'],
};

const workspaceSnapshot: CapabilitySnapshot = {
  scopes: {
    platform: false,
    organization_ids: [],
    business_line_ids: [],
    space_ids: ['space-1'],
  },
  capabilities: ['chat.ask', 'workspace.manage', 'knowledge.manage'],
  default_console: '/workspace/space-1/manage',
};

describe('authorization compatibility adapter', () => {
  it('enables deep answer rollout only for the literal true flag', () => {
    expect(isDeepAnswerModeEnabled({ VITE_DEEP_ANSWER_MODE: 'true' })).toBe(true);
    expect(isDeepAnswerModeEnabled({ VITE_DEEP_ANSWER_MODE: 'TRUE' })).toBe(false);
    expect(isDeepAnswerModeEnabled({})).toBe(false);
  });

  it('uses only server capabilities when capability navigation is enabled', () => {
    const access = createAuthorizationAdapter({
      capabilityNavigationEnabled: true,
      status: 'ready',
      snapshot: workspaceSnapshot,
      legacyUser: legacyAdmin,
      activeSpaceRole: 'owner',
      activeSpaceId: 'space-1',
    });

    expect(access.has('knowledge.manage')).toBe(true);
    expect(access.has('platform.access')).toBe(false);
    expect(access.defaultConsole).toBe('/workspace/space-1/manage');
  });

  it('keeps the legacy role fallback only while capability navigation is disabled', () => {
    const access = createAuthorizationAdapter({
      capabilityNavigationEnabled: false,
      status: 'loading',
      snapshot: null,
      legacyUser: legacyAdmin,
      activeSpaceRole: 'owner',
      activeSpaceId: 'space-1',
    });

    expect(access.has('platform.access')).toBe(true);
    expect(access.has('workspace.members.manage')).toBe(true);
    expect(access.defaultConsole).toBe('/admin');
  });

  it('fails closed while enabled capabilities are not ready', () => {
    const access = createAuthorizationAdapter({
      capabilityNavigationEnabled: true,
      status: 'error',
      snapshot: null,
      legacyUser: legacyAdmin,
      activeSpaceRole: 'owner',
      activeSpaceId: 'space-1',
    });

    expect(access.has('platform.access')).toBe(false);
    expect(access.hasAny(['platform.access', 'workspace.manage'])).toBe(false);
    expect(access.defaultConsole).toBe('/chat');
  });

  it('rejects unsafe server default console paths', () => {
    const access = createAuthorizationAdapter({
      capabilityNavigationEnabled: true,
      status: 'ready',
      snapshot: { ...workspaceSnapshot, default_console: '//untrusted.example' },
      legacyUser: legacyAdmin,
      activeSpaceRole: 'owner',
      activeSpaceId: 'space-1',
    });

    expect(access.defaultConsole).toBe('/chat');
  });

  it('keeps global capabilities but denies workspace-bound capabilities for a revoked active space', () => {
    const access = createAuthorizationAdapter({
      capabilityNavigationEnabled: true,
      status: 'ready',
      snapshot: {
        ...workspaceSnapshot,
        scopes: { ...workspaceSnapshot.scopes, platform: true, space_ids: [] },
        capabilities: [
          'platform.access',
          'governance.access',
          'chat.ask',
          'workspace.manage',
          'knowledge.read',
        ],
        default_console: '/platform-admin',
      },
      legacyUser: legacyAdmin,
      activeSpaceRole: 'owner',
      activeSpaceId: 'revoked-space',
    });

    expect(access.has('platform.access')).toBe(true);
    expect(access.has('governance.access')).toBe(true);
    expect(access.has('chat.ask')).toBe(false);
    expect(access.has('workspace.manage')).toBe(false);
    expect(access.has('knowledge.read')).toBe(false);
  });

  it('fails workspace-bound capabilities closed until an active space is selected', () => {
    const access = createAuthorizationAdapter({
      capabilityNavigationEnabled: true,
      status: 'ready',
      snapshot: {
        ...workspaceSnapshot,
        scopes: { ...workspaceSnapshot.scopes, platform: true },
        capabilities: [
          'platform.access',
          'governance.access',
          'chat.ask',
          'workspace.manage',
          'knowledge.read',
        ],
        default_console: '/platform-admin',
      },
      legacyUser: legacyAdmin,
      activeSpaceRole: null,
      activeSpaceId: null,
    });

    expect(access.has('platform.access')).toBe(true);
    expect(access.has('governance.access')).toBe(true);
    expect(access.has('chat.ask')).toBe(false);
    expect(access.has('workspace.manage')).toBe(false);
    expect(access.has('knowledge.read')).toBe(false);
  });
});
