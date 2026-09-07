# Credit-Charge Disclosure Product Release — Action Record

Prepared: 2026-09-01  
Status: staged locally; exact action-time founder approval required  
Production change: not yet authorized  
Database change: staged, not applied  
Public campaign or spend: not authorized

## Decision

This is a dedicated product-trust release for server-authoritative credit
quotes, explicit positive-charge confirmation, idempotent deductions, and a
durable manuscript credit ceiling. It is not part of the separate Word/PDF
guide release and must not be bundled with that approval.

No price, credit-pack size, allowance, entitlement, provider route, Stripe
catalog, social post, profile link, Search Console setting, or campaign budget
changes in this release.

## Product behavior staged

- Every current credit-eligible action is quoted from server-side account
  state before a paid execution.
- Included actions proceed at zero credits without a paid confirmation.
- Positive charges show the exact credits, current balance, and balance after;
  the button names the charge.
- A stale quote may result in a lower current charge but never a higher charge
  than the confirmed maximum. A higher current charge requires a fresh review.
- Accepted retries share an action/component key and deduct at most once. The
  database also enforces the confirmed maximum across every component in the
  action, so changing a component key cannot multiply one approval.
- A signed positive-credit quote is bound to a digest of the exact reviewed
  action. Changed prompts, files, options, or targets require a fresh review.
- Existing refund behavior remains available through the durable ledger
  receipt.
- Full-manuscript autopilot displays planned and chargeable steps, the
  per-step price, a maximum, and a stopping rule. It pauses before exceeding
  the approved maximum and requires a fresh review to continue.
- Plan & credits shows the current fixed rates without claiming that a static
  table can determine whether the next action is included.
- The public pricing note now uses the bounded statement: "Monthly plans expand
  included capacity. Some premium or overflow actions can use Crump Credits.
  Purchased credits never expire." Both in-app balance panels use the same
  premium-or-overflow boundary and promise an exact charge before confirmation.
- The unsupported 150-credit-pack `Popular` badge and pack-specific featured
  treatment are removed. Professional plan emphasis remains separate.
- Video-page `plan=professional` remains a registration/plan-review intent only;
  it creates no checkout, purchase, or entitlement. The server continues to
  require Enterprise for 10-second Cinematic generation and quotes 120 credits.

## Staged database boundary

Reviewed staging SQL:
`staging/confirmed_feature_spending.sql`

Latest coordinated authoritative remote migration head:
`20260901074430 harden_conversation_image_privileges`

This candidate intentionally contains no pending file in `migrations/`.
The former `20260830222959` identity predates the current live head and is
void. At the approved action time, after all preceding held release units and
the live ledger are rechecked, create a fresh migration with the Supabase CLI,
copy this reviewed SQL into it, and re-run the complete candidate hash and test
proof. Do not invent or pre-reserve a timestamp.

The migration:

1. adds durable manuscript budget fields and constraints;
2. pauses pre-disclosure active autopilot runs for a fresh owner review;
3. adds service-role-only `spend_credits_confirmed` with per-account locking
   and action/component idempotency, an action-wide confirmed ceiling, an empty
   fixed search path, and fully schema-qualified relations;
4. revokes service-role execution of the now-unused legacy unconfirmed
   `spend_credits` RPC, so a rollout gap or code rollback fails closed rather
   than restoring silent deductions.

The latest API coordination reports stable production API v0.49.1; its newer
repository-only correction has not been deployed. The remote migration ledger
must be checked again immediately before creating or applying the fresh
migration, and any shared-table change must be reconciled first.

A read-only 2026-09-01 impact query found zero active autopilot manuscript runs
in queued, running, paused, or awaiting-credit states, so the legacy-run pause
statement would currently update zero rows. This is a checkpoint, not a promise;
the impact query must be repeated at action time.

## Evidence completed locally

- Full Python suite: 656 passed.
- Focused credit disclosure coverage: 34 tests green for included, sufficient,
  insufficient, stale-lower, stale-higher, duplicate, refund/provider failure,
  analytics independence, asynchronous ceiling behavior, action-scope binding,
  allowance-race requoting, and action-wide replay resistance.
- Duplicate ledger receipts now report zero newly spent credits while
  preserving the original event receipt, so a safe replay cannot inflate a
  manuscript's durable approved-ceiling counter.
- An adversarial local proof showed the pre-hardening candidate could spend 20
  credits from one confirmed 10-credit maximum by changing component IDs. The
  hardened proof spends 10 once, rejects the second component, and leaves the
  balance at 990.
- Explicit policy coverage: 1, 2, 4, 6, 8, 10, 12, 60, 80, 90, and 120 credits,
  including both continuation and cinematic video paths.
- JavaScript syntax/integration contract: green across 48 public scripts.
- Web/PWA/future-native asset parity is guarded.
- A private localhost-only browser fixture passed all six synthetic states:
  included zero, positive confirmation, insufficient balance, stale-higher
  requote, duplicate submission, and manuscript ceiling. It returned 200 with
  meaningful content, six interactive cases, no error overlay, no console or
  page errors, and no production/account/provider/ledger connection.
- Misleading flat-rate request language is absent from current product,
  documentation, and backend surfaces.
- Misleading "credits only after allowance exhaustion" language is absent from
  public and billing-documentation surfaces; premium video remains explicitly
  credit-funded.
- Marketing independently reports its focused revenue subset green and current
  production still failing the served-candidate verifier, proving this staged
  release has not leaked live.
- No real customer content or real credit spend was used.

Current production code has advanced through 930a8ce, so this old-base held
candidate must be reconstructed on the then-current main line before action.
The exact implementation commit, candidate deployment, production deployment,
served-source proof, privacy-safe legitimate post-release observation, and
error-cluster watch are intentionally pending action-time approval.

## Required release sequence

1. Re-run the full Python and JavaScript suites and the native build.
2. Confirm the remote migration ledger still ends at the just-observed live
   head and that no conflicting shared-table change appeared.
3. Create the exact implementation commit and immutable candidate deployment
   without promoting it.
4. Verify local/candidate fixtures without real customer data or real credit
   spend.
5. Use `supabase migration new confirmed_feature_spending` to generate a fresh
   identity, copy only `staging/confirmed_feature_spending.sql` into it, then
   re-run hashes, the full suites, native build, preflight, and migration diff.
6. Apply only that freshly generated, revalidated migration.
7. Promote the already-built candidate immediately.
8. Verify the served production source/runtime, zero-charge behavior, recovery
   exits, and manuscript stop rule without manufacturing a live charge.
9. Watch runtime errors and refund/credit-ledger anomalies. If promotion fails,
   keep the legacy spend RPC revoked and fix forward; do not restore silent
   deductions.
10. Record the exact commit, deployment, migration result, and observations in
   the release evidence before marketing treats universal disclosure as live.

## Explicit exclusions

This record does not authorize:

- the Word/PDF guide product release or its migration;
- creation or reset of a production demo account;
- social publication, profile-link changes, Search Console submission, email,
  push, or lifecycle sends;
- pricing, plan, pack, entitlement, provider, Stripe, RevenueCat, or checkout
  changes;
- paid acquisition or any spend.

## Exact action-time approval

No commit, migration apply, production deployment, or public claim is
authorized until the founder sends this exact sentence:

> Approve the credit-charge disclosure product release under docs/CREDIT_CHARGE_DISCLOSURE_RELEASE_ACTION_RECORD_2026-08-30.md. Do not bundle the Word/PDF release, publish social content, change profile links, submit Search Console, alter prices or plans, modify Stripe or RevenueCat, create or reset a demo account, send lifecycle messages, or spend money.
