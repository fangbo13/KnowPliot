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
  code: string;
  name: string;
  is_hierarchical: boolean;
  required: boolean;
  sort_order: number;
  status: string;
  terms: TaxonomyTerm[];
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

export const vizApi = {
  async getGraph(term?: string): Promise<{ nodes: GraphNode[]; edges: GraphEdge[]; term_filter: string | null }> {
    const { data } = await apiClient.get('/documents/graph/', { params: term ? { term } : undefined });
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
