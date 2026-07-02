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
  organization_id: string | null;
  business_line_id: string | null;
  space_id: string | null;
  result: 'success' | 'denied' | 'failure';
  created_at: string;
}

export interface AuditLogQuery {
  action?: string;
  result?: 'success' | 'denied' | 'failure';
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
  services: Record<
    'backend' | 'database' | 'redis' | 'celery' | 'vector_db' | 'llm',
    {
      status: ServiceHealthStatus;
      latency_ms?: number;
      detail?: string;
      error?: string;
    }
  >;
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
  async auditLogs(params?: AuditLogQuery): Promise<AuditLog[]> {
    const { data } = await apiClient.get('/audit/logs/', { params });
    return unwrap(data);
  },
  async health(): Promise<SystemHealth> {
    const { data } = await apiClient.get('/admin/health/');
    return data;
  },
  async metrics(): Promise<SystemMetrics> {
    const { data } = await apiClient.get('/admin/metrics/');
    return data;
  },
  async ingestionJobs(params?: {
    status?: IngestionJobStatus;
  }): Promise<IngestionJob[]> {
    const { data } = await apiClient.get('/admin/ingestion-jobs/', { params });
    return unwrap(data);
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
  }): Promise<DocumentQuality[]> {
    const { data } = await apiClient.get('/admin/quality/documents/', { params });
    return unwrap(data);
  },
  async feedbackReviews(params?: {
    status?: string;
    type?: string;
    space?: string;
    reviewer?: string;
  }): Promise<FeedbackReview[]> {
    const { data } = await apiClient.get('/admin/quality/feedback/', { params });
    return unwrap(data);
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
  async knowledgeGaps(params?: { status?: string; priority?: string; space?: string }): Promise<KnowledgeGap[]> {
    const { data } = await apiClient.get('/admin/quality/gaps/', { params });
    return unwrap(data);
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
};
