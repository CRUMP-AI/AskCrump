# Homepage real-workflow proof release — 2026-09-08

## Outcome

The homepage secondary hero action now says **See a real workflow** and opens the existing
evidence-led guide at `/guides/rough-idea-six-week-launch-plan`. It replaces a vague
**See how it works** jump to a second product-description section on the same page. The primary
**Start free** action, its Free-plan handoff, pricing, registration, first-touch attribution, and
campaign registry remain unchanged.

The destination uses an authentic current-product capture, labels its fictional example, states
what still needs human judgment, and makes no unsupported performance or customer claim. This is
a product proof-path correction, not a marketing publication or an assertion of conversion lift.

## Decision evidence

The Vercel Web Analytics view for September 1 through September 8 showed 26 visitors and 220 page
views across a small, mixed sample that may include founder or tester traffic. The homepage had 14
visitors; the product recorded two `SignupIntent` visitors but no visible `MarketingCTA` or
`MarketingExplore` visitor in that view. The service-role, content-free production reports still
contained no comparable current registration, attribution, artifact, or checkout cohort.

Those numbers are too small for a conversion conclusion. They do establish that acquisition
volume remains the company bottleneck and support a bounded change that gives curious visitors
truthful product evidence without weakening the primary account-entry path.

## Verification

- The local rendered homepage exposed both hero actions above the fold at 1280 by 720. Each had a
  50-pixel height; the secondary action resolved to the exact guide route.
- The local and production guide rendered its title, live-product proof statement, fictional
  example boundary, and **What still needs human judgment** section.
- Canonical production returned HTTP 200 for `/`, the guide route, and `/api/health`.
- All **873 Python tests** were collected: **871 passed** and two environment-dependent tests were
  skipped.
- All **49 JavaScript files** and all six attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web-bundle generation, and diff integrity
  passed.
- Main CI, Android bundle verification, and unsigned iOS source verification passed.
- The production deployment reached READY on all six aliases with no alias error. Its initial
  30-minute runtime-error query was empty, and the build completed without a failing log event.

## Release identity

- Feature commit: `3c15427fbf15cce710af2fbaad1008a56095c2d9`
- Production deployment: `dpl_2iosjT4c1y4y5EbhakFPVpzH5GAN`
- Status: `READY`
- Main CI: `34249566159` — success
- Android verification: `34249566011` — success
- iOS verification: `34249566133` — success
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases

## Privacy and measurement boundary

Production verification inspected public DOM state and destination URLs without clicking the
analytics-tagged control, creating an account, or emitting a synthetic funnel event. No account,
prompt, response, Project, file, event, provider request, credit, subscription, payment, or
customer record was created or changed.

The first legitimate visitor cohort remains the decision boundary. Observe homepage exploration,
registration, activation, durable Project or artifact value, return, and payer outcomes before
changing the primary CTA or claiming lift.
