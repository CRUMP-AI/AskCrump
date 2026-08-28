# Ask Crump first-reply recovery release

Date: 2026-08-28
Production version: 5.9.44
Code commit: `4804fc4676742c86f9df4f35577a4e7e4be6d2b7`
Production deployment: `dpl_HgAo8qwFh1gzroqUE47SrDFqxTnf`

## Outcome

A stalled message acknowledgement or AI reply connection can no longer leave the steady-state
workspace silently ignoring Send. Both stages are bounded. If the reply connection is lost after
the server accepted the message, the client checks the existing owner-scoped job and reuses its
persisted answer instead of blindly starting another generation. The composer becomes usable again,
and an incomplete or stale job exposes a visible retry path.

This is verified delivery of an activation-readiness boundary. It is not evidence that first-message
completion or activation improved; that requires legitimate external behavior after release.

## Reproduced failures

A credential-free loopback fixture loaded the real fallback and post-load primary workspace
runtimes with the synthetic prompt `Draft a launch plan for a neighborhood bakery.`

Before the correction, a never-settling `/api/chat` request produced this primary-runtime state:

- the composer draft cleared;
- the user message remained visible;
- one reply request stayed open indefinitely;
- a deliberate second Send was ignored; and
- no recovery message or status reconciliation occurred.

The primary runtime was confirmed by its replaced `Send message` control. The fixture used only
loopback HTTP, synthetic messages, and browser-local state. It contained no credential, account,
payment, production request, or production write.

## Correction

- Added a shared chat transport with a ten-second usage check, 12-second acknowledgement boundary,
  and 105-second reply boundary, each covering response-body parsing.
- Added `GET /api/chat/status/{message_id}`. It authenticates first, filters by both authenticated
  user ID and message ID, returns `Cache-Control: no-store`, and never lists jobs.
- Reconciles active jobs for up to ten bounded polls; completed jobs return their already persisted
  response, while failed, missing, or server-defined stale jobs become safely retryable.
- Preserves the server-created assistant-message identity, file/artifact metadata, manuscript and
  creation handoffs, and conversation revision during recovery.
- Checks an existing job before retry usage preflight so a completed answer can be recovered even
  when the original request already consumed the user's final included message.
- Applied the same transport to the early fallback runtime and the real post-load primary runtime.
- Release-versioned the primary runtime and made both changed client assets network-first for
  installed web/PWA clients.

The existing `claim_chat_job` server contract remains the authority for idempotency, two-minute stale
takeover, usage charging, and cached completion. Usage limits, credit pricing, provider routing,
authentication, Supabase schema/RLS, pricing, entitlements, analytics semantics, and payment behavior
did not change.

## Browser verification

- Reply-stall scenario: the compressed 105-second boundary aborted the only open reply request;
  owner-job reconciliation observed one processing response and then the completed persisted answer.
- The real primary UI rendered `Here is a focused launch plan for the neighborhood bakery.` with its
  server assistant-message ID and restored an active composer.
- A second deliberate message was accepted and rendered, proving Send was reusable after recovery.
- Acknowledgement-stall scenario: the compressed 12-second boundary displayed `Seen · Reply failed —
  Tap to retry` plus specific timeout feedback. The real retry control then completed acknowledgement,
  reconciled the reply, and rendered the answer.

## Automated and platform verification

- 347 Python tests passed.
- Ruff passed for `backend` and `tests`.
- All 43 JavaScript files passed syntax and integration validation.
- Production preflight and the native web bundle passed.
- Android source verification passed for version 5.9.44/build 50944/API 36.
- Store metadata and tracked-signing-secret controls passed.
- Hosted CI run `33141840340` passed.
- Hosted unsigned Android App Bundle run `33141840370` passed.
- Hosted unsigned iOS Release compile run `33141840430` passed.

The local all-platform verifier correctly reports that iOS is absent on Windows. The hosted macOS
compile supplies unsigned iOS source/build evidence. RevenueCat public keys, Android Firebase,
signing credentials, physical-device results, and store submission remain separate open gates.

## Data and security verification

A read-only, content-free production query confirmed that `chat_jobs` has RLS enabled, the backend
service role can perform the required owner-filtered lookup, and the stale-processing condition
already exists in real state. No response body, message, user identifier, job identifier, or secret
was read or recorded. No table, policy, function, row, or migration changed.

## Production evidence

- Vercel deployment `dpl_HgAo8qwFh1gzroqUE47SrDFqxTnf` reached `READY` from the exact code commit,
  with all production aliases and no alias error.
- `https://askcrump.com/api/health` returned HTTP 200, `Cache-Control: no-store`, and version 5.9.44.
- The live app referenced `/chat-resilience.js?v=5.9.44`.
- The live transport, primary runtime, runtime loader, and service worker returned HTTP 200 and
  contained the bounded recovery, versioned primary-runtime, network-first, and cache-revision-78
  contracts.
- An unauthenticated reply-status probe returned the expected 401 and created no job.
- The one-hour production scan contained no warning/error/fatal runtime log or error cluster; the
  exact deployment completed its build successfully.
- No production login, message, usage check, chat generation, Project, account, payment, or synthetic
  product event was created by release verification.

## Rollback

The prior production deployment `dpl_2QnPWDSBZf6qTtvYWs5gG2ULAoEe` remains the rollback candidate.
No database, environment, authentication, payment, or infrastructure migration is required to roll
back this server/client boundary.

## Remaining evidence

The owner-run fresh credential-entry check after explicit sign-out remains the human authentication
proof. The activation gate remains legitimate users completing a first useful message and later
keeping or returning to the work; no rate or lift should be inferred before that observation exists.
