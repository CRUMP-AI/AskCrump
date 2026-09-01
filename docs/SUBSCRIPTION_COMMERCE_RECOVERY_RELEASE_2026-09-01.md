# Subscription commerce recovery release — 2026-09-01

## Outcome

Ask Crump now treats a troubled Stripe subscription as something to repair, not an invitation to
buy a second subscription. A non-entitled but still-open subscription exposes one clear **Fix
billing** action and retains the customer-portal route. Fresh Professional and Enterprise checkout
buttons remain available only when there is no open subscription that needs management.

Subscription Checkout retries also carry one content-free attempt identifier from the browser to a
Stripe `Idempotency-Key`. If the browser times out after Stripe created a session, retrying the same
attempt returns the same provider operation instead of quietly creating another Checkout Session.
The backend accepts older clients without this field and verifies that Stripe returned both a
Checkout Session ID and an HTTPS `checkout.stripe.com` destination before exposing either value.

## Lifecycle integrity

Stripe does not guarantee webhook delivery order. Subscription update and deletion events therefore
no longer write the embedded event snapshot directly into the account. Ask Crump now:

1. resolves the account by its Stripe customer;
2. rejects an event for a subscription that has already been superseded;
3. retrieves the provider's current state for the still-current subscription;
4. verifies the returned subscription and customer identities; and
5. applies the catalog plan separately from the effective entitlement state.

That separation preserves which plan needs attention while `tier_name()` continues to deny paid
allowances for `past_due`, `unpaid`, `incomplete`, paused, expired, or canceled states. A terminal
deletion still falls back to the signed event only when Stripe reports that the deleted object is no
longer retrievable, and only after the current-subscription identity check passes. Temporary provider
failures return a retryable webhook response rather than accepting an unverified mutation.

## User-interface acceptance

A credential-free fixture runs the real Plan-center layers in both states:

- `past_due`: one recovery card, one **Fix billing** action, zero checkout requests, one portal
  request after activation, and zero browser errors;
- normal Free state: **Choose Professional** and **Choose Enterprise**, exactly one checkout request
  after deliberate Professional selection, zero portal requests, and zero browser errors.

The same browser session activated the production PWA update and confirmed the four exact
`5.9.76-commerce-recovery-1` billing assets. The signed-in live Plan & credits center rendered one
dialog with both normal plan choices and no browser error; no checkout button was activated.

## Release evidence

- Code commit: `86676a6`.
- Production deployment: `dpl_CQ9o4XzBwyKgUTDfDgD2M2QQ6zzr`, `READY` on all six aliases.
- Production service-worker cache: `ask-crump-new-body-v1-r178`.
- 702 Python tests passed.
- 47 JavaScript files passed the integration contract.
- Production preflight and native web-bundle generation passed.
- Store metadata and mobile signing-source controls passed.
- Canonical health returned HTTP 200 on version 5.9.76.
- The settled deployment showed 29 observed HTTP 200 responses, no runtime-error cluster for the
  subscription routes, and no warning/error/fatal runtime log.

No price, allowance, credit behavior, product, tax setting, customer, payment, subscription, or
provider configuration was changed during verification. No real checkout or charge was created.

## Remaining gates

The first legitimate external checkout must still be reconciled from Checkout Session through
provider subscription state to Ask Crump entitlement before paid conversion is considered proven.
Refund/dispute operations, invoice collection, tax registrations, unit economics, and the separately
gated credit-disclosure candidate remain outside this release. Native store submission still requires
generated Android/iOS projects, RevenueCat public SDK keys, signed-device purchase/restore proof,
screenshots, reviewer credentials, and console completion.
