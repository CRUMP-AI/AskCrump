# Native-billing deletion retry candidate — 2026-09-20

## Boundary

This is a source-only correction on draft PR #37. It was not merged or deployed,
and no production account, provider customer, subscription, storage object, or
database schema was changed. Native store submission remains blocked on the
owner-controlled signing, billing, reviewer, and physical-device gates.

## Finding and correction

The draft account-deletion endpoint previously logged a failed RevenueCat
customer-deletion request but continued deleting the local account. Once the
local account was gone, the durable worker had no provider retry step. A later
RevenueCat webhook could also call the provider's get-or-create customer
endpoint after local deletion and recreate the provider customer. The native
SDK could similarly retain the deleted App User ID across app launches.

The durable worker now requests RevenueCat deletion before local deletion and
on each retained late-upload sweep. RevenueCat 200 and 404 are treated as
retry-safe accepted outcomes; any other response, transport error, or missing
server key when native billing is required leaves the account fenced and the
job retryable. Webhook subscription reconciliation skips missing/deletion-fenced
users before the get-or-create lookup, including transfer events. Native credit
sync has the same pre-lookup guard. Billing writes require `deleted_at is null`.
The 202 response now accurately says provider and private-storage cleanup can
still be pending. This does not cancel an Apple or Google subscription; the
existing separate store-cancellation instruction remains.

The native client now records the deleting account ID before sending the
irreversible request, logs the RevenueCat SDK out after a successful server
response, and retries logout after a restart if that attempt fails or the app
closes between server success and local cleanup. A cached copy of the deleted
account cannot be aligned back into the SDK; a different signed-in account can
align only after the old SDK identity is cleared. Normal success clears the
local marker after SDK logout and local auth cleanup. The changed billing,
account, and runtime-loader scripts have new cache-addressed URLs.

## Verification

- Focused deletion and RevenueCat tests: 40 passed. Cases cover provider 500
  then worker restart and 404, missing server key, configured native billing
  without a server key, repeated provider deletion after storage failure,
  deleted-user ordinary and transfer webhooks, failed local identity lookup,
  and fenced native-credit sync.
- Python lint and Git diff integrity passed.
- The JavaScript contract validates 55 files and includes SDK logout retry
  after restart, a transient logout error, stale cached identity suppression,
  and subsequent sign-in as a different account.
- Production build preflight and the rebuilt native web bundle passed. A
  returning-PWA service-worker fixture loaded the new runtime from cache with
  zero origin asset requests and zero browser errors.
- The local store verifier correctly remains red: both RevenueCat public SDK
  keys, Android Firebase configuration, and an iOS project are absent on this
  Windows checkout. This is not a signed-device or submission result.
- The remaining local Python suite passed when excluding two password-hash
  tests that require Argon2. The bundled Python runtime on this host lacks the
  `argon2` package; the complete local run failed only those two tests for that
  dependency reason. CI with declared project dependencies must be green
  before this draft is considered review-ready.
- Production sites returned HTTP 200 with no reported 24-hour runtime error
  cluster in the read-only operating check. The protected aggregate still has
  one comparable September account, D1 return 1/1, no observed Project or
  artifact milestone, and no payer. D7 remains ineligible. Recognized revenue
  and current social-platform outcomes are unavailable in this check.

## Decision and next action

Keep PR #37 in draft. Review the provider-deletion contract against the exact
store billing setup. Native store release must confirm the backend RevenueCat
secret API key and webhook authorization are configured alongside the public
SDK keys; otherwise a free native user has no durable server-side evidence
that provider cleanup is required. Obtain a green complete CI run, then repeat deletion,
purchase/restore, webhook, and credit-sync behavior on signed test devices.
Do not scale paid acquisition or change activation UX from the one-account
sample. Wait for a legitimate result-to-Project offer/save/return journey or a
reproducible user failure before changing that flow.
