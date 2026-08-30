# Crump Code operational-safety release - 2026-08-30

## Outcome

The disabled Crump Code foundation now emits a small, content-free set of operational signals for
metered dispatch, worker ownership, retries, completion, cancellation, terminal failure, and
refund reconciliation. It also has an explicit emergency-stop and rollback runbook.

The review closed a shutdown edge case: disabling Code no longer strands an already-owed terminal
refund. Refund reconciliation runs before the disabled compute guard, but a lookup failure fails
closed for Code and returns the shared worker slot to manuscripts. No disabled-state path can claim
a Code task, provision a Sandbox, or call a model.

Crump Code remains disabled and unadvertised. This release does not claim the live Sandbox,
cancellation, alert-routing, rollback-drill, benchmark, or equivalence gates are complete.

## Operational and privacy contract

- Dispatch acceptance, uncertain-response recovery, rejection, cancellation, worker claim,
  completion, bounded retry, lease loss, terminal observation/failure, misconfiguration,
  unexpected failure, refund reconciliation, and deferred refund lookup have fixed event names.
- Optional fields are restricted to bounded categorical state, counters, duration, credit count,
  refund state, and exception class.
- The logger drops account and task IDs, dispatch and lease tokens, objectives, prompts,
  repository URLs, source, patches, verification/model output, receipts, secrets, arbitrary keys,
  unsafe categorical strings, and exception messages.
- An unknown event raises during development instead of silently expanding the production data
  contract.
- The disabled worker may settle one pending terminal refund, then stops. A refund lookup failure
  emits only the exception class and deferred outcome, starts no Code work, and lets the manuscript
  worker continue.
- The operations runbook defines launch-window response rules, emergency stop, in-flight
  containment, refund handling, rollback, recovery verification, and remaining activation proof.

## Verification

- All 547 Python tests passed.
- All 45 JavaScript integration validations passed.
- Ruff passed across the backend and test suite.
- Python compilation passed for every changed backend module.
- Production preflight passed.
- Native web-bundle generation passed.
- Apple and Google store metadata source checks passed.
- Mobile signing-secret controls passed.
- Diff integrity passed.
- Focused executable coverage proves fixed JSON shape, unknown-event rejection, private-value
  removal, disabled-state inactivity, successful content-free completion, transient retry,
  missing-OIDC signaling, private unexpected-failure handling, retry-limit refund, refund-before-
  compute, refund reconciliation while disabled, and fail-closed refund lookup that preserves the
  shared manuscript worker.
- The native verifier continued to report only the existing release-time gates: the iOS project is
  not generated in this Windows checkout, RevenueCat public mobile keys are absent, and Android
  Firebase configuration is missing.
- No production account, task, approval, Sandbox, model run, charge, refund, repository write,
  analytics event, checkout, payment, subscription, or customer record was created for
  verification.

## Production evidence

- Feature commit: **75a40fd** (Add Crump Code operational safety).
- Deployment: **dpl_zvBBwtqctrEgipnG2arUbHftvfVz**.
- State: READY on the six configured project domains.
- The canonical Ask Crump and Clever Crump hosts returned HTTP 200; both apex domains retained
  their deliberate canonical redirects.
- Health returned HTTP 200 with no-store caching and version 5.9.76.
- Unauthenticated feature-status and cron requests returned the expected HTTP 401.
- The next authenticated Vercel cron invocation returned HTTP 200 on the exact deployment, proving
  the shared scheduled worker remained healthy after settlement.
- The exact deployment had no runtime-error cluster and no warning, error, or fatal log.
- A production Runtime Logs search found no **crump_code** event, which is the correct
  disabled/no-legitimate-Code-activity baseline.
- The backend-only release did not change public assets, native version metadata, or service-worker
  cache r155.

## Activation boundary and rollback

This release proves the logging and disabled emergency-stop contracts in executable tests and
proves the shared production cron remains healthy while no Code work exists. It does not exercise a
live customer task or manufacture an event. The monitoring and kill-switch activation gate remains
open until one owner-approved no-secret smoke test demonstrates the exact signals, cancellation,
refund, Sandbox destruction, and rollback timing under bounded live worker conditions.

Rollback is deployment **dpl_Di5YGsmCXpteMQWuqRbWhQwzvUrt**. Keep
**CRUMP_ENABLE_CODE_WORKSPACE=false** and leave the additive private database durability schema
dormant. If an incident occurs after later activation, promote the known-good disabled release,
make the false environment value durable for the next build, cancel nonterminal tasks, and verify
refund reconciliation before any re-enable decision.
