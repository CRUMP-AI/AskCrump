# Ask Crump first-message readiness release

Date: 2026-08-28  
Production version: 5.9.43  
Code commit: `61115407f56fdf0f065384f1219ed61bd1e88dd7`  
Production deployment: `dpl_52eNo3CQUC3JFcooDeBsbpgx7Z4q`

## Outcome

A first message can no longer leave the composer silently locked if the usage-availability check
stalls. The preflight is bounded through response-body parsing. A timeout or network failure now
returns visible, specific recovery feedback, preserves the user's draft, restores focus, and makes
Send immediately retryable.

This is verified delivery of an activation-readiness boundary. It is not evidence that activation
or message completion improved; that requires legitimate external behavior after release.

## Reproduced failure

A credential-free local browser fixture loaded the real `ui-functions.js` and `app.js` with the
draft `Draft a launch plan for a neighborhood bakery.` and a loopback `/api/usage/check` request
that never settled. Before the correction:

- the first Send entered usage preflight;
- the request remained open;
- a second Send was silently ignored because processing never cleared;
- the draft stayed visible, but no recovery message appeared; and
- no chat request or production request occurred.

The fixture used only loopback HTTP, browser-local state, and synthetic text. It contained no real
credentials, account, payment, user data, or production write.

## Correction

- Added a ten-second usage-preflight boundary covering both the request and response JSON parsing.
- Abort the availability request when the boundary expires.
- Report `Message check took too long. Your draft is still here — try again.` for a timeout.
- Report a connection-specific retry message for other pre-message network failures.
- Preserve the existing session-expired and daily-limit messages exactly.
- On every pre-message failure, keep the draft, restore composer focus, provide error haptics when
  enabled, and clear the processing state so Send can be tried again.

Usage limits, credit accounting, authentication, chat delivery, provider routing, product-event
semantics, Supabase, pricing, entitlements, and payments did not change.

## Verification

- Corrected browser fixture: the compressed test boundary stopped the stalled request, displayed
  the timeout recovery, preserved and refocused the draft, and accepted a second deliberate Send,
  increasing the preflight request count from one to two.
- 340 Python tests passed.
- Ruff passed for `backend` and `tests`.
- All 42 JavaScript files passed syntax and integration validation.
- Production preflight and the native web bundle passed.
- Android source verification passed for version 5.9.43/build 50943/API 36.
- Store metadata and tracked-signing-secret controls passed.
- Hosted CI run `33140715343` passed.
- Hosted unsigned Android App Bundle run `33140715347` passed.
- Hosted unsigned iOS Release compile run `33140715370` passed.

The local all-platform verifier correctly reports that iOS is absent on Windows. The hosted macOS
compile supplies unsigned iOS source/build evidence. RevenueCat public keys, Android Firebase,
signing credentials, physical-device results, and store submission remain separate open gates.

## Production evidence

- Vercel deployment `dpl_52eNo3CQUC3JFcooDeBsbpgx7Z4q` reached `READY` from the exact code commit,
  with all production aliases and no alias error.
- `https://askcrump.com/api/health` returned HTTP 200, `Cache-Control: no-store`, and version 5.9.43.
- The live app returned HTTP 200 and referenced `/app.js?v=5.9.43`.
- The live app asset returned HTTP 200 and contained the bounded preflight plus draft-preserving
  recovery contract.
- The live service worker returned HTTP 200 and cache revision 77.
- The deployment-scoped log breakdown contained one informational 200 response, no
  warning/error/fatal level, and the one-hour production error scan returned no runtime errors.
- No production login, message, usage check, chat, Project, account, payment, or synthetic product
  event was created by release verification.

## Rollback

The prior production deployment `dpl_G77wN9y7d7T1ftgWch1kw8AU63zQ` remains the rollback candidate.
No database, environment, authentication, payment, or infrastructure migration is required to
roll back this client boundary.

## Remaining evidence

The owner-run fresh credential-entry check after explicit sign-out remains the human authentication
proof. The activation gate remains legitimate users completing their first useful message and later
keeping or returning to the work; no rate or lift should be inferred before that observation exists.
