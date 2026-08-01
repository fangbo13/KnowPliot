/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// V7.0 admin-console API client. Reuses existing rbac/audit endpoints and the
// new V7 governance endpoints under /admin/.
import apiClient, * as client from './client';

function optionalClientFunction<T extends (...args: never[]) => unknown>(name: string): T | undefined {
  try {
    const candidate = (client as unknown as Record<string, unknown>)[name];
    return typeof candidate === 'function' ? candidate as T : undefined;
  } catch {
    // A narrow Vitest module mock may omit helper exports; retain the Axios
    // fallback so API call shape remains backward compatible.
    return undefined;
  }
}

function adminGet<T>(url: string, config?: Record<string, unknown>) {
  const getSignal = optionalClientFunction<() => AbortSignal | undefined>('getRequestSignal');
  const effectiveSignal = (config?.signal as AbortSignal | undefined) ?? getSignal?.();
  const requestConfig = effectiveSignal
    ? { ...(config ?? {}), signal: effectiveSignal }
    : config;
  const sharedGet = optionalClientFunction<<R>(path: string, options?: unknown) => Promise<{ data: R }>>('coalescedGet');
  if (sharedGet) return sharedGet<T>(url, requestConfig);
  return requestConfig === undefined ? apiClient.get<T>(url) : apiClient.get<T>(url, requestConfig);
}

export interface AdminUser {
  id: string;
  email: string;
  username: string;
  service_line: string | null;
  business_line: string | null;
  business_line_name: string | null;
  role_level: string | null;
  is_hr_admin: boolean;
  roles: string[];
  is_active: boolean;
}

export interface OffboardingImpact {
  subject: { id: string; display_name: string; is_active: boolean };
  impact_version: string;
  blockers: {
    owned_spaces: string[];
    owned_space_details: Array<{
      id: string;
      display_name: string;
      status: 'active' | 'archived';
      ownership_version: number;
    }>;
    last_platform_admin: boolean;
    last_organization_admin_scopes: Array<{ organization_id: string; business_line_id: string | null; role: string }>;
    last_business_admin_scopes: Array<{ organization_id: string; business_line_id: string | null; role: string }>;
  };
  actions: {
    active_sessions: number;
    active_conversation_shares: number;
    active_invite_codes: number;
    active_admin_registration_codes: number;
    pending_email_invites: number;
    open_feedback_reviews: number;
    open_knowledge_gap_tickets: number;
    running_jobs: number;
  };
  protected_history: Record<string, number>;
  can_deactivate_without_successor: boolean;
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

export interface ModelProfile {
  id: string;
  name: string;
  provider: string;
  model_id: string;
  enabled: boolean;
  created_at: string;
}

export interface GovernancePolicy {
  id: string;
  organization: string;
  space: string | null;
  revision: number;
  values: Record<string, unknown>;
  created_at: string;
}

export interface GovernancePolicyEnvelope {
  effective: Record<string, unknown>;
  revisions: GovernancePolicy[];
}

export interface AuditLog {
  id: string;
  user_email?: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  role_used: string;
  organization_id: string | null;
  business_line_id: string | null;
  space_id: string | null;
  result: 'success' | 'denied' | 'failure';
  created_at: string;
}

export interface AuditLogQuery {
  action?: string;
  result?: 'success' | 'denied' | 'failure';
  user_id?: string;
  organization?: string;
  business_line?: string;
  space?: string;
  date_from?: string;
  date_to?: string;
}

export type ServiceHealthStatus =
  | 'up'
  | 'down'
  | 'degraded'
  | 'configured'
  | 'not_configured';

export interface SystemHealth {
  overall: 'up' | 'degraded' | 'down';
  readiness?: 'up' | 'degraded' | 'down';
  liveness?: 'up' | 'down';
  dependency_health?: Record<string, ServiceHealthStatus>;
  background_worker_health?: {
    status: ServiceHealthStatus;
    latency_ms?: number;
    detail?: string;
    error?: string;
  };
  services: Record<string, {
    status: ServiceHealthStatus;
    code?: string;
    latency_ms?: number;
    latency_bucket?: 'fast' | 'normal' | 'slow';
    last_checked_at?: string;
    detail?: string;
    error?: string;
    missing?: string[];
    max_sync_rows?: number;
    retention?: {
      export_job_days?: number | null;
      audit_log_days?: number | null;
      notification_days?: number | null;
      stale_job_days?: number | null;
    };
    cleanup?: {
      expired_export_jobs?: number;
      failed_export_jobs?: number;
      failed_ingestion_jobs?: number;
    };
    backlog?: {
      sla_overdue_items?: number;
      stale_documents?: number;
    };
  }>;
}

export interface SystemMetrics {
  users: { total: number; active: number };
  usage: { sessions: number; questions: number; citations: number };
  documents: {
    total: number;
    processing: number;
    failed: number;
    stale: number;
    expiring: number;
  };
  quality: {
    average_response_time_ms: number | null;
    no_evidence_rate: number;
    citation_coverage_rate: number;
  };
  model_api: {
    calls: number;
    failures: number;
    error_rate: number;
    total_tokens: number;
    average_tokens: number;
    by_model: Array<{ model: string; calls: number }>;
  };
  knowledge_quality: {
    unused_documents: number;
    high_usage_documents: number;
    stale_cited_documents: number;
  };
  security: { permission_denied: number };
}

export type IngestionJobStatus =
  | 'queued'
  | 'processing'
  | 'retrying'
  | 'succeeded'
  | 'failed';

export interface IngestionJob {
  id: string;
  document: string;
  document_title: string;
  space: string;
  space_name: string;
  requested_by_email: string | null;
  trigger: 'upload' | 'batch' | 'crawler' | 'reindex' | 'admin_retry';
  status: IngestionJobStatus;
  celery_task_id: string;
  attempt: number;
  max_attempts: number;
  last_error: string;
  retry_of: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface DocumentQuality {
  id: string;
  title: string;
  space: string;
  status: 'active' | 'stale';
  effective_to: string | null;
  chunk_count: number;
  citation_count: number;
  average_relevance: number | null;
  last_cited_at: string | null;
  flags: {
    unused: boolean;
    high_usage: boolean;
    stale_source: boolean;
  };
}

export interface FeedbackReview {
  id: string;
  space: string;
  message: string;
  user: string;
  user_email?: string;
  type?: string;
  feedback_type: 'helpful' | 'unhelpful' | 'incorrect' | 'outdated' | 'missing_source';
  comment: string;
  suggested_source: string;
  flag_for_review: boolean;
  status: 'submitted' | 'pending_review' | 'in_review' | 'resolved' | 'dismissed' | 'withdrawn';
  reviewer: string | null;
  reviewer_email?: string | null;
  resolution_code: string;
  resolution_notes: string;
  review_context: {
    question?: string;
    answer?: string;
    citations?: Array<{ document_title?: string; quoted_text?: string }>;
    retrieval_count?: number;
    model?: string;
  };
  created_at: string;
  updated_at: string;
}

export interface KnowledgeGap {
  id: string;
  space: string;
  feedback: string | null;
  question: string;
  question_snapshot: string;
  status: 'open' | 'in_progress' | 'resolved' | 'wont_fix';
  priority: 'low' | 'medium' | 'high' | 'critical';
  assignee: string | null;
  assignee_email?: string | null;
  suggested_source: string;
  resolution_notes: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeQualityReport {
  feedback: {
    total: number;
    negative_rate: number;
    flagged_rate: number;
    by_type: Record<string, number>;
  };
  reviews: {
    pending: number;
    in_review: number;
    resolved: number;
    dismissed: number;
    average_resolution_seconds: number | null;
  };
  unanswered_questions: Array<{ question: string; count: number }>;
  knowledge_gaps: {
    open: number;
    in_progress: number;
    resolved: number;
    wont_fix: number;
  };
  documents: {
    high_citation: Array<{ id: string; title: string; citation_count: number }>;
    uncited: Array<{ id: string; title: string }>;
    stale_cited: Array<{ id: string; title: string }>;
  };
  trends: Array<{ date: string; feedback: number; negative: number }>;
}

export type QualityExportDataset = 'feedback' | 'reviews' | 'gaps' | 'unanswered' | 'documents';

export interface ComplianceExportJob {
  id: string;
  dataset: QualityExportDataset;
  status: 'queued' | 'processing' | 'succeeded' | 'failed' | 'expired';
  space: string | null;
  requested_by: string;
  retry_of?: string | null;
  row_count: number;
  error_code: string;
  safe_error_summary: string;
  date_from: string | null;
  date_to: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  download_url: string;
}

const unwrap = <T>(data: unknown, resource = 'admin_list'): T[] => {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: T[] }).results;
  }
  throw new Error(`invalid_${resource}_response`);
};

export const adminApi = {
  async modelProfiles(signal?: AbortSignal): Promise<ModelProfile[]> {
    const { data } = await adminGet<ModelProfile[]>('/admin/model-profiles/', signal ? { signal } : undefined);
    return unwrap<ModelProfile>(data, 'model_profiles');
  },
  async createModelProfile(body: Pick<ModelProfile, 'name' | 'provider' | 'model_id' | 'enabled'>): Promise<ModelProfile> {
    const { data } = await apiClient.post('/admin/model-profiles/', body);
    return data;
  },
  async governancePolicies(spaceId: string, signal?: AbortSignal): Promise<GovernancePolicyEnvelope> {
    const { data } = await adminGet<GovernancePolicyEnvelope>('/admin/governance/policies/', {
      params: { space: spaceId },
      ...(signal ? { signal } : {}),
    });
    return data;
  },
  async createGovernancePolicy(body: {
    organization?: string;
    space?: string;
    values: Record<string, unknown>;
  }): Promise<GovernancePolicy> {
    const { data } = await apiClient.post('/admin/governance/policies/', body);
    return data;
  },
  // ── Users & roles (existing rbac endpoints) ──
  async users(signal?: AbortSignal): Promise<AdminUser[]> {
    const { data } = await adminGet<AdminUser[]>('/rbac/users/', signal ? { signal } : undefined);
    return unwrap<AdminUser>(data, 'users');
  },
  async roles(signal?: AbortSignal): Promise<Role[]> {
    const { data } = await adminGet<Role[]>('/rbac/roles/', signal ? { signal } : undefined);
    return unwrap<Role>(data, 'roles');
  },
  async assignRole(userId: string, roleName: string): Promise<void> {
    await apiClient.post('/rbac/user-roles/', { user_id: userId, role_name: roleName });
  },
  async revokeRole(userRoleId: string): Promise<void> {
    await apiClient.delete(`/rbac/user-roles/${userRoleId}/`);
  },
  async userRoles(userId: string, signal?: AbortSignal): Promise<Array<{ id: string; role_name: string }>> {
    const { data } = await adminGet<Array<{ id: string; role_name: string }>>('/rbac/user-roles/', {
      params: { user: userId },
      ...(signal ? { signal } : {}),
    });
    return unwrap<{ id: string; role_name: string }>(data, 'user_roles');
  },
  async activateUser(userId: string): Promise<void> {
    await apiClient.post(`/rbac/users/${userId}/activate/`, {});
  },
  async deactivateUser(userId: string): Promise<void> {
    await apiClient.post(`/rbac/users/${userId}/deactivate/`, {});
  },
  async offboardingImpact(userId: string): Promise<OffboardingImpact> {
    const { data } = await apiClient.get(`/admin/users/${userId}/offboarding-impact/`);
    return data;
  },
  async offboardingAdminSuccessorCandidates(
    userId: string,
    params: { organization_id?: string; business_line_id?: string | null; role: string; scope_type?: 'platform' },
    signal?: AbortSignal,
  ): Promise<Array<{ id: string; display_name: string }>> {
    const { data } = await adminGet<{ results?: Array<{ id: string; display_name: string }> }>(
      `/admin/users/${userId}/offboarding-admin-candidates/`,
      { params, ...(signal ? { signal } : {}) },
    );
    return unwrap<{ id: string; display_name: string }>(data, 'offboarding_candidates');
  },
  async offboardUser(
    userId: string,
    body: {
      impact_version: string;
      reason_code: string;
      space_transfers: Array<{
        space_id: string;
        successor_user_id: string;
        expected_ownership_version: number;
      }>;
      admin_successions?: Array<
        | {
            organization_id: string;
            business_line_id: string | null;
            role: string;
            successor_user_id: string;
          }
        | {
            scope_type: 'platform';
            role: 'admin';
            successor_user_id: string;
          }
      >;
    },
  ): Promise<{ offboarded: boolean; subject_id: string }> {
    const { data } = await apiClient.post(`/admin/users/${userId}/offboard/`, body);
    return data;
  },

  // ── Admin registration codes (V7) ──
  async codes(signal?: AbortSignal): Promise<AdminCode[]> {
    const { data } = await adminGet<AdminCode[]>('/admin/registration-codes/', signal ? { signal } : undefined);
    return unwrap<AdminCode>(data, 'registration_codes');
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
  async organizations(signal?: AbortSignal): Promise<Organization[]> {
    const { data } = await adminGet<Organization[]>('/admin/organizations/', signal ? { signal } : undefined);
    return unwrap<Organization>(data, 'organizations');
  },
  async archiveOrganization(id: string): Promise<Organization> {
    const { data } = await apiClient.post(`/admin/organizations/${id}/archive/`, {});
    return data;
  },
  async restoreOrganization(id: string): Promise<Organization> {
    const { data } = await apiClient.post(`/admin/organizations/${id}/restore/`, {});
    return data;
  },
  async businessLines(orgId?: string, signal?: AbortSignal): Promise<BusinessLine[]> {
    const { data } = await adminGet<BusinessLine[]>('/admin/business-lines/', {
      params: orgId ? { organization: orgId } : {},
      ...(signal ? { signal } : {}),
    });
    return unwrap<BusinessLine>(data, 'business_lines');
  },
  async createBusinessLine(body: { organization: string; name: string; code: string; description?: string }): Promise<BusinessLine> {
    const { data } = await apiClient.post('/admin/business-lines/', body);
    return data;
  },
  async archiveBusinessLine(id: string): Promise<BusinessLine> {
    const { data } = await apiClient.post(`/admin/business-lines/${id}/archive/`, {});
    return data;
  },
  async restoreBusinessLine(id: string): Promise<BusinessLine> {
    const { data } = await apiClient.post(`/admin/business-lines/${id}/restore/`, {});
    return data;
  },

  // ── Announcements (V7) ──
  async announcements(signal?: AbortSignal): Promise<Announcement[]> {
    const { data } = await adminGet<Announcement[]>('/notifications/announcements/', signal ? { signal } : undefined);
    return unwrap<Announcement>(data, 'announcements');
  },
  async createAnnouncement(body: {
    title: string; body: string; level?: string;
    audience: string; audience_ref?: string; version?: string;
  }): Promise<Announcement> {
    const { data } = await apiClient.post('/notifications/announcements/', body);
    return data;
  },

  // ── Audit logs (existing endpoint) ──
  async auditLogs(params?: AuditLogQuery, signal?: AbortSignal): Promise<AuditLog[]> {
    const { data } = await adminGet<AuditLog[]>('/audit/logs/', { params, ...(signal ? { signal } : {}) });
    return unwrap<AuditLog>(data, 'audit_logs');
  },
  async health(signal?: AbortSignal): Promise<SystemHealth> {
    const { data } = await adminGet<SystemHealth>('/admin/health/', signal ? { signal } : undefined);
    return data;
  },
  async metrics(signal?: AbortSignal): Promise<SystemMetrics> {
    const { data } = await adminGet<SystemMetrics>('/admin/metrics/', signal ? { signal } : undefined);
    return data;
  },
  async ingestionJobs(params?: {
    status?: IngestionJobStatus;
  }, signal?: AbortSignal): Promise<IngestionJob[]> {
    const { data } = await adminGet<IngestionJob[]>('/admin/ingestion-jobs/', { params, ...(signal ? { signal } : {}) });
    return unwrap<IngestionJob>(data, 'ingestion_jobs');
  },
  async retryIngestionJob(jobId: string): Promise<IngestionJob> {
    const { data } = await apiClient.post(
      `/admin/ingestion-jobs/${jobId}/retry/`,
      {},
    );
    return data;
  },
  async documentQuality(params?: {
    status?: 'active' | 'stale';
    flag?: 'unused' | 'high_usage' | 'stale_source';
  }, signal?: AbortSignal): Promise<DocumentQuality[]> {
    const { data } = await adminGet<DocumentQuality[]>('/admin/quality/documents/', { params, ...(signal ? { signal } : {}) });
    return unwrap<DocumentQuality>(data, 'document_quality');
  },
  async feedbackReviews(params?: {
    status?: string;
    type?: string;
    space?: string;
    reviewer?: string;
  }, signal?: AbortSignal): Promise<FeedbackReview[]> {
    const { data } = await adminGet<FeedbackReview[]>('/admin/quality/feedback/', { params, ...(signal ? { signal } : {}) });
    return unwrap<FeedbackReview>(data, 'feedback_reviews');
  },
  async claimFeedback(id: string): Promise<FeedbackReview> {
    const { data } = await apiClient.post(`/admin/quality/feedback/${id}/claim/`, {});
    return data;
  },
  async assignFeedback(id: string, reviewer: string): Promise<FeedbackReview> {
    const { data } = await apiClient.post(`/admin/quality/feedback/${id}/assign/`, { reviewer });
    return data;
  },
  async resolveFeedback(id: string, body: { resolution_code?: string; resolution_notes?: string }): Promise<FeedbackReview> {
    const { data } = await apiClient.post(`/admin/quality/feedback/${id}/resolve/`, body);
    return data;
  },
  async dismissFeedback(id: string, body: { resolution_code?: string; resolution_notes?: string }): Promise<FeedbackReview> {
    const { data } = await apiClient.post(`/admin/quality/feedback/${id}/dismiss/`, body);
    return data;
  },
  async reopenFeedback(id: string): Promise<FeedbackReview> {
    const { data } = await apiClient.post(`/admin/quality/feedback/${id}/reopen/`, {});
    return data;
  },
  async knowledgeGaps(params?: { status?: string; priority?: string; space?: string }, signal?: AbortSignal): Promise<KnowledgeGap[]> {
    const { data } = await adminGet<KnowledgeGap[]>('/admin/quality/gaps/', { params, ...(signal ? { signal } : {}) });
    return unwrap<KnowledgeGap>(data, 'knowledge_gaps');
  },
  async createKnowledgeGap(body: {
    space: string;
    feedback?: string;
    question: string;
    priority?: string;
    suggested_source?: string;
  }): Promise<KnowledgeGap> {
    const { data } = await apiClient.post('/admin/quality/gaps/', body);
    return data;
  },
  async knowledgeQualityReport(): Promise<KnowledgeQualityReport> {
    const { data } = await apiClient.get('/admin/reports/knowledge-quality/');
    return data;
  },
  async exportQualityDataset(dataset: QualityExportDataset): Promise<Blob> {
    const { data } = await apiClient.get('/admin/reports/export/', {
      params: { dataset, format: 'csv' },
      responseType: 'blob',
    });
    return data;
  },
  async exportJobs(signal?: AbortSignal): Promise<ComplianceExportJob[]> {
    const { data } = await adminGet<ComplianceExportJob[]>('/admin/reports/export-jobs/', signal ? { signal } : undefined);
    return unwrap<ComplianceExportJob>(data, 'export_jobs');
  },
  async createExportJob(body: {
    dataset: QualityExportDataset;
    space?: string;
    date_from?: string;
    date_to?: string;
  }): Promise<ComplianceExportJob> {
    const { data } = await apiClient.post('/admin/reports/export-jobs/', body);
    return data;
  },
  async downloadExportJob(id: string): Promise<Blob> {
    const { data } = await apiClient.get(`/admin/reports/export-jobs/${id}/download/`, {
      responseType: 'blob',
    });
    return data;
  },
  async retryExportJob(id: string): Promise<ComplianceExportJob> {
    const { data } = await apiClient.post(`/admin/reports/export-jobs/${id}/retry/`, {});
    return data;
  },

  // --- Workspace management ---
  async listSpaces(params?: {
    status?: 'active' | 'archived';
    q?: string;
    organization?: string;
    business_line?: string;
    work_group?: string;
    office_location?: string;
    page?: number;
    page_size?: number;
  }, signal?: AbortSignal): Promise<{
    count: number;
    next: string | null;
    previous: string | null;
    results: AdminSpaceListItem[];
  }> {
    const config: Record<string, unknown> = {};
    if (signal) config.signal = signal;
    if (params) config.params = params;
    const { data } = await adminGet<{
      count: number;
      next: string | null;
      previous: string | null;
      results: AdminSpaceListItem[];
    }>('/admin/spaces/', config);
    return data;
  },
  async archiveSpace(id: string): Promise<AdminSpaceListItem> {
    const { data } = await apiClient.post(`/admin/spaces/${id}/archive/`, {});
    return data;
  },
  async restoreSpace(id: string): Promise<AdminSpaceListItem> {
    const { data } = await apiClient.post(`/admin/spaces/${id}/restore/`, {});
    return data;
  },
};

export interface AdminSpaceListItem {
  id: string;
  name: string;
  code: string;
  description: string;
  status: 'active' | 'archived';
  visibility: string;
  organization: string;
  organization_name: string;
  business_line: string | null;
  business_line_name: string | null;
  work_group: string | null;
  work_group_name: string | null;
  office_locations: Array<{ id: string; display_name: string }>;
  owner: string | null;
  owner_email: string | null;
  owner_name: string | null;
  lifecycle_version: number;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  member_count: number;
  document_count: number;
  reference_library_info: {
    id: string;
    name: string;
    category: string;
    status: 'published' | 'unpublished';
  } | null;
}
