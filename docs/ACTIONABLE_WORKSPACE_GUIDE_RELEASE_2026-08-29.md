# Actionable workspace guide release

Date: 2026-08-29

Status: production verified

Behavior commit: `0b54855` (`Make the workspace guide actionable`)

Production deployment: `dpl_24vvs9mPdzu6KwbMjGUirVkM1xkE`

Production version: `5.9.76`

## Evidence and decision

The five-destination guide already matched the reorganized Ask, Projects, Create, Library, and You
information architecture. The subsequent dedicated-Project release changed one important behavior
that the guide did not teach: a person now opens Projects and selects a named Project to enter that
Project's own workspace. The previous guide described durable context but gave no direct instruction
or action for entering it.

The release keeps the task-oriented launchpad as the non-blocking first-run experience. The full
guide remains available from You → About → Replay workspace guide, but every guide step can now hand
the person directly into the corresponding real destination.

## Shipped behavior

- The Projects step says to open Projects and select a named Project.
- The step names the dedicated workspace's conversations, instructions, notes, reference files,
  files, and canon instead of describing Projects only as an abstract storage concept.
- Ask, Projects, Create, Library, and You each expose one restrained `Open …` action.
- The action closes the guide and calls the established `CrumpNavigation5930.open()` destination
  boundary. It does not duplicate destination logic.
- The handoff itself creates no Project, conversation, artifact, generation, checkout, or credit
  charge. Projects and Library retain their existing owner-scoped reads.
- The per-account completion key advanced to `crump_tutorial_completed_v7`.
- Browser and native loaders use the independently versioned
  `5.9.76-actionable-tour-1` onboarding assets.
- Service-worker cache revision `ask-crump-new-body-v1-r126` distributes the updated guide.

## Verification

Automated gates:

- 105 focused activation, navigation, cache, mobile, and release-contract tests passed.
- All 479 Python regressions passed.
- All 45 JavaScript files validated.
- Ruff passed for `backend` and `tests`.
- The backend Python compile gate passed.
- Production build preflight passed.
- The native web bundle regenerated successfully.
- Apple and Google store metadata source checks passed.

Credential-free browser fixture:

- Desktop review at 1280 × 720 rendered the Projects step, destination map, three Project-specific
  facts, direct action, progress, Back, and Continue without clipping the fixed footer.
- Mobile review at 390 × 844 preserved the same content in a scroll-safe sheet with full-width
  Project action and reachable Back/Continue controls.
- Selecting `Open Projects` removed the guide and produced the expected `projects` handoff.
- Browser diagnostics reported zero errors.

Signed-in production review:

- The live app loaded `/onboarding.js?v=5.9.76-actionable-tour-1` and the matching stylesheet.
- You → About → Replay workspace guide opened the five-step guide.
- Continue → Open Projects closed the guide and opened the real owner-scoped Projects index with
  the account's named Project rows.
- Production browser diagnostics reported zero errors.
- `https://www.askcrump.com/api/health` returned HTTP 200 for Ask Crump `5.9.76`.
- The deployment is `READY` on all six production aliases with no alias error.
- The project had no runtime-error cluster in the inspected hour, and the deployment had no
  warning, error, or fatal log in its inspected window.

## Known native submission gates

The native source verifier still reports only the existing release-time blockers: the local Windows
checkout has no iOS project, both RevenueCat public SDK keys are unset, and Android
`google-services.json` is absent. This release did not add a native blocker and does not claim store
submission readiness.

## Measurement and rollback

The guide uses the same real destination boundary as ordinary navigation. Evaluate its impact through
the existing downstream starter-intent, Project durable-value, Project-return, activation, and paid
conversion events; do not add a content-bearing tutorial event. Small or owner-only samples remain
directional.

Rollback is the previous verified production deployment. Reverting `0b54855` removes the actionable
guide while leaving the five-destination interface, named Project workspaces, account data, Projects,
conversations, artifacts, billing, and storage unchanged.
