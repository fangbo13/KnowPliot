/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { AuditLog, AuditLogQuery, SystemMetrics } from './admin';
import apiClient, { coalescedGet, getRequestSignal } from './client';

export interface ScopedConsoleUser {
  id: string;
  email: string;
  is_active: boolean;
}

export interface SpaceAccessRequest {
  id: string;
  space_id: string;
  requester_uuid: string;
  source_kind: 'access_code' | 'discovery';
  reason: string;
  role: 'member' | 'guest';
  role_ceiling: 'member' | 'guest';
  status: 'pending' | 'approved' | 'rejected' | 'cancelled' | 'expired' | 'invalidated';
  request_version: number;
  expires_at: string;
  decision_reason_code: string;
  resulting_membership_uuid: string | null;
}

const unwrap = <T>(data: T[] | { results?: T[] }): T[] =>
  Array.isArray(data)
    ? data
    : Array.isArray(data.results)
      ? data.results
      : (() => { throw new Error('invalid_scoped_console_list_response'); })();

function readConfig(signal?: AbortSignal, params?: object) {
  const effectiveSignal = signal ?? getRequestSignal();
  if (effectiveSignal || params) return { ...(params ? { params } : {}), ...(effectiveSignal ? { signal: effectiveSignal } : {}) };
  return undefined;
}

export const scopedConsoleApi = {
  async users(query = '', signal?: AbortSignal): Promise<ScopedConsoleUser[]> {
    const { data } = await coalescedGet<ScopedConsoleUser[] | { results?: ScopedConsoleUser[] }>(
      '/admin/users/',
      readConfig(signal, query ? { q: query } : {}),
    );
    return unwrap<ScopedConsoleUser>(data);
  },

  async metrics(signal?: AbortSignal): Promise<SystemMetrics> {
    const { data } = await coalescedGet<SystemMetrics>('/admin/metrics/', readConfig(signal));
    return data;
  },

  async audit(params: AuditLogQuery = {}, signal?: AbortSignal): Promise<AuditLog[]> {
    const { data } = await coalescedGet<AuditLog[] | { results?: AuditLog[] }>('/audit/logs/', readConfig(signal, params));
    return unwrap<AuditLog>(data);
  },

  async accessRequests(spaceId: string, signal?: AbortSignal): Promise<SpaceAccessRequest[]> {
    const { data } = await coalescedGet<SpaceAccessRequest[] | { results?: SpaceAccessRequest[] }>(
      `/spaces/${spaceId}/access-requests/`,
      readConfig(signal),
    );
    return unwrap<SpaceAccessRequest>(data);
  },

  async approveAccessRequest(spaceId: string, request: SpaceAccessRequest): Promise<SpaceAccessRequest> {
    const { data } = await apiClient.post(
      `/spaces/${spaceId}/access-requests/${request.id}/approve/`,
      {
        expected_request_version: request.request_version,
        role: request.role_ceiling === 'guest' ? 'guest' : 'member',
      },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async rejectAccessRequest(spaceId: string, request: SpaceAccessRequest, reason: string): Promise<SpaceAccessRequest> {
    const { data } = await apiClient.post(
      `/spaces/${spaceId}/access-requests/${request.id}/reject/`,
      {
        expected_request_version: request.request_version,
        reason_code: 'owner_rejected',
        reason_text: reason,
      },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },
};
