/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Scenario Templates API client for the Phase 2 template center.

import apiClient from './client';
import type { KnowledgeSpace } from './spaces';

export interface ScenarioTemplate {
  id: string;
  name: string;
  code: string;
  description: string;
  scenario_type: 'onboarding' | 'audit' | 'tax' | 'consulting' | 'core_services' | 'standards_qa' | 'project_ai';
  default_language: string;
  icon: string;
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
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScenarioTemplateRevision {
  id: string;
  template: string;
  version: number;
  snapshot: Record<string, any>;
  change_note: string | null;
  created_by: string | null;
  created_by_email: string | null;
  created_at: string;
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
}

const unwrap = (data: any) => (Array.isArray(data) ? data : data.results ?? []);

export const templatesApi = {
  async list(params?: TemplateListParams): Promise<ScenarioTemplate[]> {
    const { data } = await apiClient.get('/templates/', { params });
    return unwrap(data);
  },

  async get(id: string): Promise<ScenarioTemplate> {
    const { data } = await apiClient.get(`/templates/${id}/`);
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

  async createSpace(templateId: string, body: CreateSpaceFromTemplatePayload): Promise<KnowledgeSpace> {
    const { data } = await apiClient.post(`/templates/${templateId}/create-space/`, body);
    return data;
  },
  async applications(templateId: string): Promise<ScenarioTemplateApplication[]> {
    const { data } = await apiClient.get(`/templates/${templateId}/applications/`);
    return unwrap(data);
  },
  async revisions(templateId: string): Promise<ScenarioTemplateRevision[]> {
    const { data } = await apiClient.get(`/templates/${templateId}/revisions/`);
    return unwrap(data);
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
};
