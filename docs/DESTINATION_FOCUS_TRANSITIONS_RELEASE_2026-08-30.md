# Destination focus transitions release

Date: 2026-08-30

## Product outcome

Projects, Library, and Settings now announce their newly opened workspace to keyboard and
assistive-technology users. Focus moves from the selected persistent-navigation control to the
destination heading, and a direct Close returns focus to the exact desktop or mobile control that
opened that destination.

Ask still moves focus to the composer. Create remains a separately contained true modal and still
returns focus to Create. No Project, Library, conversation, account, entitlement, credit, billing,
checkout, or generated-content state changes as part of these transitions.

## Reproduced defect

A signed-in production audit opened Projects and Settings and found that each destination became
visible while focus remained on its rail button. The active element was outside the destination
sheet, and neither destination heading was programmatically focusable.

That made the visual transition clear but left keyboard and screen-reader users without a strong
announcement that the primary workspace had changed. The audit was read-only and created no
record, generation, content-bearing event, checkout, or payment.

## Correction

The persistent-destination controller now:

- makes the dynamic product heading and Settings heading programmatically focusable;
- tracks the active Projects, Library, Create-owned studio, or Settings surface;
- focuses the destination heading after the open transition without scrolling;
- leaves focus alone when a deeper Project flow has already moved it inside the sheet;
- remembers the exact visible desktop or mobile destination control;
- restores that opener after a direct Product or Settings Close;
- suppresses obsolete opener restoration when the person explicitly switches to Ask or Create; and
- preserves the existing background-isolation and Create-modal boundaries.

The workspace loader, PWA worker, and native loader reference the same versioned navigation and
product assets. The PWA cache advances to `r141`.

## Verification

A credential-free browser fixture using the production navigation controller proved:

- Projects focused `crump53WorkspaceTitle` and kept focus inside the Projects sheet;
- Library changed the same dynamic heading to **Library** and focused it;
- Settings focused `settingsTitle` inside its destination sheet;
- Projects → Settings and Settings → Library transitions focused the new destination rather than
  restoring an obsolete control;
- direct Product Close restored **Library** and direct Settings Close restored **You**;
- Ask restored the uncovered workspace and focused `userInput`;
- switching from a persistent destination to Create focused Close, kept the app inert, and restored
  the Create control on Escape; and
- the fixture and browser console recorded zero errors.

Release gates:

- 496 Python regressions passed;
- 45 JavaScript files passed the integration validator;
- the production preflight passed;
- the native web bundle rebuilt successfully;
- Apple and Google metadata source checks passed; and
- `git diff --check` passed.

## Production evidence

- Feature commit: `189e966`
- Deployment: `dpl_FcA1gGNnkwf365XbACgC3QKipstE`
- State: `READY`
- Production aliases: all six expected Ask Crump and Clever Crump aliases
- Alias error: none
- Canonical app and four exact release assets: HTTP 200
- Signed-in read-only flow: Projects, Library, Settings, Ask, and Create all produced the expected
  focus target, background state, destination state, and exact opener restoration
- Exact live cache: `r141`
- Browser console: empty after the production flow
- Initial runtime audit: no runtime-error cluster and no warning, error, or fatal production log

## Observation boundary

Delivery is verified on web/PWA and included in the regenerated native web bundle. Physical iPhone
PWA, Android, keyboard, VoiceOver, and TalkBack passes remain release-readiness gates. Activation,
retention, or revenue impact requires legitimate post-release behavior and is not inferred from the
delivery proof.
