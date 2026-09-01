# Precision Edit workspace-guide release — 2026-09-01

## Outcome

The replayable six-destination workspace guide now teaches the shipped Precision Edit workflow at
the moment a user is learning **Create**. It explains that an image may use a reference and that,
after a result, the user can brush over only the area allowed to change. The compact feature row now
names **References & Precision Edit**.

The guide remains non-blocking. The task-oriented launchpad still opens first, and the full guide is
available from **You → About → Replay workspace guide**. Opening Create from the guide performs only
the existing local navigation handoff; it does not generate, upload, save, meter, or purchase.

## Verification

- All 749 Python tests passed.
- All 48 JavaScript files passed the repository contract gate.
- Production preflight, native web-bundle creation, store metadata, mobile signing-source controls,
  and diff integrity passed.
- The real-browser contract replayed all six guide steps on desktop and 390-by-844 mobile, proved
  every destination handoff, asserted the exact Precision Edit explanation and feature label, and
  produced zero errors.
- Production returned byte-for-byte matches for the versioned runtime loader and onboarding script.
- A signed-in production walkthrough opened **You → About → Replay workspace guide**, reached step
  3 of 6, displayed the exact new explanation, opened the real **Make something useful** Create
  surface, and closed it with zero browser errors and no customer write or generation.
- The inspected 30-minute production window contained no runtime-error cluster and no
  warning/error/fatal log.

## Release identity

- Commit: `9d081f163a9154d7c683e53c0d209006fff93fdb`
- Deployment: `dpl_HECYYCJCput4wAsPXVJ2gM9MVUgh`
- Status: `READY` on all six aliases
- Guide asset: `5.9.76-precision-edit-guide-1`
- Runtime loader: `5.9.76-precision-edit-guide-loader-1`

## Measurement and next action

This is activation readiness, not evidence that tutorial use improves activation. Evaluate it only
through legitimate downstream creation, useful-result, Project-save, artifact, and return outcomes.
Do not add content-bearing tutorial analytics or auto-block the launchpad.

Continue the current image-release observation boundary. At or after 2026-09-02 09:40 EDT, inspect
the complete post-release production window before adding live appearance controls.

