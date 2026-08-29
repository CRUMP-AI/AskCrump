# Ask Crump 5.9.71 value-aware signup entry release

Date: 2026-08-28

Production version: 5.9.71

Feature commit: `60f2c7d`

Production deployment: `dpl_5ovTWjwVjq7iUSf9u92gXqR8Lr5w`

## Accountable outcome

Give a cold visitor enough product context to decide whether to begin free registration without
adding a new commitment, field, claim, or authentication branch.

The release does not claim signup lift. Its accountable delivery outcome is a value-aware,
readable, and above-fold registration entry at desktop and phone sizes.

## Evidence and diagnosis

The privacy-safe Vercel Analytics view for the last 24 hours showed:

- 22 visitors, 145 page views, and 41% bounce.
- Seven `SignupIntent` visitors and 17 events.
- Every signup-intent visitor landed directly on `/app`.
- Six signup-intent visitors were attributed to Facebook.
- The plan was `free`; the creation intent was unspecified.
- No visitor emitted `SignupStarted`, `SignupCredentialsReady`, `SignupSubmitted`, or
  `AccountCreated`.

These anonymous counts are small and may include internal or automated visits, so they are not a
conversion rate and did not justify a broad signup redesign.

A credential-free local load of the real production markup produced the deterministic issue:

- Desktop displayed the Ask Crump product promise beside the form.
- The responsive mobile layout intentionally hid that brand panel.
- The remaining signup introduction said only that the account was free and required no card.
- A cold socially deep-linked mobile visitor therefore reached credential fields without a concise
  explanation of the product value.

The page had no browser error, focus failure, blocked field, or hidden primary action.

## Correction

- The signup introduction now states that a workspace lets a user ask questions, create useful
  work, and pick up where they left off.
- The existing free/no-card reassurance remains in the same introduction.
- The verification assurance uses the established neutral text color and an 11-pixel size instead
  of a 9.5-pixel low-emphasis treatment.
- A regression contract protects the product-value sentence and assurance readability.
- The application advanced to 5.9.71, native build 50971, and PWA cache revision 105.

## Safety and scope boundaries

The release did not change:

- email or password collection;
- password length or composition policy;
- registration, verification, login, recovery, cookie, or session behavior;
- privacy, pricing, checkout, credits, plans, or entitlements;
- acquisition attribution or funnel-event names and semantics;
- Supabase schema, RLS, provider routing, AI prompts, or customer content;
- any production account, signup, payment, message, Project, or artifact.

No synthetic production funnel event or account was created.

## Validation

- All 414 Python product/backend tests passed.
- All 44 JavaScript files passed syntax and integration validation.
- Production build preflight passed.
- The native web bundle built successfully.
- Android source verification passed for 5.9.71/build 50971; missing release-time RevenueCat and
  Firebase credentials remain an explicit store-submission gate.
- Store metadata source checks passed.
- The real local signup screen was checked at desktop, 390-by-844, and 390-by-667 viewports.
- At both phone sizes the value sentence and primary action were visible; email retained initial
  keyboard focus and the browser reported no warnings or errors.
- GitHub CI run `33224902387` passed.
- Android Store Bundle Verification run `33224902413` passed.
- iOS Store Source Verification run `33224902385` passed.

## Production evidence

- Commit `60f2c7d` was pushed to `main`.
- Vercel production deployment `dpl_5ovTWjwVjq7iUSf9u92gXqR8Lr5w` reached `READY` with all four
  canonical domains assigned.
- `/api/health` returned HTTP 200 and version 5.9.71.
- The live `/app?signup=1` source returned HTTP 200 with the new product-value sentence and
  release-versioned assets.
- The live service worker returned cache `ask-crump-new-body-v1-r105`.
- The initial release window had no runtime error cluster and no warning, error, or fatal log.
- The deployment-scoped status breakdown contained two successful 200 responses and no failure.

## Measurement decision

Observe the `SignupIntent` → `SignupStarted` boundary for at least 14 days and at least 50
socially referred visitors before attributing a behavioral change to this release. A consented,
legitimate post-boundary attempt may be diagnosed sooner.

For future cold organic social traffic, prefer the public product or relevant capability page over
a direct signup link unless the creative itself gives enough product context. Do not infer
platform click-through rate without platform impression data, and do not broaden the auth flow from
anonymous small-sample aggregates.
