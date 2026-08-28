# Registration verification handoff release evidence

Date: 2026-08-27 ET  
Release: 5.9.37 / native build 50937  
Application commit: `ebd14542256f0455fc3ea2d53a13e0701638df20`  
Production deployment: `dpl_EVrjwoQRXALKP1UvqvSnpZYsFsnj`

## Evidence and intervention boundary

The protected growth snapshot still contained zero comparable external accounts across all 18
metrics, and the protected artifact-journey snapshot returned no rows. The production Web
Analytics trailing-24-hour view showed 16 anonymous visitors, 72 page views, 50% bounce, two
visitors reaching signup intent, and two visitors starting signup. It showed no
`SignupCredentialsReady`, `SignupSubmitted`, or `AccountCreated` event. These anonymous counts are
context, not an account conversion rate or evidence of lift.

The registration source contained a separate reproducible defect: after a successful response it
showed “check your email” for only 1.8 seconds, then moved the person to a generic sign-in form. The
normal success branch did not prefill the sign-in email or leave persistent verification guidance.
The account-created/email-delivery-failure branch also moved to that generic form after a short
delay.

This release corrects only that handoff:

- successful registration opens a durable, keyboard-focused “Check your inbox” state;
- the exact destination email remains visible and is prefilled for later sign-in;
- “I’ve verified — sign in” and “Resend verification email” are explicit actions;
- initial delivery failure, resend failure, network failure, and resend success remain visible;
- the same recovery state is used when the account exists but the first email cannot be delivered;
- the content-free `AccountCreated` event is emitted on both account-created branches with only a
  `sent` or `failed` verification-delivery value.

Password policy, registration API behavior, verification mechanics, authentication, pricing,
entitlements, and backend data were not changed. No production signup request, account, email,
analytics event, payment, provider call, or customer record was created for verification.

## Automated and source verification

- 315 application tests passed.
- Backend Ruff checks passed.
- All 42 JavaScript files passed syntax and integration validation.
- Production build preflight and native web-bundle generation passed.
- Local Android source checks passed as 5.9.37/build 50937 with API 36.
- Store metadata and tracked-signing-secret controls passed.
- Missing RevenueCat public keys, Firebase configuration, owner signing credentials, signed-device
  tests, and final console submission remain unchanged native gates.

The local in-app browser security policy rejected a `file:` preview. That restriction was not
circumvented. The release instead used structural/accessibility contracts, the complete automated
suite, hosted compiles, live static-asset checks, and non-executing production HTTP inspection. A
real registration was intentionally not created to manufacture a screenshot or funnel event.

## Hosted verification

- CI run [`33136496183`](https://github.com/CRUMP-AI/AskCrump/actions/runs/33136496183)
  completed successfully.
- Android Store Bundle Verification run
  [`33136496185`](https://github.com/CRUMP-AI/AskCrump/actions/runs/33136496185) generated the
  5.9.37/build 50937 source, passed signing controls, compiled the unsigned release bundle, and
  verified the candidate without uploading it.
- iOS Store Source Verification run
  [`33136496204`](https://github.com/CRUMP-AI/AskCrump/actions/runs/33136496204) generated the
  5.9.37/build 50937 project, passed signing controls, and compiled the unsigned Release candidate
  without upload.

## Production verification

- Vercel marked deployment `dpl_EVrjwoQRXALKP1UvqvSnpZYsFsnj` `READY` with no alias error on
  `askcrump.com`, `www.askcrump.com`, `clevercrump.com`, and `www.clevercrump.com`.
- `https://askcrump.com/api/health` returned HTTP 200, `no-store`, and version 5.9.37.
- The application shell, 5.9.37 authentication controller, 5.9.37 body stylesheet, and service
  worker returned HTTP 200. The live shell contains the durable confirmation state, and the
  service worker contains cache revision `r71`.
- The release-scoped scan reported no runtime error cluster, warning/error/fatal log, or 5xx
  response. Three observed function responses were successful; request paths were only health and
  the existing manuscript cron. No `/api/auth/register` request was made during verification.

## Outcome status

Delivery is verified. Signup completion, email verification, activation, retention, and revenue
impact remain unproven until legitimate post-release behavior crosses the protected measurement
boundary. The owner’s manual sign-out and credential-entry recheck remains separate evidence for
the earlier web-session repair.
