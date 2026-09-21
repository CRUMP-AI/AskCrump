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
on each retained late-upload sweep. A RevenueCat 200 accepts the local account
deletion but only queues asynchronous provider cleanup; a 404 confirms that
customer is absent for that sweep. The durable job can be purged after the
30-hour upload window only if that same final sweep sees 404, or if no native
cleanup obligation exists. Repeated 200 responses, any other response,
transport error, or a missing required server key keep the job retryable.
When a server key exists, an older free account without a local native marker
still receives the precautionary provider DELETE. The possible-provider-
identity marker is durably snapshotted before that request, so a lost response
or a later missing key cannot erase the cleanup obligation. Failure to confirm
the marker write leaves the local account fenced without contacting the provider.
After local deletion, provider failures do not starve the separate late-upload
Storage sweep. Webhook subscription reconciliation skips missing/deletion-fenced
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

The next source-only safeguard records a monotonic, server-authoritative
native-identity marker for the authenticated account before the SDK can
configure or log in. The client requires an exact, fresh owner confirmation;
missing, mismatched, unavailable, or deletion-fenced results cannot start the
SDK. Deletion snapshots this possible-provider-customer obligation onto the
durable job before local-account removal, so later disabling the native flag
does not skip provider cleanup. The new SQL migration remains unapplied.

The next client-side candidate narrows the interval after that first marker
check: recheck the authenticated owner and server fence immediately before and
after SDK `configure` or `logIn`, recheck an already configured SDK identity
before accepting it, and recheck before native purchase, restore, or customer
refresh operations. Missing, changed, or fenced ownership must fail closed.
These are per-operation checks, not a lease, lock, or transactional guarantee
around a third-party SDK call. Their exact behavior and concurrent-account
tests must pass before this paragraph can be treated as a verified release
result.

An independent review found a remaining release-blocking race: another device
can delete the account and finish RevenueCat cleanup while a previously
authorized native client is paused between marker confirmation and SDK
`configure` or `logIn`. That client can resume later and recreate the same
provider customer. Session revocation and the 30-hour deletion sweep do not
prove a strict no-recreation guarantee. RevenueCat documents that its
[get-customer API creates absent customers](https://www.revenuecat.com/docs/api-v1/customers)
and that [SDK logout is needed after deletion](https://www.revenuecat.com/blog/engineering/app-store-account-deletion);
deletion itself is asynchronous. The provider's
[customer-blocking facility](https://www.revenuecat.com/docs/customers/blocking-customers)
is limited and warns against using it for legitimate subscribers,
so it is not an automatic account-deletion workaround. Native release stays
blocked pending a practical cross-device setup/deletion coordination design
and race tests; a mere second read or short lease alone cannot prove an
arbitrarily paused client will not resume after cleanup.

The per-operation rechecks reduce ordinary stale-client windows, but a device
can still pause after its last successful server check and resume an SDK call
after a second device completes account deletion. A purchase can also be
in flight during deletion. Neither the marker nor the rechecks prove provider
non-recreation or prevent every cross-device charge. Keep native billing OFF
and release held until signed, two-device tests cover deletion during SDK
setup, identity switching, and an in-flight purchase, with provider records
observed after cleanup and delayed resume. A remaining strict-guarantee gap
requires an explicit architecture/provider decision; tests alone cannot prove
the absence of an arbitrarily delayed replay.

Independent follow-up review found another race in this source candidate: an
account-delete request and the due-job worker can overlap. One worker can see
404 while another later sees 200 for a recreated customer; the first must not
purge by owner/token from stale local state. The source-only correction now
claims a due job by atomically advancing its existing attempt generation and
placing a 30-minute crash-recovery lease on its next-attempt time. Every job
update and final purge compares that generation; a re-entrant deletion request
does not shorten an active lease. A deterministic fixture pauses the 404 worker
past its lease, lets a newer worker record 200, and proves the stale worker
cannot purge the newer obligation. This is not a provider non-recreation
guarantee: a client can still recreate a customer after the final 404.

Historical unmarked jobs whose user row is already gone and whose last error
was cleared remain ambiguous if the server key disappears. They cannot be
distinguished from ordinary web-only jobs by the existing durable fields.
Known queued/uncertain error codes are promoted to a durable marker and held
without a key, but the unknown historical case requires an operator/provider
audit or a separately approved backfill before native release. No migration
backfill or remote provider action is part of this source candidate.

## Verification

- Focused backend configuration, deletion, RevenueCat, and readiness tests:
  60 passed. Cases cover provider 500
  then worker restart and 404, missing server key, configured native billing
  without a server key, repeated provider deletion after storage failure,
  deleted-user ordinary and transfer webhooks, failed local identity lookup,
  and fenced native-credit sync.
- A subsequent source-only reconciliation fixture verifies repeated provider
  200 beyond 30 hours, 200 then 404 on the final sweep, 200 followed by
  timeout/5xx/missing key after local deletion, earlier 404 followed by final
  200, nonnative deletion, and legacy queued/uncertain jobs with a missing key.
  Historical unmarked-customer fixtures also prove the precautionary DELETE,
  durable marker promotion before provider contact, write-failure recovery, and
  normal 404 purge. The later overlap fixture proves generation-fenced
  finalization across request/cron workers, including lease expiry, a later
  queued 200, re-entrant begin, and crash recovery. Focused counts are reported
  by the current test run, not the earlier 21/21 baseline.
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
- The marker endpoint, durable snapshot, and client fail-closed cases passed
  the focused native/deletion/API group (**51/51**). The complete local Python
  suite passed apart from the same two host-runtime Argon2 dependency tests;
  with those two excluded it passed. JavaScript, production preflight, native
  web bundle, client-secret boundary, returning-PWA worker, Ruff, and diff
  integrity passed. The local browser matrix could not launch its installed
  Chromium (`spawn UNKNOWN`), so CI and signed-device checks remain necessary.

## Decision and next action

Keep PR #37 in draft. The per-user native marker, queued-versus-absent
reconciliation, and generation-fenced worker finalization are source
candidates, not a complete cross-device deletion guarantee. Resolve the
paused-client recreation race and historical unmarked/no-key audit before
enabling native billing, including the practical
per-operation rechecks and signed two-device/in-flight-purchase verification;
do not describe those checks as a provider non-recreation guarantee. Add
server-confirmed status reconciliation for an ambiguous failed DELETE; do not clear the guard
on a mere local timeout. Native release must verify ordered schema migrations,
the backend setting and both server credentials, public SDK keys, exact
products, a green complete CI run, and deletion, purchase/restore, webhook,
and credit-sync behavior on signed test devices.
Do not scale paid acquisition or change activation UX from the one-account
sample. Wait for a legitimate result-to-Project offer/save/return journey or a
reproducible user failure before changing that flow.
