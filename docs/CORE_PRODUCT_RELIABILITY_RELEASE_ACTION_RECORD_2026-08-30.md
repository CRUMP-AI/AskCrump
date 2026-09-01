# Core product reliability cumulative release action record

Date: 2026-08-30

Status: prepared and held; this record is not authorization.

## Why a cumulative record is required

Six independently accepted code-only repairs now share runtime loaders, cache versions, native-web
bundling, and—in several cases—the same chat or Project implementation files. A whole-file or
whole-tree commit cannot honestly claim to ship only one of the older records. This cumulative
record provides one explicit approval boundary for the compatible reliability set while leaving all
database, monetization, acquisition, measurement, demo, provider, store, and outbound work separate.

## Exact cumulative scope

Only these six previously accepted repairs may be included:

1. Project file-list trust and retry.
2. Durable generated document/image Project-attachment receipts, exact-target retry for temporary
   failure, and safe retargeting when the original Project no longer exists.
3. Completed-manuscript saved-export recovery.
4. Completed-video Project-link receipt and retry.
5. Saved-answer artifact packaging/link recovery without another AI or credit action, including
   truthful delivery and owner-scoped status reconciliation when a durable reply/file outlives a
   later chat-job cache finalization outage, lost HTTP success response, or post-success account-sync,
   creation-navigation, or local presentation/render outage in either browser runtime.
6. Memory-preference fail-closed persistence and request-level permission reduction.

Their authoritative scopes and evidence remain:

- `docs/PROJECT_FILE_TRUST_RELEASE_ACTION_RECORD_2026-08-30.md`
- `docs/PROJECT_OUTPUT_ATTACHMENT_RECOVERY_RELEASE_ACTION_RECORD_2026-08-30.md`
- `docs/MANUSCRIPT_OUTPUT_RECOVERY_RELEASE_ACTION_RECORD_2026-08-30.md`
- `docs/VIDEO_PROJECT_ATTACHMENT_RECOVERY_RELEASE_ACTION_RECORD_2026-08-30.md`
- `docs/CONVERSATIONAL_ARTIFACT_RECOVERY_RELEASE_ACTION_RECORD_2026-08-30.md`
- `docs/MEMORY_PREFERENCE_FAIL_CLOSED_RELEASE_ACTION_RECORD_2026-08-30.md`

Approval under this record supersedes the six individual no-bundle boundaries only for this exact
cumulative set. It does not broaden any repair's behavior or authorize unrelated hunks that happen
to share a file.

## Required release sequence

1. Reconcile every changed hunk against the six acceptance records. Exclude credit disclosure,
   landing measurement, Word/PDF guide, account deletion, lifecycle facts, demo proof, API, and any
   unrelated shared-file change.
2. Re-run the complete Python suite, 48-file JavaScript contract, production preflight, native web
   bundle, and diff-integrity checks.
3. Create one exact implementation commit and one immutable preview candidate. Do not promote it.
4. Verify all six recovery/privacy fixtures, authentication boundaries, owner scope, fixed error
   receipts, retry idempotency, post-persistence cache-outage delivery, response-loss reconciliation,
   browser post-success sync/navigation/presentation isolation, cache/source parity, and zero unintended
   migration/provider/credit path on the candidate.
5. Confirm the candidate contains no new migration and requires no database change.
6. Promote the already-verified candidate, then verify served source, health, protected-route
   rejection, Project/Create/Memory destinations, and deployment-scoped severe logs.
7. Record the exact commit, deployment, source hashes, tests, runtime observations, and rollback
   point before calling the cumulative repair live.

## Explicit exclusions

This record does not authorize a Supabase migration; production account, conversation, Project,
file, manuscript, memory, event, or credit mutation for testing; model/provider generation;
marketing publication; profile-link or Search Console action; pricing, plan, entitlement, Stripe or
RevenueCat change; lifecycle email/push; store submission; API-repository change; or spend.

## Exact action-time approval phrase

`Approve the cumulative core product reliability release under docs/CORE_PRODUCT_RELIABILITY_RELEASE_ACTION_RECORD_2026-08-30.md. Include only the six named accepted repairs; do not bundle a Supabase migration, account-deletion release, credit-charge release, lifecycle-facts release, demo-proof release, MarketingLanding release, Word/PDF guide release, API change, production test write, model/provider run, social or Search Console action, pricing or payment-provider change, store submission, lifecycle message, or spend.`

Anything broader or materially different requires a new action record and action-time approval.
