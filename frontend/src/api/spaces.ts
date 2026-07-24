/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Spaces API client — V6.0 multi-space platform.

import apiClient, { coalescedGet, getRequestSignal } from './client';

function listPayload<T>(data: unknown, resource: string): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: T[] }).results;
  }
  throw new Error(`invalid_${resource}_response`);
}

function pagePayload<T>(data: unknown, resource: string): { results: T[]; next: number | null } {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(`invalid_${resource}_response`);
  }
  const record = data as { results?: unknown; next?: unknown };
  if (!Array.isArray(record.results)) throw new Error(`invalid_${resource}_response`);
  return {
    results: record.results as T[],
    next: typeof record.next === 'number' ? record.next : record.next == null ? null : null,
  };
}

function readConfig(signal?: AbortSignal, params?: object) {
  const effectiveSignal = signal ?? getRequestSignal();
  if (effectiveSignal || params) return { ...(params ? { params } : {}), ...(effectiveSignal ? { signal: effectiveSignal } : {}) };
  return undefined;
}

export type SpaceRole =
  | 'super_admin'
  | 'org_admin'
  | 'business_admin'
  | 'owner'
  | 'knowledge_admin'
  | 'reviewer'
  | 'member'
  | 'guest';

export type JoinPolicy = 'access_code' | 'global';

export interface KnowledgeSpace {
  id: string;
  name: string;
  code: string;
  description: string;
  icon: string;
  language: string;
  visibility: 'private' | 'business_line' | 'organization' | 'public_demo';
  join_policy: JoinPolicy;
  join_code: string | null;
  allow_member_invite: boolean;
  join_code_updated_at: string | null;
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

export interface JoinResult {
  space_id: string;
  space_name: string;
  membership_id: string;
  role: SpaceRole;
  source: string;
}

export interface JoinCodeInfo {
  space_id: string;
  join_policy: JoinPolicy;
  join_code: string | null;
  allow_member_invite: boolean;
  join_code_updated_at: string | null;
}

export interface JoinCodeRegenerateResult {
  space_id: string;
  join_code: string;
  join_policy: JoinPolicy;
  join_code_updated_at: string;
}

export interface JoinPolicySwitchResult {
  space_id: string;
  join_policy: JoinPolicy;
  join_code: string | null;
}

export interface AllowMemberInviteResult {
  space_id: string;
  allow_member_invite: boolean;
}

export interface DiscoverableSpaceCard {
  id: string;
  name: string;
  slug: string;
  description: string;
  join_policy: JoinPolicy;
  status: 'active' | 'archived';
  is_member?: boolean;
}

export interface InviteCode {
  id: string;
  space_id: string;
  display_prefix: string;
  role_ceiling: 'member' | 'guest';
  expires_at: string;
  max_uses: number;
  used_count: number;
  max_pending: number;
  pending_count: number;
  status: 'active' | 'revoked' | 'expired';
  version: number;
  /** Plaintext code — only present in the create response. */
  code?: string;
}

export interface SpaceMember {
  id: string;
  user: { id: string; email: string; display_name: string };
  role: SpaceRole;
  status: string;
  expires_at: string | null;
  effective: boolean;
  source_kind: string;
  membership_version: number;
  immutable_owner: boolean;
  updated_at: string;
}

export interface SpaceInvitation {
  id: string;
  space_id: string;
  target_user_id: string | null;
  target_kind: 'user' | 'email';
  role: Exclude<SpaceRole, 'owner' | 'super_admin' | 'org_admin' | 'business_admin'>;
  token_prefix: string;
  status: 'pending' | 'accepted' | 'declined' | 'revoked' | 'expired' | 'invalidated';
  version: number;
  expires_at: string;
  resulting_membership_uuid: string | null;
  token?: string;
}

export interface SpaceAccessRequestRecord {
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

export type WorkspaceDeletionStatus =
  | 'pending'
  | 'scheduled'
  | 'executing'
  | 'failed'
  | 'completed'
  | 'cancelled'
  | 'expired'
  | 'invalidated';

export interface WorkspaceDeletionBlocker {
  kind: string;
  id: string;
  status: string;
  remediation_route: string;
}

export interface WorkspaceDeletionRequest {
  request_id: string;
  status: WorkspaceDeletionStatus;
  request_version: number;
  status_url: string;
  expires_at?: string;
  purge_not_before?: string;
  failure_code?: string;
  purge?: {
    state: 'queued' | 'running' | 'failed' | 'completed';
    attempt: number;
    failure_code: string | null;
    stores: Array<{
      store: 'database' | 'blob' | 'search' | 'vector' | 'replay';
      status: 'pending' | 'running' | 'acked' | 'failed';
      item_count: number;
      byte_count: number;
    }>;
  };
}

export interface WorkspaceDeletionImpact {
  space_id: string;
  lifecycle_status: 'active' | 'archived';
  expected_lifecycle_version: number;
  expected_ownership_version: number;
  confirmation_phrase: string;
  impact_version: string;
  impact_expires_at: string;
  counts: { eligible_content: number; retained_evidence: number };
  blockers: WorkspaceDeletionBlocker[];
  earliest_purge_at: string | null;
  manifest_digest: string;
  manifest_version: number;
  retention_dates: string[];
  active_request: WorkspaceDeletionRequest | null;
}

export const spacesApi = {
  async list(signal?: AbortSignal): Promise<KnowledgeSpace[]> {
    const { data } = await coalescedGet<KnowledgeSpace[]>('/spaces/', readConfig(signal));
    return listPayload<KnowledgeSpace>(data, 'spaces');
  },

  async get(id: string, signal?: AbortSignal): Promise<KnowledgeSpace> {
    const { data } = await coalescedGet<KnowledgeSpace>(`/spaces/${id}/`, readConfig(signal));
    return data;
  },

  async create(body: Partial<KnowledgeSpace>, signal?: AbortSignal): Promise<KnowledgeSpace> {
    const response = signal
      ? await apiClient.post('/spaces/', body, { signal })
      : await apiClient.post('/spaces/', body);
    const { data } = response;
    return data;
  },

  async update(id: string, body: Partial<KnowledgeSpace>): Promise<KnowledgeSpace> {
    const { data } = await apiClient.patch(`/spaces/${id}/`, body);
    return data;
  },

  async archive(id: string): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/spaces/${id}/archive/`, {}, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },

  async restore(id: string): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/spaces/${id}/restore/`, {}, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },

  async deletionImpact(id: string, signal?: AbortSignal): Promise<WorkspaceDeletionImpact> {
    const { data } = await coalescedGet<WorkspaceDeletionImpact>(
      `/spaces/${id}/deletion-impact/`,
      readConfig(signal),
    );
    return data;
  },

  async submitDeletion(
    id: string,
    impact: WorkspaceDeletionImpact,
  ): Promise<WorkspaceDeletionRequest> {
    const { data } = await apiClient.post(
      `/spaces/${id}/deletion-requests/`,
      {
        impact_version: impact.impact_version,
        expected_lifecycle_version: impact.expected_lifecycle_version,
        expected_ownership_version: impact.expected_ownership_version,
      },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async confirmDeletion(
    id: string,
    request: WorkspaceDeletionRequest,
    impact: WorkspaceDeletionImpact,
    confirmationPhrase: string,
  ): Promise<WorkspaceDeletionRequest> {
    const { data } = await apiClient.post(
      `/spaces/${id}/deletion-requests/${request.request_id}/confirm/`,
      {
        expected_request_version: request.request_version,
        impact_version: impact.impact_version,
        expected_lifecycle_version: impact.expected_lifecycle_version,
        expected_ownership_version: impact.expected_ownership_version,
        confirmation_phrase: confirmationPhrase,
        acknowledge_permanent: true,
      },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async cancelDeletion(
    id: string,
    request: WorkspaceDeletionRequest,
  ): Promise<WorkspaceDeletionRequest> {
    const { data } = await apiClient.post(
      `/spaces/${id}/deletion-requests/${request.request_id}/cancel/`,
      { expected_request_version: request.request_version },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async deletionStatus(
    requestId: string,
    signal?: AbortSignal,
  ): Promise<WorkspaceDeletionRequest> {
    const { data } = await coalescedGet<WorkspaceDeletionRequest>(
      `/spaces/deletion-requests/${requestId}/`,
      readConfig(signal),
    );
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

  async ownership(id: string, signal?: AbortSignal): Promise<OwnershipDetail> {
    const { data } = await coalescedGet<OwnershipDetail>(`/spaces/${id}/ownership/`, readConfig(signal));
    return data;
  },

  async pendingOwnershipTransfers(signal?: AbortSignal): Promise<PendingOwnershipTransfer[]> {
    const { data } = await coalescedGet<PendingOwnershipTransfer[]>('/spaces/ownership-transfers/pending/', readConfig(signal));
    return listPayload<PendingOwnershipTransfer>(data, 'pending_ownership_transfers');
  },

  async ownershipCandidates(
    id: string,
    query = '',
    purpose: 'voluntary' | 'forced' = 'voluntary',
    signal?: AbortSignal,
  ): Promise<OwnershipCandidate[]> {
    return (await this.ownershipCandidatePage(id, query, purpose, 0, signal)).results;
  },

  async ownershipCandidatePage(
    id: string,
    query = '',
    purpose: 'voluntary' | 'forced' = 'voluntary',
    offset = 0,
    signal?: AbortSignal,
  ): Promise<OwnershipCandidatePage> {
    const { data } = await coalescedGet<OwnershipCandidatePage>(
      `/spaces/${id}/ownership-candidates/`,
      readConfig(signal, { purpose, q: query, ...(offset ? { offset } : {}) }),
    );
    if (Array.isArray(data)) return { results: data as unknown as OwnershipCandidate[], next: null };
    return pagePayload<OwnershipCandidate>(data, 'ownership_candidates');
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

  async discoverable(signal?: AbortSignal): Promise<DiscoverableSpaceCard[]> {
    const { data } = await coalescedGet<DiscoverableSpaceCard[] | { results: DiscoverableSpaceCard[] }>(
      '/spaces/discoverable/', readConfig(signal));
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
      return (data as { results: DiscoverableSpaceCard[] }).results;
    }
    return [];
  },

  async requestAccess(
    id: string,
    body: { reason: string; role: 'member' | 'guest' },
    signal?: AbortSignal,
  ): Promise<SpaceAccessRequestRecord> {
    const response = signal
      ? await apiClient.post(`/spaces/${id}/access-requests/`, { reason: body.reason }, {
          signal,
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        })
      : await apiClient.post(`/spaces/${id}/access-requests/`, { reason: body.reason }, {
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        });
    const { data } = response;
    return data;
  },

  async switch(id: string, signal?: AbortSignal): Promise<KnowledgeSpace> {
    const response = signal
      ? await apiClient.post(`/spaces/${id}/switch/`, {}, { signal })
      : await apiClient.post(`/spaces/${id}/switch/`, {});
    const { data } = response;
    return data;
  },

  async join(code: string, signal?: AbortSignal): Promise<JoinResult> {
    const response = signal
      ? await apiClient.post('/spaces/join-by-code/', { join_code: code }, {
          signal,
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        })
      : await apiClient.post('/spaces/join-by-code/', { join_code: code }, {
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        });
    const { data } = response;
    return data;
  },

  async joinByCode(code: string, signal?: AbortSignal): Promise<JoinResult> {
    const response = signal
      ? await apiClient.post('/spaces/join-by-code/', { join_code: code }, {
          signal,
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        })
      : await apiClient.post('/spaces/join-by-code/', { join_code: code }, {
          headers: { 'Idempotency-Key': crypto.randomUUID() },
        });
    const { data } = response;
    return data;
  },

  async getJoinCode(spaceId: string, signal?: AbortSignal): Promise<JoinCodeInfo> {
    const { data } = await coalescedGet<JoinCodeInfo>(
      `/spaces/${spaceId}/join-code/`, readConfig(signal));
    return data;
  },

  async regenerateJoinCode(
    spaceId: string,
    customCode?: string,
  ): Promise<JoinCodeRegenerateResult> {
    const { data } = await apiClient.post(
      `/spaces/${spaceId}/join-code/regenerate/`,
      { custom_code: customCode ?? null },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async globalJoin(spaceId: string): Promise<JoinResult> {
    const { data } = await apiClient.post(
      `/spaces/${spaceId}/join/`, {},
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async switchJoinPolicy(spaceId: string, joinPolicy: JoinPolicy): Promise<JoinPolicySwitchResult> {
    const { data } = await apiClient.post(
      `/spaces/${spaceId}/join-policy/switch/`,
      { join_policy: joinPolicy },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async toggleAllowMemberInvite(spaceId: string, allow: boolean): Promise<AllowMemberInviteResult> {
    const { data } = await apiClient.post(
      `/spaces/${spaceId}/allow-member-invite/`,
      { allow_member_invite: allow },
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },

  async members(id: string, signal?: AbortSignal): Promise<SpaceMember[]> {
    const { data } = await coalescedGet<SpaceMember[]>(`/spaces/${id}/members/`, readConfig(signal));
    return listPayload<SpaceMember>(data, 'space_members');
  },

  async addMember(id: string, body: { email: string; role: SpaceRole }): Promise<SpaceInvitation> {
    const { data } = await apiClient.post(`/spaces/${id}/invitations/`, {
      target_email: body.email,
      role: body.role,
      expires_in_days: 7,
    }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
    return data;
  },

  async updateMember(id: string, member: SpaceMember, role: SpaceRole): Promise<SpaceMember> {
    const { data } = await apiClient.patch(`/spaces/${id}/members/${member.id}/`, {
      expected_membership_version: member.membership_version,
      role,
      reason_code: 'owner_role_change',
      reason_text: '',
    }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
    return data;
  },

  async removeMember(id: string, member: SpaceMember): Promise<void> {
    await apiClient.delete(`/spaces/${id}/members/${member.id}/`, {
      data: { reason_code: 'owner_removed', reason_text: '' },
      headers: {
        'Idempotency-Key': crypto.randomUUID(),
        'If-Match': `"membership-v${member.membership_version}"`,
      },
    });
  },

  async listInvites(id: string, signal?: AbortSignal): Promise<InviteCode[]> {
    const { data } = await coalescedGet<InviteCode[]>(`/spaces/${id}/access-codes/`, readConfig(signal));
    return listPayload<InviteCode>(data, 'space_invites');
  },

  async createInvite(
    id: string,
    body: { role?: SpaceRole; expires_at?: string | null; max_uses?: number }
  ): Promise<InviteCode> {
    const maxUses = Math.max(1, body.max_uses ?? 20);
    const { data } = await apiClient.post(`/spaces/${id}/access-codes/`, {
      role_ceiling: body.role === 'guest' ? 'guest' : 'member',
      expires_at: body.expires_at ?? new Date(Date.now() + 7 * 86_400_000).toISOString(),
      max_uses: maxUses,
      max_pending: maxUses,
    }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
    return data;
  },

  async revokeInvite(id: string, invite: InviteCode): Promise<void> {
    await apiClient.post(`/spaces/${id}/access-codes/${invite.id}/revoke/`, {
      expected_version: invite.version,
      reason_code: 'owner_revoked',
    }, { headers: { 'Idempotency-Key': crypto.randomUUID() } });
  },
};
