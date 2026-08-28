# Ask Crump continuing-work sync readiness release

Date: 2026-08-27  
Production version: 5.9.42  
Code commit: `76455e5329110cd374a03592a8f82f5c6dcf33c4`  
Production deployment: `dpl_G77wN9y7d7T1ftgWch1kw8AU63zQ`

## Outcome

A stalled cross-device sync can no longer leave message delivery or the latest-result
`Keep in a Project` action waiting forever. Sync requests are bounded through response-body
parsing. If a push times out or the network fails, the account-scoped payload remains in the local
pending queue, the caller receives a retryable failure, and a later automatic or user-initiated
sync can replay the work.

This is verified delivery of a reliability boundary. It is not evidence that retention or Project
conversion improved; that requires legitimate external use and a later return.

## Reproduced failure

A credential-free local browser fixture loaded the real result action and Project continuity code
with a successful signed-in fixture identity and a `/api/sync/push` request that never settled.
Before the correction:

- `Keep in a Project` became disabled;
- the button was still disabled after repeated inspection;
- no Project request occurred; and
- the user received no recovery path.

The fixture used only `fixture-user`, a synthetic conversation, loopback HTTP, and local storage. It
contained no real credentials and made no production request or write.

## Correction

- Added a 12-second request boundary to sync pull and push, including JSON body parsing.
- Converted push timeout/network exceptions into `{success: false, queued: true, retryable: true}`.
- Kept the pending queue intact unless the server returns a successful sync response.
- Release-versioned `sync-manager.js`, added it to the release cache, and made it network-first so
  an installed web/PWA client receives the corrected boundary.

Project ownership checks, chat merge and revision rules, authentication, sessions, pricing,
entitlements, product-event semantics, Supabase schema/RLS, and payment behavior did not change.

## Verification

- Browser fixture after correction: the stalled request was aborted at the bounded test interval,
  the action was enabled again, and exactly one pending save remained queued.
- 336 Python tests passed.
- Ruff passed for `backend` and `tests`.
- All 42 JavaScript files passed syntax and integration validation.
- Production preflight and the native web bundle passed.
- Android source verification passed for version 5.9.42/build 50942/API 36.
- Store metadata and tracked-signing-secret controls passed.
- Hosted CI run `33140100110` passed.
- Hosted unsigned Android App Bundle run `33140100029` passed.
- Hosted unsigned iOS Release compile run `33140100058` passed.

The local all-platform verifier correctly reported that iOS is absent on Windows. The hosted macOS
compile provides the unsigned iOS source/build evidence. RevenueCat public keys, Android Firebase,
signing credentials, physical-device results, and store submission remain separate open gates.

## Production evidence

- Vercel deployment `dpl_G77wN9y7d7T1ftgWch1kw8AU63zQ` reached `READY` from the exact code commit,
  with all production aliases and no alias error.
- `https://askcrump.com/api/health` returned HTTP 200, `Cache-Control: no-store`, and version 5.9.42.
- The live app returned HTTP 200 and referenced `/sync-manager.js?v=5.9.42`.
- The live sync manager returned HTTP 200 and contained the bounded/queued recovery contract.
- The live service worker returned HTTP 200, cache revision 76, and the network-first sync-manager
  route.
- The deployment-scoped runtime log breakdown contained one 200 response, no warning/error/fatal
  level, and the one-hour project error scan contained no runtime error cluster.
- No production login, chat, Project, account, payment, or synthetic product event was created by
  release verification.

## Rollback

The prior production deployment `dpl_CRS1B7u5WNsWTHRuRvQWM9mGXFRA` remains an available rollback
candidate. No database, environment, authentication, payment, or infrastructure migration is
required to roll back this client boundary.

## Remaining evidence

The owner-run fresh credential-entry check remains the human authentication proof. The retention
gate remains at least one legitimate external conversation-to-Project transition and later return;
no rate or lift should be inferred before that observation exists.
