# Phase 9B Scoped Administration & Lifecycle — Test Audit V11.1

**Status:** PASS  
**Date:** 2026-07-12  
**Branch:** `Version_11.1`

## Scope and evidence

- Organization/business-line lifecycle is scope-authorized and archives make descendant spaces read-only.
- Space transfer is restricted to the caller's organization; ownership transfer, restore, isolated clone, and idempotent access requests are covered.
- Approval creates an active membership and a targeted notification; scoped user listing prevents cross-organization enumeration and prevents non-platform promotion to organization admin.
- Clone copies documents into the target space and queues independent ingestion; it never reuses chunks.

## Commands

| Gate | Result |
| --- | --- |
| `manage.py test apps.spaces.tests_phase9b_scoped_governance` | PASS — 10 tests |
| Docker equivalent + `check` + migration dry-run | PASS |
| `manage.py test apps` | PASS — 207 tests |
| Frontend typecheck/test/i18n/build | PASS — 53 tests |
| Docker HTTP smoke | PASS — backend 401 unauthenticated, frontend 200 |

## Negative tests

Cross-organization transfer and unscoped role promotion return 403. Private and already-joined spaces are excluded from discovery. Archived parent scopes deny document write access. Existing access requests are idempotent.

## Migration

`spaces/0005_spaceaccessrequest.py`; migration dry-run reports no drift.

## Residual risks

The production deployment must apply the migration and configure normal notification delivery. Existing expected test-suite warnings are exercised rejection paths, not failures.
