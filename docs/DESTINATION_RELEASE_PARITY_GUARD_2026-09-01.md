# Destination release parity guard — 2026-09-01

## Outcome

Ask Crump now has one build-breaking contract for its current six-destination product:
**Ask, Projects, Create, Video, Library, and You**. Navigation, the replayable workspace guide,
store descriptions, store screenshot order, and the intentionally hidden Code boundary cannot
quietly drift apart.

## Evidence that justified the work

A currentness audit followed a marketing hold caused by old five-destination creative. The live
product sources were already correct, but no single release gate compared all of the authoritative
surfaces. Historical notes correctly described earlier releases; rewriting them would weaken the
record. The safer response was an exact forward-looking parity guard.

## Guarded contract

- The customer-visible destination order is Ask → Projects → Create → Video → Library → You.
- Internal navigation may retain Code only in its explicit hidden, gated position between Projects
  and Create; it cannot become customer-visible by accidental source drift.
- The workspace guide must expose the same six labels and matching destination actions.
- Apple and Google descriptions must name the same six destinations.
- Both store screenshot arrays and the capture README must retain the exact eight-frame order:
  Ask, Projects, Create, Video, Research in Ask, Editable work, Library, You.
- The production build fails with one clear error if any of these sources diverge.

## Verification

- The browser regression now opens all six guide actions, rather than checking Video alone. Each
  step proved its exact number, title, map, current destination, action label, and opened target.
- Desktop and 390×844 browser runs also proved the six visible persistent destinations, direct
  Video entry, Create → Video handoff, and zero browser errors.
- A signed-in production walkthrough replayed all six guide steps and opened every real destination.
  Ask focused the composer; Projects, Video, and Library focused their workspace title; Create
  focused its close control; You focused the Settings title. Every handoff closed the guide and
  produced zero horizontal overflow.
- All 721 Python tests and all 47 JavaScript validations passed.
- Production preflight, Python compilation, native web bundling, store metadata, signing-source
  controls, and diff integrity passed.

## Production

- Commit: `caf0c67d411bb2ae6bdd9119503f9e7a902fa171`.
- Deployment: `dpl_G4rspSsPvsaUcU6Bpxk1XUtZ1u5r`, READY on all six aliases with no alias error.
- Canonical homepage, `/app`, and the exact onboarding asset returned HTTP 200.
- The release window had no runtime-error cluster, 4xx/5xx log, or warning/error/fatal log.
- This release changes build verification and test depth only. It does not modify product runtime,
  account state, conversations, Projects, files, generation, providers, credits, billing, analytics,
  API behavior, database objects, or customer data.

## Remaining gate

Legacy five-destination campaign captures remain invalid and must be replaced by fresh sanitized
captures from the exact current production build. Store screenshots still require the exact signed
native candidate, a dedicated reviewer account, physical-device testing, privacy declarations, and
explicit per-platform submission approval.
