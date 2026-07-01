# KnowPilot Long-Term Delivery and Audit Roadmap

**Baseline date:** 2026-07-01
**Source of truth:** `SPEC.MD` and
`audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md`

## Delivery Rules

1. A major phase is complete only when acceptance tests pass and its versioned
   test audit report exists under `audit_reports/`.
2. A failed audit blocks the next phase; remediation stays in the same version.
3. `SPEC_IMPLEMENTATION_PROGRESS.md` is updated only from fresh audit evidence.
4. Security boundaries use backend authorization; frontend guards are UX only.
5. Migrations, i18n, frontend build, and focused regression suites are standard
   gates whenever relevant.

## Roadmap

| Version / phase | Outcome | Major deliverables | Required audit artifact |
|---|---|---|---|
| V7.3 / Phase 3A | Protected document delivery | Object-authorized download API, raw media URL removal, download audit logs, frontend action | `audit_reports/v7.3/Phase3A_Document_Access_Test_Audit_Report_V7.3.md` |
| V7.3 / Phase 3B | Trustworthy upload validation | Consistent allowed types, extension/MIME/magic checks, safe text validation, manual/batch parity | `audit_reports/v7.3/Phase3B_File_Validation_Test_Audit_Report_V7.3.md` |
| V7.5 / Phase 3C | Retrieval safety | Allowlisted filter schema, mandatory `space_id`, active-document default, archived/expired exclusion, adversarial filter tests | `audit_reports/v7.5/Phase3C_Retrieval_Safety_Test_Audit_Report_V7.5.md` |
| V7.6 / Phase 3D | Governed document lifecycle | Explicit stale/expired/failed/archive transitions, admin errors, stale warnings, retry/re-index behavior | `audit_reports/v7.6/Phase3D_Document_Lifecycle_Test_Audit_Report_V7.6.md` |
| V8.0 / Phase 4A | Audit and governance closure | Sensitive-action coverage matrix, failed-access visibility, immutable API posture, scoped audit filters/export | `audit_reports/v8.0/Phase4A_Audit_Governance_Test_Audit_Report_V8.0.md` |
| V8.1 / Phase 4B | Operations dashboard | Health, ingestion queue, retry actions, model/API errors, token/latency/no-answer metrics | `audit_reports/v8.1/Phase4B_Operations_Metrics_Test_Audit_Report_V8.1.md` |
| V8.2 / Phase 4C | Knowledge quality dashboard | Stale sources, citation coverage, unused/high-use documents, quality drill-down | `audit_reports/v8.2/Phase4C_Knowledge_Quality_Test_Audit_Report_V8.2.md` |
| V9.0 / Phase 5A | Feedback loop | Helpful/unhelpful/incorrect/outdated/missing-source feedback tied to answer and citations | `audit_reports/v9.0/Phase5A_Feedback_Test_Audit_Report_V9.0.md` |
| V9.1 / Phase 5B | Review and gap workflow | Flagged-answer queue, assignments, resolution history, knowledge-gap tickets | `audit_reports/v9.1/Phase5B_Review_Workflow_Test_Audit_Report_V9.1.md` |
| V9.2 / Phase 5C | Reporting | Usage/compliance export, top unanswered questions, improvement trend reports | `audit_reports/v9.2/Phase5C_Compliance_Reporting_Test_Audit_Report_V9.2.md` |
| V10.0 / Hardening | Production readiness | Accessibility audit, mobile citation flows, performance budgets, stream cancellation, retry reliability, deployment/secrets/observability guide | `audit_reports/v10.0/Production_Readiness_Test_Audit_Report_V10.0.md` |

## Dependency Order

```text
3A secure delivery
  -> 3B safe ingestion
    -> 3C safe retrieval
      -> 3D governed lifecycle
        -> 4A complete audit evidence
          -> 4B operational metrics
            -> 4C knowledge quality
              -> 5A feedback capture
                -> 5B reviewer workflow
                  -> 5C reporting
                    -> production hardening
```

## Cross-Cutting Audit Matrix

Every report records:

- SPEC requirements and threat/quality risks in scope;
- exact commands, environment, exit codes, and test counts;
- migrations and Django system-check result;
- backend authorization and cross-space isolation evidence;
- frontend unit/i18n/build evidence when UI changes;
- manual inspection items that automation cannot prove;
- known warnings and residual risk;
- changed-file list and unrelated dirty-tree confirmation;
- GO/NO-GO decision and the next authorized phase.

## Deferred Product Decisions

The following remain product decisions rather than hidden implementation
assumptions: production access-code policy, cross-space search roles, project
space granularity, global-template override policy, and source quotation rules.
They must be resolved before a dependent phase begins.
