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
  it('provides a knowledge shortcut when the user can read and has an active space', () => {
    const entries = buildManagementEntries(
      access(['knowledge.read']),
      'space-1',
    );

    expect(entries).toEqual([
      { id: 'knowledge', label: 'Knowledge base', to: '/knowledge' },
    ]);
  });

  it('returns no privileged entry for an unprivileged capability set', () => {
    expect(buildManagementEntries(access(['unknown.cap']), 'space-1')).toEqual([]);
  });

  it('adds a reference-libraries shortcut for users who can ask', () => {
    const entries = buildManagementEntries(
      access(['knowledge.read', 'chat.ask']),
      'space-1',
    );

    expect(entries).toEqual([
      { id: 'knowledge', label: 'Knowledge base', to: '/knowledge' },
      { id: 'reference-libraries', label: 'Reference libraries', to: '/reference-libraries' },
    ]);
  });

  it('omits knowledge when no active space is set', () => {
    expect(buildManagementEntries(access(['knowledge.read', 'chat.ask']), null)).toEqual([
      { id: 'reference-libraries', label: 'Reference libraries', to: '/reference-libraries' },
    ]);
  });
});
