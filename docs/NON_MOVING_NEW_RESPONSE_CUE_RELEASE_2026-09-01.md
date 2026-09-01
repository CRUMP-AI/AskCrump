# Non-moving new-response cue release — 2026-09-01

## Outcome

Ask Crump now makes a newly completed offscreen response discoverable without taking control of the
conversation viewport. The prior user-controlled scrolling release remains authoritative: rendering,
presence, streaming, restored history, and delayed media cannot move the feed.

When a genuinely new completed assistant outcome arrives while the reader is away from the bottom,
the existing **Jump to newest message** control receives a restrained dot and the accessible name
**New response available. Jump to newest message**. A polite, content-free status announces the same
state to assistive technology. Presence alone and repeated renders of the same streaming response do
not create a cue. Changing conversations resets the baseline without announcing old work. Reaching
the bottom manually or activating the explicit jump clears the cue.

The browser keeps only the latest completed assistant message ID in memory to distinguish a new
outcome. It does not persist or announce prompt text, response text, filenames, customer content, or
message identifiers. No generation, model, provider, prompt transformation, Project, file, credit,
plan, billing, account, database, analytics, campaign, or marketing behavior changed.

## Release evidence

- Feature commit: `4a4cb04b2f56161b84769d63109d803105a0a4d2`.
- Production deployment: `dpl_8aAQRA2g2Fs6pf4bvsjQjeu389uW`, `READY`, built from the exact feature
  commit in about 41 seconds with all six expected production aliases and no alias error.
- Exact web/PWA/native identities: `5.9.76-new-response-cue-1`; runtime-loader identity:
  `5.9.76-new-response-cue-loader-1`; service-worker cache:
  `ask-crump-new-body-v1-r202`.
- The canonical app, runtime loader, cue JavaScript, cue CSS, and health endpoint all returned HTTP
  200 after deployment.
- A 390×844 real-browser fixture held `scrollTop=420` through presence, a new response, a second
  render of that response, retired legacy scroll calls, restored history, and delayed image load.
  Presence produced no cue. The new response produced the exact visual/accessibility state without
  moving the viewport. The explicit jump reached one pixel from the end, cleared the cue, and a later
  manual position held exactly. Browser errors: zero.
- Signed-in production loaded the exact new loader, JavaScript, and CSS. The final scroll owner and
  its polite status region were mounted, and the idle control retained the exact accessible name
  **Jump to newest message**. No message, upload, generation, file, Project, credit, checkout, or
  account action was performed during the production check.
- All **742 Python tests**, **47 JavaScript validations**, Python compilation, production preflight,
  native web-bundle generation, store-metadata source checks, mobile signing-source controls, and
  diff integrity passed.
- Vercel reported no production runtime-error cluster in the inspected 30-minute window.

## Remaining evidence boundary

Repeat the cue and manual-scroll interaction while a legitimate long image or video response
finishes on exact signed iPhone and Android PWA/native candidates, including VoiceOver/TalkBack,
touch momentum, background/foreground, and slow-network media load. Observe legitimate external use
before claiming reduced abandonment, higher activation, or retention lift. This release proves the
production web/PWA behavior and native web-bundle inclusion, not a signed store candidate.
