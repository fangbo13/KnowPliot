/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

import { coalescedGet, getRequestSignal } from './client';

interface ScopeIdentity {
  id: string;
  code?: string;
  slug?: string;
  name: string;
}

export interface PlatformKnowledgeDocument {
  id: string;
  title: string;
  status: string;
  version: number;
  organization: ScopeIdentity | null;
  business_line: ScopeIdentity | null;
  work_group: ScopeIdentity | null;
  space: { id: string | null; code: string | null; name: string };
  created_at: string;
  updated_at: string;
}

export interface PlatformKnowledgeFilters {
  q?: string;
  organization_id?: string;
  business_line_id?: string;
  work_group_id?: string;
  space_id?: string;
  status?: string;
  cursor?: string;
}

export interface PlatformKnowledgePage {
  results: PlatformKnowledgeDocument[];
  next_cursor: string | null;
}

export const platformKnowledgeApi = {
  async list(filters: PlatformKnowledgeFilters, signal?: AbortSignal): Promise<PlatformKnowledgePage> {
    const effectiveSignal = signal ?? getRequestSignal();
    const params = Object.fromEntries(
      Object.entries(filters).filter(([, value]) => typeof value === 'string' && value.trim()),
    );
    const { data } = await coalescedGet<PlatformKnowledgePage>('/admin/documents/', {
      params,
      ...(effectiveSignal ? { signal: effectiveSignal } : {}),
    });
    if (!data || !Array.isArray(data.results)) throw new Error('invalid_platform_knowledge_response');
    return data;
  },
};
