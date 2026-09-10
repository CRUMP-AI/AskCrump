# Ask Crump interactive-control CI gate

Date: 2026-09-10  
Scope: authenticated web/PWA controls and the credential-free browser fixture matrix

## Outcome

Ask Crump's complete browser-control matrix is now a required CI step instead of an optional local
command. A change cannot pass the JavaScript job if any of the 38 exact browser flows fails.
Playwright is pinned in the development dependency lock, and CI installs the matching Chromium
runtime before exercising the matrix. The runner accepts an explicit browser only when that
executable exists on the current host; otherwise it uses Playwright's installed Chromium, so a
stale Windows browser path cannot break the Linux release gate.

The existing fail-closed source guard separately inventories every shipped button construction
site: 182 rendered buttons plus 94 programmatically created buttons, for 276 total. Every markup
button must declare its behavior type, every rendered control must have a bounded form or runtime
owner, and every dynamic control must have a direct or explicitly reviewed delegated click owner.
Adding or removing a button changes the locked inventory and requires review.

Release `3d1286a` also closes the final composer-state mismatch found during the live audit. Send
now has an authoritative browser `disabled` state, not only an accessibility label: it is disabled
for an empty composer, enabled by text or a visible attachment, disabled again when either is
removed, and reset immediately after a sent draft is cleared. The initial HTML is fail-closed while
the workspace scripts load. The browser fixture proves all five state transitions without sending a
message, uploading a file, starting generation, or touching production data.

## Live signed-in verification

A non-destructive production pass verified the visible outcomes for:

- all six primary destinations: Ask, Projects, Create, Video, Library, and You;
- Projects to Files, file filters, file search, pagination, and a foreground image preview;
- all five Settings sections and their close path;
- Intelligence effort and review choices, memory details, back, and close paths;
- the Add menu, Image Studio, every image ratio/quality selector, setup handoff, and composer-mode
  reset;
- Chats open/close, conversation options, rename/cancel, delete confirmation/cancel, and New
  conversation without creating a blank persisted chat; and
- the disabled-send state before input and the disabled precision-edit state before a reference
  image, both of which communicate their prerequisite instead of behaving like dead actions.

The live page exposed no browser-console error during this pass. No conversation was renamed or
deleted, no file was downloaded or uploaded, no generation was started, no checkout was opened,
and no account, campaign, or external communication was created.

## Automated evidence

- `tests/test_button_integrity.py`: all 25 tests passed.
- Full Python suite: 995/995 passed.
- JavaScript validation: 49 files passed, including 22/22 rough-to-useful attribution cases,
  10/10 Word/PDF cases, 10/10 resume cases, and the 14/14 store-packet self-test.
- Browser control matrix: 38/38 flows passed.
- `git diff --check`: passed.

GitHub CI run `34513572466`, Android source-verification run `34513572482`, and iOS
source-verification run `34513572465` all passed for `3d1286a`. Production deployment
`dpl_GoofjTHHJNQKcCy6ZymwcU6RTTrJ` is READY and current. A signed-in canonical replay loaded
`/crump-4.3.js?v=5.9.76-composer-actionability-1`, proved empty → typed → cleared state parity,
left the composer empty, and produced no browser-console error.

## Boundary

This gate proves browser interaction wiring and deterministic UI outcomes. Provider generations,
payment completion, destructive confirmations, native permission prompts, and exact signed iPhone
or Android behavior still require their separate legitimate-user or physical-device gates.
