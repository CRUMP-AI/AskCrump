# Stripe webhook payload boundary release — 2026-09-13

## Outcome

Ask Crump's subscription and one-time credit webhook routes now reject a signed body that is
not a valid Stripe event object with a controlled HTTP 400 response. Previously, both routes
verified the signature and then called `json.loads(body)` followed by dictionary methods without
checking either decoding success or the decoded shape. Damaged JSON, invalid UTF-8, an array, or
a scalar could therefore raise an unhandled exception and produce a 500 response.

Commits `bb91fea7980cf0fe4dfc4cf95b827b71ae6d0ee3` and
`ece0ed22b56ea07d662e8f090ab384ddc5bac1f4` add shared fail-closed decoding for both the outer
event and its nested `data.object` envelope. Checkout metadata must also be a dictionary when it
is present. Both webhook routes use these boundaries, and signature verification still runs first.
Valid event behavior,
Checkout completion reconciliation, duplicate protection, current-provider subscription refresh,
credit granting, dynamic payment methods, catalog values, and customer-facing billing controls
are unchanged.

## Verification

- Subscription webhook regression coverage rejects malformed JSON, an array, a JSON string, and
  invalid UTF-8 after the signature boundary.
- Credit webhook regression coverage rejects the same four payload classes.
- Relevant Checkout and subscription events also reject malformed `data`, `object`, and `metadata`
  shapes instead of raising an unhandled exception. Unrelated valid event types remain safely
  acknowledged without touching billing state.
- Focused credit/subscription tests passed 40/40.
- The complete Python suite passed 1,033/1,033.
- JavaScript validation passed 54/54.
- The production build preflight, native-web bundle, and client-credential boundary passed.
- The complete credential-free browser control matrix passed 45/45, including Projects, Files,
  foreground viewers, Image Studio and Precision Edit, Video and reference images, Library,
  Settings, account entry/recovery, plans, credits, and checkout recovery.
- GitHub Actions runs `34780633156` and `34781363674` completed successfully for Python 3.12 and
  JavaScript.
- Production deployments `dpl_AGTZKejnvTEfqYQdALoSrumpgobX` and
  `dpl_Fif5gEPjJevtKAV8vpZ5Uz6gEvSV` are READY with no alias error on the six expected Ask Crump,
  Clever Crump, and Vercel aliases.
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
