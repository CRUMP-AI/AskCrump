# Crump Code source release lock

Date: 2026-09-13

## Outcome

Crump Code now has two independent activation controls. The operator environment switch and a
source-controlled public-release lock must both be open before the feature can report configured,
accept a task, or let the worker claim compute. The checked-in source lock remains false.

This closes the risk that an accidental Vercel environment change could expose or run the disabled
foundation. It does not approve a live Sandbox run, activate the provider, or establish parity with
Codex or Claude Code.

## Implementation

- Product commit: `943036251e44b41c4cb0c820e875c5f6b7ba1bfc`
- `backend/config.py` requires both `CODE_WORKSPACE_PUBLIC_RELEASED` and
  `CRUMP_ENABLE_CODE_WORKSPACE`.
- The feature-status route, Code route, and worker all consume the same authoritative setting and
  contain no direct environment or source-lock bypass.
- The operations runbook now requires both controls to remain closed during emergency stop,
  rollback, and recovery.
- Regression coverage proves that `CRUMP_ENABLE_CODE_WORKSPACE=true` cannot bypass the checked-in
  false source lock.

## Verification

- Complete Python suite: 1006/1006 passed.
- JavaScript validation: 54/54 files passed.
- Browser control matrix: 45/45 verifiers passed.
- Production build preflight and native build passed.
- Client credential scan and native privacy source verification passed.
- Fixed four-case offline Code benchmark passed 4/4 with a 100/100 score.
- The Sandbox smoke harness remained in dry-run mode: no Sandbox, model call, database write,
  customer data, credit, or provider cost was used.
- Production deployment `dpl_5tmX4BNYBS8uRzqjh6MkVLCfWLGd` is Ready for the exact product commit.
- GitHub CI run `34776843880` completed successfully.
- Production health returned HTTP 200 on version 5.9.76.
- A signed-in production workspace showed zero visible Code destinations, no configured body state,
  and no full Code script or stylesheet loaded.
- The inspected one-hour production window contained no runtime-error cluster and no
  `crump_code` log entry.

## Remaining activation gates

Crump Code remains disabled and unadvertised. Public activation still requires separate
action-time approval and evidence for the real no-secret Sandbox/OIDC smoke, live destruction and
network boundaries, cancellation and expiry, refund reconciliation, monitoring/alert visibility,
rollback timing, a real approval-boundary scenario, and representative live quality, latency, and
unit cost. Only after those gates pass may a reviewed release deliberately change the source lock;
the environment switch remains an independent operator control.
