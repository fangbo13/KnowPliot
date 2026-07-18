/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spaces API client — V6.0 multi-space platform.

import apiClient from './client';

export type SpaceRole =
  | 'super_admin'
  | 'org_admin'
  | 'business_admin'
  | 'owner'
  | 'knowledge_admin'
  | 'reviewer'
  | 'member'
  | 'guest';

export interface KnowledgeSpace {
  id: string;
  name: string;
  code: string;
  description: string;
  icon: string;
  language: string;
  visibility: 'private' | 'business_line' | 'organization' | 'public_demo';
  status: 'active' | 'archived';
  organization: string;
  organization_name: string;
  business_line: string | null;
  business_line_name: string | null;
  my_role: SpaceRole | null;
  member_count: number | null;
  settings?: {
    template_id?: string;
    template_code?: string;
    scenario_type?: string;
    quick_questions?: string[];
    [key: string]: unknown;
  };
  created_at: string;
  updated_at: string;
}

export interface InviteCode {
  id: string;
  space: string;
  code_prefix: string;
  role: SpaceRole;
  expires_at: string | null;
  max_uses: number;
  used_count: number;
  status: 'active' | 'revoked';
  created_at: string;
  /** Plaintext code — only present in the create response. */
  code?: string;
}

export interface SpaceMember {
  id: string;
  user: string;
  user_email: string;
  role: SpaceRole;
  status: string;
  last_accessed_at: string | null;
  created_at: string;
}

export interface AddMemberResult {
  pending: boolean;
  email?: string;
  role?: SpaceRole;
  member?: SpaceMember;
}

export interface SpaceAccessRequestRecord {
  id: string;
  space: string;
  user: string;
  reason: string;
  role: 'member' | 'guest';
  status: 'pending' | 'approved' | 'rejected';
  rejection_reason?: string;
  created_at: string;
  updated_at: string;
}

export interface OwnershipTransfer {
  id: string;
  space_id: string;
  from_owner_id: string;
  to_owner_id: string;
  mode: 'voluntary' | 'forced' | 'offboarding';
  status: 'pending' | 'completed' | 'declined' | 'cancelled' | 'expired' | 'invalidated';
  expected_ownership_version: number;
  expires_at: string | null;
  completed_at: string | null;
}

export interface OwnershipDetail {
  owner: { id: string; display_name: string; is_active: boolean } | null;
  ownership_version: number;
  pending_transfer: OwnershipTransfer | null;
}

export interface OwnershipCandidate {
  id: string;
  display_name: string;
  role?: SpaceRole;
  requires_membership: boolean;
}

export interface OwnershipCandidatePage {
  results: OwnershipCandidate[];
  next: number | null;
}

export interface PendingOwnershipTransfer extends OwnershipTransfer {
  space: { id: string; display_name: string; status: 'active' | 'archived' };
}

export const spacesApi = {
  async list(): Promise<KnowledgeSpace[]> {
    const { data } = await apiClient.get('/spaces/');
    return Array.isArray(data) ? data : data.results ?? [];
  },

  async get(id: string): Promise<KnowledgeSpace> {
    const { data } = await apiClient.get(`/spaces/${id}/`);
    return data;
  },

  async create(body: Partial<KnowledgeSpace>): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post('/spaces/', body);
    return data;
  },

  async update(id: string, body: Partial<KnowledgeSpace>): Promise<KnowledgeSpace> {
    const { data } = await apiClient.patch(`/spaces/${id}/`, body);
    return data;
  },

  async archive(id: string): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/spaces/${id}/archive/`, {});
    return data;
  },

  async restore(id: string): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/spaces/${id}/restore/`, {});
    return data;
  },

  async clone(
    id: string,
    body: { name: string; code: string; copy_documents: boolean },
  ): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/spaces/${id}/clone/`, body);
    return data;
  },

  async transfer(id: string, businessLine: string): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/spaces/${id}/transfer/`, {
      business_line: businessLine,
    });
    return data;
  },

  async ownership(id: string): Promise<OwnershipDetail> {
    const { data } = await apiClient.get(`/spaces/${id}/ownership/`);
    return data;
  },

  async pendingOwnershipTransfers(): Promise<PendingOwnershipTransfer[]> {
    const { data } = await apiClient.get('/spaces/ownership-transfers/pending/');
    return Array.isArray(data) ? data : data.results ?? [];
  },

  async ownershipCandidates(
    id: string,
    query = '',
    purpose: 'voluntary' | 'forced' = 'voluntary',
  ): Promise<OwnershipCandidate[]> {
    return (await this.ownershipCandidatePage(id, query, purpose)).results;
  },

  async ownershipCandidatePage(
    id: string,
    query = '',
    purpose: 'voluntary' | 'forced' = 'voluntary',
    offset = 0,
  ): Promise<OwnershipCandidatePage> {
    const { data } = await apiClient.get(`/spaces/${id}/ownership-candidates/`, {
      params: { purpose, q: query, ...(offset ? { offset } : {}) },
    });
    return Array.isArray(data) ? { results: data, next: null } : { results: data.results ?? [], next: data.next ?? null };
  },

  async requestOwnershipTransfer(
    id: string,
    body: { to_user_id: string; expected_ownership_version: number; reason_code?: string },
  ): Promise<OwnershipTransfer> {
    const { data } = await apiClient.post(`/spaces/${id}/ownership-transfers/`, body, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },

  async forceOwnershipTransfer(
    id: string,
    body: { to_user_id: string; expected_ownership_version: number; reason_code: string },
  ): Promise<OwnershipTransfer> {
    const { data } = await apiClient.post(`/spaces/${id}/ownership-transfers/force/`, body, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },

  async acceptOwnershipTransfer(id: string, transferId: string): Promise<OwnershipTransfer> {
    const { data } = await apiClient.post(`/spaces/${id}/ownership-transfers/${transferId}/accept/`, {});
    return data;
  },

  async declineOwnershipTransfer(id: string, transferId: string): Promise<OwnershipTransfer> {
    const { data } = await apiClient.post(`/spaces/${id}/ownership-transfers/${transferId}/decline/`, {});
    return data;
  },

  async discoverable(): Promise<KnowledgeSpace[]> {
    const { data } = await apiClient.get('/spaces/discoverable/');
    return Array.isArray(data) ? data : data.results ?? [];
  },

  async requestAccess(
    id: string,
    body: { reason: string; role: 'member' | 'guest' },
  ): Promise<SpaceAccessRequestRecord> {
    const { data } = await apiClient.post(`/spaces/${id}/access-requests/`, body);
    return data;
  },

  async switch(id: string): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/spaces/${id}/switch/`, {});
    return data;
  },

  async join(code: string): Promise<{ joined: boolean; space: KnowledgeSpace }> {
    const { data } = await apiClient.post('/spaces/join/', { code });
    return data;
  },

  async members(id: string): Promise<SpaceMember[]> {
    const { data } = await apiClient.get(`/spaces/${id}/members/`);
    return Array.isArray(data) ? data : data.results ?? [];
  },

  // V7.0: add a member by email. Existing accounts become active members and
  // are notified; unknown emails become a pending invite redeemed on signup.
  async addMember(id: string, body: { email: string; role: SpaceRole }): Promise<AddMemberResult> {
    const { data } = await apiClient.post(`/spaces/${id}/members/`, body);
    return data;
  },

  async updateMember(id: string, userId: string, role: SpaceRole): Promise<SpaceMember> {
    const { data } = await apiClient.patch(`/spaces/${id}/members/${userId}/`, { role });
    return data;
  },

  async removeMember(id: string, userId: string): Promise<void> {
    await apiClient.delete(`/spaces/${id}/members/${userId}/`);
  },

  async listInvites(id: string): Promise<InviteCode[]> {
    const { data } = await apiClient.get(`/spaces/${id}/invites/`);
    return Array.isArray(data) ? data : data.results ?? [];
  },

  async createInvite(
    id: string,
    body: { role?: SpaceRole; expires_at?: string | null; max_uses?: number }
  ): Promise<InviteCode> {
    const { data } = await apiClient.post(`/spaces/${id}/invites/`, body);
    return data;
  },

  async revokeInvite(id: string, inviteId: string): Promise<void> {
    await apiClient.post(`/spaces/${id}/invites/${inviteId}/revoke/`, {});
  },
};
