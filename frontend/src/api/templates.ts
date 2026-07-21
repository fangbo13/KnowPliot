/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Scenario Templates API client for the Phase 2 template center.

import apiClient, * as client from './client';

export interface ScenarioTemplate {
  id: string;
  name: string;
  code: string;
  description: string;
  scenario_type: 'onboarding' | 'audit' | 'tax' | 'consulting' | 'core_services' | 'standards_qa' | 'project_ai';
  default_language: string;
  icon: string;
  category?: { id: string; name: string; slug: string } | null;
  tags: Array<{ id: string; name: string; slug: string }>;
  featured: boolean;
  quick_questions: string[];
  prompt_policy: Record<string, any>;
  retrieval_policy: Record<string, any>;
  default_visibility: 'private' | 'business_line' | 'organization' | 'public_demo';
  is_active: boolean;
  organization?: string | null;
  organization_name?: string | null;
  business_line?: string | null;
  business_line_name?: string | null;
  can_manage: boolean;
  usage_count: number;
  last_applied_at: string | null;
  latest_version: number;
  current_revision_id: string | null;
  current_revision_version: number | null;
  current_revision_hash: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScenarioTemplateRevision {
  id: string;
  template: string;
  version: number;
  snapshot: Record<string, any>;
  snapshot_hash: string;
  published_at: string | null;
  change_note: string | null;
  created_by: string | null;
  created_by_email: string | null;
  created_at: string;
}

export interface ScenarioTemplateRevisionPreview {
  id: string;
  template_id: string;
  version: number;
  snapshot_hash: string;
  published_at: string | null;
  included_components: string[];
  excluded_components: string[];
  components: Record<string, unknown>;
}

export interface ActivateTemplateRevisionPayload {
  expected_template_version: number;
  expected_revision_hash: string;
}

export interface ScenarioTemplateApplication {
  id: string;
  template: string;
  template_code: string;
  template_name: string;
  space: string;
  space_code: string;
  space_name: string;
  organization: string | null;
  organization_name: string | null;
  business_line: string | null;
  business_line_name: string | null;
  created_by: string | null;
  created_by_email: string | null;
  template_snapshot: Record<string, any>;
  created_at: string;
}

export interface CreateSpaceFromTemplatePayload {
  name: string;
  code: string;
  organization?: string | null;
  business_line?: string | null;
  visibility?: 'private' | 'business_line' | 'organization' | 'public_demo';
}

export interface WorkspaceCreationRequestResult {
  request_id: string;
  status: 'pending';
  request_version: number;
  status_url: string;
  expires_at: string | null;
}

export interface CloneScenarioTemplatePayload {
  name: string;
  code: string;
  organization?: string | null;
  business_line?: string | null;
  is_active: boolean;
}

export interface TemplateListParams {
  q?: string;
  scenario_type?: ScenarioTemplate['scenario_type'];
  is_active?: boolean;
  scope?: 'global' | 'organization' | 'business_line';
  organization?: string;
  business_line?: string;
  category?: string;
  tags?: string;
  sort?: 'recommended' | 'popular' | 'recent' | 'name';
  page?: number;
}

function templateGet<T>(url: string, config?: Record<string, unknown>) {
  let getSignal: (() => AbortSignal | undefined) | undefined;
  let sharedGet: (<R>(path: string, options?: unknown) => Promise<{ data: R }>) | undefined;
  try {
    getSignal = (client as unknown as Record<string, unknown>).getRequestSignal as typeof getSignal;
    sharedGet = (client as unknown as Record<string, unknown>).coalescedGet as typeof sharedGet;
  } catch {
    // Keep compatibility with narrow test mocks that expose only apiClient.
  }
  const effectiveSignal = (config?.signal as AbortSignal | undefined) ?? getSignal?.();
  const requestConfig = effectiveSignal ? { ...(config ?? {}), signal: effectiveSignal } : config;
  return sharedGet
    ? sharedGet<T>(url, requestConfig)
    : requestConfig === undefined ? apiClient.get<T>(url) : apiClient.get<T>(url, requestConfig);
}

function unwrap<T>(data: unknown, resource = 'templates'): T[] {
  if (Array.isArray(data)) return data as T[];
  if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: T[] }).results;
  }
  throw new Error(`invalid_${resource}_response`);
}

export const templatesApi = {
  async list(params?: TemplateListParams, signal?: AbortSignal): Promise<ScenarioTemplate[]> {
    const { data } = await templateGet<ScenarioTemplate[]>('/templates/', { params, ...(signal ? { signal } : {}) });
    return unwrap<ScenarioTemplate>(data);
  },

  async get(id: string, signal?: AbortSignal): Promise<ScenarioTemplate> {
    const { data } = await templateGet<ScenarioTemplate>(`/templates/${id}/`, signal ? { signal } : undefined);
    return data;
  },

  async create(body: Partial<ScenarioTemplate>): Promise<ScenarioTemplate> {
    const { data } = await apiClient.post('/templates/', body);
    return data;
  },

  async update(id: string, body: Partial<ScenarioTemplate>): Promise<ScenarioTemplate> {
    const { data } = await apiClient.patch(`/templates/${id}/`, body);
    return data;
  },

  async createSpace(templateId: string, body: CreateSpaceFromTemplatePayload): Promise<WorkspaceCreationRequestResult> {
    const { data } = await apiClient.post(`/templates/${templateId}/create-space/`, body, {
      headers: { 'Idempotency-Key': crypto.randomUUID() },
    });
    return data;
  },
  async applications(templateId: string, signal?: AbortSignal): Promise<ScenarioTemplateApplication[]> {
    const { data } = await templateGet<ScenarioTemplateApplication[]>(`/templates/${templateId}/applications/`, signal ? { signal } : undefined);
    return unwrap<ScenarioTemplateApplication>(data, 'template_applications');
  },
  async revisions(templateId: string, signal?: AbortSignal): Promise<ScenarioTemplateRevision[]> {
    const { data } = await templateGet<ScenarioTemplateRevision[]>(`/templates/${templateId}/revisions/`, signal ? { signal } : undefined);
    return unwrap<ScenarioTemplateRevision>(data, 'template_revisions');
  },
  async revisionPreview(
    templateId: string,
    revisionId: string,
    signal?: AbortSignal,
  ): Promise<ScenarioTemplateRevisionPreview> {
    const { data } = await templateGet<ScenarioTemplateRevisionPreview>(
      `/templates/${templateId}/revisions/${revisionId}/preview/`,
      signal ? { signal } : undefined,
    );
    return data;
  },
  async activateRevision(
    templateId: string,
    revisionId: string,
    body: ActivateTemplateRevisionPayload,
  ): Promise<ScenarioTemplateRevision> {
    const { data } = await apiClient.post(
      `/templates/${templateId}/revisions/${revisionId}/activate/`,
      body,
      { headers: { 'Idempotency-Key': crypto.randomUUID() } },
    );
    return data;
  },
  async clone(templateId: string, body: CloneScenarioTemplatePayload): Promise<ScenarioTemplate> {
    const { data } = await apiClient.post(`/templates/${templateId}/clone/`, body);
    return data;
  },
  async archive(templateId: string): Promise<ScenarioTemplate> {
    const { data } = await apiClient.post(`/templates/${templateId}/archive/`);
    return data;
  },
  async restore(templateId: string): Promise<ScenarioTemplate> {
    const { data } = await apiClient.post(`/templates/${templateId}/restore/`);
    return data;
  },
  async diff(templateId: string, from: number, to: number) {
    const { data } = await apiClient.get(`/templates/${templateId}/diff/`, {
      params: { from, to },
    });
    return data as {
      from: number;
      to: number;
      changes: Record<string, { from: unknown; to: unknown }>;
    };
  },
  async rollback(templateId: string, revision: number, expectedTemplateVersion: number): Promise<ScenarioTemplate> {
    const { data } = await apiClient.post(`/templates/${templateId}/rollback/`, {
      revision,
      expected_template_version: expectedTemplateVersion,
    });
    return data;
  },
};
