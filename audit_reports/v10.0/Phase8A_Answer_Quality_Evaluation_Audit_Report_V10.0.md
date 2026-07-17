# Phase 8A Answer Quality & Evaluation Audit Report V10.0

## Verdict

**PASS**

Phase 8A meets the V10.0 functional, isolation, quality, migration, frontend,
and Docker PostgreSQL/pgvector gates.

## Environment

- Date: 2026-07-03 (Asia/Shanghai)
- Branch: `Version_10.0`
- Baseline commit: `e2dce0f`
- Local tests: Python 3.13, SQLite in-memory
- Integration: Docker 29.5.3, PostgreSQL 16 + pgvector, Redis 7
- Compose services: database, Redis, backend, Celery worker, frontend all up

## Requirement Trace

| Requirement | Evidence | Result |
|---|---|---|
| Mandatory single-space retrieval | isolation and hybrid retrieval tests | PASS |
| Active documents only | lexical and existing retrieval safety tests | PASS |
| pgvector + PostgreSQL FTS | Docker PostgreSQL Phase 8A suite | PASS |
| Parameterized query handling | ORM FTS and existing pgvector parameter tests | PASS |
| RRF and deterministic reranking | ranking tests | PASS |
| Maximum two chunks per document | diversity test | PASS |
| Confidence and review metadata | model, serializer, pipeline tests | PASS |
| Low-evidence refusal | no-LLM refusal tests | PASS |
| SSE quality event | pipeline and chat SSE persistence tests | PASS |
| Read-only evaluation API | permission and method tests | PASS |
| Fixed, idempotent corpus | seed command executed twice; 2 documents/2 chunks | PASS |

## Evaluation Metrics

- Dataset: `phase8a-v1`
- Recall@5: **1.0** (gate ≥ 0.80)
- MRR: **1.0** (gate ≥ 0.65)
- Refusal accuracy: **1.0** (gate = 1.0)
- Cross-space leaks: **0**
- PostgreSQL retrieval p95: **11 ms** (gate < 1000 ms)

## Verification Results

- Backend full suite: **182 tests passed** in 149.379 seconds.
- Phase 8A local suite: **18 tests passed**.
- Phase 8A Docker PostgreSQL suite: **19 tests passed**.
- Django local check: PASS.
- Migration drift check: PASS, no changes detected.
- Django production deploy check: PASS.
- Frontend: **49 tests passed**.
- i18n: PASS, 52 source files checked.
- TypeScript typecheck: PASS.
- Production frontend build: PASS, no new warnings.
- `docker compose config --quiet`: PASS.
- All five compose services: running; database and Redis healthy.

## Migration Audit

- `chat.0010_message_quality_fields` applied in clean SQLite and PostgreSQL test databases.
- `chat.0011_ragevaluationrun` applied in clean SQLite and PostgreSQL test databases.
- No model/migration drift remains.

## Negative and Failure Coverage

- Non-admin evaluation access returns 403; write attempts return 405.
- Missing, invalid, or foreign space data cannot enter retrieval.
- Archived, stale, failed, and other non-active documents remain excluded.
- No evidence and weak evidence refuse without invoking the LLM.
- Common stop words cannot manufacture lexical evidence.
- PostgreSQL's tiny no-match `ts_rank` sentinel is excluded.
- Evaluation failures persist a safe failed run instead of fabricating metrics.

## Known Warnings and Residual Risk

- Expected HTTP 4xx/5xx messages originate from negative-path tests.
- The reused local PostgreSQL volume required `CREATEDB` on the application
  role and pgvector preinstallation in `template1` for isolated Django tests.
  Fresh compose volumes create the configured database owner directly.
- The benchmark corpus is intentionally small and deterministic; broader
  domain datasets remain future quality work.

## Final Decision

Phase 8A / V10.0 is approved. Phase 8B may begin from the V10.0 commit.
