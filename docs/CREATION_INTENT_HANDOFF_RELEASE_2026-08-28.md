# Ask Crump 5.9.56 creation-intent handoff release

Date: 2026-08-28

Production version: 5.9.56

Code commit: `5ceb57af838e4ae649acddbbf9278e0ecb135cca`

Production deployment: `dpl_ENikqcrY6BYhZHvzoDU5VGtgHnFc`

## Outcome

A visitor who chooses presentations, documents, résumés, or video on a public capability page now
reaches that exact non-generating workspace after sign-in, registration plus verification, or an
existing authenticated session. The high-intent action no longer collapses into the generic Ask
Crump launchpad at the authentication boundary.

The handoff stores only one allowlisted category, bounded acquisition/source labels, and a capture
time for at most 24 hours. It stores no prompt, résumé detail, filename, message, response, account
identifier, or token. Authentication, verification, sessions, pricing, entitlements, payments,
provider selection, and generation behavior remain unchanged.

## Evidence that selected the work

The last-24-hour production Web Analytics view showed 19 visitors, 102 page views, 47% bounce, two
`SignupStarted` visitors, and no credential-ready or submitted milestone. Both starts were direct,
US, desktop Mac visits with no referrer. That tiny anonymous sample may include automation and was
not treated as a conversion rate or evidence for another signup rewrite.

The deterministic code audit found a stronger discontinuity: all four capability-page CTAs carried
acquisition, location, and plan into `/app`, but none carried the capability the visitor selected.
The authenticated bootstrap therefore had no way to open the promised creation surface.

## Correction

- Added an allowlisted `intent=document|presentation|resume|video` value to every sign-in and signup
  CTA on the four matching capability pages.
- Kept the existing privacy-minimized acquisition parameter and added the allowlisted intent to
  existing marketing and auth funnel context.
- Stored the pending creation category locally for no more than 24 hours so an email-verification
  return can finish the original journey on the same browser.
- Deferred delivery until the existing body runtime is ready, then opened the exact established
  product surface without generating or charging.
- Opened general documents, PowerPoint with a presentation-specific brief, Word with a factual
  résumé-specific brief, or Video Studio as selected.
- Cleared the pending intent only after the destination acknowledged it.
- Added the content-free `CreationIntentContinued` client event for outcome reconciliation.
- Advanced the application to 5.9.56, native build 50956, and PWA cache revision 90.

## Real-controller browser proof

The loopback fixture loads the real Ask Crump authentication controller and five-destination
navigation runtime. It contains no production account, token, content, or write-capable endpoint.

| Intent | Verified destination | Pending state | Browser errors |
| --- | --- | --- | --- |
| Document | Document Studio opened | Cleared once | 0 |
| Presentation | Document Studio selected editable PPTX | Cleared once | 0 |
| Résumé | Document Studio selected editable DOCX with factual-experience guidance | Cleared once | 0 |
| Video | Video Studio opened | Cleared once | 0 |
| Invalid value | No product surface opened | Not retained | 0 |

A separate two-page run began signed out with `signup=1&intent=resume`, verified that no tool opened
and the content-free intent remained pending, then returned authenticated without the query
parameter. The résumé workspace opened, attribution remained `organic`/`resume-hero`, and the
pending value cleared. This exercises the registration/verification-return boundary without
creating a production account.

All four local capability pages and all four production clean URLs were also checked at a 390 by
844 viewport. Their primary CTAs were visible, carried the correct intent plus signup/acquisition,
had no horizontal overflow, and produced no console warning or error.

## Automated and native verification

- 378 Python tests passed.
- Ruff passed for `backend` and `tests`; Python compilation passed for `backend`.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight, native web-bundle generation, and store metadata source checks passed.
- Local Android configuration advanced to Ask Crump 5.9.56/build 50956/API 36.
- GitHub CI run `33185622078` passed.
- Hosted unsigned Android App Bundle run `33185622086` passed.
- Hosted unsigned iOS Release compile run `33185622138` passed.

The local Windows verifier still correctly reports the absent iOS project. RevenueCat public keys,
Android `google-services.json`, signing credentials, physical-device results, screenshots, privacy
forms, and store submissions remain open release gates.

## Production evidence

- Deployment `dpl_ENikqcrY6BYhZHvzoDU5VGtgHnFc` reached `READY` from the exact commit.
- Production health returned HTTP 200 and version 5.9.56.
- The live service worker returned cache revision `ask-crump-new-body-v1-r90`.
- The live app referenced `auth-controller.js?v=5.9.56`.
- The live controller, navigation runtime, and all four capability pages contained the allowlisted
  handoff contract.
- Each production capability page passed the phone-size CTA, acquisition, overflow, and console
  check.

The exact deployment recorded intermittent background `POST /api/sync/push` 503 responses with the
categorical transport error `Database connection failed`. The client kept its existing account-
scoped queue, and the next observed sync returned 200. Supabase reported `ACTIVE_HEALTHY`; matching
session, user, chat, settings, and `apply_chat_sync` calls returned 200. The failure pattern existed
before this release and is not attributed to the creation handoff. It remains an explicit
reliability signal rather than being omitted from release evidence.

## Rollback

The prior production deployment `dpl_GchJJJKoqu4mBNdjhxz6Q4qunka6` remains available. This release
requires no database, schema, RLS, environment, authentication, payment, pricing, or provider
migration.

## Remaining evidence

Observe legitimate `MarketingCTA` or `MarketingSignin` → auth → `CreationIntentContinued` → starter
intent → activation → artifact requested/packaged/downloaded. Do not infer conversion lift from
the current anonymous sample. Keep the intermittent database-transport failures in reliability
monitoring and use the existing queued retry evidence before proposing a shared database-boundary
change.
