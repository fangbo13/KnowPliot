// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { capabilitiesApi, type CapabilitySnapshot } from '../api/capabilities';
import { CapabilityProvider, useAuthorization, useCapabilities } from './CapabilityProvider';

const authState: { user: { id: string } | null } = { user: { id: 'user-1' } };
const spaceState = { activeSpaceId: 'space-1' as string | null, spaces: [] };

vi.mock('./AuthProvider', () => ({
  useAuth: () => authState,
}));

vi.mock('../store/spaceStore', () => ({
  useSpaceStore: (selector: (state: typeof spaceState) => unknown) => selector(spaceState),
}));

vi.mock('../api/capabilities', async () => {
  const actual = await vi.importActual('../api/capabilities');
  return {
    ...actual,
    capabilitiesApi: { me: vi.fn() },
  };
});

const snapshot = (
  defaultConsole: string,
  capabilities: CapabilitySnapshot['capabilities'] = ['chat.ask'],
): CapabilitySnapshot => ({
  navigation_mode: 'capability',
  configuration_revision: 'config-v3',
  feature_availability: {
    deep: true,
    thinking: false,
    workspace_creation_approval: true,
    workspace_join_v2: true,
    workspace_permanent_delete: false,
  },
  scopes: {
    platform: false,
    organization_ids: [],
    business_line_ids: [],
    space_ids: ['space-1', 'space-2'],
  },
  capabilities,
  default_console: defaultConsole,
});

function Probe() {
  const state = useCapabilities();
  return (
    <div>
      <span data-testid="status">{state.status}</span>
      <span data-testid="console">{state.snapshot?.default_console ?? ''}</span>
      <span data-testid="error">{state.errorCode ?? ''}</span>
      <span data-testid="mode">{state.snapshot?.navigation_mode ?? ''}</span>
    </div>
  );
}

function AuthorizationProbe() {
  const access = useAuthorization();
  return (
    <div>
      <span data-testid="platform-capability">{String(access.has('platform.access'))}</span>
      <span data-testid="governance-capability">{String(access.has('governance.access'))}</span>
      <span data-testid="chat-capability">{String(access.has('chat.ask'))}</span>
      <span data-testid="workspace-capability">{String(access.has('workspace.manage'))}</span>
    </div>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('CapabilityProvider', () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.mocked(capabilitiesApi.me).mockReset();
    authState.user = { id: 'user-1' };
    spaceState.activeSpaceId = 'space-1';
  });

  it('publishes loading then ready for the authenticated user and active space', async () => {
    vi.mocked(capabilitiesApi.me).mockResolvedValue(
      snapshot('/workspace/space-1/manage', ['workspace.manage']),
    );

    render(
      <CapabilityProvider enabled>
        <Probe />
      </CapabilityProvider>,
    );

    expect(screen.getByTestId('status').textContent).toBe('loading');
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('ready'));
    expect(screen.getByTestId('console').textContent).toBe('/workspace/space-1/manage');
    expect(capabilitiesApi.me).toHaveBeenCalledWith('space-1', expect.any(AbortSignal));
  });

  it('aborts and discards an older space response', async () => {
    const first = deferred<CapabilitySnapshot>();
    const second = deferred<CapabilitySnapshot>();
    vi.mocked(capabilitiesApi.me)
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const view = render(
      <CapabilityProvider enabled>
        <Probe />
      </CapabilityProvider>,
    );
    const firstSignal = vi.mocked(capabilitiesApi.me).mock.calls[0][1]!;

    spaceState.activeSpaceId = 'space-2';
    view.rerender(
      <CapabilityProvider enabled>
        <Probe />
      </CapabilityProvider>,
    );

    expect(firstSignal.aborted).toBe(true);
    await act(async () => second.resolve(snapshot('/workspace/space-2/manage')));
    await waitFor(() => expect(screen.getByTestId('console').textContent).toBe('/workspace/space-2/manage'));

    await act(async () => first.resolve(snapshot('/workspace/space-1/manage')));
    expect(screen.getByTestId('console').textContent).toBe('/workspace/space-2/manage');
  });

  it('refreshes when the authenticated user changes', async () => {
    vi.mocked(capabilitiesApi.me)
      .mockResolvedValueOnce(snapshot('/governance'))
      .mockResolvedValueOnce(snapshot('/platform-admin'));
    const view = render(
      <CapabilityProvider enabled>
        <Probe />
      </CapabilityProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('console').textContent).toBe('/governance'));

    authState.user = { id: 'user-2' };
    view.rerender(
      <CapabilityProvider enabled>
        <Probe />
      </CapabilityProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('console').textContent).toBe('/platform-admin'));
    expect(capabilitiesApi.me).toHaveBeenCalledTimes(2);
  });

  it.each([403, 404])('uses an explicit denied state for non-disclosing %s responses', async (status) => {
    vi.mocked(capabilitiesApi.me).mockRejectedValue({ response: { status } });

    render(
      <CapabilityProvider enabled>
        <Probe />
      </CapabilityProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('denied'));
    expect(screen.getByTestId('error').textContent).toBe('capability_denied');
  });

  it.each([
    [true, 'legacy'],
    [false, 'capability'],
  ] as const)(
    'reports one bounded mismatch for build=%s and server=%s without a second bootstrap',
    async (enabled, serverMode) => {
      vi.mocked(capabilitiesApi.me).mockResolvedValue({
        ...snapshot('/chat'),
        navigation_mode: serverMode,
      });

      render(
        <CapabilityProvider enabled={enabled}>
          <Probe />
        </CapabilityProvider>,
      );

      await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('mismatch'));
      expect(screen.getByTestId('error').textContent).toBe('navigation_mode_mismatch');
      expect(capabilitiesApi.me).toHaveBeenCalledTimes(1);
    },
  );

  it('falls back to an unscoped snapshot for a revoked persisted workspace', async () => {
    spaceState.activeSpaceId = 'revoked-space';
    const unscoped = {
      ...snapshot('/platform-admin', [
        'platform.access',
        'governance.access',
        'chat.ask',
        'workspace.manage',
      ]),
      scopes: {
        platform: true,
        organization_ids: ['org-1'],
        business_line_ids: [],
        space_ids: [],
      },
    } satisfies CapabilitySnapshot;
    vi.mocked(capabilitiesApi.me).mockImplementation((spaceId) => {
      if (spaceId === 'revoked-space') {
        return Promise.reject({ response: { status: 404 } });
      }
      return Promise.resolve(unscoped);
    });

    render(
      <CapabilityProvider enabled>
        <Probe />
        <AuthorizationProbe />
      </CapabilityProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('ready'));
    expect(capabilitiesApi.me).toHaveBeenNthCalledWith(
      1,
      'revoked-space',
      expect.any(AbortSignal),
    );
    expect(capabilitiesApi.me).toHaveBeenNthCalledWith(
      2,
      null,
      expect.any(AbortSignal),
    );
    expect(screen.getByTestId('platform-capability').textContent).toBe('true');
    expect(screen.getByTestId('governance-capability').textContent).toBe('true');
    expect(screen.getByTestId('chat-capability').textContent).toBe('false');
    expect(screen.getByTestId('workspace-capability').textContent).toBe('false');
  });

  it('bootstraps exact capabilities once in paired legacy mode', async () => {
    vi.mocked(capabilitiesApi.me).mockResolvedValue({
      ...snapshot('/admin'),
      navigation_mode: 'legacy',
    });

    render(
      <CapabilityProvider enabled={false}>
        <Probe />
      </CapabilityProvider>,
    );

    expect(screen.getByTestId('status').textContent).toBe('loading');
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('ready'));
    expect(screen.getByTestId('mode').textContent).toBe('legacy');
    expect(capabilitiesApi.me).toHaveBeenCalledTimes(1);
  });
});
