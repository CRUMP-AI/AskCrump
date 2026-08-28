# First-action runtime readiness release — 2026-08-27

## Decision

Ship the launchpad readiness correction as Ask Crump 5.9.39. Replace the fixed
120-millisecond Projects/Video retry with the runtime's existing completion event so a first
workspace choice made on a slower connection is held and opened when the product surface is
actually ready.

This is a reliability correction, not evidence that starter-intent or activation conversion has
improved.

## Evidence boundary before the change

The service-role production growth snapshot still returned zero comparable external accounts for
all 18 metrics, and the artifact-journey snapshot remained empty. There was therefore no honest
external funnel drop-off to optimize from live account behavior.

The source provided a deterministic defect instead. The body runtime loads and wires the launchpad
before it loads `crump-product-5.3.js`, which owns Projects and Video. During that gap,
`openProduct` scheduled one optional-chain retry after 120 milliseconds. If the product runtime
arrived later, the click still recorded the content-free, idempotent `StarterIntentReached` event,
but the selected workspace never opened and the user received no progress or failure feedback.

## Reproduction

A credential-free local browser fixture delayed the product runtime beyond the old retry:

- The user clicked Start or open a Project.
- After 250 milliseconds, the fixture contained one Projects starter-intent call and zero opened
  product tabs.
- The product runtime was then made ready and emitted `crump:body-runtime-ready`.
- The old implementation still contained zero opened tabs, no busy state, and no error feedback.

The fixture does not call production, create an account, submit a credential, write data, or send a
real analytics event.

## Bounded correction

- A Projects, Video, or Library choice is held until `crump:body-runtime-ready` when the existing
  product API is not yet available.
- The selected launch card exposes `aria-busy="true"` and replaces its arrow with a restrained
  ellipsis while waiting. Both restore before the workspace opens.
- If the runtime reports ready without the product API, the busy state clears and a truthful retry
  message appears instead of failing silently.
- If the user changes the queued choice before readiness, the latest choice wins and the earlier
  card is restored.
- If the product API is already available, the existing immediate-open path is unchanged.
- Starter intent remains recorded at the user's click with its existing content-free, idempotent
  key and allowlisted source. Authentication, verification, terms, pricing, entitlement, and
  product-workspace behavior did not change.

## Source and release identity

- Application commit: `e8fb9f0e5916bfbb7b2d2f26fcb191712fa426af`
- Production deployment: `dpl_HE8v2SbtqeuayEJajMYiTrLt3Q1p`
- Production version: 5.9.39
- Native build: 50939
- Service-worker cache: `ask-crump-new-body-v1-r73`
- Production aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the Vercel production aliases

## Verification evidence

The corrected local browser fixture proved:

- a Projects choice remained visibly busy while the product API was unavailable;
- emitting the real runtime-ready event opened Projects exactly once and restored the card;
- a missing API after readiness restored the Video card and surfaced an explicit error;
- clicking Projects and then Video before readiness restored Projects, kept Video busy, and opened
  only Video when ready;
- the existing starter event name, key, and allowlisted sources were unchanged.

The full local release gate passed:

- 324 backend/contract tests
- backend/test lint
- all 42 JavaScript source validations and edited-source syntax checks
- production build preflight and native web-bundle generation
- Android 5.9.39/build 50939/API 36 source verification
- store metadata and mobile signing-source controls
- clean patch and release-version/cache consistency checks

Hosted verification passed on the exact application commit:

- CI: [run 33137897554](https://github.com/CRUMP-AI/AskCrump/actions/runs/33137897554)
- Android unsigned App Bundle: [run 33137897556](https://github.com/CRUMP-AI/AskCrump/actions/runs/33137897556)
- iOS unsigned Release compile: [run 33137897614](https://github.com/CRUMP-AI/AskCrump/actions/runs/33137897614)

The native workflows generated and verified release source and compiled unsigned candidates. They
did not sign, upload, submit, or use store credentials.

## Production verification

- The exact Git commit produced a `READY` production deployment with no alias error.
- `https://askcrump.com/api/health` returned HTTP 200, `Cache-Control: no-store`, and version
  5.9.39.
- The live app shell, launchpad body, runtime loader, and service worker returned HTTP 200.
- The launchpad asset contained the queued readiness contract, the runtime loader contained the
  completion event after the product load, and the service worker contained cache revision 73.
- The release-scoped scan found no runtime error cluster, non-informational log level, or 5xx
  response.
- No production workspace click, account, profile, terms acceptance, product event, or synthetic
  activation was generated for verification.

## Measurement and rollback

Delivery is verified; activation lift is unproven. Observe legitimate external
`WorkspaceOpened` → `StarterIntentReached` → `ActivationReached` behavior before claiming an
outcome. A starter click proves intent, not that the selected workspace produced value.

Rollback is the prior application commit and cache revision. The correction changes only the
client readiness handoff and requires no data migration or cleanup.
