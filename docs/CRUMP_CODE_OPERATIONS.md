# Crump Code operations runbook

Last reviewed: 2026-08-30

## Current operating state

Crump Code remains disabled in production. **CRUMP_ENABLE_CODE_WORKSPACE=false** is the
authoritative compute stop: customer feature status reports Code as unconfigured, task creation and
run requests fail closed, and the shared worker does not claim new Code tasks. The worker may still
reconcile an already-terminal refund before returning to manuscript work; that path never
provisions a Sandbox or calls a model.

This runbook documents the release-safe controls and signals. It does not claim the remaining live
OIDC, Sandbox-destruction, cancellation, alert-routing, rollback-drill, or benchmark activation
gates are complete.

## Content-free operational signal contract

Every Crump Code operations record is one compact JSON object with **component=crump_code**. The
event allowlist is:

- **dispatch_accepted**, **dispatch_recovered**, **dispatch_rejected**
- **worker_claimed**, **worker_completed**, **worker_retry_scheduled**
- **worker_terminal_observed**, **worker_terminal_failure**, **worker_lease_superseded**
- **worker_unexpected_failure**, **worker_misconfigured**
- **cancellation_recorded**, **refund_reconciled**, **refund_reconciliation_failed**

The only optional fields are bounded categorical state, attempt and duration counters, lease or
retry duration, credit count, refund-pending state, and exception class. Logs never include account
or task IDs, dispatch or lease tokens, objectives, prompts, repository URLs, source, patches,
verification output, model output, receipts, secrets, or arbitrary exception messages.

Use Vercel Runtime Logs with the production environment and search for **crump_code**. Inspect
grouped runtime errors first for a broad incident, then filter the JSON events for the Code control
plane. Retain the existing application-level upstream transport filter; operational logs are not
an exception to that privacy boundary.

## Launch-window response rules

Until representative legitimate traffic establishes baselines, treat these as manual gates rather
than statistical alerts:

- **worker_misconfigured:** stop activation immediately; the worker lacks the short-lived Vercel
  OIDC identity or another required runtime control.
- **dispatch_rejected** with any outcome other than **refunded**, or
  **worker_unexpected_failure** with **recovery_failed:** page the operator and stop new Code work.
- **worker_terminal_failure:** verify the task reached a terminal state and its usage receipt is
  refunded or queued for reconciliation before allowing more compute.
- **refund_reconciliation_failed:** Code compute remains stopped and the shared slot returns to
  manuscripts. Investigate the refund boundary immediately and confirm the next retry settles it.
- Repeated **worker_retry_scheduled** records in the same launch window: inspect provider and
  Sandbox health; do not raise attempt or duration limits as the first response.
- **dispatch_accepted** without a later terminal outcome beyond the task's bounded retry and lease
  window: inspect the shared cron, queue eligibility, OIDC delivery, and current lease state.
- Any evidence of content or identifiers in logs: treat as a privacy incident and roll back the
  instrumentation release.

Do not create synthetic production tasks, charges, refunds, or analytics events to exercise these
signals. The activation drill must use one owner-approved, no-secret public repository and a
pre-agreed sub-cent budget.

## Emergency stop

1. Set the production **CRUMP_ENABLE_CODE_WORKSPACE** value to **false** and deploy that exact
   configuration. If a Code incident is active, immediately promote the most recent known-good
   disabled deployment while making the environment change durable for the next build.
2. Confirm an authenticated **/api/features** response reports
   **code_workspace.configured=false**. An unauthenticated response is expected to remain 401 and
   is not sufficient proof.
3. Confirm no new **dispatch_accepted** or **worker_claimed** record appears after the stopped
   release begins serving traffic. Manuscript processing must continue through the shared cron.
4. Cancel any nonterminal owner tasks through the authenticated Code API. Cancellation clears the
   lease; an already-running worker stops at its next guarded boundary. A Sandbox already inside a
   bounded command may continue only until the configured deadline, after which
   destruction-on-exit remains mandatory.
5. Reconcile every terminal **refund_pending** task. The disabled worker intentionally continues
   this refund-only path before manuscript work and must emit **refund_reconciled** without
   starting Code compute.
6. Preserve the incident window, deployment ID, aggregate event counts, affected task count, refund
   reconciliation result, and resolution. Do not copy customer content or identifiers into the
   incident record.
7. Re-enable only after the root cause is fixed, the exact disabled-state and refund tests pass, a
   fresh preview is verified, and the owner explicitly approves a new bounded smoke test.

Changing the environment value does not terminate a function or Sandbox already running on the old
deployment. Cancellation checks, the maximum execution deadline, lease expiry, and Sandbox
destruction are the in-flight containment controls.

## Rollback and recovery

- Roll back the application to the latest known-good disabled deployment. Keep the additive private
  database columns, indexes, and functions dormant; do not remove them during an incident.
- Keep **CRUMP_ENABLE_CODE_WORKSPACE=false** throughout recovery.
- Verify the four customer-facing domains and health endpoint, the authenticated feature response,
  the protected cron boundary, continued manuscript processing, refund reconciliation, and the
  absence of a new runtime-error cluster.
- Re-run the complete Python and JavaScript suites, production preflight, native bundle, store
  metadata, and diff-integrity checks before promoting a repair.

## Remaining activation evidence

Before public activation, record one owner-approved end-to-end drill that proves OIDC identity,
deny-all networking, empty Sandbox environment, destruction, cancellation, expiry, refund,
operational signal visibility, and rollback timing. Then complete the fixed quality, latency, and
unit-cost benchmark. Crump Code remains unadvertised and disabled until those gates and explicit
enablement approval are complete.
