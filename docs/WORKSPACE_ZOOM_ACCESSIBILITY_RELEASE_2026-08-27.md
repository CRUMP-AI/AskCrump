# Workspace zoom accessibility release evidence

Date: 2026-08-27
Release: 5.9.34 / native build 50934
Code commit: `7f6013bc3a33325599b2bd484ab9dc2a76d3ab6f`
Production deployment: `dpl_4SgvrggyDSKbr5jJuEzipjhdo4yF`

## Decision

A local mobile Lighthouse audit of the public registration state found one objective accessibility
failure: the app viewport fixed maximum scale at 1 and disabled user scaling. The stability layer
also intercepted Safari gesture events and every two-finger touch move. Those controls prevented
people from using browser or installed-PWA pinch zoom anywhere in the workspace.

This release removes the global zoom lock. It does not redesign registration from a tiny anonymous
sample and does not change authentication, password rules, sessions, billing, private data, or
analytics semantics.

## Delivered

- The application viewport retains device width, initial scale, and safe-area coverage without a
  maximum scale or `user-scalable=no` restriction.
- The stability layer no longer registers `gesturestart`, `gesturechange`, or two-finger
  `touchmove` blockers.
- The shell now uses `touch-action: pan-y pinch-zoom`, preserving native vertical scrolling and
  pinch zoom while the existing width and overscroll constraints continue to prevent horizontal
  page drift.
- Existing 16-pixel mobile editor rules remain in place, preventing unwanted iOS focus zoom at the
  source without removing user-controlled accessibility zoom.
- Contract tests now fail if the viewport lock, gesture blockers, or old touch-action policy return.
- Release 5.9.34 advances the app/runtime asset version and service-worker cache to `r68` so
  returning browsers and installed PWAs receive the corrected shell.

## Baseline and result

The local registration-state mobile baseline scored 93 for accessibility and failed Lighthouse's
meta-viewport audit. After the correction, the same registration state scored 100, passed the
meta-viewport audit, reported zero contrast failures, and had no failed accessibility audit. The
local signed-out state also scored 100 with zero contrast failures.

The production registration state then scored 100 for accessibility, passed the meta-viewport
audit, and reported zero contrast failures. Delivery of the Vercel analytics script was blocked for
that audit, so the verification did not transmit a synthetic signup event.

At a 390-by-667 short-phone viewport, the registration card stayed within the viewport, its primary
action remained fully visible from y=412 through y=467, document width remained 390 pixels with no
horizontal overflow, computed touch action was `pan-y pinch-zoom`, and no console warning or error
was reported.

## Verification

- All 307 backend and contract tests passed.
- Ruff checks passed and all 41 JavaScript files passed the integration validator.
- Production preflight and the native web-bundle build passed.
- Android source configured and passed the 5.9.34/build 50934/API 36 release verifier. The local
  checkout still lacks the RevenueCat Android public key and `google-services.json`.
- Store metadata limits and mobile signing source controls passed. No signing secret is tracked.
- Hosted CI run `33133179838`, Android run `33133179924`, and iOS run `33133179768` completed
  successfully. The mobile workflows generated and compiled unsigned candidates without upload.
- Production health returned 5.9.34. The live app shell returned HTTP 200, exposed the accessible
  viewport, referenced 5.9.34 assets, served `pan-y pinch-zoom`, omitted the gesture-blocking code,
  and served service-worker cache `r68`.
- The deployment is `READY` on every Ask Crump and Clever Crump production alias. The inspected
  release window contained no runtime error cluster, warning/error/fatal log, or 5xx response.

## Outcome boundary

This is verified web/PWA accessibility and source delivery, not a claim of improved signup,
activation, retention, or revenue. Actual pinch behavior, zoomed-layout usability, screen-reader
flow, and billing must still be checked on the exact signed iOS and Android candidates before store
submission.

No production account, credential, payment setting, private record, external post, sitemap,
indexing request, or advertising spend changed. The owner's manual sign-out and credential-entry
test remains the final human proof for the earlier session-handoff repair.
