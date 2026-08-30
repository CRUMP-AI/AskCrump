# Crump Code durable-worker release — 2026-08-30

## Outcome

The disabled Crump Code foundation now separates a customer's confirmed request from the bounded
Sandbox execution that follows. A confirmed task is accepted once, metered once, and then owned by
a private scheduled worker. Refreshing the browser, closing the workspace, or losing the original
request no longer owns the lifetime of the run.

Crump Code remains disabled in production. This release hardens the control plane; it does not
activate the feature or make a Codex- or Claude Code-equivalence claim.

## Durability, safety, and cost contract

- The authenticated run endpoint still requires explicit review confirmation and Professional
  entitlement before metering.
- Metered dispatch is one private Postgres transaction. A unique dispatch token makes an uncertain
  PostgREST response replay-safe and writes the content-free claim event in the same transaction.
- The browser receives HTTP 202 with an accepted task instead of holding a serverless request open
  for the entire coding run. The workspace polls durable status and tells the user it can be closed.
- A service-role-only worker claims one previously metered task with a unique, time-limited lease.
  The claim uses `FOR UPDATE SKIP LOCKED`, and retrying an uncertain claim token returns the same
  lease rather than a second task.
- Every mutable runner boundary includes the private lease token. A stale worker stops before its
  next expensive step after another worker safely reclaims the task.
- Only model-network, timeout, rate-limit, workspace-list, and patch-packaging failures retry.
  Retries use bounded exponential delay, retain the original usage receipt, and never recharge.
- A retry-limit or permanent failure terminalizes the task and uses the existing idempotent refund
  path. Refund-pending terminal tasks are reconciled before the worker starts new provider compute.
- Owner cancellation and lifecycle expiry clear the execution lease and mark a persisted usage
  receipt refund-pending. An active worker observes the terminal state and settles the refund.
- The existing minute manuscript cron is shared rather than adding a third Vercel cron. When Crump
  Code is disabled or no task is ready, the manuscript worker retains its existing path.
- The feature flag, paid model requirement, short-lived Vercel OIDC identity, public-GitHub-only
  source rule, deny-all Sandbox network, empty environment, non-persistent workspace,
  destruction-on-exit behavior, source-repository no-write rule, bounded duration, and bounded
  patch size remain unchanged.

## Database proof

- Supabase migration `20260830094939_crump_code_durable_worker` applied successfully.
- Live schema inspection confirmed the dispatch token, lease token, lease expiry, next-attempt,
  attempt-count, and max-attempt columns with the intended defaults and nullability.
- Live index inspection confirmed the unique non-null dispatch token, ready-worker queue, and
  refund-pending terminal indexes.
- Both `dispatch_code_task` and `claim_code_task` are security-invoker functions with fixed
  `public, pg_temp` search paths.
- Live privilege checks confirmed anonymous and authenticated roles cannot execute either function
  or access `code_tasks`; the service role can execute both and retains server table access.
- The table still has row-level security enabled. Its no-client-policy state is deliberate because
  the authenticated API is the only gateway and direct client table privileges are revoked.
- Post-change advisors reported only informational existing deny-by-default RLS notices and
  immediately-unused-index notices. The worker privileges were verified independently.

## Verification

- All 540 Python tests passed.
- All 45 JavaScript files passed the integration validator.
- Ruff passed across the backend and new worker tests.
- Python compilation passed for every changed backend module.
- Production preflight passed.
- Native web-bundle creation passed.
- Store-metadata source validation passed.
- Diff integrity passed.
- Regression coverage proves disabled-worker inactivity, private token redaction, unique replay-safe
  claim tokens, successful durable completion, transient retry without refund or recharge,
  retry-limit refund before more compute, refund reconciliation before new compute, and stale-lease
  shutdown.
- The native verifier truthfully retained the existing store gates: the iOS project is not
  generated in this Windows checkout, RevenueCat public mobile keys were absent from the local
  build, and Android Firebase configuration is not present.
- The isolated `agent-browser` CLI was not installed on this host. Because the customer-facing
  Crump Code surface remains feature-gated, verification used executable real-runtime tests plus
  credential-free production HTTP and asset probes rather than modifying a signed-in account.
- No production account, task, approval, Sandbox, model run, credit charge, refund, Project,
  repository write, analytics event, checkout, payment, subscription, or customer record was
  created for verification.

## Production evidence

- Feature commit: `64743c2` (`Make Crump Code execution durable`).
- Deployment: `dpl_8Deq7hEPhphqGLHX3MxGHVXK5u3a`.
- State: READY, with all six production aliases attached and no alias error.
- Cache: `ask-crump-new-body-v1-r155`.
- Workspace runtime: `5.9.76-code-durable-worker-1`.
- All four customer-facing Ask Crump and Clever Crump hosts returned HTTP 200. The two generated
  Vercel aliases retained their configured Vercel authentication boundary.
- Health returned HTTP 200, service Ask Crump, version 5.9.76.
- The live runtime loader references the exact durable-worker asset, and the live service worker
  serves cache r155.
- Unauthenticated feature-status and cron-worker requests returned the expected HTTP 401.
- The exact deployment had no runtime error cluster after settlement; the remote build completed
  successfully.

## Activation boundary and rollback

This release verifies the disabled durable control plane only. Public activation still requires a
real owner-approved, no-secret Sandbox/OIDC/destruction smoke test, benchmark and cost envelopes,
monitoring and kill-switch proof under live worker conditions, and explicit enablement approval.

Rollback is deployment `dpl_4sJKpMzZWYfUtPPbqCkHqeTfnvvx`. Promoting it restores the prior
synchronous disabled application code. The additive database columns, indexes, and private
functions should remain dormant rather than be destructively removed; the feature flag stays off.
