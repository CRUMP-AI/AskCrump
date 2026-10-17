# Crump Code operations runbook

Last reviewed: 2026-10-15

## Current operating state

Crump Code remains disabled in production. The source-controlled
`CODE_WORKSPACE_PUBLIC_RELEASED=false` lock and the production
`CRUMP_ENABLE_CODE_WORKSPACE=false` switch are independent compute stops: both must be deliberately
opened before customer feature status can report Code as configured. While either is closed, task
creation and run requests fail closed and the shared worker does not claim new Code tasks. The
shared cron first runs bounded task/approval/started-lease expiry and terminal refund maintenance,
before account-deletion or manuscript early returns. The worker may also reconcile a terminal
refund. Neither maintenance path provisions a Sandbox or calls a model.

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
  either refunded before provider begin or retained with started/uncertain provider cost accounted.
  Missing settlement evidence must stop further compute.
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
   configuration. Confirm the repaired source also restores
   `CODE_WORKSPACE_PUBLIC_RELEASED=false`. If a Code incident is active, immediately promote the
   most recent known-good disabled deployment while making both stops durable for the next build.
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
- Keep **CRUMP_ENABLE_CODE_WORKSPACE=false** and
  `CODE_WORKSPACE_PUBLIC_RELEASED=false` throughout recovery.
- Verify the four customer-facing domains and health endpoint, the authenticated feature response,
  the protected cron boundary, continued manuscript processing, refund reconciliation, and the
  absence of a new runtime-error cluster.
- Re-run the complete Python and JavaScript suites, production preflight, native bundle, store
  metadata, and diff-integrity checks before promoting a repair.

## Remaining activation evidence

The release-safe preparation harness is:

```powershell
python scripts/run_crump_code_sandbox_smoke.py --dry-run
```

It provisions nothing. Do not run its live mode without separate action-time approval for exactly
one cent and the fixed public, no-secret fixture. The short-lived `VERCEL_OIDC_TOKEN` must be passed
only through the process environment and must resolve to the exact Ask Crump project and team; the
public feature flag must remain false. Once those conditions are approved, the only permitted live
shape is:

```powershell
python scripts/run_crump_code_sandbox_smoke.py --live --confirm-max-cost-cents 1 --confirm-source public-no-secret-fixture
```

Evidence and privacy boundaries are recorded in
`docs/CRUMP_CODE_LIVE_SMOKE_HARNESS_RELEASE_2026-09-09.md`.

Before public activation, record one owner-approved end-to-end drill that proves OIDC identity,
deny-all networking, absence of privileged Sandbox environment variables, destruction, cancellation, expiry, refund,
operational signal visibility, and rollback timing. Then complete the fixed quality, latency, and
unit-cost benchmark. Only after those gates and explicit enablement approval may a reviewed code
release change `CODE_WORKSPACE_PUBLIC_RELEASED`; the environment switch remains a separate
operator control. Crump Code stays unadvertised and disabled until both controls are deliberately
open.

## Atomic billing and model budget rollout

Keep both compute stops closed. Apply
`migrations/20261015230059_atomic_code_dispatch_provider_budget.sql` before deploying the
application that uses its RPCs. The migration revokes legacy `dispatch_code_task` execution from
the service role, so older rolling instances fail closed. Never restore that grant to make a
mixed deployment appear healthy. Roll back to a disabled application and retain the additive
schema if needed.

Signed workload admission requires explicit `CODE_OIDC_ISSUER`, `CODE_OIDC_AUDIENCE`,
`CODE_OIDC_PROJECT_ID`, `CODE_OIDC_TEAM_ID`, and `CODE_OIDC_ENVIRONMENT`. The last three may use
the documented server-side Vercel project/team/environment fallback. Pin values from the intended
deployment; never infer trusted values from the incoming token. RSA signature and issuer,
audience, project, team, environment and time claims are checked before claim and provisioning.

Model admission additionally requires all of these operator-approved environment values:

- `CODE_PROVIDER_MODEL` (exact match with the configured Anthropic model)
- `CODE_PROVIDER_INPUT_USD_MICROS_PER_MILLION` (upper bound including cache-write premiums)
- `CODE_PROVIDER_OUTPUT_USD_MICROS_PER_MILLION`
- `CODE_PROVIDER_MAX_INPUT_BYTES`, `CODE_PROVIDER_MAX_OUTPUT_TOKENS`
- `CODE_PROVIDER_CALL_USD_MICROS`, `CODE_PROVIDER_RUN_USD_MICROS`
- `CODE_PROVIDER_ACCOUNT_DAILY_USD_MICROS`, `CODE_PROVIDER_GLOBAL_DAILY_USD_MICROS`

No price defaults or model aliases are assumed. Amounts are integer USD millionths. Policy is
pinned atomically at task dispatch and checked again before Sandbox provisioning and every model
reservation. A policy change requires a newly prepared task. Daily caps use UTC and retain the
strictest observed cap for that day. Started requests never automatically replay or release
their maximum cost hold when acceptance or usage is uncertain. Reconcile against provider billing
before any manual correction; do not silently delete or downgrade a reservation.

These budgets meter model calls only. Sandbox infrastructure cost, throughput, customer credit
pricing and margin remain separately measured business/release gates. The browser fixture and
PGlite verifier are offline evidence, not production activation evidence.
