# Parallel workspace asset fetch release

Date: 2026-08-29

Feature commit: `0083a1d`

Production deployment: `dpl_zWcikDWvY5SY2ETcmkPNSU2Htz3Y`

## Outcome

Ask Crump's authenticated workspace now starts fetching its complete visual and script plan in
parallel while preserving the established cascade and execution order. Previously, ten base styles
loaded together, eight final-authority styles waited one after another, and all 29 classic scripts
started only after the prior script completed.

The corrected loader inserts all 18 styles in final cascade order before awaiting them, primes all
29 script downloads, and then executes those scripts in the unchanged proven order. This removes the
network waterfall without weakening the authentication gate, changing product behavior, or making
optional private-data requests during ordinary Ask startup.

No account, conversation, Project, file, artifact, subscription, credit, payment, analytics event,
provider setting, environment variable, or production record was created or changed during
verification.

## Evidence before the change

- Vercel Speed Insights reported a seven-day desktop Real Experience Score of 79 for `/app` across
  317 performance events. The public homepage and parent-company route scored 100 in the same view.
  Mobile did not yet have enough Speed Insights data for a score.
- A credential-free real-loader fixture applied the same 120-millisecond simulated fetch delay to
  every asset. The prior runtime reached `ready` in 5,060 milliseconds, requested 18 styles with a
  maximum of ten concurrent style fetches, preloaded zero scripts, and executed all 29 scripts in
  order with zero browser errors.
- Protected aggregate growth, artifact, and plan-conversion reports still lacked a comparable
  external journey. That boundary did not support another authentication redesign or a claim about
  conversion lift.

## Verification

- Under the identical fixture conditions, the corrected runtime reached `ready` in 299
  milliseconds. All 18 styles were concurrent, all 29 scripts were primed before execution, all 29
  scripts executed in the original first-to-last order, and the browser reported zero errors. This
  is a controlled loader comparison, not a claim that every production device will improve by the
  same percentage.
- The executable JavaScript release guard now requires exactly 18 loaded styles, 29 script
  preloads, 29 ordered script executions, complete preload coverage, idempotent loading, and one
  final runtime-ready event.
- The complete 491-test regression suite passed across 71 test files.
- All 45 browser JavaScript files, production preflight, generated-native web bundling, and
  canonical store-metadata verification passed.
- The canonical production host returns HTTP 200 for the versioned
  `runtime-body-v1.js?v=5.9.76-parallel-fetch-1` asset and service-worker cache revision `r137`.
- A signed-in, read-only production load reached the runtime `ready` state with 29 preload nodes and
  rendered the five-destination navigation, synchronized conversation library, launchpad, and
  composer. No user data was changed.
- The exact commit reached `READY` on all six production aliases with no alias error. Vercel reported
  no runtime-error cluster in the inspected hour and no error/fatal log for the deployment.

## Product decision

This release addresses the only route with a measured real-user performance gap while leaving the
100-score public routes and mature product behavior intact. Re-evaluate `/app` after at least seven
full post-release days or 300 post-release desktop performance events, whichever comes later. Do not
claim a production Real Experience Score improvement from the controlled fixture alone.
