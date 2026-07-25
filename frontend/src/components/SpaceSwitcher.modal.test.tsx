// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAuthorization } from '../auth/CapabilityProvider';
import SpaceSwitcher from './SpaceSwitcher';

const mocks = vi.hoisted(() => {
  const spaceState = {
    spaces: [
      { id: 'space-1', name: 'One', status: 'active', my_role: 'member' },
      { id: 'space-2', name: 'Two', status: 'active', my_role: 'member' },
    ],
    activeSpaceId: 'space-1',
    setActiveSpace: vi.fn(),
    joinByCode: vi.fn(),
    createSpace: vi.fn(),
  };
  const mockNavigate = vi.fn();
  return { spaceState, mockNavigate };
});

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('../auth/CapabilityProvider', () => ({
  useAuthorization: vi.fn(),
  useCapabilities: () => ({
    snapshot: { feature_availability: { workspace_join_v2: true } },
  }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => mocks.mockNavigate,
}));

vi.mock('../store/spaceStore', () => ({
  useSpaceStore: () => mocks.spaceState,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function openJoinModal() {
  render(<SpaceSwitcher />);
  fireEvent.click(screen.getByRole('button', { name: 'switch_space' }));
  fireEvent.click(await screen.findByText('join_space'));
  return screen.findByRole('dialog');
}

describe('SpaceSwitcher modal lifecycle', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      unobserve() {}
      disconnect() {}
    });
  });

  beforeEach(() => {
    vi.mocked(useAuthorization).mockReturnValue({
      enabled: true,
      status: 'ready',
      snapshot: null,
      has: () => true,
      hasAny: () => true,
      hasAll: () => true,
      defaultConsole: '/chat',
    });
    mocks.spaceState.setActiveSpace.mockReset();
    mocks.spaceState.joinByCode.mockReset();
    mocks.spaceState.createSpace.mockReset();
    mocks.mockNavigate.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it.each([
    ['close icon', (dialog: HTMLElement) => fireEvent.click(dialog.querySelector('.ant-modal-close') as HTMLElement)],
    ['cancel button', (_dialog: HTMLElement) => fireEvent.click(screen.getByRole('button', { name: /^Cancel$/i }))],
    ['escape key', () => fireEvent.keyDown(document, { key: 'Escape' })],
    ['mask click', () => fireEvent.click(document.querySelector('.ant-modal-mask') as HTMLElement)],
  ])('closes the idle join modal through the %s path and clears the secret', async (_label, close) => {
    const dialog = await openJoinModal();
    const input = screen.getByPlaceholderText('access_code') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'one-time-secret' } });
    expect(input.value).toBe('one-time-secret');

    close(dialog);

    await waitFor(() => expect(screen.queryByPlaceholderText('access_code')).toBeNull());
    expect(screen.queryByText('one-time-secret')).toBeNull();
  });

  it('closes immediately while join is pending, sends one request, and ignores late success', async () => {
    const request = deferred<{ id: string; name: string }>();
    mocks.spaceState.joinByCode.mockReturnValue(request.promise);
    const dialog = await openJoinModal();
    fireEvent.change(screen.getByPlaceholderText('access_code'), { target: { value: 'pending-code' } });
    fireEvent.click(screen.getByRole('button', { name: 'join' }));
    fireEvent.click(dialog.querySelector('.ant-modal-close') as HTMLElement);

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(mocks.spaceState.joinByCode).toHaveBeenCalledTimes(1);
    expect(mocks.spaceState.setActiveSpace).not.toHaveBeenCalled();

    request.resolve({ id: 'space-2', name: 'Two' });
    await request.promise;
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.queryByText('space_join_success')).toBeNull();
    expect(mocks.spaceState.setActiveSpace).not.toHaveBeenCalled();
  });

  it('detaches a late join error without reopening the modal or writing an error state', async () => {
    const request = deferred<{ id: string; name: string }>();
    mocks.spaceState.joinByCode.mockReturnValue(request.promise);
    await openJoinModal();
    fireEvent.change(screen.getByPlaceholderText('access_code'), { target: { value: 'late-error' } });
    fireEvent.click(screen.getByRole('button', { name: 'join' }));
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());

    request.reject(new Error('network'));
    await request.promise.catch(() => undefined);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.queryByText('space_join_failed')).toBeNull();
  });

  it('routes creation through the governed request page without directly creating a space', async () => {
    render(<SpaceSwitcher />);
    fireEvent.click(screen.getByRole('button', { name: 'switch_space' }));
    fireEvent.click(await screen.findByText('create_space'));

    expect(mocks.mockNavigate).toHaveBeenCalledWith('/spaces/create');
    expect(mocks.spaceState.createSpace).not.toHaveBeenCalled();
    expect(screen.queryByPlaceholderText('space_name')).toBeNull();
  });
});
