# Version1.74.1 Handoff Prompt

Use this prompt when handing Version1.74.1 to a reviewer, operator, or the next Codex task.

Follow-on work approved on 2026-07-17 is design-only and is not included in
the implementation-complete claims below. For space-owner succession and
account offboarding, read
[the ownership-continuity design](../superpowers/specs/2026-07-17-ownership-continuity-account-offboarding-design.md)
and use
[the ownership implementation handoff](Version1.74.1_ownership_continuity_implementation_handoff.md).

```text
You are taking over KnowPilot Version1.74.1 for acceptance review.

Repository:
- GitHub: https://github.com/fangbo13/KnowPliot
- Branch to review: Version1.74.1
- Source worktree used for preparation: D:\KnowPliot\.worktrees\knowpilot-optimization

Primary objective:
Validate the optimization package for the current KnowPilot product: repeated-click disconnect/content-loss fixes, user/admin/chat capability boundaries, project admin vs super admin separation, streaming/recovery behavior, visual system consistency, and the documented future route.

Important files to read first:
- SPEC.MD
- docs/specs/2026-07-16-knowpilot-optimization-spec.md
- docs/superpowers/plans/2026-07-16-knowpilot-optimization-implementation.md
- audit_reports/current/SPEC_IMPLEMENTATION_PROGRESS.md
- memory.md
- docs/operations/Version1.74.1_handoff_prompt.md

Implemented and documented:
- Governed chat capability checks for ask/history/export/branch/regenerate/recovery paths.
- Safer session/history authorization behavior for downgraded, guest, direct member, platform, organization, and business-line scopes.
- Metrics sanitizer fix for boolean rollout metrics while still rejecting integer-like unsafe values.
- Product closure documentation for SPEC, memory, route map, and acceptance contract.
- Verification records for backend, frontend, TypeScript, i18n, build, lint, Django checks, migration drift, link resolution, and repository cleanliness.

Known acceptance boundary:
Do not claim production acceptance from local-only evidence. The remaining gates require authorized live or staging access:
- Yundang/PostgreSQL migration rehearsal.
- Redis and multi-worker stream recovery validation.
- Real provider latency/SLO/privacy evidence.
- Browser UAT for user, module admin, and super admin workflows.
- Responsive visual pass for spacing, breathing room, transitions, and restrained micro-motion.

Operator constraints:
- The prior implementation intentionally did not start the Yundang environment.
- Do not start local services unless the reviewer explicitly asks for runtime verification.
- Preserve user changes if the worktree is dirty.
- Treat memory.md as the continuity ledger and update it after material acceptance results.

Suggested review flow:
1. Read SPEC.MD for the acceptance contract.
2. Compare docs/specs/2026-07-16-knowpilot-optimization-spec.md against the six original product concerns.
3. Inspect the final implementation commits:
   - fd3f478 docs(spec): finalize optimization acceptance contract
   - 4798506 fix(chat): close metrics and history authorization gaps
   - 60c82ec feat(product): close conversation and governance workflows
4. Run only the checks appropriate to the reviewer environment.
5. Record acceptance results, unresolved live-environment evidence, and any regressions back into memory.md or a new audit report.

Expected reviewer output:
- Accepted / accepted with conditions / rejected.
- Exact failing scenario if rejected.
- Whether live Yundang validation has been completed.
- Any screenshots, logs, or migration output needed for final release confidence.
```
