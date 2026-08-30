# Feature access recovery release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

A user who reaches a real plan, credit, or Project-cap boundary can now understand the
constraint and move directly into the existing Plan & credits review instead of stopping at a
plain error.

The recovery is proportional to the context:

- chat opens the Plan & credits review when the server returns an explicit access code;
- manuscript planning, drafting, export, and video creation show an inline recovery action;
- a durable manuscript run waiting on credits keeps its saved progress and offers the same
  recovery beside Resume;
- Project creation and conversation-to-Project handoff recover when the active-Project cap is
  reached.

Opening checkout remains a separate, explicit choice inside Plan & credits.

## Evidence and decision

The server already returned structured access responses containing a fixed code, required tier,
credit cost, and current balance. Chat opened the upgrade surface only for one subscription flag,
and the product workspaces reduced the other responses to status text. A user who had already
received or attempted valuable work therefore had no consistent next step at the commercial
boundary.

This release uses only the existing server-authoritative codes:

- `SUBSCRIPTION_REQUIRED`
- `CREDITS_REQUIRED`
- `FEATURE_LIMIT_REACHED`
- `PROJECT_LIMIT_REACHED` in the Project workspace

Network failures, provider failures, validation errors, and unrelated API responses do not open
or display a billing recovery action.

## Product and safety contract

- The response details remain attached to the client error so the interface can show exact,
  server-returned costs and balances.
- Chat uses the existing combined Plan & credits center for explicit access codes.
- Creation tools add one accessible recovery button beside the original error.
- The recovery button opens a review surface; it does not create a Stripe checkout, buy credits,
  change a subscription, change an entitlement, or retry a generation.
- A saved manuscript waiting on credits remains durable and resumable after the user resolves the
  boundary.
- Project-cap recovery applies to both the Projects form and conversation-to-Project handoff.
- No price, allowance, credit cost, tier policy, metering rule, provider route, database schema,
  RLS policy, payment route, or analytics payload changed.

## Verification

- All 500 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production build preflight passed.
- The native web bundle was rebuilt successfully.
- Store metadata source verification passed.
- A credential-free browser fixture executed the real chat transport and product runtime and
  proved:
  - a 402 chat response retains `CREDITS_REQUIRED` and its exact credit requirement;
  - chat opens one recovery review;
  - video shows **Add credits or compare plans** beside the exact balance message;
  - the video recovery opens only after the user selects it;
  - selecting recovery makes no additional API request;
  - no browser error occurred.
- Diff integrity passed.

The native release verifier continued to report the pre-existing store-submission gates: the iOS
native project is missing, the RevenueCat Android and iOS public SDK keys are empty, and Android
FCM configuration is absent. These are unrelated to this web/PWA release and remain explicitly
unclaimed.

## Production release

- Feature commit: `63793f5`
- Deployment: `dpl_7tuPryyC49ShuirGiUc8UEwaUpWg`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r143`
- Runtime and changed assets: `5.9.76-feature-recovery-1`
- Canonical health: HTTP 200, service `Ask Crump`, version `5.9.76`

The canonical app, exact runtime loader, chat transport, product controller, stylesheet, service
worker, and health route returned successfully and contained their expected release markers.
After the deployment had been ready for more than one minute, the inspected deployment reported
only HTTP 200 observations, no runtime-error cluster, and no warning, error, or fatal log.

No production account, message, Project, manuscript, video, credit purchase, subscription,
payment, checkout, or synthetic funnel event was created for verification.

## Next operating decision

Observe the first legitimate access boundary through Plan-center review and either an explicit
checkout choice or a safe return to work. Compare that content-free outcome with later successful
use before changing prices, allowances, or acquisition spend.
