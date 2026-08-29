# Ask Crump 5.9.73 immediate account-entry release

Date: 2026-08-29

Production version: 5.9.73

Feature commit: `1f49a39`

Production deployment: `dpl_3aKh1GgGrP1qN77WtvcWhr4zb2rb`

## Accountable outcome

Always show a truthful, usable first surface while Ask Crump verifies a saved session, without
weakening server authority or letting a late bootstrap result overwrite an authentication action
the person already began.

The release does not claim signup lift. Its accountable delivery outcome is the removal of a
deterministic dead-air state at the account-entry boundary.

## Evidence and diagnosis

Privacy-safe Vercel Web Analytics showed that traffic was reaching account-entry intent while the
protected server funnel still had no comparable external-account cohort:

- trailing seven days: 107 visitors, 373 page views, 27 `SignupIntent` visitors, two
  `SignupStarted` visitors, and one client-side `AccountCreated` event;
- trailing 24 hours: 22 visitors, 132 page views, eight `SignupIntent` visitors, and no
  `SignupStarted`, credentials-ready, submitted, or account-created event;
- the protected 14-day production growth-funnel and artifact-journey snapshots returned no
  eligible accounts or artifact journeys.

These small anonymous counts can include internal or automated visits. The client-side event was
not treated as a verified external account because it had no matching protected server cohort.
They justified inspecting the entry boundary, not claiming a conversion rate or rewriting auth.

Source inspection and a credential-free delayed-session browser fixture reproduced the concrete
failure: both `authContainer` and `appContainer` were hidden until `checkSession()` returned, while
the bounded session request can take up to ten seconds. During the fixture's three-second delay,
the old first snapshot contained only the fixture status and no usable product surface.

## Correction

- Explicit `/app?signup=1` entry now exposes the existing registration surface before native
  bridge readiness and the saved-session probe finish.
- A normal returning `/app` entry now exposes the existing branded “Opening your workspace” gate;
  the private workspace shell remains `inert` and `aria-busy` until session authority is known.
- Signed-out completion hands the returning path to sign-in; a valid saved session continues into
  the existing authenticated route.
- A local authentication-flow revision invalidates the stale bootstrap result when login or
  registration submission begins, preventing a late probe from replacing the active outcome.
- `SignupIntent` remains content-free and ordered before `SignupStarted`; signed-in deep links do
  not become anonymous signup intent merely because the form was exposed during the probe.
- The application advanced to 5.9.73, native build 50973, and PWA cache revision 107.

## Safety and scope boundaries

The release did not change:

- session authority, cookies, native tokens, login, registration, verification, or recovery API
  behavior;
- email/password fields, password policy, terms acceptance, account creation, or profile setup;
- pricing, checkout, credits, plans, products, entitlements, RevenueCat keys, or Stripe;
- Supabase schema, RLS, provider routing, customer content, or AI prompts;
- developer accounts, signing, store records, console declarations, or app submission.

The production checks used public GET requests only. No account, login, signup, checkout, artifact,
customer-data mutation, or synthetic production funnel event was created.

## Validation

- The pre-change delayed-session fixture reproduced both cold routes as dead air.
- Corrected cold signup exposed and focused the real registration form before the probe settled.
- Corrected returning entry exposed the branded gate with the workspace shell inert and busy.
- Typed signup state survived the signed-out result, and a late valid saved-session result could
  not overwrite an active registration failure; the fixture recorded zero app starts in that race.
- A valid saved session moved from the returning gate into the existing app startup exactly once.
- The fully loaded public app tree was checked locally; the shipped static auth, runtime, style,
  and brand assets resolved, while Vercel Analytics and API routes were intentionally absent from
  localhost. The real form exposed the value statement, password guidance, assurance, and primary
  action.
- All 423 Python product/backend tests passed.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight, the native web-bundle build, store metadata validation, explicit Python
  compilation, and local Android release-source verification passed.
- Local Android verification accepted 5.9.73/build 50973 and kept the missing RevenueCat public
  key and Firebase file as explicit submission blockers.
- GitHub CI [run 33233033441](https://github.com/CRUMP-AI/AskCrump/actions/runs/33233033441)
  passed.
- Android Store Bundle Verification
  [run 33233033460](https://github.com/CRUMP-AI/AskCrump/actions/runs/33233033460) generated and
  compiled the unsigned 5.9.73/build 50973 candidate successfully.
- iOS Store Source Verification
  [run 33233033493](https://github.com/CRUMP-AI/AskCrump/actions/runs/33233033493) generated and
  compiled the unsigned 5.9.73/build 50973 Release candidate successfully.

## Production evidence

- Commit `1f49a39` was pushed to `main`.
- Production deployment `dpl_3aKh1GgGrP1qN77WtvcWhr4zb2rb` reached `READY` from the exact commit.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.73.
- The public signup HTML returned HTTP 200 with the 5.9.73 auth asset and value statement.
- The live service worker returned cache `ask-crump-new-body-v1-r107`.
- The deployment-scoped runtime log contained the successful health request, no runtime error
  cluster, and no warning, error, or fatal log in the inspected release window.

## Measurement decision

Keep the earlier decision boundary: observe the `SignupIntent` → `SignupStarted` boundary for at
least 14 days and 50 socially referred visitors before attributing behavioral improvement. A
consented legitimate account attempt can be diagnosed sooner. Do not infer a platform click-through
rate without impression data, and do not broaden auth from anonymous small-sample aggregates.
