import { afterEach, describe, expect, it, vi } from 'vitest';

import apiClient from '../client';
import {
  workspaceCreationApi,
  type WorkspaceCreationImpact,
  type WorkspaceCreationRequest,
  type WorkspaceCreationSubmission,
} from '../workspaceCreation';

const submission: WorkspaceCreationSubmission = {
  name: 'Assurance methodology',
  code: 'assurance-methodology',
  purpose: 'Bounded methodology knowledge',
  visibility: 'private',
  business_line_id: 'line-1',
  work_group_id: 'group-1',
  office_location_ids: ['office-1'],
  template_version_id: null,
};

const request: WorkspaceCreationRequest = {
  request_id: 'request-1',
  status: 'pending',
  request_version: 3,
  expires_at: null,
  submitted: submission,
};

describe('governed workspace creation API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('submits the complete governed payload with an idempotency key', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: request });

    await workspaceCreationApi.submit(submission);

    expect(post).toHaveBeenCalledWith('/spaces/creation-requests/', submission, {
      headers: { 'Idempotency-Key': expect.any(String) },
    });
  });

  it('loads only pending workspace-create requests for platform review', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { results: [request], next_cursor: null } });

    await workspaceCreationApi.reviewQueue();

    expect(get).toHaveBeenCalledWith('/admin/governed-requests/', {
      params: { action: 'workspace_create', status: 'pending' },
    });
  });

  it('approves using the exact request version, impact version, owner acknowledgement, and idempotency', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { ...request, status: 'completed' } });
    const impact: WorkspaceCreationImpact = {
      request_id: request.request_id,
      impact_version: 'impact-v5',
      impact_revision: 5,
      impact_expires_at: null,
      impact: {},
    };

    await workspaceCreationApi.approve(request, impact);

    expect(post).toHaveBeenCalledWith(
      '/admin/governed-requests/request-1/approve/',
      {
        expected_request_version: 3,
        impact_version: 'impact-v5',
        acknowledge_requester_becomes_owner: true,
      },
      { headers: { 'Idempotency-Key': expect.any(String) } },
    );
  });

  it('cancels and rejects with server-authored request versions', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: request });

    await workspaceCreationApi.cancel(request);
    await workspaceCreationApi.reject(request, 'scope_not_approved', 'Outside beta scope');

    expect(post).toHaveBeenNthCalledWith(
      1,
      '/spaces/creation-requests/request-1/cancel/',
      { expected_request_version: 3 },
      { headers: { 'Idempotency-Key': expect.any(String) } },
    );
    expect(post).toHaveBeenNthCalledWith(
      2,
      '/admin/governed-requests/request-1/reject/',
      {
        expected_request_version: 3,
        reason_code: 'scope_not_approved',
        reason_text: 'Outside beta scope',
      },
      { headers: { 'Idempotency-Key': expect.any(String) } },
    );
  });
});
