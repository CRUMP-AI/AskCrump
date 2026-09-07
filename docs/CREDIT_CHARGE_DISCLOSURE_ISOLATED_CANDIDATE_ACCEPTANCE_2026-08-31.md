# Credit-charge disclosure isolated candidate acceptance

Prepared: 2026-09-01  
Status: held in a clean detached local worktree; not committed, migrated, or deployed  
Base commit: 86cd73feabc6b65b809999c5efc45dec239f3b68

## Outcome

The credit-charge disclosure release is reconstructed from a clean base as one
bounded product-trust unit. Included actions continue without a paid prompt.
Any positive credit use is quoted from current server state, names the exact
maximum, requires an explicit confirmation, and uses a stable action/component
key so an accepted retry deducts at most once. The signed quote is also bound
to a content-free digest of the reviewed action, so altered input requires a
fresh review.

Durable manuscript runs persist their approved paid-credit ceiling, stop before
crossing it, and require a fresh quote before continuing. A duplicate ledger
receipt now reports zero newly spent credits while preserving the original
receipt, preventing a replay from inflating the manuscript ceiling counter.
The database now enforces the confirmed maximum across the complete action,
not just each component. An adversarial replay of one 10-credit quote against
two different component keys spends 10 credits once and rejects the second
component before deduction.

The public and in-app copy distinguishes monthly included capacity from premium
or overflow credit use. It changes no price, pack size, allowance, entitlement,
provider route, checkout, Stripe or RevenueCat configuration, campaign, or
outbound message.

## Database and migration boundary

The reviewed SQL is held at staging/confirmed_feature_spending.sql. It is
intentionally absent from migrations/. The former 20260830222959 identity is
void because it predates the latest coordinated live head
20260901074430 harden_conversation_image_privileges. The live read-only schema
check confirms that spend_credits_confirmed and the manuscript budget columns
remain absent, so this held SQL has not leaked into production.

At the approved action time, recheck the remote ledger and every preceding held
release, generate a fresh identity with the Supabase CLI, copy only the reviewed
SQL into that file, regenerate hashes, and rerun the entire proof. No timestamp
is invented or reserved by this candidate.

The new SECURITY DEFINER function is required to mutate private credit tables.
It has an empty fixed search path, fully schema-qualified relations, execute
revoked from PUBLIC, anon, and authenticated, and execute granted only to
service_role. Per-account advisory locking, an action-wide sum of confirmed
feature-spend ledger entries, and the existing unique provider/external-id
ledger boundary provide serialized idempotency and enforce the exact approved
maximum. The
legacy unconfirmed service-role spend grant is revoked so a rollout gap fails
closed.

A read-only 2026-09-01 impact query found zero active autopilot manuscript runs
in queued, running, paused, or awaiting-credit states. The impact query must be
repeated at action time.

## Product and cache boundary

The confirmation controller is authentication-gated and shared by chat, voice,
code, image/media, direct manuscript actions, and workspace requests. The web,
PWA, legacy runtime configs, and native loader use explicit credit-specific
asset versions. The isolated service-worker cache is reserved as r169 because
this unit follows the earlier r166-r168 held units and must be rebuilt after
any predecessor ships.

The unsupported featured treatment on the 150-credit pack remains removed.
Professional-plan emphasis remains separate from credit-pack presentation.

## Exact isolation evidence

docs/credit-charge-disclosure-isolated-diff.json pins the base commit, complete
path set, immutable SHA-256 hashes, staging-only SQL, observed remote head,
required behavior markers, fresh-migration gate, and mandatory rebase gate.

scripts/verify-credit-charge-disclosure-candidate.mjs fails on base, path, hash,
staged-index, migration-queue, SQL object, privilege, search-path, API namespace,
cache/version, action-boundary, or diff-integrity drift.

## Verification

- Focused credit disclosure contract: 34 passed.
- Complete clean-candidate Python suite: 656 passed.
- JavaScript syntax and runtime integration contract: 48 files passed.
- Native web bundle parity build: passed.
- Production build preflight: passed; its optional local Python discovery
  skipped, while the complete bundled-runtime Python suite above passed.
- Python compilation for all changed backend modules: passed.
- Read-only live schema, privilege, index, migration-ledger, and impact checks:
  passed without customer content or writes.
- No real credit deduction, provider request, account mutation, database
  migration, preview, deployment, or publication was used.
- The desktop rendered-browser helper remains unavailable. The private
  localhost synthetic fixture is retained, but this acceptance makes no new
  rendered-browser claim.

## Mandatory rebase and release order

This proof candidate is based directly on 86cd73f while current production code
has advanced through 930a8ce. The held release train also places core
reliability, lifecycle durable facts, and account-deletion cleanup before this
unit. The credit unit must therefore be reconstructed from the then-current
production commit, the migration ledger rechecked, a fresh migration identity
generated only at approved action time, hashes regenerated, and all validation
repeated.

## Explicit exclusions

This candidate contains no unrelated Project/artifact recovery, account
deletion implementation, lifecycle decision/send, MarketingLanding
measurement, Word/PDF guide, demo-account proof, API repository or API-owned
data, social/profile/Search Console action, store submission, price/plan/
checkout/webhook configuration, or spend.

## Action-time boundary

No commit, migration creation or application, preview, deployment, promotion,
provider request, customer-data write, public claim, or external action is
authorized by this record. The only applicable authorization remains the exact
sentence in
docs/CREDIT_CHARGE_DISCLOSURE_RELEASE_ACTION_RECORD_2026-08-30.md.
