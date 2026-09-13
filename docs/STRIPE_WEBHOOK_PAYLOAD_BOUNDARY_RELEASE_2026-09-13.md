# Stripe webhook payload boundary release — 2026-09-13

## Outcome

Ask Crump's subscription and one-time credit webhook routes now reject a signed body that is
not a valid Stripe event object with a controlled HTTP 400 response. Previously, both routes
verified the signature and then called `json.loads(body)` followed by dictionary methods without
checking either decoding success or the decoded shape. Damaged JSON, invalid UTF-8, an array, or
a scalar could therefore raise an unhandled exception and produce a 500 response.

Commit `bb91fea7980cf0fe4dfc4cf95b827b71ae6d0ee3` adds one shared fail-closed decoder and uses it
at both webhook boundaries. Signature verification still runs first. Valid event behavior,
Checkout completion reconciliation, duplicate protection, current-provider subscription refresh,
credit granting, dynamic payment methods, catalog values, and customer-facing billing controls
are unchanged.

## Verification

- Subscription webhook regression coverage rejects malformed JSON, an array, a JSON string, and
  invalid UTF-8 after the signature boundary.
- Credit webhook regression coverage rejects the same four payload classes.
- Focused credit/subscription tests passed 33/33.
- The complete Python suite passed 1,026/1,026.
- JavaScript validation passed 54/54.
- The production build preflight, native-web bundle, and client-credential boundary passed.
- The complete credential-free browser control matrix passed 45/45, including Projects, Files,
  foreground viewers, Image Studio and Precision Edit, Video and reference images, Library,
  Settings, account entry/recovery, plans, credits, and checkout recovery.
- GitHub Actions run `34780633156` completed successfully for Python 3.12 and JavaScript.
- Production deployment `dpl_AGTZKejnvTEfqYQdALoSrumpgobX` is READY with no alias error on the
  six expected Ask Crump, Clever Crump, and Vercel aliases.
- All four custom-domain health endpoints returned HTTP 200 at version 5.9.76.
- Unsigned malformed production probes returned HTTP 400 at the signature boundary for both
  webhook routes; they made no billing mutation.
- The initial one-hour Vercel runtime-error scan was empty.

## Deliberate boundaries

No checkout, purchase, refund, dispute, subscription, catalog, tax, credential, webhook endpoint,
provider event selection, database row, or customer data was changed during verification. A real
signed Stripe delivery remains provider-owned evidence. Credit refund/dispute recovery remains a
separate commerce-lifecycle gate because the currently verified credit webhook path is scoped to
Checkout completion; it must not be claimed complete until the required Stripe events, an
idempotent ledger reversal policy, and a legitimate end-to-end provider exercise are all in place.

Stripe Tax remains intentionally disabled until the business has confirmed applicable tax
registrations; this release does not change that decision.
