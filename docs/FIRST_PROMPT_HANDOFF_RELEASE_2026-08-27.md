# First-prompt handoff release — 2026-08-27

## Decision

Ship the composer handoff correction as Ask Crump 5.9.40. Preserve a user's draft when they choose
Research, Image, or Code, synchronize the real input state after programmatic changes, and stop a
bare mode scaffold before it reaches usage checks or chat mutation.

This is a verified usability and cost-avoidance correction. It is not evidence that external
starter-intent or activation conversion has improved.

## Reproducible defects

A credential-free local browser fixture loaded the real `app.js` and `crump-v1-body.js` handoff
sources.

With an empty composer, choosing Research produced visible text (`Search the web for `) and focused
the field, but the input container did not have its content state and the body did not have its
composer-active state. The programmatic value change had not emitted the same input event as real
typing.

With `Compare AMD and Nvidia earnings` already typed, choosing Research replaced the complete draft
with only `Search the web for `. With `A premium black and gold dashboard` typed, choosing Image
replaced the draft with only `Generate an image of `. The incomplete scaffolds could then reach the
send path as content-bearing requests even though they did not contain an actual task.

The same fixture proved that Analyze a file still opened the file chooser once; no File defect was
present.

## Bounded correction

- Research, Image, and Code now prefix an existing trimmed draft once instead of replacing it.
- Choosing the same mode again recognizes the exact scaffold or scaffold-plus-space boundary and
  does not duplicate it.
- An empty composer still receives the familiar visible scaffold so the existing backend routing
  behavior is unchanged.
- Every programmatic update dispatches a bubbling input event, focuses without scrolling, and
  places the caret at the end. Existing auto-resize, send-state, and body-state listeners now agree
  with the visible value.
- An exact bare scaffold is stopped before `ensureUsageAvailable` and before the chat receives a
  message. The user keeps focus and receives specific guidance for Research, Image, or Code.
- File selection and the content-free, idempotent starter-intent event are unchanged.
- Authentication, verification, terms, pricing, entitlement, provider routing, and backend APIs did
  not change.

## Source and release identity

- Application commit: `3ab5acba1f35f11fad74724704c22d851b26ce9f`
- Production deployment: `dpl_CT2aQtDDAwNLAEc2MzDwoWkvCaeW`
- Production version: 5.9.40
- Native build: 50940
- Service-worker cache: `ask-crump-new-body-v1-r74`
- Production aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the Vercel production aliases

## Browser verification

The corrected 390-by-844 browser fixture proved:

- Empty Research: the visible scaffold, content state, body-active state, focus, and caret all
  matched.
- Drafted Research: the value became `Search the web for Compare AMD and Nvidia earnings` and the
  full original draft remained.
- Research selected twice: no second scaffold was added.
- Drafted Image: the value became `Generate an image of A premium black and gold dashboard` and the
  full original draft remained.
- Bare Research send: no chat or usage path ran; focus remained and the interface returned
  `Add what you want Crump to research.`
- File: the existing chooser still received exactly one click.

The fixture contains no credential, production request, real analytics call, or data write.

## Release verification

The full local gate passed:

- 329 backend/contract tests
- backend/test lint
- all 42 JavaScript source validations and edited-source syntax checks
- production build preflight and native web-bundle generation
- Android 5.9.40/build 50940/API 36 source verification
- store metadata and mobile signing-source controls
- clean patch and release-version/cache consistency checks

Hosted verification passed on the exact application commit:

- CI: [run 33138434467](https://github.com/CRUMP-AI/AskCrump/actions/runs/33138434467)
- Android unsigned App Bundle: [run 33138434500](https://github.com/CRUMP-AI/AskCrump/actions/runs/33138434500)
- iOS unsigned Release compile: [run 33138434478](https://github.com/CRUMP-AI/AskCrump/actions/runs/33138434478)

The native workflows generated and verified release source and compiled unsigned candidates. They
did not sign, upload, submit, or use store credentials.

## Production verification

- The exact Git commit produced a `READY` production deployment with no alias error.
- `https://askcrump.com/api/health` returned HTTP 200, `Cache-Control: no-store`, and version
  5.9.40.
- The live app shell, composer source, and service worker returned HTTP 200.
- The composer source contained draft preservation, input synchronization, and incomplete-scaffold
  blocking. The service worker contained cache revision 74.
- The release-scoped scan found no runtime error cluster, non-informational log level, or 5xx
  response.
- No production prompt, workspace click, account, usage check, chat message, or synthetic product
  event was generated for verification.

## Measurement and rollback

Delivery is verified; activation lift and cost savings are unproven until legitimate external
behavior occurs. Measure `WorkspaceOpened` → `StarterIntentReached` → `ActivationReached` and
provider cost per successful task without capturing prompt content.

Rollback is the prior application commit and cache revision. The correction changes only the
client composer handoff and requires no data migration or cleanup.
