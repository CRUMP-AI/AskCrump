# Contextual signup handoff release — 2026-08-29

Status: verified in production; legitimate visitor outcome pending

## Decision evidence

The trailing-seven-day Vercel Web Analytics view showed 121 visitors, 466 page
views, and a 55% bounce rate. Thirty visitors reached `SignupIntent`, but only
two reached `SignupStarted`; one `SignupSubmitted` and one `AccountCreated`
appeared in the directional dashboard. Facebook and mobile Facebook accounted
for 28 referred visitors.

The independent service-role Supabase growth snapshot reported zero comparable
external accounts over both seven and 30 days, zero artifact journeys, and zero
external plan-center views. The dashboard totals may include internal or
otherwise non-comparable activity, so no true signup rate or acquisition lift
is claimed. The evidence nevertheless places the largest observable drop
between a visitor choosing a signup CTA and beginning the two-field form.

## Product correction

The prior registration screen replaced every public promise with the generic
headline “Create your workspace.” Production cache revision `r122` now keeps
the exact allowlisted choice visible through registration:

- document explains the editable Word/PDF continuation;
- presentation explains the editable PowerPoint continuation;
- résumé explains the fact-grounded editable Word continuation;
- video explains Video Studio, visible credit cost, and private Library result;
- Professional states $20/month and requires checkout review/confirmation;
- Enterprise states $50/month and requires checkout review/confirmation.

The primary action changes to “Create account & continue” for a creation path,
or “Create account & review Professional/Enterprise” for a paid-plan path.
Account creation remains free and no payment begins on the registration screen.

An explicit generic Free signup now clears a stale paid-plan or creation intent
from a previous browsing path. Missing or arbitrary query values never become
rendered copy; all text comes from fixed allowlisted maps. Authentication,
verification, pricing, entitlements, checkout, account data, analytics events,
and provider behavior are unchanged.

## Verification

- Commit: `0e6ee53` (`Preserve signup intent through registration`).
- Production deployment: `dpl_E99hQJ1PzviET4XgLKCk7SicJnM1`.
- Deployment state: `READY`; six production aliases; no alias error; build
  duration approximately 34 seconds.
- All 457 Python regression tests passed.
- All 45 JavaScript files passed syntax and integration validation.
- Production preflight, native web build, store metadata, and mobile signing
  source-control checks passed.
- A credential-free local browser used the real controller to prove
  presentation, Video Studio + Professional, Enterprise, and stale-specific to
  generic-Free behavior.
- The exact deployed build repeated all four paths with the registration email
  focused and no submission state.
- Canonical production assets contained the new handoff logic, stale-intent
  cleanup, and service-worker cache `r122`.
- Canonical health returned HTTP 200 and version `5.9.76`.
- The inspected release window contained 11 HTTP 200 responses, no
  `/api/auth/register` request, no warning/error/fatal log, and no runtime error
  cluster. No credentials, account, event, or payment were manufactured.

## Outcome boundary

Re-evaluate after the earlier of 50 additional legitimate `SignupIntent`
visitors or 14 days. Compare `SignupStarted`, `SignupCredentialsReady`,
`SignupSubmitted`, and comparable external `AccountCreated` accounts by the
existing allowlisted source, plan, and intent categories. Do not scale paid
acquisition from impressions or directional dashboard events alone.

## Unchanged native-store gates

RevenueCat public SDK keys, Android Firebase configuration, and generating the
iOS project remain owner-controlled store submission gates. They do not block
the deployed web/PWA correction.
