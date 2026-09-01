# Billing-safe account deletion release — 2026-09-01

## Outcome

Ask Crump will no longer erase its local account and billing linkage when it cannot confirm that an
open Stripe web subscription stopped. Deletion now removes the Stripe customer first, verifies an
exact successful provider response, and only then calls the existing atomic local-account deletion.
If Stripe is unavailable, rejects the request, or returns an unconfirmed identity, Ask Crump keeps
the account intact and tells the user to retry or open Plan & credits.

Canceled and otherwise terminal subscriptions retain the privacy-preserving best-effort path: a
temporary provider cleanup failure does not prevent local deletion when there is no evidence of an
open web subscription. Store subscriptions remain subject to Apple or Google cancellation because
RevenueCat customer deletion cannot cancel the underlying store renewal.

## User contract

The in-app deletion dialog, public deletion-help page, and legal billing section now say the same
thing:

- a successful account deletion cancels an associated Stripe web subscription immediately;
- deleting the Stripe customer does not automatically issue a refund; and
- an Apple App Store or Google Play subscription must be canceled separately in store settings.

The server failure message explicitly states that no account data was deleted when web-subscription
cancellation could not be confirmed. The form remains enabled for a safe retry.

## Automated acceptance

Executable coverage proves:

- `active` and `past_due` Stripe subscriptions require provider confirmation;
- a known Stripe subscription with an internally ambiguous `inactive` state fails closed;
- a customer created for an abandoned Checkout attempt, with no subscription evidence, can still be
  deleted;
- a native RevenueCat subscription does not get misclassified as a Stripe subscription;
- a missing Stripe key, provider rejection, or mismatched success payload blocks local deletion;
- an exact Stripe deletion confirmation allows the atomic database deletion; and
- a canceled subscription preserves local privacy deletion when provider cleanup is unavailable.

The static contract also keeps the web/store/refund explanation aligned across all three customer
surfaces.

## Release evidence

- Code commit: `a255695`.
- Production deployment: `dpl_41ryMztKTU3GrTNpobdZrDzEL2iK`, `READY` on all six aliases.
- Production service-worker cache: `ask-crump-new-body-v1-r179`.
- Exact account asset: `5.9.76-account-deletion-billing-1`.
- 709 Python tests passed.
- 47 JavaScript files passed the integration contract.
- Python compilation, production preflight, native web-bundle generation, store metadata, mobile
  signing-source controls, and diff integrity passed.
- The signed-in production app displayed the exact new deletion warning. The dialog and Settings
  were then closed without entering a password or submitting deletion.
- The versioned account asset, service worker, and deletion-help page returned HTTP 200 with the
  expected release markers.
- The release deployment showed successful observed responses, no `/api/account` runtime-error
  cluster, and no warning/error/fatal runtime log.

No real account, password, customer, subscription, payment, refund, entitlement, credit, or provider
configuration was changed during verification.

## Remaining gates

The first legitimate paid-account deletion still needs owner-controlled end-to-end evidence across
Stripe cancellation, webhook delivery, local deletion, session revocation, and invoice state. The
first legitimate native deletion must confirm the store-cancellation guidance on signed iOS and
Android builds. Native release readiness separately still requires generated platform projects,
RevenueCat public SDK keys, signed-device purchase/restore proof, screenshots, reviewer credentials,
and store-console completion.
