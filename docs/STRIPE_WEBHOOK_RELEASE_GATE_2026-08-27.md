# Stripe webhook release gate — 2026-08-27

## Outcome

Both live Ask Crump Stripe destinations now deliver directly to the canonical `www` host and have
returned HTTP 200 to signed Stripe replays. Their original descriptions, API version, signing
secrets, and narrow event allowlists are preserved.

| Destination | Direct endpoint | Final scope | Signed proof |
| --- | --- | --- | --- |
| Subscription entitlement | `https://www.askcrump.com/api/stripe/webhook` | 3 original events | 200 |
| Crump Credits | `https://www.askcrump.com/api/billing/credits/stripe-webhook` | `checkout.session.completed` only | 200 |

## Repair evidence

The first credits replay reached the direct handler and returned 400 because production stored the
credits signing secret under the deployed plural alias `STRIPE_CREDITS_WEBHOOK_SECRETS`, while the
handler read the documented singular key before falling back to the unrelated subscription secret.
No secret value was displayed, copied into source, or rotated.

Commit `4dfed9b` makes the credits handler prefer the documented singular key, accept the deployed
plural alias for backward compatibility, and use the legacy fallback last. Automated coverage proves
the plural alias is accepted, the unrelated subscription secret is rejected, and the singular key
takes precedence.

Production deployment `dpl_H5Dn15BVY5rzh5G6azq36eKiTXb3` reached `READY` on version 5.9.27. The
final signed credits replay returned 200. The temporary `checkout.session.expired` test event was
then removed, restoring the credits destination to its original single-event scope. The harmless
expired-session replay did not enter either handler's subscription or credit mutation path.

## Release verification

- 295 backend tests passed.
- 40 JavaScript validations passed.
- Production build, native bundle, store metadata, and signing-source checks passed.
- Production health returned 5.9.27.
- The two payment routes had no runtime error cluster in the release window.
- Deployment logs were limited to 200 and 302 responses in the inspected window.
- CI [33126121600](https://github.com/CRUMP-AI/AskCrump/actions/runs/33126121600), Android
  [33126121646](https://github.com/CRUMP-AI/AskCrump/actions/runs/33126121646), and iOS
  [33126121595](https://github.com/CRUMP-AI/AskCrump/actions/runs/33126121595) completed successfully.

No price, product, customer, tax setting, payment, or signing secret changed during this gate. The
next monetization proof is the first real checkout reconciled against Ask Crump entitlement or
durable credit state.
