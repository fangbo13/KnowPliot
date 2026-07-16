// @vitest-environment jsdom

import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { scopedConsoleApi } from '../../api/scopedConsole';
import AccessRequestsPage from './AccessRequestsPage';
import ConsoleOverviewPage from './ConsoleOverviewPage';
import ConsolePlaceholderPage from './ConsolePlaceholderPage';
import ScopedAuditPage from './ScopedAuditPage';
import ScopedMetricsPage from './ScopedMetricsPage';

vi.mock('../../api/scopedConsole', () => ({
  scopedConsoleApi: {
    metrics: vi.fn(),
    audit: vi.fn(),
    accessRequests: vi.fn(),
  },
}));

describe('scoped console pages', () => {
  beforeEach(() => {
    vi.mocked(scopedConsoleApi.metrics).mockReset().mockResolvedValue({
      users: { total: 2, active: 1 },
      usage: { sessions: 3, questions: 4, citations: 5 },
      documents: { total: 6, processing: 0, failed: 0, stale: 0, expiring: 0 },
      quality: { average_response_time_ms: 120, no_evidence_rate: 0, citation_coverage_rate: 1 },
      model_api: { calls: 1, failures: 0, error_rate: 0, total_tokens: 20, average_tokens: 20, by_model: [] },
      knowledge_quality: { unused_documents: 0, high_usage_documents: 0, stale_cited_documents: 0 },
      security: { permission_denied: 0 },
    });
    vi.mocked(scopedConsoleApi.audit).mockReset().mockResolvedValue([]);
    vi.mocked(scopedConsoleApi.accessRequests).mockReset().mockResolvedValue([]);
  });

  afterEach(cleanup);

  it('loads metrics through the server-scoped metric source', async () => {
    render(<ScopedMetricsPage />);
    await waitFor(() => expect(scopedConsoleApi.metrics).toHaveBeenCalledTimes(1));
  });

  it('qualifies workspace audit by the route space id', async () => {
    render(<ScopedAuditPage spaceId="space-1" />);
    await waitFor(() => expect(scopedConsoleApi.audit).toHaveBeenCalledWith({ space: 'space-1' }));
  });

  it('loads access requests only from the route workspace resource', async () => {
    render(
      <MemoryRouter
        initialEntries={['/workspace/space-1/manage/access']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/workspace/:spaceId/manage/access" element={<AccessRequestsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(scopedConsoleApi.accessRequests).toHaveBeenCalledWith('space-1'));
  });

  it('renders honest overview and pending-surface copy without loading data', () => {
    const view = render(
      <ConsoleOverviewPage title="Governance" description="Scoped work only" />,
    );
    expect(view.getByRole('heading', { name: 'Governance' })).toBeTruthy();
    view.unmount();

    render(<ConsolePlaceholderPage title="Model binding" />);
    expect(document.body.textContent).toContain('Model binding');
  });
});
