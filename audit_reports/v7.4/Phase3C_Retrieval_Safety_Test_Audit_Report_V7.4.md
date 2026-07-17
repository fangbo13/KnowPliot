# Phase 3C Retrieval Safety Test Audit Report — V7.4

**Date:** 2026-07-02

**Baseline commit:** `d4b9050`

**Phase commit subject:** `feat(rag): enforce safe space-scoped retrieval`
**Environment:** Windows, Python virtual environment, Django local-test settings, SQLite fallback; PostgreSQL SQL path verified with a mocked DB cursor.

## Scope and requirement traceability

| Requirement | Evidence | Result |
| --- | --- | --- |
| Retrieval cannot run without a space | Missing, blank, and malformed UUID tests | PASS |
| Cross-space chunks cannot be returned | Two-space SQLite retrieval test | PASS |
| Only active documents are eligible | Draft, processing, expired, stale, archived, and failed exclusion test | PASS |
| Filter keys are allowlisted | Raw dict and ORM traversal rejection tests | PASS |
| Filter IDs are validated | Invalid document/category UUID tests | PASS |
| SQLite/PostgreSQL semantics match | Shared normalized filter type and SQL assertions | PASS |
| PostgreSQL values are parameterized | Cursor SQL/parameter separation assertions | PASS |

## Changed interfaces

- `PgVectorRetriever.search()` now requires keyword-only `space_id`.
- `RetrievalFilters` supports only `document_ids` and `category_ids`.
- `RAGPipeline.retrieve_and_generate()` now requires keyword-only `space_id`.
- No database migration is required.

## Verification evidence

```text
python manage.py test apps.rag.test_phase3c_retrieval --settings=config.settings.local_test -v 1
6 tests passed.

python manage.py test apps.rag.test_phase3c_retrieval apps.knowledge.tests_phase3_governance apps.spaces apps.users.tests_v7_identity apps.users.tests_v7_smoke apps.scenario_templates.tests_phase2a --settings=config.settings.local_test -v 1
100 tests passed.

python manage.py check --settings=config.settings.local_test
Passed with the 3 previously documented django-allauth deprecation warnings.

python manage.py makemigrations --check --dry-run --settings=config.settings.local_test
No changes detected.
```

## Negative testing

- Confirmed the pre-change implementation accepted no space and returned
  inactive-document chunks.
- Confirmed arbitrary Django lookup dictionaries could influence SQLite
  retrieval before the typed allowlist.
- Confirmed invalid UUIDs now fail before embedding or query execution.

## Residual risks

- This workstation has no live PostgreSQL/pgvector service; SQL shape and
  parameterization are unit tested, while live integration remains in the
  production-hardening roadmap.
- Hybrid retrieval, reranking, and confidence markers remain outside Phase 3C.
- `SPEC.MD` contains legacy non-UTF-8 bytes and could not be safely patched by
  the repository editing tool; the UTF-8 progress tracker is authoritative for
  this phase until the SPEC encoding is normalized.
- The three django-allauth warnings and existing Vite chunk warnings are
  pre-existing and non-blocking.

## Verdict

**PASS** — Phase 3C meets the scoped retrieval safety gate and may proceed to
Phase 4A.
