# Autonomous Crump: reviewable execution foundation

Date: 2026-10-15

## Outcome and boundary

This change strengthens the existing AskCrump monorepo engineering workspace. It does not create
a separate product, migrate the established stack, or change pricing. Autonomous Crump remains
disabled behind both `CODE_WORKSPACE_PUBLIC_RELEASED=false` and
`CRUMP_ENABLE_CODE_WORKSPACE=false`. No production migration, paid model call, or live Sandbox
was performed during this implementation. IONWAKE and the other Clever Crump products were not
modified.

The customer story is: prepare a project-bound public-repository task, explicitly approve its
run and any credit quote, execute within a pinned budget, then inspect the patch, checks and
activity before applying anything. No source repository is pushed, merged or deployed.

## Implemented controls

- Atomic server-derived allowance/confirmed-credit charge, canonical receipt, dispatch token and
  audit event in one transaction. Retrying the same task with a fresh HTTP request token returns
  the original dispatch without a second charge. Failed transactions roll back the debit.
- Durable model reservations with per-call/run/account/global caps, pinned exact model/prices,
  bounded request bytes/output tokens, stable call key and request digest. Fixed
  global/account/task lock order protects admission; no floating-point money arithmetic.
- Daily aggregates retain cost and the strictest admitted cap when tasks are deleted. Account
  deletion removes account identifiers but cannot free the identifier-free global daily budget.
- Reserve, begin, settle and pre-dispatch release have distinct semantics. Only a newly confirmed
  begin permits the provider POST. Lost/uncertain begin or provider outcomes retain the full hold;
  a new worker lease cannot replay a started execution. Valid idempotent settlement replays are
  accepted only when the canonical reservation is settled.
- Refund eligibility and reversal share the task lock with provider begin. A pre-provider
  cancellation can refund; cancellation after begin retains original charge and cost accounting.
- Signed, pinned RS256 workload identity before claim/provisioning. Bounded public JWKS fetch,
  rotation/cache behavior and failure handling; no token or arbitrary claim logging.
- Budget/model configuration before task claim, exact pinned policy before Sandbox provisioning,
  and fresh admission before each model call. Missing or drifted policy fails closed.
- Scheduled bounded task/approval expiry, expired-started-lease retirement and pending-refund
  reconciliation before shared-cron early returns, even when Code is disabled. Live lease state
  is rechecked atomically, so a concurrent extension wins over an old scan.
- Failed, missing or unknown check results never claim a verified implementation. Incomplete
  patch/changed-file artifacts fail closed. Verification caches stay outside the repository;
  final changed-file inventory is checked again before packaging. Ignored writes are rejected;
  NUL-delimited Git inventory validates both sides of renames and refuses incomplete records.

## Workbench

The warm paper/charcoal visual system extends the existing app. The workbench has mobile
Brief/Progress/Review navigation, preserved keyboard focus/disclosures/scroll during polling,
busy controls through refreshed states, explicit check outcomes, and file-by-file text diffs.
Patch content is inert text, never HTML. Preview limits bound characters, files, rows and line
length; the full original patch remains downloadable. Valid hunk content resembling diff headers
does not corrupt filenames or line counts.

`tests/fixtures/autonomous-workbench.html` intercepts every API request and prohibits network
connections via CSP. All scenarios are labelled synthetic. It proves rendering/client behavior,
not real agent capability or production API integration. The verifier produces ignored local
desktop and mobile screenshots in `artifacts/autonomous-workbench/`.

## Reproducible evidence

Final local result: **1,965 Python tests passed**, **57/57 browser verifiers passed**,
**16/16 SQL scenarios passed**, **54/54 visual scenarios passed**, and **33/33 public
accessibility scenarios passed**. Ruff, application compilation, JavaScript contracts, production
preflight, native web-bundle construction, smoke dry-run, client secret scan and diff checks passed.
Preflight's PATH-based Python discovery skipped its compile substep on this Windows host; the
application was compiled separately with the verified Python 3.12 runtime. The Python suite reports
one upstream Starlette/AnyIO deprecation warning.

- Python: signed identity, feature/route admission, atomic service contracts, budget validation,
  no model POST or Sandbox provisioning after refused admission, uncertainty/no-replay behavior,
  expiry/lease/refund maintenance, honest verification, complete artifact bounds and smoke parity.
- `node scripts/verify-code-budget-sql.mjs`: 16 actual SQL scenarios against a fresh in-memory
  PGlite database, applying existing wallet/allowance functions and the actual new migration.
  Set `PGLITE_MODULE` to an already-installed PGlite module if it is not on this checkout's path.
  It never reads a production database URL. Scenarios cover debit rollback, cross-request replay,
  allowance exhaustion, budget levels, cancellation/begin ordering, uncertainty, expired leases,
  original-lease settlement, deletion-independent daily aggregates and service-only privileges.
  The real durable `delete_user_account` wrapper keeps its storage-cleanup job semantics and now
  locks its parent user before child cleanup to match dispatch/refund lock ordering. Both overloads
  are exercised, including an idempotent retry after deletion.
- `node scripts/verify-autonomous-workbench.cjs`: 11 browser groups, including explicit run
  confirmation, safe patch rendering/full-download parity, both themes, keyboard/polling recovery,
  and accessibility in every mobile pane at 390 and 320 pixels.
- Existing app regression: 54 visual scenarios and 33 public-page accessibility scenarios;
  JavaScript contracts, production preflight, native web bundle and client secret scan.

PGlite executes PostgreSQL semantics but does not prove real multi-session lock contention,
deadlock behavior, Supabase/PostgREST deployment privileges, or provider billing. The fixed
four-case scripted orchestration benchmark remains a plumbing test and is not a model fix rate.

## Deployment order and remaining acceptance evidence

1. Keep both locks closed. Review/test the migration on a disposable local/staging PostgreSQL
   database with independent concurrent sessions, including same-task requests, competing tasks
   at account/global caps, begin versus cancel/refund, UTC rollover and commit-response loss.
2. Apply `20261015230059_atomic_code_dispatch_provider_budget.sql`, then deploy the reviewed
   application. The migration intentionally revokes the legacy dispatch RPC; older rolling
   instances must fail closed. Retain additive schema during rollback and use a disabled app.
3. Configure explicit workload trust and approved model price/budget values documented in
   `CRUMP_CODE_OPERATIONS.md`. Verify intended environment, deployment, team and project bindings.
4. Perform the separately approved fixed-source Sandbox smoke and end-to-end cancellation,
   retained-cost/refund, expiry, destruction, monitoring and rollback drills. Verify physical
   iOS Safari/WKWebView, download behavior, keyboard and VoiceOver.
5. Freeze at least 20 representative real failing tasks with held-out acceptance checks. Measure
   actual no-human-intervention fix rate, patch validity, regressions, security, p50/p95 latency,
   and model plus Sandbox cost per task type. Do not substitute scripted offline results.
6. Measure queue/backlog fairness with account deletion/manuscript work and define operational
   thresholds. Only open the source lock and operator switch after the evidence and explicit
   activation decision support release.

Muse provided product critique and correctly emphasized real completion reliability, total unit
cost and adversarial budget-race evidence. Older product memories were treated as leads and
checked against source/live behavior. Codex implemented and tested the code; Muse did not verify
the new source or run the test suite.
