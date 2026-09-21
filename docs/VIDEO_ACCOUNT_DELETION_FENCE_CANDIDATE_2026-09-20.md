# Video provider-start/account-deletion race — source-only candidate

Status: **HOLD — no production change.** This branch is based on committed
`origin/main` `d2aa857`, not the dirty native checkout. No remote migration,
provider generation, production request, push, or deployment was made.

## Defect and candidate boundary

`media_jobs.user_id` cascades on account deletion. Previously, video start
and continuation reserved a media row, awaited the provider, then updated
that row with the provider ID. Deletion during that await could remove the
only durable handle after a provider accepted billable work.

The staged SQL adds a service-only deletion fence and a minimal provider-start
claim, deliberately without prompts, references, file names, or credit
receipts. Video claims are reserved before charging, then dispatch is
atomically refused after a deletion fence. A provider acceptance is recorded
in the independent claim before relying on `media_jobs`. A token-owned
deletion fence is acquired before billing cleanup; an unexpired reserved
start returns 409 **without** creating a fence or canceling billing. Unconfirmed
billing cancellation and a failed local delete invoke a token-matched
compensation RPC, serialized on the user row. If a delete RPC response was
lost after commit, that RPC reports `user_deleted` instead of resurrecting an
account. A prior Stripe customer deletion is accepted on retry only after
the exact customer ID is retrieved and marked deleted, consistent with
[Stripe's Customer API](https://docs.stripe.com/api/customers/retrieve).

An unresolved no-ID `dispatching` or `unknown` claim blocks a fresh video
reservation **before** charge/provider dispatch and returns the owner job ID.
HTTP 503 start/tracking ambiguity and HTTP 409 fresh-start refusal include
`reconciliationPending: true` and `jobId`. Owner-scoped GET and same-key
POST replay return `job.reconciliationPending`, which can remain true even
when the media job says `failed`. An accepted provider ID can repair a local
`pending:<uuid>` handle; the placeholder is never sent to the provider.
The integrated client must honor this contract and retain its owner-scoped
idempotency key.

The existing minute cron rotates first priority among deleted-video, code,
and manuscript workers, so a long-running provider job cannot take every
minute. It can reconcile one deleted-account claim:
poll known provider IDs but never download or retain a generated output;
unknown starts without an ID remain marked for review and are not retried or
automatically refunded. Provider polling errors omit response-body details
from logs.

## Local evidence

- Deterministic fake-DB/fake-provider races cover deletion-first, held
  provider start followed by deletion, reserved-claim conflict without a
  lasting fence/billing action, held continuation, unknown-start suppression,
  same-key claim cleanup, accepted-ID repair, failed-but-pending GET,
  deleted-output discard, and no-ID review. Account route tests cover
  billing-failure compensation, local-delete failure, lost successful delete
  response, and verified prior Stripe deletion. HTTP 500/read timeout vs
  connect timeout is tested for both provider adapters. No test contacts a
  real provider or Stripe.
- Affected route/service/cron/refund tests: **76 passed**.
- The operator-only demo-account replacement now acquires the same
  deletion fence before removing private Storage objects. A reserved video
  start leaves both the old account and its files untouched; a failed local
  delete releases only that operation's fence. Its **22 workflow tests pass**,
  including a lost delete response that committed.
- Full Python suite: all candidate-related tests pass; two unrelated tests
  fail because the bundled local Python cannot import Argon2 and falls back
  to scrypt. `backend/security.py` is unchanged.
- A path-scoped GitHub Actions job now boots an official disposable
  `postgres:17-bookworm` service and exercises the candidate with separate
  database connections. Static harness tests, YAML parsing, and the focused
  local contract pass. The real PostgreSQL job is still **pending** because
  this Windows host has no local PostgreSQL, Docker, WSL, or `psql`.
- Migration preflight now aborts the whole transaction with an explicit
  operator-review error if an in-flight legacy video row has an unsupported
  provider/operation or blank provider ID. Accepted IDs are trimmed by the
  constraint, and only exact provider/operation reservation retries remain
  idempotent.
- `git diff --check` passes.

## Release gates and residual risks

1. The SQL is a **staged candidate**, not an applied or numbered Supabase
   migration. Generate a migration with the Supabase CLI and inspect the
   remote migration ledger. Apply and verify SQL **before** shipping any
   code that calls these RPCs; deploying code first would block video starts
   and account deletion. Coordinate with the separate API team's Supabase
   changes. No production schema was touched here.
2. The disposable PostgreSQL workflow must pass before this candidate can
   become a numbered migration. It compiles and reapplies the SQL, proves the
   invalid-legacy preflight rolls back, validates ACL/RLS/SECURITY INVOKER
   behavior and trigger gates, and observes reservation/deletion,
   acceptance/deletion, lease-replay, expiry-reclaim, and `SKIP LOCKED`
   orderings with independent connections. Local static validation does not
   substitute for that hosted result.
3. An accepted provider start followed by total database unavailability
   before its provider ID is journaled remains intrinsically ambiguous.
   Provider-supported idempotency or an independent receipt/correlation
   mechanism is needed before claiming complete recovery. Without an ID,
   this design errs against duplicate provider spend and automatic refund.
4. Provider-side cancellation/deletion capability and actual data-retention
   behavior are unverified. Polling and discarding is not proof that the
   provider removed the generated media. The claim contains a user UUID and
   provider job ID after account deletion, so an approved retention and
   operator-reconciliation policy is required before production release.
5. Existing clients/workers must be quiesced or migrated in a coordinated
   rollout; old code can still dispatch without a claim. Re-run live
   integration and privacy/security checks after merging with the separate
   browser/account-isolation fixes. Include the demo-account reset utility
   in the coordinated rollout: its old version would partially remove
   private files before the new user-delete trigger rejects the call.
6. An unconfirmed compensation RPC can leave a fenced active account and
   requires operator recovery. There is not yet an approved operator
   investigation/settlement path for an active no-ID unknown start; until
   one exists, the conservative block can prevent further video generation.
   Stripe cancellation may already have completed when a later local
   deletion fails. Verify entitlement/webhook and customer-deletion retry
   behavior in a disposable Stripe environment.

Next action: publish the draft integration branch so the disposable
PostgreSQL workflow can run. If and only if it passes, independently review
the evidence, generate a numbered migration through the Supabase CLI, compare
the fresh remote migration ledger, and approve a coordinated migration-first
rollout or keep video deletion release-held.
