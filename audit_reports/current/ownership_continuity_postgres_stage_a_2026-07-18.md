# Ownership continuity — PostgreSQL Stage-A rehearsal (2026-07-18)

The local Docker Compose PostgreSQL database was used for the additive Stage-A
migrations below. No Stage-C non-null constraint was applied and the audit was
run without `--apply`.

| Item | Result |
| --- | --- |
| `spaces.0009_ownership_continuity_stage_a` | Applied successfully |
| `users.0004_user_offboarding_metadata` | Applied successfully |
| Audit backfills | 0 (no space had exactly one safe legacy owner) |
| Canonical-owner anomalies | 5 zero-owner spaces; 1 multi-owner space |
| Stage-C eligibility | Blocked pending explicit remediation of every anomaly |

The command reported these space identifiers, without user names, email
addresses, access tokens, or other secrets:

```text
zero-owner:
0734b03a-0ead-4b02-8ac3-7bbd053c70d0
1b5e2bfd-1937-4198-8fd4-8278ee79f98a
2f96e628-0b5e-4e91-9310-4c6cd7f1a957
694f5b6c-39e5-4a0a-b3aa-d37a14fe5ae9
85cf5656-52f8-4230-bca2-504542a5e347

multi-owner:
fbf1d719-caba-4080-bd55-408c425147c7
```

No `--apply` invocation was made: the safe backfill command only changes
spaces with exactly one effective legacy owner, and none met that criterion.
