# Autonomous Crump queue guardrails — disabled review candidate

Status: **local review candidate only; feature remains disabled; migration is unapplied; candidate branch is unpushed and undeployed**

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

`create_code_task_guarded` acquires the global advisory transaction lock and then the user advisory transaction lock, checks both queue limits, owner-checks the Project, inserts the task, and appends the content-free `task.created` event in one transaction. The API creates one private UUID replay token before its retry-capable database call. The database binds that token to the exact request, so an uncertain after-commit response returns the original task and cannot create a second task or `task.created` event.

Direct `service_role` INSERT access to `code_tasks` is revoked. Queue admission is the narrowly granted, fixed-search-path `SECURITY DEFINER` function above; all other customer roles remain revoked. Its defensive insert trigger still enforces queued/unaccepted shape and the global → user lock order. The generic Python transition boundary no longer permits `queued → provisioning`, and the old direct `CodeTaskService.claim()` path is removed, so only the guarded acceptance/claim transactions can enter provisioning.

The API no longer inserts `code_tasks` directly. A capacity rejection returns a bounded, truthful retry/deferred response.

### Run acceptance

`accept_code_task_run` now acquires locks in global → user → task order. Before calling either allowance consumption or confirmed credit spending, it rejects:

- a different accepted non-terminal task for the same user;
- the per-user UTC-day accepted-run limit;
- the global UTC-day accepted-run limit; or
- missing guardrail configuration.

A partial unique index is a second database-level defense against two accepted active tasks for one user. Replaying the same private dispatch token returns the existing task without a second charge or budget receipt.

Before the active-task check, the same global → user transaction reconciles expired accepted tasks across all of the user's Projects to `cancelled / CODE_TASK_EXPIRED / refund_pending`, clears their lease, and appends one content-free cancellation event. A stale task in an abandoned Project therefore cannot occupy the partial unique index forever.

### Worker claim

`claim_code_task_guarded` replaces service-role access to the older unguarded claim function. It:

- caps live global leases;
- skips users who already own a live lease;
- checks per-user and global UTC-day model-start and declared-Sandbox-second budgets;
- computes remaining global Sandbox seconds before selection and excludes oversized tasks, so an older large task cannot starve a smaller fitting task;
- selects the least-recently-served eligible account first among fitting tasks, then oldest ready work;
- acquires locks in global → selected user → task order and uses `FOR UPDATE SKIP LOCKED`;
- reserves one bounded model start and the task's declared maximum Sandbox seconds before returning compute ownership; and
- replays the same live claim token without another reservation.

If the final allowed lease has expired, the claim transaction fails the task with `CODE_RETRY_LIMIT`, records `refund_pending` and one content-free failure event, and returns a handled terminal receipt without reserving attempt `max_attempts + 1`, a model start, or additional Sandbox seconds. A queue with work but no task fitting the remaining global seconds receives a truthful UTC-reset deferral; an actually empty queue still returns `no_work`.

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

Customer deletion still cascades these task/user-linked receipts. Global UTC-day ceilings instead read a separate private `code_guardrail_global_daily_facts` row containing only the date, accepted count, model-start count, declared Sandbox seconds, and update time. It has no user, task, Project, content, source, path, provider, or token identifier. The acceptance/claim transactions increment it atomically while holding the existing global lock, and no customer deletion cascades to it, so deleting an account cannot reopen global capacity.

## Verification

Completed locally:

- focused queue/worker/foundation tests: **62 passed**;
- complete Python suite: **1,213 collected; 1,212 passed; one environment-dependent skip**;
- changed-file Ruff: passed;
- changed Python compilation: passed;
- JavaScript validation: **54 files passed**;
- production build preflight, including its Python compile guard: passed;
- existing Autonomous Crump desktop/phone/durable/ownership/failed-verification browser review: passed with zero accessibility violations or overflow;
- client credential scan: passed against unchanged client source and a freshly generated isolated native `dist` artifact;
- Git diff integrity: passed;
- deterministic executable race oracle: two simultaneous different-task acceptances for one user produce exactly one winner in the model;
- deterministic scheduler tests: reserved manuscript turn, code-deferred yield, UTC cycle, and separate check-in schedule all passed;
- static migration tests: lock order, private privileges, direct-insert rejection, stable create replay, owner-scoped Project admission, ready-work-before-cap ordering, deletion-invariant global facts, expired-task recovery, final-attempt terminalization, fit-aware fair selection, fixed bounds, pre-charge rejection ordering, content-free schemas, old-claim revocation, generic-transition closure, and both disabled release gates passed.

Real PostgreSQL evidence now exists for the immediately preceding repaired source identity `7359a742c083a9a022ac53baf57b839a02116a19`. CI-only mirror `17f94113009183e94f00581ce1e85d0d3b2e76d5` differs from that source only by the three-line branch trigger needed to run the otherwise manual workflow. [GitHub Actions run 35167844192](https://github.com/CRUMP-AI/AskCrump/actions/runs/35167844192) passed both caller-owned disposable PostgreSQL 15 and PostgreSQL 17 jobs.

That CI gate was deliberately **not Supabase** and did not touch any hosted, shared, staging, production, or customer database. `scripts/run_autonomous_crump_guardrails_postgres.py` refuses non-loopback hosts, refuses database names outside `askcrump_guardrails_*`, requires an exact ownership attestation, and refuses any database with an existing public table. It exercises concurrent per-user/global queue admission, same-token create replay singularity, service-role direct-insert rejection, cross-owner Project rejection, concurrent same-user acceptance, deletion-invariant global counters, per-user/global accepted-run limits, cross-Project stale-task recovery, least-recently-served and fit-aware claim order, active-lease deferral, attempt-five terminalization without attempt six, and per-user/global model-start and declared-Sandbox-second limits.

This follow-up repair additionally proves that an empty queue returns `no_work` while the active-lease ceiling is saturated and while the UTC-day model-start ceiling is saturated. Its account-deletion fixture creates and accepts fresh ready work after the linked receipt is cascaded away, then requires the surviving content-free global counter to defer that work at the model-start ceiling. It also runs a positive `SET ROLE service_role` same-owner call through the `SECURITY DEFINER` queue-admission RPC after direct table INSERT has been revoked, and requires exactly one `task.created` event. Those new fixtures are committed only in this local candidate, so the exact repaired tip still requires the same owned-disposable PostgreSQL 15/17 matrix rerun before release acceptance; the earlier successful run is preserved as baseline evidence, not misrepresented as proof of later bytes.

## Release hold / remaining P0s

Do not apply, merge, push, deploy, or enable this candidate until all of the following are complete:

1. Rerun the updated owned-disposable PostgreSQL gate on PostgreSQL 15 and 17 for the exact repaired commit and preserve both receipts; the successful baseline run above does not cover later fixture/SQL bytes.
2. Independently review SQL semantics, indexes, lock order, deadlock behavior, and PostgREST JSON shapes.
3. Re-read the fresh remote migration ledger and resolve any later migration before application.
4. Prove the complete application suite and protected CI on the eventual integration identity.
5. Prove live OIDC/Sandbox provisioning, deny-all networking, cancellation, destruction, retry, refund, monitoring, rollback, and actual provider quality/cost/latency gates.
6. Make a separate, explicit release decision; changing either false feature gate is outside this candidate.
