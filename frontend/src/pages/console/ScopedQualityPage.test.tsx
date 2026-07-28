// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { adminApi } from '../../api/admin';
import type { Capability } from '../../api/capabilities';
import type { AuthorizationAdapter } from '../../auth/authorization';
import { useAuthorization } from '../../auth/CapabilityProvider';
import ScopedQualityPage from './ScopedQualityPage';

vi.mock('../../api/admin', () => ({
  adminApi: {
    feedbackReviews: vi.fn(),
    claimFeedback: vi.fn(),
    resolveFeedback: vi.fn(),
  },
}));

vi.mock('../../auth/CapabilityProvider', () => ({ useAuthorization: vi.fn() }));

const makeAccess = (canReview: boolean): AuthorizationAdapter => ({
  enabled: true,
  status: 'ready' as const,
  snapshot: null,
  has: (capability: Capability) => capability === 'quality.read' || (canReview && capability === 'quality.review'),
  hasAny: (capabilities: readonly Capability[]) => capabilities.some((capability) => capability === 'quality.read' || (canReview && capability === 'quality.review')),
  hasAll: (capabilities: readonly Capability[]) => capabilities.every((capability) => capability === 'quality.read' || (canReview && capability === 'quality.review')),
  defaultConsole: '/workspace/space-1/manage',
});

describe('ScopedQualityPage', () => {
  beforeEach(() => {
    vi.mocked(adminApi.feedbackReviews).mockReset().mockResolvedValue([{
      id: 'review-1',
      space: 'space-1',
      message: 'message-1',
      user: 'user-1',
      feedback_type: 'incorrect',
      comment: 'Needs review',
      suggested_source: '',
      flag_for_review: true,
      status: 'submitted',
      reviewer: null,
      resolution_code: '',
      resolution_notes: '',
      review_context: {},
      created_at: '2026-07-17T00:00:00Z',
      updated_at: '2026-07-17T00:00:00Z',
    }]);
  });

  afterEach(cleanup);

  function renderPage() {
    return render(
      <MemoryRouter
        initialEntries={['/workspace/space-1/manage/quality']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/workspace/:spaceId/manage/quality" element={<ScopedQualityPage />} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('uses a workspace-qualified data source and hides mutations without quality.review', async () => {
    vi.mocked(useAuthorization).mockReturnValue(makeAccess(false));
    renderPage();

    await waitFor(() => expect(adminApi.feedbackReviews).toHaveBeenCalledWith({ space: 'space-1' }));
    expect(screen.queryByRole('button', { name: 'quality_claim' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'quality_resolve' })).toBeNull();
  });

  it('shows review mutations only with quality.review', async () => {
    vi.mocked(useAuthorization).mockReturnValue(makeAccess(true));
    renderPage();

    await waitFor(() => expect(screen.getByRole('button', { name: 'quality_claim' })).toBeTruthy());
    expect(screen.getByRole('button', { name: 'quality_resolve' })).toBeTruthy();
  });
});
