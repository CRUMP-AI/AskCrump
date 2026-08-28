# Ask Crump 5.9.55 authentication-entry handoff release

Date: 2026-08-28

Production version: 5.9.55

Code commit: `ed88c445160ddcb5c1dd6a6f4f2433afc9977634`

Production deployment: `dpl_B1jKEcq7mgoU2gacvvUicBBuUXfQ`

## Outcome

Every signed-out authentication view now moves focus to its first actionable field. Sign in,
registration, password recovery, and password reset no longer leave keyboard focus on a link that
was just hidden or on the page body. Browser validation that stops a login before any network
request now leaves a persistent, announced field-specific message.

The correction does not change passwords, verification, session rotation, cookies, database rows,
RLS, pricing, entitlements, payments, or provider configuration. New authentication funnel events
contain only the transition and a bounded categorical reason; they contain no email, password,
account ID, token, or other credential.

## Production incident triage

A user-reported PWA sign-in concern produced two distinct pieces of evidence:

- One `POST /api/auth/login` request on an older deployment returned 503 at 05:53 UTC with the
  categorical error `Database connection failed`. Ten nearby background-job requests showed the
  same transient upstream failure. Supabase Auth had no corresponding auth event because Ask
  Crump's own database boundary failed first.
- The current deployment later returned only successful session responses. Ten credential-free
  database-backed session probes returned HTTP 200 with `authenticated:false`, and the owner then
  completed a real phone/PWA sign-out and sign-in. The owner also confirmed the PWA update prompt
  worked as intended.

The transient upstream 503 is retained as an operating signal. No password or session-policy change
was justified by the evidence.

## Correction

- Added one explicit mapping from each auth view to its container and first field.
- Centralized view transitions through `showAuth`, which hides every inactive view, exposes exactly
  one destination, and moves focus on the next animation frame without scrolling the page.
- Applied the same path to startup, deep-linked signup, deep-linked reset, registration return,
  recovery return, and completed password-reset handoff.
- Added a persistent `role=alert` message when native browser validation blocks login before submit.
- Added content-free `LoginValidationFailed`, `LoginSubmitted`, `LoginCompleted`, and `LoginFailed`
  funnel events so future client-versus-server failures can be distinguished without credentials.
- Advanced the application to 5.9.55, native build 50955, and PWA cache revision 89.

## Real-controller browser proof

The credential-free loopback fixture loads the actual Ask Crump auth transport and controller. It
contains no production hostname, account, token, or write-capable endpoint.

| Path | Before | After |
| --- | --- | --- |
| Initial signed-out entry | Page body retained focus | `loginEmail` focused |
| Create account | Hidden `showRegisterLink` retained focus | `registerEmail` focused |
| Return to sign in | Hidden `showLoginLink` retained focus | `loginEmail` focused |
| Forgot password | Hidden recovery link retained focus | `forgotPasswordEmail` focused |
| Deep-linked signup | Page body retained focus | `registerEmail` focused |
| Deep-linked reset | Page body retained focus | `newPassword` focused |
| Empty sign-in action | Relied on transient native validation | Persistent `Enter your email.` alert and email focus |

Every corrected browser path completed with zero script errors.

## Automated and native verification

- 373 Python tests passed.
- Ruff passed for `backend` and `tests`; Python compilation passed for `backend`.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight and native web-bundle generation passed.
- Android source verification passed for Ask Crump 5.9.55, build 50955, and API 36.
- Store metadata source checks passed.
- GitHub CI run `33179824223` passed.
- Hosted unsigned Android App Bundle run `33179824154` passed.
- Hosted unsigned iOS Release compile run `33179824243` passed.

The local verifier correctly reports that the iOS project is absent on Windows. RevenueCat public
keys, Android Firebase, signing credentials, physical-device results, and store submission remain
separate open gates.

## Production evidence

- Deployment `dpl_B1jKEcq7mgoU2gacvvUicBBuUXfQ` reached `READY` from the exact code commit.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.55.
- The live app referenced `auth-controller.js?v=5.9.55` and exposed the field-specific login alert.
- The live service worker returned HTTP 200 with `ask-crump-new-body-v1-r89`.
- Five post-release credential-free session/database probes returned HTTP 200 and
  `authenticated:false`.
- The exact deployment contained no warning, error, or fatal log in its release window.

## Rollback

The prior production deployment `dpl_BjiKpBqFgL9TsW9NC4Gs8233Le1k` remains available. This release
requires no schema, RLS, environment, authentication-policy, payment, pricing, or infrastructure
migration.

## Remaining evidence

Observe legitimate `LoginSubmitted` to `LoginCompleted` outcomes and retain the transient database
503 in reliability monitoring. Do not infer conversion lift until enough real post-release traffic
exists. Native signed-build, purchase, push, screenshot, privacy-form, and store-console gates remain
open.
