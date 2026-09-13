# Stripe destination integrity release

Date: 2026-09-13

## Outcome

Ask Crump now requires the exact Stripe HTTPS origin before any web credit,
subscription, or subscription-management button may navigate away from the app.
Checkout is limited to `checkout.stripe.com`; the customer portal is limited to
`billing.stripe.com`. Lookalike hosts, embedded credentials, non-HTTPS URLs,
explicit nonstandard ports, malformed URLs, and unrelated destinations fail
closed.

The same rule now runs at both boundaries:

- the server validates Stripe's returned destination before it sends a URL to
  the browser or records the corresponding opened event; and
- every active browser billing layer validates the destination again before
  navigation, restores the button on rejection, and shows a controlled error.

The release preserves Stripe-hosted Checkout, dynamic payment methods, existing
idempotency identities, session-expiry recovery, subscription reconciliation,
credit grants, and webhook verification. It does not enable Stripe Tax, change
prices or products, alter payment-method settings, rotate credentials, open a
live checkout, or create a charge.

## Verification

- Product commit `3cb4687cacd52f2da2dacf768c404b657491a1e1` is on `main`.
- Production deployment `dpl_CfY7tjcWUQAm7pYJ1dCrp964LNJ8` is `READY`.
- GitHub CI `34779728633`, Android source/bundle verification `34779728628`, and
  iOS source verification `34779728653` completed successfully.
- The complete Python suite passed 1,018/1,018.
- JavaScript validation passed 54/54 files.
- The browser control matrix passed 45/45 workflows.
- The checkout recovery workflow exercised four button attempts: two bounded
  authentication handoffs and two deceptive-destination rejections. It proved
  zero automatic purchase attempts, preserved the selected credit/plan intent,
  kept the browser on Ask Crump, restored both buttons, and produced zero
  browser errors.
- Server fixtures rejected deceptive Checkout and Customer Portal hosts before
  analytics or navigation.
- Production health returned HTTP 200 on version 5.9.76.
- Seven deployed billing/runtime assets matched the committed bytes exactly.
- Signed-in production inspection reached Settings → Plan & credits and showed
  all three credit packs and both subscription actions ready. No purchase button
  was clicked.
- The first post-release Vercel runtime-error query was empty.

## Operating implication

The web purchase controls now have an explicit destination-safety contract in
addition to their existing action, timeout, idempotency, and recovery contracts.
The remaining monetization outcome gate is still a legitimate customer purchase
and provider reconciliation. Do not infer conversion lift from a safety release,
and do not enable tax collection until the founder confirms applicable tax
registrations and the tax configuration is separately reviewed.
