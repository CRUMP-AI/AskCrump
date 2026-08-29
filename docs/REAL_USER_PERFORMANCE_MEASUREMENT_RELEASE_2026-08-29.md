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

## Measurement boundary

Delivery is verified; field performance is not yet known. Wait for legitimate production traffic
to populate Speed Insights before selecting a Core Web Vitals intervention. Do not infer a score
from local checks or manufacture traffic to create a sample.

Separately, Search Console shows that the presentation page is live-indexable but not yet known to
Google. The sitemap and internal discovery paths are already correct. Sitemap submission remains
an owner-gated external action and was not performed.
