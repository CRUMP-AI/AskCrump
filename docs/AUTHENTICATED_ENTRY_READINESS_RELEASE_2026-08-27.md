# Authenticated-entry readiness release — 2026-08-27

## Decision

Ship Ask Crump 5.9.41 so a completed login or restored session opens the account-scoped workspace
without waiting for the secondary cross-device sync. Server-authoritative synchronization remains
in the existing authenticated background lifecycle after the shell opens.

This is a verified availability correction. It is not evidence of improved external signup,
activation, or retention.

## Reproducible defect

A credential-free local browser fixture loaded the real `auth-controller.js`, returned a successful
fixture login or authenticated fixture session, and made `SyncManager.pull()` never settle.

Before the correction:

- A completed login still showed the authentication screen after 500 milliseconds. The primary
  button remained disabled with `Signing in…`, the app remained hidden, and no error explained the
  stall.
- A restored authenticated session hid the authentication screen but never showed the app,
  producing a blank entry state.

The credential/session response had already succeeded in both cases. Only the optional full-state
prefetch was stalled.

## Bounded correction

- Removed the full-state prefetch from the login and restored-session critical paths.
- Applied the user and server-returned settings before routing, exactly as before.
- Opened the account-scoped shell immediately after the authenticated response.
- Kept the existing non-blocking `initializeAuthenticatedApp` synchronization, which renders the
  account cache first and then performs the server-authoritative pull/merge/push lifecycle.
- Left credentials, password verification, email verification, opaque session rotation, cookie
  handling, session persistence, account ownership, pricing, entitlement, and analytics semantics
  unchanged.
- Made no Supabase schema, RLS, Auth configuration, storage, or environment change.

## Corrected browser evidence

With the same never-settling sync fixture:

- completed login: app visible, authentication hidden, primary button restored;
- restored session: app visible, authentication hidden;
- neither path waited for the stalled secondary sync;
- the fixture used only `fixture@example.test` and a synthetic local password and made no network
  write.

## Source and release identity

- Application commit: `ee3862dc86dacfebb62b3846cf9b172b3d8764d3`
- Production deployment: `dpl_7sBD8Y3e8oyW696ec7HpHBLNLMVU`
- Production version: 5.9.41
- Native build: 50941
- Service-worker cache: `ask-crump-new-body-v1-r75`
- Production aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the Vercel production aliases

## Release verification

The full local gate passed:

- 332 backend and contract tests;
- backend/test lint;
- all 42 JavaScript source validations and edited-source syntax checks;
- production build preflight and native web-bundle generation;
- Android 5.9.41/build 50941/API 36 source verification;
- store metadata and mobile signing-source controls;
- clean patch plus release-version/cache consistency checks.

Hosted verification passed on the exact application commit:

- CI: [run 33139229180](https://github.com/CRUMP-AI/AskCrump/actions/runs/33139229180)
- Android unsigned App Bundle: [run 33139229175](https://github.com/CRUMP-AI/AskCrump/actions/runs/33139229175)
- iOS unsigned Release compile: [run 33139229205](https://github.com/CRUMP-AI/AskCrump/actions/runs/33139229205)

The native workflows generated and verified 5.9.41 release source and compiled unsigned candidates.
They did not sign, upload, submit, or use store credentials. RevenueCat, Firebase/push, signing,
physical-device, billing, screenshot, declaration, and console gates remain open.

## Production verification

- The exact Git commit produced a `READY` production deployment with no alias error.
- `https://askcrump.com/api/health` returned HTTP 200, `Cache-Control: no-store`, and version
  5.9.41.
- The live app shell, 5.9.41 authentication controller, and service worker returned HTTP 200.
- The live authentication controller no longer contains the blocking prefetch, and the service
  worker contains cache revision 75.
- The release-scoped scan found no runtime error cluster, warning/error/fatal log, or 5xx response.

No production login, logout, account creation, credential transmission, or session mutation was
performed by the operator. An existing owner session was opened once before the isolated fixture
was selected, so this release makes no claim that the observation window was product-event free.

## Remaining human proof and rollback

The owner's remembered-device path already worked. A fresh credential-entry attempt after explicit
sign-out remains the final human proof; the result should be recorded only as `worked` or the exact
visible error/screenshot, never as a shared password.

Rollback is application commit `a2fb681edb65fcc154275d9488b566527b892830` and service-worker
cache revision 74. The correction requires no data migration or cleanup.
