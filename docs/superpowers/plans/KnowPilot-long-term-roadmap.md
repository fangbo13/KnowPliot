# KnowPilot Long-Term Delivery and Audit Roadmap

**Baseline date:** 2026-07-02
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
| V7.4 / Phase 3C | Retrieval safety | Allowlisted filter schema, mandatory `space_id`, active-document default, archived/expired exclusion, adversarial filter tests | `audit_reports/v7.4/Phase3C_Retrieval_Safety_Test_Audit_Report_V7.4.md` |
| V7.5 / Phase 4A | Audit and governance closure | Sensitive-action coverage matrix, failed-access visibility, immutable API posture, scoped audit filters | `audit_reports/v7.5/Phase4A_Audit_Governance_Test_Audit_Report_V7.5.md` |
| V7.5 / Phase 4B | Operations and lifecycle MVP | Real service health, scoped usage/quality/security metrics, stale/archive lifecycle, provenance-preserving archive UX | `audit_reports/v7.5/Phase4B_Operations_Metrics_Test_Audit_Report_V7.5.md` |
| V7.5 / Phase 4C | Operations and quality completion | Ingestion queue/retry, model/API/token metrics, unused/high-use documents, quality drill-down | `audit_reports/v7.5/Phase4C_Knowledge_Quality_Test_Audit_Report_V7.5.md` |
| V7.6 / Phase 5A | Feedback loop | Helpful/unhelpful/incorrect/outdated/missing-source feedback tied to answer and citations | `audit_reports/V7.6/Phase5A_Feedback_Test_Audit_Report_V7.6.md` |
| V7.7 / Phase 5B | Review and gap workflow | Flagged-answer queue, assignments, resolution history, knowledge-gap tickets | `audit_reports/V7.7/Phase5B_Review_Workflow_Test_Audit_Report_V7.7.md` |
| V7.8 / Phase 5C | Reporting | Usage/compliance export, top unanswered questions, improvement trend reports | `audit_reports/V7.8/Phase5C_Compliance_Reporting_Test_Audit_Report_V7.8.md` |
| V8.0 / Phase 6A | Production hardening baseline | Readiness health checks, safe API error shape, admin readiness UI, deploy-check evidence | `audit_reports/v8.0/Phase6A_Production_Baseline_Test_Audit_Report_V8.0.md` |
| V8.1 / Phase 6B | Async operations and SLA alerts | Async compliance export jobs, export-complete notifications, quality SLA scanner, SLA UI | `audit_reports/v8.1/Phase6B_Async_Operations_Test_Audit_Report_V8.1.md` |
| V8.2 / Phase 6C | Release readiness and regression closure | Performance indexes, V8 smoke script, release readiness report, V8 documentation closure | `audit_reports/v8.2/Phase6C_Release_Readiness_Test_Audit_Report_V8.2.md` |
| V9.0 / Phase 7A | Long-run operations baseline | Readiness/liveness/dependency health, long-run cleanup config, export cleanup command, admin operations visibility | `audit_reports/v9.0/Phase7A_Long_Run_Operations_Baseline_Audit_Report_V9.0.md` |
| V9.1 / Phase 7B | Scale hardening and background reliability | Export retry, SLA scanner dry-run/statistics, duplicate-operation prevention, scale-path indexes | `audit_reports/v9.1/Phase7B_Scale_Hardening_Background_Reliability_Audit_Report_V9.1.md` |
| V9.2 / Phase 7C | Operational runbook and regression closure | V9 smoke checks, operational runbook, final regression audit, Phase 7 documentation closure | `audit_reports/v9.2/Phase7C_Operational_Runbook_Regression_Closure_Audit_Report_V9.2.md` |
| V10.0 / Phase 8A | Answer quality and evaluation | Single-space hybrid retrieval, explainable ranking, confidence/refusal policy, deterministic evaluation | `audit_reports/v10.0/Phase8A_Answer_Quality_Evaluation_Audit_Report_V10.0.md` |
| V10.1 / Phase 8B | Template catalog and knowledge packs | Categories/tags, explainable recommendations, revision diff/rollback, isolated asset cloning | `audit_reports/v10.1/Phase8B_Template_Knowledge_Pack_Audit_Report_V10.1.md` |
| V10.2 / Phase 8C | Accessible product closure | Pinned/exportable sessions, mobile citations, WCAG keyboard/screen-reader/reduced-motion closure | `audit_reports/v10.2/Phase8C_Accessibility_Product_Closure_Audit_Report_V10.2.md` |

## Dependency Order

```text
3A secure delivery
  -> 3B safe ingestion
    -> 3C safe retrieval
      -> 4A complete audit evidence
        -> 4B operational metrics and lifecycle
          -> 4C operations and knowledge quality completion
            -> 5A feedback capture
              -> 5B reviewer workflow
                -> 5C reporting
                  -> 6A production baseline
                    -> 6B async operations
                      -> 6C release readiness
                        -> 7A long-run operations baseline
                          -> 7B scale hardening and background reliability
                            -> 7C operational runbook and regression closure
                              -> V10.0 candidate planning
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
