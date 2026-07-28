import { describe, expect, it } from 'vitest';

import type { AuthorizationAdapter } from './authorization';
import { buildManagementEntries } from './managementEntries';

const access = (allowed: string[], enabled = true): AuthorizationAdapter => ({
  enabled,
  status: 'ready',
  snapshot: null,
  has: (capability) => allowed.includes(capability),
  hasAny: (capabilities) => capabilities.some((capability) => allowed.includes(capability)),
  hasAll: (capabilities) => capabilities.every((capability) => allowed.includes(capability)),
  defaultConsole: enabled ? '/governance' : '/admin',
});

describe('active management surface entries', () => {
  it('collapses capability-mode management into the single hub entry', () => {
    const entries = buildManagementEntries(
      access(['governance.access', 'workspace.manage', 'knowledge.read']),
      'space-1',
    );

    expect(entries).toEqual([
      { id: 'hub', label: 'Management hub', to: '/console' },
      { id: 'knowledge', label: 'Knowledge base', to: '/workspace/space-1/knowledge' },
    ]);
  });

  it('offers the hub to workspace-only managers as well', () => {
    const entries = buildManagementEntries(access(['workspace.manage']), 'space-1');
    expect(entries).toEqual([
      { id: 'hub', label: 'Management hub', to: '/console' },
    ]);
  });

  it('preserves one-release legacy destinations only while the flag is disabled', () => {
    const entries = buildManagementEntries(
      access(['governance.access', 'workspace.manage', 'knowledge.read'], false),
      'space-1',
    );

    expect(entries.map((entry) => entry.to)).toEqual([
      '/admin',
      '/spaces/manage',
      '/admin/knowledge',
    ]);
  });

  it('returns no privileged entry for an unprivileged capability set', () => {
    expect(buildManagementEntries(access(['chat.ask']), 'space-1')).toEqual([]);
  });
});
