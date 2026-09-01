# Project conversation resume focus release — 2026-09-01

## Outcome

Choosing **Continue** inside a Project now returns the user to the linked conversation with
the **Message Crump** composer focused. The closed Projects surface no longer retains focus
on a hidden destination button.

## User-eye finding

A signed-in production walkthrough proved that the conversation, Project context, and mobile
context strip restored correctly, but keyboard focus remained on the Projects destination after
the Project workspace closed. This was easy to miss with a pointer and disruptive for keyboard
and screen-reader users.

The first implementation focused the composer after one animation frame. Production validation
then exposed a second navigation callback that restored focus to the Projects opener. The final
implementation returns through the shared Ask destination owner before loading the conversation,
suppresses that stale restoration, and then focuses the composer without scrolling the page.

## Boundaries

- The linked conversation and its owner-scoped Project relationship are unchanged.
- A current-session **Leave** choice remains respected; Continue does not silently override it.
- No message is sent and no account, Project, conversation, file, content, generation, billing,
  entitlement, credit, analytics, API, or database state is written by this handoff.
- The separate Ask Crump API image candidates remain disabled until their own production and
  funded-smoke gates are met.

## Verification

- The deterministic Project context browser proof passed at 1280×760 and 390×844. It verified
  the Ask destination handoff, exact linked chat, composer focus, prior Leave preservation,
  Project target preservation, mobile dock sizing, and zero browser errors.
- All 720 Python tests passed.
- All 47 JavaScript validations passed.
- Production preflight and the native web build passed.
- Store metadata and signing-source checks passed; native platform/signing/device acceptance
  remains a separate store-release gate.
- Diff integrity passed.

## Production proof

- Final commit: `c7f934dced7ea959aad55ee8165ca09d808d4e51`.
- Final deployment: `dpl_6KGNR9gCSdeevbk3V6gVB2NANSRp`, READY with all six aliases and no
  alias error.
- Canonical production serves `5.9.76-project-resume-focus-2` and service-worker cache `r186`.
- A signed-in, phone-width walkthrough continued a real saved Project conversation and measured:
  `userInput` as the active element, Projects hidden, Project context active, a 146px mobile dock,
  and zero horizontal overflow. No message was sent and no durable state was changed.
- The release window showed 30 successful 200 responses, no 4xx or 5xx logs, no runtime-error
  cluster, and no warning/error/fatal log.

## Remaining acceptance

Repeat the saved-Project Continue flow on a physical iPhone with VoiceOver, safe areas, the
software keyboard, backgrounding, and PWA relaunch before store screenshots. Retention impact
must be observed from legitimate use rather than inferred from delivery.
