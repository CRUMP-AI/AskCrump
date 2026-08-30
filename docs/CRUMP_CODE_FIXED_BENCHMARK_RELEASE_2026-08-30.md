# Crump Code fixed-benchmark foundation - 2026-08-30

## Outcome

The disabled Crump Code foundation now has a fixed, provider-neutral quality suite pinned to one
immutable public Ask Crump revision. It measures three bounded implementation repairs and one
concurrency-planning task without calling a model, running candidate code, creating a production
task, spending credits, or enabling the feature.

This is a deterministic evaluation foundation, not a Codex or Claude Code parity claim. The
visible acceptance cases are not an adversarial holdout, and provider cost remains a separate
activation gate.

## Fixed suite and safety contract

- Fixture commit **f75ae5c** contains deliberately failing Python boundary, JavaScript slug,
  security-header, and atomic rate-limit planning cases.
- The versioned manifest accepts only the approved public repository and full fixture commit SHA.
- Every implementation case has exact required, allowed, and forbidden paths, one canonical
  allowlisted verification, a patch-size budget, one attempt, and a duration ceiling.
- The plan case permits no source change and no verification command.
- The command-line evaluator is locked to the tracked manifest; it cannot substitute a custom
  easier suite.
- The evaluator never executes candidate code. It validates runner-produced receipts against the
  same read-only verification allowlist used by Crump Code.
- Absolute, parent-relative, drive-qualified, malformed, binary, mismatched, out-of-scope, and
  acceptance-file diffs fail closed.
- Missing, duplicate, extra, unsafe, noncanonical, failed, or malformed verification receipts fail
  closed.
- Secret-like candidate summaries, patches, stdout, and stderr fail the case, while reports retain
  only suite/case IDs, scores, counts, thresholds, and categorical failure codes.
- Local result artifacts remain under `output/crump-code-benchmark` and are never committed.
- `benchmarks/**` is excluded from the Vercel function bundle.

## Verification

- The three intentionally broken implementation fixtures failed their acceptance baselines before
  evaluation: one Python boundary failure, three JavaScript slug failures, and one security-header
  failure.
- All 12 focused evaluator tests passed, including exact passing scores, pinned-source integrity,
  report redaction, forbidden-path rejection, absolute/path-traversal rejection, malformed-patch
  handling, unsafe extra-command rejection, strict field types, report-boundary containment, and
  the no-candidate-execution contract.
- All 559 Python tests passed on the final source state.
- All 45 JavaScript integration validations passed.
- Ruff, Python compilation, production preflight, native web-bundle generation, Apple/Google store
  metadata, mobile signing-secret controls, and diff integrity passed.
- The native verifier continued to report only the known release-time gates: iOS is not generated
  in this Windows checkout, RevenueCat public mobile keys are absent, and Android Firebase
  configuration is missing.
- GitHub push protection rejected a realistic fake-key test value. It was replaced with a harmless
  synthetic secret marker before either commit reached the remote; no credential was involved.
- No production account, task, approval, Sandbox, model run, charge, refund, analytics event,
  checkout, payment, subscription, or customer record was created for verification.

## Production evidence

- Fixture commit: **f75ae5c** (Add fixed Crump Code benchmark fixtures).
- Evaluator commit: **782f332** (Add fixed Crump Code benchmark evaluator).
- Deployment: **dpl_HruEkha3TKW13QGzKvUCZiDqv2WR**.
- State: READY on all six configured project domains.
- Canonical Ask Crump and Clever Crump pages returned HTTP 200; apex hosts retained their intended
  redirects.
- Canonical health returned HTTP 200, version 5.9.76, and no-store caching.
- The deployment had no runtime-error cluster and no warning, error, or fatal runtime log.
- A deployment-scoped Runtime Logs search found no `crump_code` event, which is the correct
  disabled/no-legitimate-Code-activity baseline.
- Because fixtures are excluded from the function bundle and the evaluator is a local script, the
  release does not alter customer-facing behavior or enable Crump Code.

## Remaining activation boundary

Before Crump Code can be advertised or enabled, run one explicit owner-approved, no-secret live
drill to prove Sandbox OIDC, destruction, cancellation, refund, monitoring, alert routing, and
rollback timing. Then execute this fixed suite across candidate providers, add separately injected
Sandbox-only holdouts, reconcile actual provider cost, define a sustainable product-credit
envelope, and require repeatable results before making any competitive quality claim.

Rollback remains the prior disabled production deployment
**dpl_5DHWxDRPCFoXcXzL6pkPwcYW1xvU**. Keep `CRUMP_ENABLE_CODE_WORKSPACE=false`; the benchmark adds no
production data or schema to unwind.
