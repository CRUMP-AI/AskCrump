# Conversation image node stability release — 2026-09-08

## Outcome

Generated images and uploaded image attachments now remain the same loaded browser nodes when an
unchanged conversation rerenders. Presence changes, streaming text, a newly completed response,
and history synchronization therefore no longer force an already visible photo to disappear and
repaint. Scrolling remains entirely user controlled.

## Defect and repair

The conversation renderer rebuilt every message row whenever presence or synchronized message
state changed. Although it restored the numeric scroll offset, it also recreated every generated
image. The richer attachment layer then removed and recreated every uploaded-image gallery in a
follow-up animation frame. Those two replacement paths explain the intermittent one-frame blink
reported on a stationary phone screen.

The renderer now indexes reusable image nodes by nonempty message ID. A generated-image wrapper is
reused only when its sanitized source URL is unchanged. Uploaded attachment galleries are retained
only while their ordered, content-free file identity signature is unchanged. A changed file gets a
new node; a removed file disappears; failed or invalid images still fail closed. Existing download,
open, edit, delivery, and feedback behavior is unchanged.

## Verification

- A real 390-by-844 browser proof kept the exact generated-image node through nine identity checks
  and the exact uploaded-photo node through six identity checks covering presence, completed reply,
  streamed text, history restore, and delayed image loading.
- The same proof replaced a changed uploaded reference, removed a deleted reference, recorded one
  network request per image, preserved `scrollTop=420` through every rerender, and reported zero
  console or page errors.
- The button-state, public account-entry, attachment routing, image-recovery, visual-media, Project
  save, Project output, and lifecycle Project-continuity browser verifiers all passed.
- The complete Python suite collected **904 tests**: **902 passed** and two environment-dependent
  tests skipped; there were no failures or errors.
- All **49 JavaScript files** and all six attribution cases passed validation. Ruff, Python
  compilation, production preflight, native web-bundle generation, and diff integrity also passed.
- Main CI run **34275320127**, Android verification run **34275320261**, and iOS source
  verification run **34275320046** completed successfully.

## Production evidence

- Feature commit: **50fb72572b74c91d91d32acfd40491d4356c678d**.
- Automatic production deployment: **dpl_34ASm4HCQjGzPGVJwUBWRpBQaPKk**.
- The deployment reached READY with all six configured aliases and no alias error.
- Exact live bytes for `ui-functions.js`, `crump-5.2.js`, `runtime-body-v1.js`, and `sw.js` matched the
  feature commit; the service worker advanced to cache `r223`.
- Canonical homepage, app, and API health returned HTTP 200.
- Deployment-scoped error/fatal and 5xx runtime-log queries were empty.

## Remaining device boundary

The deterministic browser proof covers the reported mobile viewport and both generated and uploaded
images, but it does not substitute for physical Safari/PWA compositor behavior. Reopen the affected
conversation on the reporting iPhone after the updated service worker activates and leave the image
stationary long enough to confirm the one-frame blink is gone. No activation, retention, or quality
lift is claimed from this reliability repair.
