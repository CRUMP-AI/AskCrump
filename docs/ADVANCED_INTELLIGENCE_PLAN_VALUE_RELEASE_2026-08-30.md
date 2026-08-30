# Advanced Intelligence Plan Value Release — 2026-08-30

## Outcome

Ask Crump's public pricing, signed-in Plan and credits center, fallback plan renderer, and subscription renderer now describe the same paid Intelligence value:

- Professional includes **Advanced Intelligence: Think Longer + Always Review** and retains premium creation access.
- Enterprise includes the same Advanced Intelligence controls alongside its larger usage allowances and Cinematic video access.
- Paid-plan registration now names Advanced Intelligence while preserving the existing statement that no purchase occurs until checkout is reviewed and confirmed.

Prices, quotas, entitlements, credits, payment behavior, and checkout confirmation were not changed.

## Delivery controls

- All changed plan renderers and the authentication controller use the `5.9.76-plan-intelligence-1` asset version.
- The PWA cache advanced to `r158` so installed clients replace stale pricing and signup assets.
- Regression contracts require the exact paid benefit in both tiers and reject the superseded Professional-only wording.

## Verification

- 563 Python tests passed.
- 45 JavaScript files passed the integration validation.
- Production build preflight and the native web bundle completed.
- Real Edge checks at 1,440-by-1,000 and 390-by-844 verified three public plan cards, two paid Advanced Intelligence promises, two matching signed-in plan cards, zero stale promises, zero horizontal overflow, and zero browser errors.
- Feature commit `4407732e2510343346ec803ae69f5b946a916ffd` deployed as `dpl_FXc2HxuN8cr5boK4m9Ej4tswadAH` and reached READY on all six aliases.
- Read-only live fetches confirmed the homepage, app shell, service worker, authentication controller, billing controller, subscription controller, and `/api/health` returned HTTP 200 with cache `r158` and the expected value language.
- Vercel reported no runtime error cluster and no warning, error, or fatal log for the deployment in the release window.

## Operating interpretation

The release removes a pre-purchase value mismatch; it does not prove a conversion increase. A same-day service-role aggregate refresh returned zero comparable external account, artifact, and plan-conversion activity in the current measurement windows. Legitimate acquisition traffic remains the binding evidence constraint before changing pricing or claiming lift.

