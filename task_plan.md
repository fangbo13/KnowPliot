# Five-Hour Work Plan and Phase 3 Execution

## Goal
Review the current SPEC and implementation-progress documents, produce an
executable five-hour plan and long-term roadmap, then begin Phase 3 Knowledge
Governance Hardening with a versioned audit gate and audit report after every
major phase.

## Phases

| Phase | Status | Output |
|---|---|---|
| 1. Establish current project state | complete | SPEC/progress findings and constraints |
| 2. Select and sequence five-hour scope | complete | Time-boxed phases, dependencies, acceptance gates |
| 3. Write implementation and long-term plans | complete | Detailed plans in `docs/superpowers/plans/` |
| 4. Self-audit plans against SPEC | complete | Coverage, feasibility, and audit-report checks |
| 5. Implement Phase 3A with TDD | complete | Authenticated, object-authorized document delivery |
| 6. Audit Phase 3A | complete | `audit_reports/v7.3/Phase3A_Document_Access_Test_Audit_Report_V7.3.md` |
| 7. Design Phase 3B after Phase 3A passes | complete | `docs/superpowers/specs/2026-07-01-phase-3b-file-validation-design.md` |
| 8. Implement Phase 3B with TDD | complete | File-policy convergence and upload repair |
| 9. Audit Phase 3B | complete | `audit_reports/v7.3/Phase3B_File_Validation_Test_Audit_Report_V7.3.md` |
| 10. Implement and audit Phase 3C | complete | `audit_reports/v7.4/Phase3C_Retrieval_Safety_Test_Audit_Report_V7.4.md` |
| 11. Implement and audit Phase 4A | complete | `audit_reports/v7.5/Phase4A_Audit_Governance_Test_Audit_Report_V7.5.md` |
| 12. Implement and audit Phase 4B MVP | complete | `audit_reports/v7.5/Phase4B_Operations_Metrics_Test_Audit_Report_V7.5.md` |
| 13. Implement and audit Phase 4C | complete | `audit_reports/v7.5/Phase4C_Knowledge_Quality_Test_Audit_Report_V7.5.md` |

## Planning Constraints

- Total execution window: 5 hours.
- Every major implementation phase ends with an audit.
- Every phase audit produces a corresponding versioned report under `audit_reports/`.
- Preserve unrelated working-tree changes.
- The user explicitly requested that today's implementation begin after planning.
- Do not start a later phase until the preceding phase audit is complete and its
  report is saved under `audit_reports/`.
- The Phase 3A design requires user approval before implementation under the
  brainstorming skill's design gate.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `/goal` creation reported an unfinished goal already exists | 1 | Reused the active goal, which matches the user request |
| Recursive SPEC discovery used a malformed PowerShell regex and timed out | 1 | Replaced it with narrow `rg --files` filters; do not retry the malformed expression |
| Default `python` could not import Django during baseline verification | 1 | Locate and use the repository virtual-environment interpreter; do not rerun with system Python |
| Recursive Python discovery repeated the malformed trailing-backslash regex pattern and timed out | 2 | Stop recursive discovery; probe exact `.venv\Scripts\python.exe` and `backend\venv\Scripts\python.exe` paths |
| Worktree detection tried to call `.Trim()` on empty superproject output | 1 | Detection still proved this is a normal checkout; treat empty superproject output as null-safe in future checks |
| URL-resolution smoke command ran from repository root where `manage.py` is absent | 1 | Re-run from `backend/`; no product code or test result was affected |
| Large Phase 3B patch did not match mixed-line-ending serializer context | 1 | Confirmed no partial change, then applied smaller targeted patches |
| Python compile smoke used backend-relative paths from repository root | 1 | Re-run compile and all Django checks from `backend/` during the final audit |

---

# Next Goal Handoff Plan: Phase 7A–7C / V9.0–V9.2

## Goal

Complete Phase 7 Long-Run Operations / Scale Hardening from the `Version_8.2`
baseline, with one local version branch and one local commit per phase:
Phase 7A = `Version_9.0`, Phase 7B = `Version_9.1`, and Phase 7C =
`Version_9.2`. Each phase must follow the same execution rhythm:
failing tests first → minimal implementation → focused tests → full gates →
audit report → SPEC/progress/roadmap updates → local commit.

## Baseline and Guardrails

- Starting point: `Version_8.2` at commit `95f3be5`.
- Create local branches in order:
  - Phase 7A: `Version_9.0`
  - Phase 7B: `Version_9.1`
  - Phase 7C: `Version_9.2`
- Do not skip or merge version numbers. Each phase maps to exactly one version.
- Preserve unrelated user worktree changes. Do not stage or modify protected
  local artifacts unless the user explicitly authorizes it:
  - `backend/db.sqlite3`
  - `frontend/tsconfig.tsbuildinfo`
  - deleted `session_id.txt`
  - deleted `token.txt`
  - screenshots, videos, `.claude/`, `skills/`, and other untracked assets
- No push, no PR, no history rewrite.
- If `backend\manage.py check --deploy --settings=config.settings.prod` fails
  only because the local environment lacks PostgreSQL driver support
  (`psycopg` / `psycopg2`), record it as an environment limitation, not as a
  PASS.

## Phase 7A / V9.0: Long-Run Operations Baseline

### Implementation scope

- Add regression tests first for long-run operations health and maintenance:
  - health/readiness payload includes safe operational summaries
  - retention/export cleanup configuration is reported without leaking secrets
  - export cleanup dry-run reports candidates without mutation
  - expired export cleanup mutates only eligible expired jobs
- Implement minimal long-run operations baseline:
  - health payload fields for cleanup/backlog/retention status
  - safe retention configuration summaries
  - `cleanup_export_jobs --dry-run`
  - admin dashboard readiness labels for long-run operations

### Verification gate

Run the focused Phase 7A tests first, then the full gate:

```powershell
backend\venv\Scripts\python.exe backend\manage.py test apps.spaces.test_phase7a_long_run_ops --settings=config.settings.local_test -v 1
backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1
backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test
backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test
npm --prefix frontend run test
npm --prefix frontend run check:i18n
npm --prefix frontend run typecheck
npm --prefix frontend run build
backend\venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.prod
```

### Required output

- Audit report:
  `audit_reports/v9.0/Phase7A_Long_Run_Operations_Baseline_Audit_Report_V9.0.md`
- Documentation updates:
  - `SPEC.MD`
  - `progress.md`
  - roadmap section, if version mapping is stale
- Local commit:
  `chore(ops): add long-run operations baseline`

## Phase 7B / V9.1: Scale Hardening and Background Reliability

### Implementation scope

- Add failing tests first for reliability and scale paths:
  - failed export jobs can be retried with scoped permission checks
  - retry lineage is preserved
  - retry action is audited without exporting sensitive contents
  - SLA scanner supports dry-run/statistics
  - high-traffic notification/audit/ingestion/export paths have explicit
    indexes
- Implement minimal reliability hardening:
  - `ComplianceExportJob.retry_of`
  - scoped retry API:
    `POST /api/v1/admin/reports/export-jobs/{id}/retry/`
  - `export_job_retry` audit action
  - `scan_quality_sla --dry-run` statistics
  - scale-path database indexes
  - frontend retry control and safe error summaries

### Verification gate

Run the focused Phase 7B tests first, then the full gate:

```powershell
backend\venv\Scripts\python.exe backend\manage.py test apps.chat.test_phase7b_scale_reliability --settings=config.settings.local_test -v 1
backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1
backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test
backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test
npm --prefix frontend run test
npm --prefix frontend run check:i18n
npm --prefix frontend run typecheck
npm --prefix frontend run build
backend\venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.prod
```

### Required output

- Audit report:
  `audit_reports/v9.1/Phase7B_Scale_Hardening_Background_Reliability_Audit_Report_V9.1.md`
- Documentation updates:
  - `SPEC.MD`
  - `progress.md`
  - roadmap section, if version mapping is stale
- Local commit:
  `feat(ops): harden background reliability and scale paths`

## Phase 7C / V9.2: Operational Runbook and Regression Closure

### Implementation scope

- Add guard tests first for operational closure:
  - V9 operations runbook exists and covers `health degraded`,
    `export job failed`, `SLA backlog`, `migration`, `deploy check`,
    `smoke script`, and `rollback`
  - V9 smoke script validates frontend build artifacts
  - API smoke mode fails safely with JSON errors instead of traceback
  - `SPEC.MD`, `progress.md`, and roadmap consistently document
    Phase 7 = V9.0–V9.2, with V10.0 only as the next candidate
- Implement closure artifacts:
  - `docs/operations/KnowPilot_V9_Operations_Runbook.md`
  - `backend/scripts/smoke_v9_operations.py`
  - final documentation reconciliation for V9.0, V9.1, and V9.2

### Verification gate

Run the focused Phase 7C tests and V9 smoke check first, then the full gate:

```powershell
backend\venv\Scripts\python.exe backend\manage.py test apps.chat.test_phase7c_operational_closure --settings=config.settings.local_test -v 1
backend\venv\Scripts\python.exe backend\scripts\smoke_v9_operations.py --check-build-only --frontend-dist frontend\dist
backend\venv\Scripts\python.exe backend\manage.py test apps --settings=config.settings.local_test -v 1
backend\venv\Scripts\python.exe backend\manage.py check --settings=config.settings.local_test
backend\venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run --settings=config.settings.local_test
npm --prefix frontend run test
npm --prefix frontend run check:i18n
npm --prefix frontend run typecheck
npm --prefix frontend run build
backend\venv\Scripts\python.exe backend\manage.py check --deploy --settings=config.settings.prod
```

### Required output

- Audit report:
  `audit_reports/v9.2/Phase7C_Operational_Runbook_Regression_Closure_Audit_Report_V9.2.md`
- Documentation updates:
  - `SPEC.MD`
  - `progress.md`
  - roadmap section, confirming V10.0 is only the next candidate
- Local commit:
  `chore(release): complete v9 long-run operations readiness`

## Final Handoff Audit

After Phase 7C is committed, run a non-mutating final audit:

```powershell
git status --short --branch
git log --oneline --decorate -5
Test-Path audit_reports/v9.0/Phase7A_Long_Run_Operations_Baseline_Audit_Report_V9.0.md
Test-Path audit_reports/v9.1/Phase7B_Scale_Hardening_Background_Reliability_Audit_Report_V9.1.md
Test-Path audit_reports/v9.2/Phase7C_Operational_Runbook_Regression_Closure_Audit_Report_V9.2.md
```

Completion criteria:

- `Version_9.0`, `Version_9.1`, and `Version_9.2` each have their own local
  commit.
- All focused tests and full gates have recorded results.
- Production deploy check result is recorded honestly, including any
  PostgreSQL-driver environment limitation.
- All three audit reports exist and include environment, branch, baseline,
  requirement traceability, command results, warnings, residual risks, rollback
  recommendation, and final verdict.
- `SPEC.MD` and `progress.md` agree that Phase 7 maps to V9.0–V9.2.
- No protected local files or unrelated untracked assets are staged.
