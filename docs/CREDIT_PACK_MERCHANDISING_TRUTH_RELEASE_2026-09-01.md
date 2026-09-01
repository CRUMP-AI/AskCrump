# Credit-pack merchandising truth release — 2026-09-01

## Outcome

Ask Crump no longer labels or visually recommends the 150-credit pack as **Popular** without
authoritative sales evidence. Both active Plan & credits renderers and the loading state present the
50-, 150-, and 400-credit packs neutrally and in the existing order.

The separate Professional plan emphasis remains intact. Pack quantities, displayed prices,
availability checks, accessible action names, keyboard behavior, balance/history hydration,
checkout routes, completion/recovery logic, plans, entitlements, and payment behavior are unchanged.

This bounded correction does not claim that universal server-authoritative credit quoting is live.
The separate credit-charge disclosure candidate and its database/action-time release gate remain
held. Production still requires that larger release before credit packs are promoted or broad paid
acquisition enters credit boundaries.

## Release evidence

- Commit: `475f2c53d54ff5133c3c175e9b08a054e168ec98`.
- Production deployment: `dpl_DYLhVAFhoag1HWhudhFhG61jKfk3`, `READY` with no alias error on all
  six production aliases.
- Web/PWA/native asset identity: `5.9.76-credit-pack-truth-1`; service-worker cache:
  `ask-crump-new-body-v1-r199`.
- Before release, both exact production billing assets returned HTTP 200 and contained the 150-pack
  `Popular` badge and pack-specific featured condition; the current renderer also included the claim
  in its loading markup.
- After release, the canonical app, runtime loader, service worker, health endpoint, both exact
  billing JavaScript owners, the billing stylesheet, and the shell stylesheet returned HTTP 200.
  Neither JavaScript owner contained the claim or conditional 150-pack emphasis; neither stylesheet
  contained a pack-featured rule. The Professional plan-featured rule remained present.
- A real-runtime browser fixture ran at 390×844 and 1280×720. Each run proved three neutral pack
  cards, zero pack-featured cards, zero unsupported comparative claims, zero nested interactive
  cards, three exact purchase actions, the unchanged 50/150/400 order and $4.99/$9.99/$19.99
  labels, keyboard focus, one safely blocked checkout attempt, restored action labeling, and zero
  browser errors.
- All **740 Python tests**, **47 JavaScript validations**, Python compilation, production preflight,
  native web-bundle generation, store metadata, mobile signing-source controls, and diff integrity
  passed.
- The initial release window contained three successful HTTP 200 runtime requests, no 4xx or 5xx
  log, no runtime-error cluster, and no warning/error/fatal log.

No checkout completed or provider page opened. No price, pack, plan, entitlement, allowance,
subscription, balance, ledger, payment, refund, account, customer content, analytics record, database
object, environment value, social post, campaign, or spend changed during verification.

## Remaining gate

Do not promote credit packs or claim exact universal pre-charge disclosure from this release. The
server-authoritative quote/confirmation/idempotency/manuscript-ceiling candidate still requires its
dedicated action-time authorization, a fresh migration identity after remote-ledger reconciliation,
full revalidation, production acceptance, and a legitimate privacy-safe observation.
