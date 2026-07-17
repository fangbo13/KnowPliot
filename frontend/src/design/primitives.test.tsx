// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ActionBar,
  AppShell,
  ConfirmDialog,
  EmptyState,
  PageHeader,
  Status,
  Surface,
} from './primitives';

describe('design primitives', () => {
  beforeEach(() => {
    const getComputedStyle = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element) => getComputedStyle(element));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('provides semantic shells and stable page structure', () => {
    render(
      <AppShell width="management" aria-label="Workspace content">
        <PageHeader title="Knowledge" description="Manage approved sources." />
        <Surface as="section" aria-label="Sources">Rows</Surface>
      </AppShell>,
    );

    expect(
      screen.getByRole('main', { name: 'Workspace content' }).classList.contains(
        'kp-app-shell--management',
      ),
    ).toBe(true);
    expect(screen.getByRole('heading', { name: 'Knowledge', level: 1 })).toBeTruthy();
    expect(
      screen.getByRole('region', { name: 'Sources' }).classList.contains('hover-lift'),
    ).toBe(false);
  });

  it('keeps empty and status states understandable without color', () => {
    render(
      <>
        <EmptyState title="No conversations" body="Start a new conversation." />
        <Status tone="warning">Review required</Status>
      </>,
    );

    expect(screen.getByRole('heading', { name: 'No conversations' })).toBeTruthy();
    expect(screen.getByText('Review required').parentElement?.getAttribute('data-tone')).toBe('warning');
  });

  it('orders responsive actions and uses async-safe confirmation', async () => {
    const onConfirm = vi.fn(() => new Promise<void>(() => undefined));
    render(
      <>
        <ActionBar
          primary={<button>Save</button>}
          secondary={<button>Cancel</button>}
          destructive={<button>Delete</button>}
        />
        <ConfirmDialog
          open
          title="Delete conversation?"
          description="This action cannot be undone."
          confirmLabel="Delete"
          cancelLabel="Cancel"
          destructive
          onConfirm={onConfirm}
          onCancel={vi.fn()}
        />
      </>,
    );

    expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy();
    const dialog = within(screen.getByRole('dialog'));
    fireEvent.click(dialog.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(dialog.getByRole<HTMLButtonElement>('button', { name: /Delete/ }).disabled).toBe(true);
  });
});
