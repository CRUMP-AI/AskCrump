# Ask Crump 5.9.65 cross-device blank-conversation release

Date: 2026-08-28
Production version: 5.9.65
Feature commit: `1d7e908c3e3c93aa39707796b5b398000df17250`
Production deployment: `dpl_DU1j6CsCCnHFGBcjtH4quoYjAych`

## Outcome

Opening Ask Crump on a new device previously created and saved a blank `New Conversation` before
the user typed or sent anything. Each additional device could therefore add another empty row to
the same account, making cross-device history look noisy and unreliable.

Production 5.9.65 makes a fresh canvas ephemeral. Ask Crump now materializes a conversation only
after the user begins a real send. Server synchronization can still restore existing work, but it
cannot turn an untouched startup canvas into durable history. Legacy default-titled empty rows are
suppressed from the client cache and outbound merge so they stop multiplying across devices.

## Scope and safety

- No conversation, message, Project, file, account, artifact, or customer content was deleted from
  the server or database.
- Existing non-empty conversations and intentionally titled conversations remain available.
- Authentication, ownership checks, RLS, storage, pricing, credits, entitlements, providers,
  payments, and server analytics semantics did not change.
- The release also corrects signup-start measurement: programmatic focus no longer records
  `SignupStarted`; the milestone begins only when a person edits a credential field or submits.
- Browser verification used synthetic local state and did not create a production conversation,
  account, message, signup event, Project, artifact, or payment.

## Verification

### Local contracts and build

- All 399 Python tests passed.
- Ruff and backend compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight and native web-bundle build passed.
- Android synchronization, configuration, and native-source checks passed for version 5.9.65,
  build 50965.
- Store metadata and mobile signing-source checks passed. RevenueCat Android configuration,
  `google-services.json`, store signing, physical-device testing, and final console submission
  remain separate human/store gates.

### Cross-device browser fixture

- A clean synthetic device pulled one real server conversation plus two legacy default empty rows.
- After startup, the fixture contained one visible durable conversation, zero local blank rows,
  zero outbound blank rows, no current durable conversation, and zero browser errors.
- After the first real send, exactly one new conversation materialized, the visible durable count
  became two, and local/outbound blank-row counts remained zero.
- A separate registration fixture recorded `SignupIntent` on automatic registration-screen focus
  and added `SignupStarted` only after real email input, with zero browser errors.

### Hosted gates

- CI: [run 33210710079](https://github.com/CRUMP-AI/AskCrump/actions/runs/33210710079) — passed.
- Android store bundle: [run 33210710087](https://github.com/CRUMP-AI/AskCrump/actions/runs/33210710087) — passed.
- iOS store source: [run 33210710074](https://github.com/CRUMP-AI/AskCrump/actions/runs/33210710074) — passed.

### Production

- Git deployment `dpl_DU1j6CsCCnHFGBcjtH4quoYjAych` reached READY on production and serves
  commit `1d7e908` through `askcrump.com` and `www.askcrump.com`.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.65.
- The live application referenced the 5.9.65 app, authentication, and synchronization assets.
- The live service worker returned cache `ask-crump-new-body-v1-r99` with 5.9.65 versioned assets.
- Vercel reported no runtime error cluster and no warning, error, or fatal deployment log in the
  inspected one-hour release window.

## Outcome still to prove

The release verifies that untouched device startups do not create or propagate blank conversation
history. Repeated real-device use still needs to confirm lower history noise and easier returning-work
discovery. Those outcomes require legitimate post-release behavior and content-free aggregate
evidence.
