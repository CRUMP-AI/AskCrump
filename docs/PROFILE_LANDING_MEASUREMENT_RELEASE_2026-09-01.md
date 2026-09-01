# Truthful profile-link landing measurement release — 2026-09-01

## Outcome

Ask Crump can now count a valid Facebook or Instagram profile-link landing for the registered
`real-product-continuity` campaign without inventing a creative label. Profile links emit the exact
three-token touchpoint `acquisition.profile-link.campaign`; creative-specific feed and Story links
continue to emit the existing four-token `acquisition.placement.campaign.creative` shape.

This restores a truthful anonymous landing denominator for the shared profile destination while
keeping feed and Story creative performance distinguishable.

## Finding and correction

The reported analytics preload race was not present. Every measured page loads
`telemetry-config.js` before `landing.js` and the Vercel Analytics runtime, and both first-party
scripts install the documented `window.va` / `window.vaq` queue. A real-browser proof using the exact
live Analytics runtime confirmed that the deferred script drains the queued event.

The actual gap was the registered profile-link contract: a valid campaign with no creative was
preserved as first-touch attribution, but `MarketingLanding` required a creative and therefore did
not emit. The corrected runtime recognizes only an exact allowlisted profile-link tuple whose URL
does not contain a `creative` parameter. Invalid, empty, mismatched, overlong, or unregistered values
remain rejected.

The once-per-tab marker is now written only after Analytics accepts or queues the event. If the
analytics call throws, the marker stays absent so a later page in the same tab can retry. A stored,
unexpired first touch remains immutable when a second campaign is opened in the same tab.

## Privacy boundary

- `MarketingLanding` contains exactly two properties: `touchpoint` and `intent`.
- It contains no prompt, response, filename, email, user/account identifier, raw URL, referrer, or
  customer content.
- Query strings and fragments remain removed from Vercel page-view telemetry before the Analytics
  runtime loads.
- The event remains anonymous and is not written to Ask Crump account, product-event, database, or
  conversation storage.
- No historical event was backfilled and no production campaign visit was manufactured for QA.

## Verification

- All **767 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- JavaScript syntax, changed-file Ruff, Python compilation, production preflight, native web-bundle
  creation, store metadata, mobile signing-source controls, and diff integrity passed.
- The normal browser proof covered an exact feed event, truthful creative-free profile event,
  immutable same-tab first touch, exact referral, invalid tuple rejection, and mobile containment.
- The deferred-order proof served the exact current Vercel Analytics runtime into the real local
  pages while intercepting event delivery. It observed exactly one four-token feed event and one
  three-token profile event in isolated tabs, and no same-tab duplicate.
- Production serves the exact committed landing script, service worker, and representative pages
  byte-for-byte. Script order is `telemetry-config.js`, `landing.js`, then Vercel Analytics.
- Both canonical health endpoints returned HTTP 200 with `Cache-Control: no-store`.
- The exact deployment is `READY` on all six aliases. After the observation window it had no 4xx,
  5xx, warning/error/fatal log, or runtime-error cluster.

## Release identity

- Feature commit: `14145f7522f4d8703f45a7056edf213fa0d637c8`
- Production deployment: `dpl_4KzDciwMEode9YKzo5rwQzs8PKy4`
- Status: `READY`
- Build duration: about 50 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases
- Landing script: `5.9.76-profile-landing-1`; SHA-256
  `27B0D37C0854F183435338DCC6CF4C51F1B748095EB22D1FF34BFDEDA47C6991`
- Service-worker cache: `ask-crump-new-body-v1-r206`; SHA-256
  `3022860AD97F3DB2625AA9AD4F33AB2EFA516379B5424912856025CC0D8BF667`

## Remaining evidence

1. Let natural profile traffic populate the anonymous denominator; do not backfill or synthesize it.
2. Use the service-role weekly export for signup, activation, Project/artifact, D1/D7, payer, refund,
   recognized-revenue, and variable-cost decisions. Anonymous landing counts are not user-level
   conversion proof by themselves.
3. Keep broad paid acquisition held until legitimate cohort volume and activated-user D7 evidence
   satisfy the existing decision contract.
