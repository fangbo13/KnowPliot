# Phase 8 / V10 Product Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining answer-quality, template-replication, mobile, and accessibility gaps through audited V10.0-V10.2 releases.

**Architecture:** Preserve single-space security while adding explainable hybrid retrieval and evaluation, isolated template knowledge-pack cloning, and accessible product workflows. Each release slice is independently migrated, tested, audited, and committed.

**Tech Stack:** Django/DRF, PostgreSQL/pgvector, SQLite test fallback, Celery/Redis, React/TypeScript/Ant Design, Vitest, Playwright, Docker Compose.

---

## Phase 8A / V10.0

- [ ] Add RED tests for lexical retrieval, RRF, deterministic reranking,
  source diversity, confidence, refusal, isolation, and SSE quality.
- [ ] Add hybrid retrieval and persisted answer-quality fields.
- [ ] Add evaluation dataset, evaluation command/model, and scoped read API.
- [ ] Add frontend confidence/review indicators and tests.
- [ ] Run focused, full, production, Docker, and V10.0 smoke gates.
- [ ] Write `audit_reports/v10.0/Phase8A_Answer_Quality_Evaluation_Audit_Report_V10.0.md`.
- [ ] Reconcile SPEC/progress and commit
  `feat(rag): add hybrid retrieval and evaluation`.

## Phase 8B / V10.1

- [ ] Create `Version_10.1` only after V10.0 PASS.
- [ ] Add RED tests for catalog filters/order, diff/rollback, asset scope,
  physical cloning, partial failure, retry, and isolation.
- [ ] Add template categories/tags, catalog behavior, revision operations,
  knowledge assets, application provisioning, and UI.
- [ ] Run focused, full, production, Docker, and V10.1 smoke gates.
- [ ] Write `audit_reports/v10.1/Phase8B_Template_Knowledge_Pack_Audit_Report_V10.1.md`.
- [ ] Reconcile SPEC/progress and commit
  `feat(templates): add catalog and isolated knowledge packs`.

## Phase 8C / V10.2

- [ ] Create `Version_10.2` only after V10.1 PASS.
- [ ] Add RED tests for pinning, exports, ownership, keyboard/focus, live
  regions, reduced motion, contrast, mobile citations, and i18n.
- [ ] Implement chat/session closure and accessibility behavior.
- [ ] Add V10 smoke and browser checks at 390px, 768px, and desktop.
- [ ] Run all local, production, Docker, accessibility, and browser gates.
- [ ] Write `audit_reports/v10.2/Phase8C_Accessibility_Product_Closure_Audit_Report_V10.2.md`.
- [ ] Mark Phase 8 actual PASS and commit
  `feat(product): close accessibility and mobile workflows`.

## Stop conditions

- Any cross-space retrieval or asset leak blocks the release.
- A failed migration, test, deploy check, Docker smoke, or required browser
  check produces an Incomplete Audit and blocks the next branch.
- No phase is marked complete from code inspection alone.
