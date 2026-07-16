/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import type { AuditLog, AuditLogQuery, SystemMetrics } from './admin';
import apiClient from './client';

export interface ScopedConsoleUser {
  id: string;
  email: string;
  is_active: boolean;
}

export interface SpaceAccessRequest {
  id: string;
  user: string;
  user_email?: string;
  reason: string;
  status: 'pending' | 'approved' | 'rejected' | 'cancelled';
  created_at: string;
}

const unwrap = <T>(data: T[] | { results?: T[] }): T[] =>
  Array.isArray(data) ? data : data.results ?? [];

export const scopedConsoleApi = {
  async users(query = ''): Promise<ScopedConsoleUser[]> {
    const { data } = await apiClient.get('/admin/users/', {
      params: query ? { q: query } : {},
    });
    return unwrap<ScopedConsoleUser>(data);
  },

  async metrics(): Promise<SystemMetrics> {
    const { data } = await apiClient.get('/admin/metrics/');
    return data;
  },

  async audit(params: AuditLogQuery = {}): Promise<AuditLog[]> {
    const { data } = await apiClient.get('/audit/logs/', { params });
    return unwrap<AuditLog>(data);
  },

  async accessRequests(spaceId: string): Promise<SpaceAccessRequest[]> {
    const { data } = await apiClient.get(
      `/admin/spaces/${spaceId}/access-requests/`,
    );
    return unwrap<SpaceAccessRequest>(data);
  },
};
