# Phase 8 Product Completeness Design

## Release structure

Phase 8 is the V10 release line:

- Phase 8A / V10.0: Answer Quality and Evaluation
- Phase 8B / V10.1: Template Catalog and Isolated Knowledge Packs
- Phase 8C / V10.2: Accessibility and Product Closure

Each slice requires a versioned PASS audit before the next branch starts.

## Phase 8A architecture

Retrieval remains strictly single-space. A hybrid retriever gathers semantic
and lexical candidates, combines their ranks with Reciprocal Rank Fusion, then
applies deterministic freshness, relevance, and source-diversity rules. The
final result carries component scores so ranking remains explainable.

The pipeline derives a bounded confidence score and label from fused evidence,
source diversity, and result count. Insufficient evidence produces a refusal;
low confidence is marked for human review. A new SSE `quality` event and
persisted message fields expose this decision without revealing prompts or
internal credentials.

A versioned deterministic evaluation dataset and management command measure
Recall@5, MRR, refusal accuracy, isolation failures, and latency. Evaluation
runs are persisted and exposed through a scoped, read-only administrator API.

## Phase 8B architecture

Templates gain normalized categories, tags, explainable catalog ordering,
revision diff, and rollback-as-new-revision. Template knowledge assets point
only to source documents the template administrator can access.

Applying a template creates the space first, then physically copies each asset
file and document record into the target space and enqueues independent
ingestion jobs. Chunks and embeddings are never shared across spaces.
Application state records complete, partial-failure, and retryable outcomes.

## Phase 8C architecture

The final slice closes key chat and accessibility gaps: pinned sessions,
Markdown/printable-HTML exports, mobile citation and feedback workflows,
keyboard/focus behavior, screen-reader live regions, reduced motion, contrast,
and remaining critical-path i18n.

Automated accessibility checks and browser tests run at 390px, 768px, and
desktop widths. V10 smoke covers health, hybrid quality, template provisioning,
mobile citations, and session export.

## Boundaries

- No cross-space retrieval.
- No SSO implementation without a real identity-provider contract.
- The crawler removed in V6.0 is not restored.
- Printable HTML is the PDF path; no server-side PDF runtime is introduced.
- User-owned database, build cache, token, screenshot, and video files are
  excluded from all commits.
