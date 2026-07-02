# Phase 4C Operations and Knowledge Quality Design

## Release mapping

Phase 4A, Phase 4B, and Phase 4C are slices of the same V7.5 release. The
release branch is `Version_7.5`, and all three Phase 4 audit reports live under
`audit_reports/v7.5/`. Existing Git history is retained; only current release
metadata and report locations are corrected.

## Scope

Phase 4C closes the remaining Phase 4 operational loop:

- persistent ingestion queue visibility;
- safe, scoped retry of failed ingestion;
- model/API failure and token-usage telemetry;
- scoped document-use and retrieval-quality analysis;
- an admin UI that exposes these facts and retry actions.

Exports and answer-review workflows remain Phase 5.

## Ingestion job lifecycle

`knowledge.IngestionJob` is the durable source of truth for ingestion
operations. It records the document and space, requester, trigger, Celery task
id, attempt, terminal error, timestamps, and an optional `retry_of` link.

All supported upload, batch upload, reindex, and admin retry paths enqueue work
through one `enqueue_document_ingestion()` service. The retired crawler remains
outside the current product scope. The Celery task updates the job through
`queued -> processing -> succeeded|retrying|failed`.

The retry API:

- accepts only terminal failed jobs;
- scopes lookup through the caller's administered spaces;
- rejects archived documents;
- rejects retry if another queued/processing/retrying job exists;
- creates a new job linked to the failed one rather than mutating history;
- writes a scoped audit record.

## Model/API telemetry

`chat.ModelInvocation` records one row per attempted answer generation:
model, status (`success`, `failure`, `timeout`, `cancelled`), token count,
latency, safe error code, message/session/space, and timestamp. It never stores
prompts, answers, credentials, or raw exception text.

The stream handler writes a success record after persisting the answer, and a
failure/timeout/cancelled record on each terminal error path. Scoped metrics
calculate total and average tokens, completed calls, failures, error rate, and
per-model use from these rows.

## Knowledge-quality analysis

`GET /api/v1/admin/quality/documents/` returns scoped document rows with:

- status and effective date;
- chunk and citation counts;
- average citation relevance;
- last citation timestamp;
- flags for `unused`, `high_usage`, and `stale_source`.

Only active/stale documents are included by default. Query parameters may
filter status and risk flag. Aggregate counts also appear in `/admin/metrics/`.

## API and UI

- `GET /api/v1/admin/ingestion-jobs/`
- `POST /api/v1/admin/ingestion-jobs/{job_id}/retry/`
- `GET /api/v1/admin/quality/documents/`

The admin dashboard adds model/token/error metrics, ingestion queue and failed
jobs, safe retry controls, and document-quality rows. All endpoints reuse the
Phase 4A/4B admin-scope rules.

## Verification

Tests must prove cross-organization isolation, retry state guards, immutable
retry history, task lifecycle updates, safe telemetry, metric calculations,
document ranking/flags, UI API wiring, and the complete existing regression
suite. The V7.5 Phase 4C audit report is written only after all gates pass.
