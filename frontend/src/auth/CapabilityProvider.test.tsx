// @vitest-environment jsdom

import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { capabilitiesApi, type CapabilitySnapshot } from '../api/capabilities';
import { CapabilityProvider, useCapabilities } from './CapabilityProvider';

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

  it('keeps the compatibility mode ready without calling the capability endpoint', () => {
    render(
      <CapabilityProvider enabled={false}>
        <Probe />
      </CapabilityProvider>,
    );

    expect(screen.getByTestId('status').textContent).toBe('ready');
    expect(capabilitiesApi.me).not.toHaveBeenCalled();
  });
});
