# Autonomous Crump queue guardrails — disabled review candidate

Status: **local review candidate only; feature remains disabled; migration is unapplied; no push or deployment**

Base: `1015069440a06f426c5281a631deed0ec451ecd5`

## Outcome

This slice adds the first server-authoritative capacity boundary around Autonomous Crump's already-atomic allowance/credit acceptance. It does not make the feature public and does not contact a model, Sandbox, Supabase, Vercel, or customer account.

Both release gates remain closed:

- checked-in source lock: `CODE_WORKSPACE_PUBLIC_RELEASED = False`
- operator switch: `CRUMP_ENABLE_CODE_WORKSPACE` still defaults to `False` and cannot bypass the source lock

## Fixed database limits

The singleton `code_guardrail_limits` row is private, read-only to `service_role`, and constrained to reviewed ranges. Changing a limit requires another database migration.

| Boundary | Candidate default |
|---|---:|
| Prepared, unaccepted tasks per user | 3 |
| Prepared, unaccepted tasks globally | 100 |
| Concurrent active code leases globally | 2 |
| Accepted runs per user per UTC day | 3 |
| Accepted runs globally per UTC day | 30 |
| Model-start reservations per user per UTC day | 4 |
| Model-start reservations globally per UTC day | 24 |
| Declared Sandbox seconds per user per UTC day | 720 |
| Declared Sandbox seconds globally per UTC day | 4,320 |

These are circuit breakers, not advertised entitlements or promises. A later pricing/entitlement decision must remain inside these operational ceilings unless a reviewed migration deliberately changes them.

## Atomic boundaries

### Queue admission

`create_code_task_guarded` acquires the global advisory transaction lock and then the user advisory transaction lock, checks both queue limits, owner-checks the Project, inserts the task, and appends the content-free `task.created` event in one transaction. A defensive insert trigger applies the same global → user lock order and rejects an unguarded direct insert.

The API no longer inserts `code_tasks` directly. A capacity rejection returns a bounded, truthful retry/deferred response.

### Run acceptance

`accept_code_task_run` now acquires locks in global → user → task order. Before calling either allowance consumption or confirmed credit spending, it rejects:

- a different accepted non-terminal task for the same user;
- the per-user UTC-day accepted-run limit;
- the global UTC-day accepted-run limit; or
- missing guardrail configuration.

A partial unique index is a second database-level defense against two accepted active tasks for one user. Replaying the same private dispatch token returns the existing task without a second charge or budget receipt.

### Worker claim

`claim_code_task_guarded` replaces service-role access to the older unguarded claim function. It:

- caps live global leases;
- skips users who already own a live lease;
- checks per-user and global UTC-day model-start and declared-Sandbox-second budgets;
- selects the least-recently-served eligible account first, then oldest ready work;
- acquires locks in global → selected user → task order and uses `FOR UPDATE SKIP LOCKED`;
- reserves one bounded model start and the task's declared maximum Sandbox seconds before returning compute ownership; and
- replays the same live claim token without another reservation.

The worker returns a content-free deferred state and yields the shared cron invocation when a guardrail prevents a claim.

## Shared scheduler fairness

The existing one-minute `/api/cron/manuscripts` slot now has a deterministic three-minute cycle:

- UTC minutes divisible by three: manuscript first, then code only if no manuscript was claimed;
- the other two minutes: code first, then manuscript whenever code is idle, disabled, misconfigured, or guardrail-deferred.

This bounds manuscript wait under a sustained code queue to less than three scheduler minutes. Minute zero is manuscript-first while the separate `/api/cron/check-ins` route runs on its existing hourly schedule, so code cannot take the check-in lane or every manuscript turn.

## Privacy and privilege boundary

`code_guardrail_receipts` stores only:

- task and user foreign keys for server-side accounting;
- UTC budget date;
- fixed receipt kind (`accepted` or `model_start`);
- bounded attempt number;
- bounded declared Sandbox seconds; and
- timestamp.

It contains no prompt, objective, repository URL/ref, filename/path, patch, result, output, provider, Sandbox name/session, lease token, dispatch token, credential, or customer content. RLS is enabled. PUBLIC, `anon`, and `authenticated` have no table or function access. `service_role` receives only the minimum table privileges and exact RPC execution grants; it cannot update the fixed limit row.

## Verification

Completed locally:

- focused queue/atomic-worker/foundation/observability tests: **56 passed**;
- complete Python suite: **1,203 collected; 1,202 passed; one environment-dependent skip**;
- changed-file Ruff: passed;
- changed Python compilation: passed;
- JavaScript validation: **54 files passed**;
- production build preflight, including its Python compile guard: passed;
- existing Autonomous Crump desktop/phone/durable/ownership/failed-verification browser review: passed with zero accessibility violations or overflow;
- client credential scan: passed against the unchanged client source and an existing base-equivalent native `dist` artifact (this isolated worktree intentionally did not generate a new `dist` directory);
- Git diff integrity: passed;
- deterministic executable race oracle: two simultaneous different-task acceptances for one user produce exactly one winner in the model;
- deterministic scheduler tests: reserved manuscript turn, code-deferred yield, UTC cycle, and separate check-in schedule all passed;
- static migration tests: lock order, private privileges, fixed bounds, pre-charge rejection ordering, fair selection, content-free receipt schema, old-claim revocation, and both disabled release gates passed.

The workstation does not currently provide Docker, `psql`, or `psycopg`, so **no real PostgreSQL runtime or concurrency pass is claimed**. `scripts/run_autonomous_crump_guardrails_postgres.py` is the required next gate. It refuses non-loopback hosts, refuses database names outside `askcrump_guardrails_*`, requires an exact ownership attestation, and refuses any database with an existing public table. Against a fresh caller-owned local database it exercises concurrent per-user and global queue admission, concurrent same-user acceptance, receipt singularity, per-user/global accepted-run limits, least-recently-served claim order, active-lease deferral, and per-user/global model-start and declared-Sandbox-second limits. The manual-only `autonomous-crump-guardrails-postgres.yml` workflow prepares that exact owned-disposable gate on PostgreSQL 15 and 17 with pinned `psycopg[binary]==3.3.5`; it was added for review but was not pushed or run.

## Release hold / remaining P0s

Do not apply, merge, push, deploy, or enable this candidate until all of the following are complete:

1. Run the owned-disposable PostgreSQL gate on PostgreSQL 15 and 17 and preserve the receipts.
2. Independently review SQL semantics, indexes, lock order, deadlock behavior, and PostgREST JSON shapes.
3. Re-read the fresh remote migration ledger and resolve any later migration before application.
4. Prove the complete application suite and protected CI on the eventual integration identity.
5. Prove live OIDC/Sandbox provisioning, deny-all networking, cancellation, destruction, retry, refund, monitoring, rollback, and actual provider quality/cost/latency gates.
6. Make a separate, explicit release decision; changing either false feature gate is outside this candidate.
