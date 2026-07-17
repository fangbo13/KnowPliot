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
  it('builds command and shell destinations only from capabilities', () => {
    const entries = buildManagementEntries(
      access(['governance.access', 'workspace.manage', 'knowledge.read']),
      'space-1',
    );

    expect(entries).toEqual([
      { id: 'console', label: 'Management console', to: '/governance' },
      { id: 'workspace', label: 'Workspace management', to: '/workspace/space-1/manage' },
      { id: 'knowledge', label: 'Knowledge base', to: '/workspace/space-1/manage/knowledge' },
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
