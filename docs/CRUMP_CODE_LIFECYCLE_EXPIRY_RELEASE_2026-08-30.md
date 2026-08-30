# Crump Code lifecycle-expiry release — 2026-08-30

## Outcome

The disabled Crump Code foundation now closes three lifecycle gaps before any public activation:

- a stale task cannot be claimed or charged after its seven-day expiry;
- a pending approval cannot be accepted after its 30-minute expiry; and
- an owner cancellation or expiry is checked before Sandbox provisioning and again around every
  expensive execution boundary.

Expired work becomes a durable, reviewable terminal state instead of remaining actionable in the
interface. Crump Code remains disabled in production.

## Product, safety, and cost contract

- Owner-scoped task lists and task details lazily reconcile expired nonterminal tasks to
  cancelled with failure code CODE_TASK_EXPIRED.
- The run endpoint checks expiry before entitlement evaluation, task claim, and credit
  consumption. The claim operation independently rechecks expiry to close a concurrent race.
- Approval decisions require both pending status and an expiration later than the decision time
  in the same database update. A late decision cannot win after expiry.
- An expired approval is durably marked expired, emits bounded content-free audit events, and
  terminalizes its waiting task with CODE_APPROVAL_EXPIRED.
- The runner checks cancellation/expiry before resolving Sandbox identity or importing/provisioning
  the Sandbox runtime, immediately after provisioning, after the model/tool loop, and before
  verification and patch extraction.
- A cancellation that races after charging still follows the existing error path and refund
  contract. An already-expired queued task never reaches charging.
- The workspace labels task and approval expiry explicitly, shows the task expiration time, and
  refreshes after a late approval attempt.
- The task and approval schemas, public-GitHub-only source rule, empty Sandbox environment,
  deny-all post-checkout network rule, non-persistent execution, destruction-on-exit policy,
  provider boundary, pricing, entitlements, and source-repository no-write rule are unchanged.

Expiry reconciliation is intentionally lazy on owner reads and command boundaries rather than a
new background scheduler. The atomic claim and approval filters enforce the security boundary even
when a dormant task has not been opened recently.

## Verification

- All 531 Python tests passed.
- The focused Crump Code lifecycle and workspace suite passed all 20 checks.
- All 45 JavaScript files passed the repository integration validator.
- Ruff passed across the changed Python implementation and tests.
- Production preflight passed.
- Native web-bundle creation passed.
- Store-metadata source validation passed.
- Diff integrity passed.
- A credential-free real-runtime browser fixture proved:
  - expired work is labeled **Expired safely** in both the list and detail;
  - the expiry timestamp and **Not started** charge state remain visible;
  - the terminal explanation reads **Stopped safely: code task expired.**;
  - queued work keeps **Run isolated task** disabled until explicit confirmation;
  - the disabled feature renders no workspace surface; and
  - every tested state recorded zero browser errors.
- The temporary browser tab and localhost server were closed after verification.
- No production account, task, approval, Sandbox, model run, credit charge, refund, Project,
  repository write, event, checkout, payment, subscription, or customer record was created for
  verification.

The native release verifier also truthfully retained the existing store-submission gates: the iOS
project is not generated in this Windows checkout, both RevenueCat public mobile keys were absent
from the local build, and Android Firebase configuration is not yet present. Those are native
submission blockers, not blockers for this disabled web foundation.

## Production evidence

- Feature commit: b77f1f4 (Enforce Crump Code lifecycle expiry).
- Deployment: dpl_5gkEyG4fKFfGPMJsieK2x3vcrLU4.
- State: READY, with all six production aliases attached and no alias error.
- Cache: ask-crump-new-body-v1-r154.
- Workspace runtime: 5.9.76-code-lifecycle-expiry-1.
- All four public Ask Crump and Clever Crump hosts returned HTTP 200.
- Health returned HTTP 200 and version 5.9.76.
- The live service worker and versioned Crump Code runtime returned HTTP 200 with the exact cache
  revision and both expiry codes.
- An unauthenticated request to the feature endpoint returned the expected HTTP 401 boundary.
- The exact deployment had no warning/error/fatal runtime log or 5xx response after settlement.
  The successful build completed in 12 seconds; its only warning was Vercel's non-blocking
  package-cache hardlink fallback.

## Activation boundary and rollback

This release verifies deterministic lifecycle enforcement and production delivery only. It does
not satisfy the remaining public-activation gates: a real no-secret Sandbox/OIDC/destruction smoke
test, the benchmark set, production monitoring/kill-switch proof, and owner approval to enable the
feature remain required. No Codex- or Claude Code-equivalence claim is made.

Rollback is deployment dpl_781mSZ42JRPsP3Uxd9uX6xrMnrpC. Reverting b77f1f4 removes the lazy
expiry reconciliation, atomic late-approval rejection, extra runner cancellation boundaries,
expiry interface states, and cache revision. It does not migrate or delete tasks, approvals,
Projects, repositories, accounts, credits, events, or payments.
