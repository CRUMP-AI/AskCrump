# Real-user performance measurement release

Date: 2026-08-29

Status: verified in production; field sample pending

## Decision

Measure the real acquisition and workspace surfaces before making another performance
intervention. The Vercel project had Speed Insights enabled but had collected no field events, so
Core Web Vitals and Real Experience Score were unavailable.

This is an observability release. It does not change authentication, account creation, pricing,
entitlements, product behavior, customer data, public claims, or social publication.

## Change

The existing first-party Vercel Speed Insights collector now loads exactly once on:

- the Ask Crump homepage;
- the presentation, document, résumé, and video acquisition pages;
- the web/PWA app shell; and
- the Clever Crump parent-company page.

The project-hosted collector route was already active and returned HTTP 200 JavaScript with the
Vercel vitals endpoint. No package, dependency, provider account, API key, environment variable,
or paid API was added.

The collector adds one deferred script to the cold signed-out app shell. The authenticated
workspace runtime, login and signup controls, attribution logic, and service-worker cache revision
remain unchanged.

## Route-label follow-up

The first seven desktop events proved ingestion but were all grouped under `Unknown`, making the
sample unusable for page-level decisions. Production commit `a3fc449`, deployed as
`dpl_DtaaNbQUhvpvekMjG973eBfjuyGy`, now gives each collector one explicit route:

- `/` for the Ask Crump homepage;
- the exact public path for each of the four acquisition pages;
- `/app` for the web/PWA shell; and
- `/clever-crump` as the parent-company surface's logical project route, keeping it distinct from
  the Ask Crump homepage inside the shared Vercel project.

All seven canonical documents returned HTTP 200 with the expected route exactly once. One bounded
desktop verification visit then produced three `/` metric events alongside the seven historical
`Unknown` events, proving the route label reached the dashboard. Those ten events are release
verification traffic, not a legitimate customer sample and not evidence of product performance.

## URL-redaction follow-up

The app accepts password-reset tokens in the `/app` query string, while the Speed Insights event
shape contains a page URL. There is no evidence that a real reset token was captured, but route
labels alone were not a sufficient prevention boundary because `/app?token=...` and `/app`
share the same pathname.

Production commit `448841a`, deployed as `dpl_3KmLcZ97Pra7DpG8qY7Drw5kQ1z3`, adds one shared
configuration script before every Speed Insights collector. It uses the supported `beforeSend`
hook to remove the complete query string and fragment from valid event URLs. Events without a
valid URL are dropped rather than transmitted.

The executable contract proves that
`https://www.askcrump.com/app?token=secret&signup=1#recovery` becomes exactly
`https://www.askcrump.com/app` while retaining the explicit `/app` route. The production
sanitizer and a synthetic sentinel recovery URL both returned HTTP 200; the live DOM loaded the
configuration once before the collector, retained the route, had zero horizontal overflow, and
reported no warning/error console entry. No real token, account, credential, or customer content
was used in verification.

## Verification

- Commit `ddb4344` deployed as `dpl_8H52xj6sQDmT55HznVmcmLenmxbo`.
- All six production aliases point to the release.
- The canonical homepage, four acquisition pages, app shell, and parent-company page each returned
  HTTP 200 and contained the collector exactly once.
- The collector route returned HTTP 200 JavaScript and referenced the production vitals endpoint.
- Live browser checks on the homepage, app, and parent-company page found the exact script once,
  zero horizontal overflow, and zero warning/error console entries.
- All 433 Python regressions and all 44 JavaScript validations passed.
- Explicit Python compilation, production preflight, native web-bundle build, and store metadata
  checks passed.
- Native release verification retained the existing release-time gates: RevenueCat public SDK
  keys, Android `google-services.json`, and an iOS project are still required. No new native gate
  was introduced by this release.
- The release window contained no runtime error cluster or warning/error/fatal deployment log; the
  observed deployment status group was HTTP 200.
- The route-label follow-up repeated all 433 regressions, all 44 JavaScript validations, production
  preflight, native web-bundle build, and store metadata checks.
- The route-label deployment reached all six aliases, returned only HTTP 200 in the observed status
  group, and had no runtime error cluster or warning/error/fatal log.
- The URL-redaction follow-up passed all 434 Python regressions, all 45 JavaScript validations,
  production preflight, native web-bundle build, and store metadata checks.
- All six aliases point to the redaction release. Its observed runtime group contained 51 HTTP 200
  responses with no runtime error cluster or warning/error/fatal log.

## Measurement boundary

Delivery is verified; field performance is not yet known. Wait for legitimate production traffic
to populate Speed Insights before selecting a Core Web Vitals intervention. Do not infer a score
from local checks or manufacture traffic to create a sample.

Separately, Search Console shows that the presentation page is live-indexable but not yet known to
Google. The sitemap and internal discovery paths are already correct. Sitemap submission remains
an owner-gated external action and was not performed.
