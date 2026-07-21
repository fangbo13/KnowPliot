/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import apiClient, { coalescedGet, getRequestSignal } from './client';

export type WorkspaceCreationStatus =
  | 'pending'
  | 'completed'
  | 'rejected'
  | 'cancelled'
  | 'expired'
  | 'invalidated'
  | 'failed';

export interface TaxonomyOption {
  id: string;
  parent_id: string;
  normalized_code: string;
  display_name: string;
  description: string;
  active: boolean;
  sort_order?: number;
  version: number;
}

export interface WorkspaceCreationSubmission {
  name: string;
  code: string;
  purpose: string;
  visibility: 'private' | 'business_line' | 'organization' | 'public_demo';
  business_line_id: string;
  work_group_id: string;
  office_location_ids: string[];
  template_version_id: string | null;
}

export interface WorkspaceCreationRequest {
  request_id: string;
  status: WorkspaceCreationStatus;
  request_version: number;
  impact_revision?: number;
  impact_version?: string;
  impact_expires_at?: string | null;
  expires_at: string | null;
  requester_uuid?: string;
  scope_type?: string;
  submitted?: WorkspaceCreationSubmission;
  result_uuid?: string;
  failure_code?: string;
  status_url?: string;
  space?: { id: string; provisioning_status: string };
}

export interface WorkspaceCreationImpact {
  request_id: string;
  impact_version: string;
  impact_revision: number;
  impact_expires_at: string | null;
  impact: {
    action_type?: string;
    resources?: Array<Record<string, unknown>>;
    policy_version?: { id?: string; revision?: number };
    [key: string]: unknown;
  };
}

export interface WorkspaceCreationPage {
  results: WorkspaceCreationRequest[];
  next_cursor: string | null;
}

function readConfig(signal?: AbortSignal, params?: object) {
  const effectiveSignal = signal ?? getRequestSignal();
  return {
    ...(params ? { params } : {}),
    ...(effectiveSignal ? { signal: effectiveSignal } : {}),
  };
}

export const workspaceCreationApi = {
  async taxonomy(
    kind: 'business-lines' | 'work-groups' | 'office-locations',
    scopeId?: string,
    signal?: AbortSignal,
  ): Promise<TaxonomyOption[]> {
    const { data } = await coalescedGet<{ results: TaxonomyOption[] }>(
      `/spaces/taxonomy/${kind}/`,
      readConfig(signal, { context: 'creation', ...(scopeId ? { scope_id: scopeId } : {}) }),
    );
    return data.results;
  },

  async submit(body: WorkspaceCreationSubmission, signal?: AbortSignal): Promise<WorkspaceCreationRequest> {
    const { data } = await apiClient.post('/spaces/creation-requests/', body, {
      ...(signal ? { signal } : {}),
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },

  async mine(signal?: AbortSignal): Promise<WorkspaceCreationRequest[]> {
    const { data } = await coalescedGet<WorkspaceCreationPage>(
      '/spaces/creation-requests/mine/',
      readConfig(signal),
    );
    return data.results;
  },

  async detail(requestId: string, signal?: AbortSignal): Promise<WorkspaceCreationRequest> {
    const { data } = await coalescedGet<WorkspaceCreationRequest>(
      `/spaces/creation-requests/${requestId}/`,
      readConfig(signal),
    );
    return data;
  },

  async cancel(request: WorkspaceCreationRequest): Promise<WorkspaceCreationRequest> {
    const { data } = await apiClient.post(
      `/spaces/creation-requests/${request.request_id}/cancel/`,
      { expected_request_version: request.request_version },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async reviewQueue(signal?: AbortSignal): Promise<WorkspaceCreationRequest[]> {
    const { data } = await coalescedGet<WorkspaceCreationPage>(
      '/admin/governed-requests/',
      readConfig(signal, { action: 'workspace_create', status: 'pending' }),
    );
    return data.results;
  },

  async impact(requestId: string, signal?: AbortSignal): Promise<WorkspaceCreationImpact> {
    const { data } = await coalescedGet<WorkspaceCreationImpact>(
      `/admin/governed-requests/${requestId}/impact/`,
      readConfig(signal),
    );
    return data;
  },

  async approve(
    request: WorkspaceCreationRequest,
    impact: WorkspaceCreationImpact,
  ): Promise<WorkspaceCreationRequest> {
    const { data } = await apiClient.post(
      `/admin/governed-requests/${request.request_id}/approve/`,
      {
        expected_request_version: request.request_version,
        impact_version: impact.impact_version,
        acknowledge_requester_becomes_owner: true,
      },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async reject(
    request: WorkspaceCreationRequest,
    reasonCode: string,
    reasonText: string,
  ): Promise<WorkspaceCreationRequest> {
    const { data } = await apiClient.post(
      `/admin/governed-requests/${request.request_id}/reject/`,
      {
        expected_request_version: request.request_version,
        reason_code: reasonCode,
        reason_text: reasonText,
      },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },
};
