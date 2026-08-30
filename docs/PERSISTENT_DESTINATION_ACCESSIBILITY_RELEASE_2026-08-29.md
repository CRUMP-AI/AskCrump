# Persistent destination accessibility release

Date: 2026-08-29

## Product outcome

The signed-in Projects, Library, and Settings destinations now match their persistent-navigation
design. People can continue switching destinations from the desktop rail or mobile destination bar,
while the covered conversation sidebar and Ask workspace are removed from keyboard and
assistive-technology navigation until the destination closes.

Create remains a true modal chooser with complete workspace containment. This release changes no
Project, Library, conversation, account, entitlement, credit, billing, or checkout data.

## Reproduced defect

A signed-in production audit found that Projects and Settings declared `aria-modal="true"` even
though the product deliberately leaves its five-destination navigation available. At the same time,
the covered conversation sidebar and main workspace remained keyboard-reachable and visible to
assistive technology.

That combination described a blocking modal that did not exist and exposed controls a person could
not meaningfully use. The audit opened destinations read-only and created no record, generation,
event, checkout, or payment.

## Correction

The destination controller now:

- preserves the existing `inert` and `aria-hidden` state of the conversation sidebar and main
  workspace;
- applies `inert` plus `aria-hidden="true"` to those two covered regions while Projects, Library,
  manuscripts, video, or Settings is open;
- leaves the desktop rail and mobile five-destination navigation interactive;
- restores the exact prior background state on Close, destination switching, or return to Ask;
- identifies the persistent destination sheets as nonmodal dialogs; and
- leaves the separate Create chooser's true-modal focus containment unchanged.

The workspace loader, PWA worker, and native loader now reference the same versioned destination
assets. The PWA cache advances to `r140`.

## Verification

A credential-free browser fixture using the production navigation controller proved:

- Projects and Library selected their exact destination and isolated only the covered sidebar and
  workspace;
- Settings closed the product studio, remained reachable from persistent navigation, and applied
  the same covered-region boundary;
- both desktop and mobile destination navigation stayed outside the inert boundary;
- Ask, the product Close control, and the Settings Close control restored the prior background
  state;
- Create still applied true-modal containment, focused Close, wrapped Shift+Tab to Video, wrapped
  Tab back to Close, and restored its opener on Escape; and
- the fixture recorded zero browser errors.

Release gates:

- 495 Python regressions passed;
- 45 JavaScript files passed the integration validator;
- the production preflight passed;
- the native web bundle rebuilt successfully;
- Apple and Google metadata source checks passed; and
- `git diff --check` passed.

## Production evidence

- Feature commit: `508fabf`
- Deployment: `dpl_2AcqJH4Jk4rTnTSyesYsHGNudFBY`
- State: `READY`
- Production aliases: all six expected Ask Crump and Clever Crump aliases
- Alias error: none
- Canonical app and four exact release assets: HTTP 200
- Signed-in read-only flow: Projects, Library, Settings, and Ask all reported the expected
  destination, dialog semantics, covered-region isolation, persistent-navigation availability, and
  clean restoration
- Exact live cache: `r140`
- Browser console: empty after the production flow
- Initial runtime audit: no runtime-error cluster and no warning, error, or fatal production log

## Observation boundary

Delivery is verified on web/PWA and included in the regenerated native web bundle. Physical iPhone
PWA, Android, keyboard, and screen-reader passes remain release-readiness gates; user growth,
retention, or revenue impact requires legitimate post-release behavior and is not inferred from
delivery evidence.
