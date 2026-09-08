# Referral recipient context — 2026-09-08

## Outcome

An exact shared-response referral URL now gives its recipient a restrained, truthful explanation
before signup:

- **Someone shared Ask Crump with you.**
- **This link shares the product—not their conversation, files, or private content.**

The message appears only for `?acquisition=referral&source=response-share`. It remains hidden for
direct, campaign, profile, and invalid attribution tuples. The primary **Start free** action stays
dominant and no additional conversion action was introduced.

## Evidence and privacy boundary

The service-role, content-free production review at `2026-09-08T18:55:54.940627Z` found no
external `ResponseShared`, `AccountCreated`, `ActivationReached`, or `AhaReached` events in the
reviewed period. The overall growth snapshot contained zero across its 18 stages and the weekly
attribution export had no rows. This is an evidence gap, not a conversion result.

The deterministic audit found that the shared URL already preserved first-touch attribution, but
the recipient received only the generic homepage and no explanation that the sender's private
work was not included. The new context is derived from the current exact URL. Existing unexpired
first-touch state remains immutable, a later tagged page cannot enrich it, and the context display
does not emit a second landing event. No prompt, response, filename, customer identifier, referrer
URL, conversation, file, or Project is exposed.

## Browser and visual acceptance

Credential-free browser verification covered the exact referral route, direct/campaign/profile/
invalid negative cases, and same-tab first-touch precedence. Desktop and 390×844 visual review
confirmed a restrained layout, no horizontal overflow, a dominant primary CTA, and zero browser
or console errors. The public preload, account-entry, and all three guide start-path fixtures also
passed unchanged.

An exact tagged production visit was deliberately not created because it would manufacture a
marketing event. The production asset bytes were instead compared with the locally browser-tested
bytes and matched exactly.

## Automated and release verification

- Full Python suite: **896 collected**, **894 passed**, two environment-dependent tests skipped.
- Focused marketing/product-analytics/revenue verification: **54 passed**.
- JavaScript integration contract: **49 files** and **6/6** attribution runtime cases passed.
- Ruff, explicit Python compilation, production preflight, native web build, and diff integrity
  passed.
- Main CI `34267274499`: success.
- Android Store Bundle Verification `34267274477`: success.
- iOS Store Source Verification `34267274441`: success.
- Production deployment `dpl_J8FBHv8b8Q1jVznibtyCZEp8qhok`: READY on all six aliases with no
  alias error.
- Canonical `/api/health`: HTTP 200, Ask Crump `5.9.76`.
- Deployment-scoped 30-minute error/fatal and HTTP 5xx queries: empty.

## Release identity and exact bytes

- Feature commit: `a34ad26c76c231d4bd287e0f14d0190743206aa4`
- `public/ask-crump.html` live/local SHA-256:
  `BCB96C4DEA8C93AFD49FA06DCC21AE6EBCD284B2AB1E1901DDD3235E723E938C`
- `public/landing.js` live/local SHA-256:
  `3FF9152F4CABEB8071C1CC8E4E8C108FBD02CE8FD2293AA690E54042FFE8FE24`
- `public/landing-5.6.css` live/local SHA-256:
  `901E859B694332B1BBDF2817F018244A2EA2A63804BF4736B01B364EBD9FD046`
- `public/sw.js` live/local SHA-256:
  `029A963714F7D043F603BAB1332AC5876D67A99DF3EF1EFE2BB89FB3E82A02F9`

## Boundary and next evidence

No account, message, response, conversation, file, Project, generation, signup, referral delivery,
analytics event, publication, social action, checkout, payment, lifecycle send, or customer-data
operation was created during this release. Marketing publication, advertising spend, lifecycle
sends, and Search Console actions remain separately held.

Observe the first legitimate response share → recipient visit → account creation → activation
journey before changing this copy or claiming referral lift.
