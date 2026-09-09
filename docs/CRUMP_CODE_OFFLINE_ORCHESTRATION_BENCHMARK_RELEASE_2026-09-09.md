# Crump Code offline orchestration benchmark release — 2026-09-09

## Outcome

The fixed Crump Code benchmark now exercises the production runner's agent loop instead of scoring
only hand-built receipts. The production runner keeps the Vercel Sandbox provisioning boundary,
then delegates its already-isolated workspace lifecycle through one injectable method. The offline
harness supplies a temporary Git repository, the real `SandboxWorkspace` tool surface, a memory-only
task service, and deterministic scripted model turns.

All four pinned cases completed and scored **100/100**:

- Python inclusive-boundary repair;
- JavaScript slug normalization;
- case-insensitive sensitive-header redaction; and
- atomic rate-limit planning without edits.

The three implementation cases performed real bounded reads and writes, ran their required
allowlisted acceptance commands, received automatic syntax verification, and produced scoped Git
patches. The plan case read its three fixed files, returned the required concurrency plan, produced
no patch, and ran no verification command.

## Safety and claim boundary

- The harness copies only the checked-in public benchmark fixtures into a new temporary directory.
- It uses no network request, API key, OIDC token, production Sandbox, production task, user content,
  customer identifier, credit, provider call, or database row.
- Model turns and fixes are fixed test data. This proves runner orchestration and regression
  detection; it does **not** prove live-model quality, production Sandbox readiness, cancellation
  under live compute, cost, reliability, or parity with Codex/Claude Code.
- `CRUMP_ENABLE_CODE_WORKSPACE` remains disabled. No customer-facing Crump Code capability was
  enabled or advertised by this release.

## Validation and delivery

- Feature commit `fc87c6c37baf29fe5ef40eb3dfc605de0ab2cb66`.
- Offline benchmark: four of four cases passed; mean score **100.0** against threshold 90.
- Focused Crump Code tests: **34/34** passed.
- Complete Python suite: **947 collected**, **945 passed**, two environment-dependent skips.
- JavaScript validation: **49 files** and all six rough-to-useful attribution cases passed.
- Browser control matrix: **36/36** verifiers passed, including the fail-closed button inventory.
- Ruff, Python compilation, production preflight, native web bundle, and diff integrity passed.
- Native store verification stayed fail-closed because the local checkout has no Android/iOS project
  shells and the RevenueCat public keys were absent; no store-readiness claim is made.
- GitHub Actions CI `34405607942` passed.
- Production deployment `dpl_F43PWir83hwDp2fsh8t9fumz1iiY` is READY on all six aliases with no
  alias error.
- Production health returned HTTP 200 on Ask Crump 5.9.76. The initial one-hour grouped runtime-error
  and production 5xx queries were empty.

## Remaining Crump Code gates

Before enablement, retain the approved sub-cent production-Sandbox smoke test, production OIDC
verification, live cancellation/expiry behavior, failure monitoring, rollback exercise, one real
approval-boundary scenario, and a genuine live-model benchmark. Any such run needs its own explicit
cost, data, and release evidence.
