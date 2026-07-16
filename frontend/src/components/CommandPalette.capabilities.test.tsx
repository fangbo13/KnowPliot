// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import type { Capability } from '../api/capabilities';
import type { AuthorizationAdapter } from '../auth/authorization';
import { useAuthorization } from '../auth/CapabilityProvider';
import CommandPalette from './CommandPalette';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key }),
}));

vi.mock('../auth/CapabilityProvider', () => ({ useAuthorization: vi.fn() }));

vi.mock('../hooks/useTheme', () => ({
  useTheme: () => ({ effective: 'light', setThemeMode: vi.fn() }),
}));

vi.mock('../store/chatStore', () => {
  const state = {
    sessions: [],
    setActiveSession: vi.fn(),
    resetSession: vi.fn(),
  };
  return { useChatStore: (selector: (value: typeof state) => unknown) => selector(state) };
});

vi.mock('../store/spaceStore', () => {
  const state = {
    spaces: [{ id: 'space-1', name: 'Workspace One' }],
    activeSpaceId: 'space-1',
    setActiveSpace: vi.fn(),
  };
  return { useSpaceStore: (selector: (value: typeof state) => unknown) => selector(state) };
});

function makeAccess(allowed: readonly Capability[]): AuthorizationAdapter {
  const capabilities = new Set(allowed);
  const has = (capability: Capability) => capabilities.has(capability);
  return {
    enabled: true,
    status: 'ready',
    snapshot: null,
    has,
    hasAny: (required) => required.some(has),
    hasAll: (required) => required.every(has),
    defaultConsole: '/governance',
  };
}

describe('CommandPalette capability commands', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
    vi.mocked(useAuthorization).mockReturnValue(makeAccess([]));
  });
  afterEach(cleanup);

  it('derives chat and management destinations only from capabilities', () => {
    vi.mocked(useAuthorization).mockReturnValue(makeAccess([
      'chat.ask',
      'chat.history',
      'governance.access',
      'workspace.manage',
      'knowledge.read',
    ]));

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CommandPalette open onClose={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByText('Management console')).toBeTruthy();
    expect(screen.getByText('Workspace management')).toBeTruthy();
    expect(screen.getByText('Knowledge base')).toBeTruthy();
    expect(screen.getByText('nav_history')).toBeTruthy();
    expect(screen.getByText('sidebar_new_chat')).toBeTruthy();
  });

  it('hides privileged and conversation commands when capabilities deny them', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CommandPalette open onClose={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.queryByText('Management console')).toBeNull();
    expect(screen.queryByText('Workspace management')).toBeNull();
    expect(screen.queryByText('Knowledge base')).toBeNull();
    expect(screen.queryByText('nav_history')).toBeNull();
    expect(screen.queryByText('sidebar_new_chat')).toBeNull();
  });
});
