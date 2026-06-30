/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin-console API client. Reuses existing rbac/audit endpoints and the
// new V7 governance endpoints under /admin/.
import apiClient from './client';

export interface AdminUser {
  id: string;
  email: string;
  username: string;
  service_line: string | null;
  role_level: string | null;
  is_hr_admin: boolean;
  roles: string[];
  is_active: boolean;
}

export interface Role { id: string; name: string; label: string; scope: string; }

export interface AdminCode {
  id: string;
  code_prefix: string;
  grants_role: 'org_admin' | 'business_admin';
  organization: string;
  organization_name: string;
  business_line: string | null;
  business_line_name: string | null;
  expires_at: string | null;
  max_uses: number;
  used_count: number;
  status: 'active' | 'revoked';
  created_at: string;
  code?: string; // plaintext, only on create
}

export interface Organization { id: string; name: string; slug: string; status: string; }
export interface BusinessLine { id: string; organization: string; name: string; code: string; description: string; status: string; }

export interface Announcement {
  id: string;
  title: string;
  body: string;
  level: string;
  audience: 'all' | 'org' | 'business_line' | 'role';
  audience_ref: string;
  version: string;
  is_active: boolean;
  published_at: string | null;
  created_at: string;
}

export interface AuditLog {
  id: string;
  user_email?: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  role_used: string;
  created_at: string;
}

const unwrap = (data: any) => (Array.isArray(data) ? data : data.results ?? []);

export const adminApi = {
  // ── Users & roles (existing rbac endpoints) ──
  async users(): Promise<AdminUser[]> {
    const { data } = await apiClient.get('/rbac/users/');
    return unwrap(data);
  },
  async roles(): Promise<Role[]> {
    const { data } = await apiClient.get('/rbac/roles/');
    return unwrap(data);
  },
  async assignRole(userId: string, roleName: string): Promise<void> {
    await apiClient.post('/rbac/user-roles/', { user_id: userId, role_name: roleName });
  },
  async revokeRole(userRoleId: string): Promise<void> {
    await apiClient.delete(`/rbac/user-roles/${userRoleId}/`);
  },
  async userRoles(userId: string): Promise<Array<{ id: string; role_name: string }>> {
    const { data } = await apiClient.get('/rbac/user-roles/', { params: { user: userId } });
    return unwrap(data);
  },
  async activateUser(userId: string): Promise<void> {
    await apiClient.post(`/rbac/users/${userId}/activate/`, {});
  },
  async deactivateUser(userId: string): Promise<void> {
    await apiClient.post(`/rbac/users/${userId}/deactivate/`, {});
  },

  // ── Admin registration codes (V7) ──
  async codes(): Promise<AdminCode[]> {
    const { data } = await apiClient.get('/admin/registration-codes/');
    return unwrap(data);
  },
  async createCode(body: {
    grants_role: 'org_admin' | 'business_admin';
    organization: string;
    business_line?: string | null;
    max_uses?: number;
    expires_at?: string | null;
  }): Promise<AdminCode> {
    const { data } = await apiClient.post('/admin/registration-codes/', body);
    return data;
  },
  async revokeCode(id: string): Promise<void> {
    await apiClient.post(`/admin/registration-codes/${id}/revoke/`, {});
  },

  // ── Organizations & business lines (V7) ──
  async organizations(): Promise<Organization[]> {
    const { data } = await apiClient.get('/admin/organizations/');
    return unwrap(data);
  },
  async businessLines(orgId?: string): Promise<BusinessLine[]> {
    const { data } = await apiClient.get('/admin/business-lines/', {
      params: orgId ? { organization: orgId } : {},
    });
    return unwrap(data);
  },
  async createBusinessLine(body: { organization: string; name: string; code: string; description?: string }): Promise<BusinessLine> {
    const { data } = await apiClient.post('/admin/business-lines/', body);
    return data;
  },

  // ── Announcements (V7) ──
  async announcements(): Promise<Announcement[]> {
    const { data } = await apiClient.get('/notifications/announcements/');
    return unwrap(data);
  },
  async createAnnouncement(body: {
    title: string; body: string; level?: string;
    audience: string; audience_ref?: string; version?: string;
  }): Promise<Announcement> {
    const { data } = await apiClient.post('/notifications/announcements/', body);
    return data;
  },

  // ── Audit logs (existing endpoint) ──
  async auditLogs(params?: { action?: string }): Promise<AuditLog[]> {
    const { data } = await apiClient.get('/audit/logs/', { params });
    return unwrap(data);
  },
};
