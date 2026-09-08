# Crump Code benchmark/runner parity repair — 2026-09-08

## Outcome

The disabled Crump Code candidate now produces verification receipts that its own fixed offline
benchmark can evaluate truthfully. The repair does not enable Crump Code, call a model, create a
production task, run candidate code locally, spend credits, or support a Codex/Claude Code parity
claim.

## Defect and repair

The task runner always adds a syntax receipt after an implementation changes source:

- `python3 -m py_compile` for changed Python files; and
- `node --check` for each changed JavaScript file.

The benchmark previously rejected every receipt beyond the case's required acceptance command.
As a result, each of the three implementation cases could return the correct patch and pass its
required test but still fail because of the runner's own additional syntax check.

The evaluator now accepts only those two exact automatic receipt shapes, and only when every path
in the receipt is present in the already parsed patch and has the matching language suffix. An
automatic syntax failure still fails the case. A command aimed at any unrelated path, any other
extra command, malformed or noncanonical input, duplicate receipt, missing required receipt, or
unsafe verification remains a categorical failure. The evaluator still never executes candidate
code or echoes candidate content into its report.

## Verification

- Focused Crump Code benchmark, workspace, durable-worker, and observability coverage passed
  **38/38**.
- New executable cases prove the current runner's Python and JavaScript syntax receipts preserve a
  valid 4/4 benchmark result, are bound to changed paths, and fail when their return code is nonzero.
- The complete Python suite collected **903 tests**: **901 passed** and two environment-dependent
  tests skipped; there were no failures or errors.
- All **49 JavaScript files** and all six attribution cases passed validation.
- Ruff, production preflight, native web-bundle generation, and diff integrity passed. The
  production preflight's PATH-only Python probe was unavailable in this Windows shell, so Python
  coverage was supplied explicitly by the full suite and Ruff run above.
- Main CI run **34271687031** completed successfully.

## Production evidence

- Feature commit: **5e8b8dd5fd49154920623ee284e2e9b2448c8232**.
- Automatic production deployment: **dpl_HgycUGV6WKn2zKSanaLdFN2xUsMX**.
- The deployment reached READY with all six configured aliases and no alias error.
- Canonical health returned HTTP 200 with Ask Crump version 5.9.76.
- Deployment-scoped error/fatal, 5xx, and `crump_code` runtime-log queries were empty.
- Benchmark fixtures remain excluded from the Vercel function bundle. The evaluator and its tests
  are offline release tooling, so no customer-facing asset or runtime behavior changed.
- The documented `output/crump-code-benchmark/` report boundary is now explicitly ignored by Git,
  with an automated guard preventing that privacy boundary from silently drifting again.

## Remaining activation boundary

Keep `CRUMP_ENABLE_CODE_WORKSPACE=false`. Enabling or advertising Crump Code still requires the
separate explicit owner-approved, no-secret, sub-cent Sandbox/OIDC drill plus verified destruction,
cancellation, refund reconciliation, monitoring, alert routing, rollback timing, provider quality,
holdout, and actual unit-cost evidence. No production task, provider run, charge, refund, or user
exposure was created by this release.
