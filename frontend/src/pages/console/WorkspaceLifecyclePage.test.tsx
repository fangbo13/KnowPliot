// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import {
  spacesApi,
  type KnowledgeSpace,
  type WorkspaceDeletionImpact,
  type WorkspaceDeletionRequest,
} from '../../api/spaces';
import WorkspaceLifecyclePage from './WorkspaceLifecyclePage';

vi.mock('../../api/spaces', () => ({
  spacesApi: {
    get: vi.fn(),
    ownership: vi.fn(),
    ownershipCandidatePage: vi.fn(),
    deletionImpact: vi.fn(),
    deletionStatus: vi.fn(),
    submitDeletion: vi.fn(),
    confirmDeletion: vi.fn(),
    cancelDeletion: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
    clone: vi.fn(),
    transfer: vi.fn(),
    requestOwnershipTransfer: vi.fn(),
    forceOwnershipTransfer: vi.fn(),
  },
}));

const refresh = vi.fn();
vi.mock('../../auth/CapabilityProvider', () => ({
  useCapabilities: () => ({
    refresh,
    snapshot: { feature_availability: { workspace_permanent_delete: true } },
  }),
  useAuthorization: () => ({
    has: (capability: string) => capability === 'workspace.delete.permanent',
  }),
}));

const space: KnowledgeSpace = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Assurance hub',
  code: 'assurance-hub',
  description: '',
  icon: '',
  language: 'en',
  visibility: 'private',
  status: 'archived',
  organization: '22222222-2222-4222-8222-222222222222',
  organization_name: 'Assurance',
  business_line: null,
  business_line_name: null,
  my_role: 'owner',
  member_count: 1,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-07-18T00:00:00Z',
};

const pendingRequest: WorkspaceDeletionRequest = {
  request_id: '33333333-3333-4333-8333-333333333333',
  status: 'pending',
  request_version: 1,
  status_url: '/spaces/deletion-requests/33333333-3333-4333-8333-333333333333/',
};

const impact: WorkspaceDeletionImpact = {
  space_id: space.id,
  lifecycle_status: 'archived',
  expected_lifecycle_version: 2,
  expected_ownership_version: 1,
  confirmation_phrase: 'assurance/assurance-hub',
  impact_version: 'a'.repeat(64),
  impact_expires_at: '2026-07-18T00:05:00Z',
  counts: { eligible_content: 12, retained_evidence: 4 },
  blockers: [],
  earliest_purge_at: '2026-08-17T00:00:00Z',
  manifest_digest: 'b'.repeat(64),
  manifest_version: 1,
  retention_dates: [],
  active_request: null,
};

function renderPage() {
  return render(
    <MemoryRouter
      initialEntries={[`/workspace/${space.id}/manage/lifecycle`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <Routes>
        <Route
          path="/workspace/:spaceId/manage/lifecycle"
          element={<WorkspaceLifecyclePage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe('WorkspaceLifecyclePage permanent deletion', () => {
  beforeEach(() => {
    refresh.mockReset();
    vi.mocked(spacesApi.get).mockReset().mockResolvedValue(space);
    vi.mocked(spacesApi.ownership).mockReset().mockResolvedValue({
      owner: { id: 'owner-1', display_name: 'Workspace Owner', is_active: true },
      ownership_version: 1,
      pending_transfer: null,
    });
    vi.mocked(spacesApi.ownershipCandidatePage).mockReset().mockResolvedValue({
      results: [],
      next: null,
    });
    vi.mocked(spacesApi.deletionImpact).mockReset().mockResolvedValue(impact);
    vi.mocked(spacesApi.deletionStatus).mockReset().mockResolvedValue(pendingRequest);
    vi.mocked(spacesApi.submitDeletion).mockReset().mockResolvedValue(pendingRequest);
    vi.mocked(spacesApi.confirmDeletion).mockReset().mockResolvedValue({
      ...pendingRequest,
      status: 'scheduled',
      request_version: 2,
      purge_not_before: '2026-08-17T00:00:00Z',
    });
    vi.mocked(spacesApi.cancelDeletion).mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllTimers();
  });

  it('uses a fresh impact, exact in-memory phrase and explicit acknowledgement', async () => {
    renderPage();
    const requestButton = await screen.findByRole('button', {
      name: 'request_permanent_deletion',
    });
    expect(screen.queryByText('copy_documents')).toBeNull();
    fireEvent.click(requestButton);

    await waitFor(() =>
      expect(spacesApi.submitDeletion).toHaveBeenCalledWith(space.id, impact),
    );
    const phraseInput = await screen.findByLabelText(
      'deletion_confirmation_phrase',
    );
    const schedule = screen.getByRole('button', { name: 'schedule_permanent_deletion' });
    expect((schedule as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(phraseInput, { target: { value: 'Assurance/assurance-hub' } });
    fireEvent.click(screen.getByRole('checkbox'));
    expect((schedule as HTMLButtonElement).disabled).toBe(true);

    fireEvent.change(phraseInput, { target: { value: impact.confirmation_phrase } });
    expect((schedule as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(schedule);

    await waitFor(() =>
      expect(spacesApi.confirmDeletion).toHaveBeenCalledWith(
        space.id,
        pendingRequest,
        impact,
        impact.confirmation_phrase,
      ),
    );
  });

  it('shows safe blockers and does not offer a deletion request', async () => {
    vi.mocked(spacesApi.deletionImpact).mockResolvedValue({
      ...impact,
      blockers: [
        {
          kind: 'active_shares',
          id: 'opaque-share',
          status: 'active',
          remediation_route: '',
        },
      ],
    });
    renderPage();
    expect(await screen.findByText('deletion_blocker_active_shares')).toBeTruthy();
    expect(
      (screen.getByRole('button', {
        name: 'request_permanent_deletion',
      }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
