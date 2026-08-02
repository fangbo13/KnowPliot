/*
 * Copyright (c) 2026 Haibo Fang.
 * Licensed under the CC BY-NC-SA 4.0 License.
 * See LICENSE file in the project root for full license details.
 */

// Knowledge iteration spec — taxonomy / review gate / visualization API client.
// All endpoints live under /documents/ and are scoped by the X-Space-Id header
// that apiClient injects automatically.

import apiClient from './client';

// ── Taxonomy (spec §2) ───────────────────────────────────────────────

export interface TaxonomyTerm {
  id: string;
  dimension: string;
  dimension_code: string;
  parent: string | null;
  code: string;
  label: string;
  sort_order: number;
  status: string;
}

export interface TaxonomyDimension {
  id: string;
  business_line: string | null;
  space: string | null;
  code: string;
  name: string;
  is_hierarchical: boolean;
  required: boolean;
  sort_order: number;
  status: string;
  terms: TaxonomyTerm[];
}

// KB optimization spec §3.1 — preset catalog entry for the creation wizard.
export interface TaxonomyPresetTerm {
  code: string;
  label: string;
  children?: TaxonomyPresetTerm[];
}

export interface TaxonomyPreset {
  code: string;
  name: string;
  description: string;
  dimensions: Array<{
    code: string;
    name: string;
    required: boolean;
    is_hierarchical: boolean;
    terms: TaxonomyPresetTerm[];
  }>;
}

export interface DocumentTagInfo {
  term_id: string;
  code: string;
  label: string;
  dimension: string;
}

export interface TermOwnership {
  id: string;
  space: string;
  term: string;
  term_code: string;
  term_label: string;
  owner: string;
  owner_name: string;
  created_at: string;
}

export const taxonomyApi = {
  async getDimensions(): Promise<TaxonomyDimension[]> {
    const { data } = await apiClient.get('/documents/taxonomy/dimensions/');
    return data;
  },

  async getDocumentTags(documentId: string): Promise<DocumentTagInfo[]> {
    const { data } = await apiClient.get(`/documents/${documentId}/tags/`);
    return data;
  },

  async setDocumentTags(documentId: string, termIds: string[]): Promise<{ terms: string[] }> {
    const { data } = await apiClient.put(`/documents/${documentId}/tags/`, { term_ids: termIds });
    return data;
  },

  async getTermOwners(): Promise<TermOwnership[]> {
    const { data } = await apiClient.get('/documents/term-owners/');
    return data;
  },

  async assignTermOwner(body: { term: string; owner: string }): Promise<TermOwnership> {
    const { data } = await apiClient.post('/documents/term-owners/', body);
    return data;
  },

  async removeTermOwner(id: string): Promise<void> {
    await apiClient.delete(`/documents/term-owners/${id}/`);
  },

  async getMyTerms(): Promise<{
    terms: TermOwnership[];
    documents: Array<{ id: string; title: string; status: string; version: number; updated_at: string }>;
  }> {
    const { data } = await apiClient.get('/documents/my-terms/');
    return data;
  },

  async confirmFresh(documentId: string): Promise<{ id: string; status: string; last_reviewed_at: string }> {
    const { data } = await apiClient.post(`/documents/${documentId}/confirm-fresh/`);
    return data;
  },

  // KB optimization spec §3.1 — space-private taxonomy management.
  async createDimension(body: {
    code: string;
    name: string;
    is_hierarchical?: boolean;
    required?: boolean;
    sort_order?: number;
  }): Promise<TaxonomyDimension> {
    const { data } = await apiClient.post('/documents/taxonomy/dimensions/', body);
    return data;
  },

  async updateDimension(
    id: string,
    body: Partial<{ name: string; required: boolean; sort_order: number; status: string; is_hierarchical: boolean }>,
  ): Promise<TaxonomyDimension> {
    const { data } = await apiClient.patch(`/documents/taxonomy/dimensions/${id}/`, body);
    return data;
  },

  async createTerm(body: {
    dimension: string;
    code: string;
    label: string;
    parent?: string | null;
    sort_order?: number;
  }): Promise<TaxonomyTerm> {
    const { data } = await apiClient.post('/documents/taxonomy/terms/', body);
    return data;
  },

  async updateTerm(
    id: string,
    body: Partial<{ label: string; sort_order: number; status: string }>,
  ): Promise<TaxonomyTerm> {
    const { data } = await apiClient.patch(`/documents/taxonomy/terms/${id}/`, body);
    return data;
  },

  async getPresets(): Promise<{ presets: TaxonomyPreset[] }> {
    const { data } = await apiClient.get('/documents/taxonomy/presets/');
    return data;
  },

  async seedDefaults(preset = 'audit_default'): Promise<{ created: number; dimensions: TaxonomyDimension[] }> {
    const { data } = await apiClient.post('/documents/taxonomy/seed-defaults/', { preset });
    return data;
  },
};

// ── Reference libraries (KB optimization spec §3.2) ───────────────────

export interface ReferenceLibrary {
  id: string;
  space: string;
  space_name: string;
  space_code: string;
  name: string;
  description: string;
  category: 'ifrs' | 'cas' | 'ipo_cases' | 'policy' | 'other';
  status: 'published' | 'unpublished';
  is_official: boolean;
  is_favorite: boolean;
  favorite_position: number | null;
  published_at: string | null;
  created_at: string;
}

export interface SpaceLibraryReference {
  id: string;
  space: string;
  library: string;
  library_name: string;
  library_category: string;
  library_status: string;
  enabled: boolean;
  created_at: string;
}

export const libraryApi = {
  // Platform admin management.
  async list(): Promise<ReferenceLibrary[]> {
    const { data } = await apiClient.get('/documents/libraries/');
    return data;
  },

  async create(body: {
    space: string;
    name: string;
    description?: string;
    category?: string;
    status?: string;
  }): Promise<ReferenceLibrary> {
    const { data } = await apiClient.post('/documents/libraries/', body);
    return data;
  },

  async update(
    id: string,
    body: Partial<{ name: string; description: string; category: string; status: string; is_official: boolean }>,
  ): Promise<ReferenceLibrary> {
    const { data } = await apiClient.patch(`/documents/libraries/${id}/`, body);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/documents/libraries/${id}/`);
  },

  // Global official catalog for onboarded users; favorites are ordered first.
  async catalog(): Promise<ReferenceLibrary[]> {
    const { data } = await apiClient.get('/reference-libraries/');
    return data;
  },

  async favorite(id: string, position?: number): Promise<ReferenceLibrary> {
    const { data } = await apiClient.post(
      `/reference-libraries/${id}/favorite/`,
      position == null ? {} : { position },
    );
    return data;
  },

  async unfavorite(id: string): Promise<void> {
    await apiClient.delete(`/reference-libraries/${id}/favorite/`);
  },

  // Space-scoped references (X-Space-Id injected by apiClient).
  async getReferences(): Promise<SpaceLibraryReference[]> {
    const { data } = await apiClient.get('/documents/library-references/');
    return data;
  },

  async addReference(libraryId: string): Promise<SpaceLibraryReference> {
    const { data } = await apiClient.post('/documents/library-references/', { library: libraryId });
    return data;
  },

  async toggleReference(id: string, enabled: boolean): Promise<SpaceLibraryReference> {
    const { data } = await apiClient.patch(`/documents/library-references/${id}/`, { enabled });
    return data;
  },

  async removeReference(id: string): Promise<void> {
    await apiClient.delete(`/documents/library-references/${id}/`);
  },
};

// ── Review gate (spec §3) ────────────────────────────────────────────

export interface ConflictHint {
  document_id: string;
  title: string;
  score: number;
}

export interface DiffSummary {
  old_line_count: number;
  new_line_count: number;
  added_lines: number;
  removed_lines: number;
  changed_blocks: number;
  samples: Array<{ tag: string; old_lines: string[]; new_lines: string[] }>;
}

export interface ReviewRequestInfo {
  id: string;
  document: {
    id: string;
    title: string;
    version: number;
    status: string;
    parent_document: string | null;
  };
  submitted_by: { id: string; name: string };
  reviewer: { id: string; name: string } | null;
  diff_summary: DiffSummary | Record<string, never>;
  conflict_hints: ConflictHint[];
  decision: 'pending' | 'approved' | 'rejected';
  comment: string;
  decided_at: string | null;
  created_at: string;
}

export const reviewApi = {
  async submitReview(documentId: string): Promise<ReviewRequestInfo> {
    const { data } = await apiClient.post(`/documents/${documentId}/submit-review/`);
    return data;
  },

  async getQueue(decision: 'pending' | 'approved' | 'rejected' | 'all' = 'pending'): Promise<ReviewRequestInfo[]> {
    const { data } = await apiClient.get('/documents/review-queue/', { params: { decision } });
    return data;
  },

  async approve(
    reviewId: string,
    body: { comment?: string; mark_stale_ids?: string[] } = {},
  ): Promise<ReviewRequestInfo & { publish?: unknown; stale_marked?: string[] }> {
    const { data } = await apiClient.post(`/documents/reviews/${reviewId}/approve/`, body);
    return data;
  },

  async reject(reviewId: string, body: { comment?: string } = {}): Promise<ReviewRequestInfo> {
    const { data } = await apiClient.post(`/documents/reviews/${reviewId}/reject/`, body);
    return data;
  },
};

// ── Visualization (spec §5) ──────────────────────────────────────────

export interface GraphNode {
  id: string;
  title: string;
  status: string;
  version: number;
  terms: string[];
  freshness: number;
  incoming_links: number;
  updated_at: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  kind: 'link' | 'term' | 'similar';
  term?: string;
  anchor?: string;
  score?: number;
}

export interface TimelineData {
  months: Array<{ month: string; versions: number; new_documents: number }>;
  fiscal_years: Array<{ code: string; label: string; documents: number }>;
}

export interface DashboardData {
  review_backlog: Array<{
    review_id: string;
    document_id: string;
    title: string;
    version: number;
    submitted_by: string;
    submitted_at: string;
    conflicts: number;
  }>;
  review_pending_count: number;
  coverage: Array<{
    term_id: string;
    code: string;
    label: string;
    dimension: string;
    documents: number;
    avg_freshness: number | null;
  }>;
  uncovered_terms: Array<{ code: string; label: string; dimension: string }>;
  stale_documents: Array<{ id: string; title: string; status: string; updated_at: string; freshness: number | null }>;
  expiring_documents: Array<{ id: string; title: string; effective_to: string }>;
  quality: {
    window_days: number;
    total_answers: number;
    refusals: number;
    refusal_rate: number | null;
    needs_human_review: number;
    confidence_distribution: Record<string, number>;
    feedback_submitted: number;
    knowledge_gaps_created: number;
    knowledge_gaps_resolved: number;
  };
}

export interface BacklinkInfo {
  id: string;
  title: string;
  anchor_text: string;
  status: string;
  updated_at: string;
}

export const vizApi = {
  async getGraph(
    term?: string,
    local?: { center: string; depth: number },
  ): Promise<{
    nodes: GraphNode[];
    edges: GraphEdge[];
    term_filter: string | null;
    mode?: 'global' | 'local';
    center?: string;
    depth?: number;
  }> {
    const params: Record<string, string | number> = {};
    if (term) params.term = term;
    if (local) {
      params.center = local.center;
      params.depth = local.depth;
    }
    const { data } = await apiClient.get('/documents/graph/', {
      params: Object.keys(params).length ? params : undefined,
    });
    return data;
  },

  // KB optimization spec §3.4 — Obsidian-style backlinks.
  async getBacklinks(documentId: string): Promise<{ document_id: string; backlinks: BacklinkInfo[] }> {
    const { data } = await apiClient.get(`/documents/${documentId}/backlinks/`);
    return data;
  },

  async getTimeline(months = 24): Promise<TimelineData> {
    const { data } = await apiClient.get('/documents/timeline/', { params: { months } });
    return data;
  },

  async getDashboard(): Promise<DashboardData> {
    const { data } = await apiClient.get('/documents/dashboard/');
    return data;
  },
};
