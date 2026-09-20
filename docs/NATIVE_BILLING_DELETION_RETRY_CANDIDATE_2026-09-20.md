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

A second review found that an explicit pre-fence Stripe-cancellation 502 left
the billing guard on an active account. The client now releases a *new* guard
only for a definite pre-fence rejection (400, 401, or the exact 502 code),
or when preparation failed before any DELETE was sent. A prior ambiguous
deletion attempt remains guarded even if a later retry fails validation.
Network failures and uncertain 503 responses deliberately remain guarded;
there is not yet a server-confirmed status-reconciliation recovery path.

Native billing is now a deliberate backend release setting, off by default.
`CRUMP_ENABLE_NATIVE_BILLING=true` fails startup unless both the RevenueCat
server key and non-placeholder Bearer webhook authorization are configured.
The public, content-free `/api/billing/native-readiness` endpoint returns only
whether that validated setting is enabled, with `Cache-Control: no-store`.
The native client requires this server signal before SDK configuration, so
public keys in a candidate bundle cannot by themselves create a provider
customer. A failed concurrent readiness check does not log out an already
active store identity.

## Verification

- Focused backend configuration, deletion, RevenueCat, and readiness tests:
  60 passed. Cases cover provider 500
  then worker restart and 404, missing server key, configured native billing
  without a server key, repeated provider deletion after storage failure,
  deleted-user ordinary and transfer webhooks, failed local identity lookup,
  and fenced native-credit sync.
- Python lint and Git diff integrity passed.
- The JavaScript contract validates 55 files and includes SDK logout retry
  after restart, a transient logout error, stale cached identity suppression,
  subsequent sign-in as a different account, definitive versus ambiguous
  deletion failures, and disabled/offline/concurrent readiness responses.
- Production build preflight and the rebuilt native web bundle passed. A
  returning-PWA service-worker fixture loaded the new runtime from cache with
  zero origin asset requests and zero browser errors.
- The local store verifier correctly remains red: both RevenueCat public SDK
  keys, Android Firebase configuration, and an iOS project are absent on this
  Windows checkout. This is not a signed-device or submission result.
- The local Python suite passed with only the two known password-hash tests
  excluded. The bundled Python runtime on this host lacks `argon2`; the
  unfiltered run failed those two host-dependency tests and initially caught
  a new browser API inventory count, which was corrected and rechecked.
  Complete CI with declared project dependencies remains required.
- On 2026-09-20, production pages returned HTTP 200 and Vercel reported no
  4xx, 5xx, or grouped runtime errors in the prior 24 hours. The protected
  aggregate had one comparable external account: verified, activated, D1 1/1,
  no observed useful feedback, durable Project value, checkout, or payer. D7
  is ineligible. Recognized revenue and matched variable cost are unavailable,
  not zero. Signed-in social checks found no active ads; those channels remain
  owned by marketing, not this source-only change.

## Decision and next action

Keep PR #37 in draft. Before any native release, add durable per-user evidence
that the SDK may have created a RevenueCat customer, so later disabling the
server flag or removing the key cannot silently skip a free user's provider
deletion. Add server-confirmed status reconciliation for an ambiguous failed
DELETE; do not clear the guard on a mere local timeout. Native release must
verify the backend setting and both server credentials, alongside public SDK
keys, exact products, a green complete CI run, and deletion, purchase/restore,
webhook, and credit-sync behavior on signed test devices.
Do not scale paid acquisition or change activation UX from the one-account
sample. Wait for a legitimate result-to-Project offer/save/return journey or a
reproducible user failure before changing that flow.
