# Verified workspace handoff release — 2026-08-29

## Outcome

An account holder who follows a valid Ask Crump verification email now enters an
authenticated workspace directly. The email-confirmation step no longer succeeds and
then requires the same person to type the password again on that device.

Production release:

- behavior commit: `165f37bc7170116fb5f4f42afa6df98b8b555acc`
- product-name hardening commit: `17a9700ac20bfdaf7f58eedd40cf3b453a78d42f`
- behavior deployment: `dpl_6GWtm1E82DDDYzqZCRdAYMMk3txt`
- final deployment: `dpl_H6EgjJW1KkUrq8ZLhrg52G4TN19v`
- final deployment state: `READY`
- production version: `5.9.76`

## Evidence before the correction

The trailing seven-day Vercel Web Analytics view contained 122 visitors, 500
pageviews, and a 55% bounce rate. Content-free funnel events showed 32 visitors
producing 53 `SignupIntent` events but only two visitors producing two
`SignupStarted` events. Both starts were direct desktop Mac visits, while 22
signup-intent visitors arrived from Facebook or mobile Facebook. There were no
`SignupValidationFailed` events.

The independent protected Supabase reports contained zero comparable external new
accounts, zero external artifact-journey rows, and zero external plan-center or
checkout accounts. The all-traffic plan report contained one internal plan-center
view and no checkout.

Those anonymous totals remain below the precommitted 14-day or 50-social-visitor
decision boundary. They do not support attributing the gap to a specific campaign
or rewriting registration. The deterministic post-registration seam was narrower:
a valid verification link marked the account verified and redirected to login,
requiring redundant password entry before the first workspace visit.

## Correction

- A valid verification link verifies the account, creates the normal web session,
  sets the existing hardened session cookie, and redirects with HTTP 303 to
  `/app?verification=success`.
- The pending-account screen and verification email explicitly say the link opens
  the workspace. Password sign-in remains available for another device.
- On first use, the original 24-hour verification token is retained only for a
  15-minute replay window. A mail security scanner or accidental first opening
  therefore cannot silently consume the only usable GET link.
- A repeated valid click during that short window can create a fresh session but
  cannot repeat the verification database update.
- Expired, malformed, or unknown tokens still redirect to
  `/app?verification=failed` and never create a session.
- The retired production `AI Virtual Assistant` environment label is normalized
  to the canonical `Ask Crump` name in transactional email and operational
  metadata. Deliberate non-legacy environment names remain unchanged.

No password, verification token, email address, account identifier, conversation,
Project, file, prompt, response, artifact, entitlement, credit, checkout, or payment
data is added to logs or analytics.

## Verification

- 476 Python regression tests passed. The focused verification and release-hardening
  group passed 13 tests, including first-click session creation, replay behavior,
  single verification update, invalid-link rejection, cookie handoff, email copy,
  and legacy-name normalization.
- The live application paths passed Ruff, and the backend compiled successfully.
- All 45 JavaScript files passed syntax and integration validation.
- Production preflight, native web-bundle creation, and Apple/Google store-metadata
  source checks passed.
- The final Vercel deployment is `READY` on all six production aliases with no
  alias error.
- Canonical production health returned HTTP 200 with service `Ask Crump` and
  version `5.9.76`.
- The canonical app served
  `/auth-controller.js?v=5.9.76-verification-session-1`; that controller contained
  the verified-workspace completion state.
- A fabricated invalid token against the behavior deployment returned HTTP 303 to
  the failed-verification state and created no account, session, event, or other
  product record.
- The final deployment's first inspected window contained 22 HTTP 200 responses,
  no 4xx or 5xx response, no runtime error cluster, and no warning, error, or fatal
  log.
- Verification created no account, conversation, message, Project, file, artifact,
  checkout, payment, or synthetic product event.

## Outcome boundary

Delivery is verified; activation lift is not yet claimed. The next legitimate
registration should produce a real account verification followed by workspace
entry without a second password step. Compare that sequence at the existing
14-day or 50-social-visitor boundary before changing campaign targeting or the
registration form.
