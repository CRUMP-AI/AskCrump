# Ask Crump authentication request recovery release

**Date:** 2026-08-28  
**Release:** 5.9.45 / native build 50945  
**Code commit:** `0012a307884b888ab9c33e15b42e53d7c7ff2b0d`  
**Production deployment:** `dpl_3QsniFHTrMSACqNWPf7DzNqMckJ2`

## Outcome

Authentication entry and recovery actions can no longer remain silently busy forever when a request
or its response body stalls. Registration now restores its button with truthful uncertain-outcome
guidance, and web login can safely recognize a session that the server issued before the login
response connection stalled.

This is verified activation-readiness delivery, not evidence of improved signup conversion. Fresh
manual credential entry after an explicit owner sign-out remains the final human proof.

## Decision evidence

- The protected, content-free production growth report still returned zero comparable external
  accounts across all 18 metrics, and the aggregate artifact-journey report returned no rows.
- In the trailing 24-hour Vercel Web Analytics view, production showed 15 visitors, 73 page views,
  and 53% bounce. Two visitors reached `SignupStarted`; the visible event set contained no
  `SignupCredentialsReady`, `SignupSubmitted`, or `AccountCreated` event.
- These anonymous aggregates can include internal or automated traffic and are not a conversion rate.
  They justified checking the signup boundary, not rewriting it from inferred behavior.

## Reproduced failure and audit

A credential-free loopback registration fixture submitted valid synthetic form values to a stalled
`/api/auth/register` response. Before the correction, the button remained disabled at
`Creating account…` indefinitely and offered no recovery.

The same audit found registration, verification-email resend, forgot-password, reset-password,
terms acceptance, profile save, session check, login, logout, and native push-registration cleanup
using request paths that did not consistently bound both network delivery and response parsing.

## Correction

- `public/auth-resilience.js` now provides one bounded authentication transport. It aborts stalled
  fetches and stalled JSON parsing with the stable `AUTH_REQUEST_TIMEOUT` outcome.
- Registration, resend, password recovery/reset, terms acceptance, and profile save use the shared
  transport. Registration timeout guidance tells the user to check their inbox before retrying
  because the account may already exist.
- Session checks, login, login confirmation, logout, and native push-registration cleanup also use
  the shared transport.
- If a web login response stalls after the server has issued its HttpOnly session, the client performs
  bounded session confirmation and accepts the valid session. Native login still requires its returned
  session token and reports the timeout when it cannot be recovered.
- Logout navigation runs even when remote confirmation is unavailable.
- The release updates public asset versioning to 5.9.45, native build 50945, and service-worker cache
  revision r79. The new auth asset is versioned and network-first.

Password rules, verification rules, session and cookie policy, ownership, pricing, entitlements,
analytics semantics, database schema, RLS, and payment behavior are unchanged.

## Browser verification

- The registration-stall fixture now restores an enabled button and displays the exact
  uncertain-outcome recovery guidance.
- A separate login-response-stall fixture marks the session as issued before stalling the response.
  The released client reconciles that session and opens the workspace with `Workspace ready.`
- Both fixtures run only on loopback with synthetic values. They created no production account,
  login, event, message, Project, payment, or other production write.

## Automated and hosted verification

- 352 backend tests passed.
- Backend/test lint and Python compilation passed.
- 44 JavaScript validations passed, including five authentication-request resilience tests.
- Production preflight, native web-bundle, store-metadata, and signing-secret-control checks passed.
- Hosted CI run `33142697258` passed.
- Hosted Android run `33142697156` generated 5.9.45/build 50945, verified API 36/Java 21 controls,
  and compiled a non-empty unsigned release bundle.
- Hosted iOS run `33142697157` generated 5.9.45 and compiled the unsigned Release configuration on
  macOS.

The existing external gates remain: RevenueCat public configuration, Firebase
`google-services.json`, production signing credentials, and the local-machine absence of iOS tooling.

## Production verification

- Deployment `dpl_3QsniFHTrMSACqNWPf7DzNqMckJ2` reached `READY` on all production aliases.
- `/api/health` returned HTTP 200, `Cache-Control: no-store`, and version 5.9.45.
- `/app`, the versioned auth-resilience, device-auth, and auth-controller assets, and the service worker
  returned HTTP 200 with the released transport/cache references.
- An unauthenticated session check returned the expected content-free `authenticated: false` result
  with no-store caching.
- The one-hour production scan found no runtime error cluster and no warning/error/fatal application
  logs.

## Data and privacy

Only protected aggregate, content-free growth reports and anonymous aggregate web analytics were
read. No identifiers, credentials, message content, files, or private artifacts were retained in this
evidence. No Supabase schema, policy, row, account, or event was created or changed.

## Rollback

The immediately preceding known-good production deployment is the 5.9.44 documentation release,
`dpl_3KwsSruexuaMVejscEsXuQfbB3sE`. A rollback should also restore the matching service-worker and
native version metadata.

## Remaining evidence

1. Complete one owner-run explicit sign-out followed by fresh manual credential entry on production
   5.9.45. Do not capture or share the password or verification code.
2. Observe and diagnose the first legitimate post-boundary signup and artifact journey before
   claiming activation lift or scaling acquisition spend.
