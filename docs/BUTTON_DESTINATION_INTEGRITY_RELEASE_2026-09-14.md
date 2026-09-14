# Ask Crump button-destination integrity release — 2026-09-14

## Decision

Keep the complete fail-closed control inventory and add an exact browser proof for the launchpad's
Continue action. A control is not accepted merely because its click handler runs: its visible label,
bound conversation, and actual destination must agree.

## Production finding

A signed-in production walkthrough found a long-lived tab with an available runtime update. In that
stale state, Continue appeared operable but did not change the conversation. After the waiting update
was applied, Continue opened the exact conversation named on the card and the visible Chats rows
opened their exact conversations.

The walkthrough used existing fixed fictional quality-assurance conversations. It did not create or
change a prompt, response, conversation, Project, file, media job, feedback record, analytics event,
subscription, checkout, or provider action.

## Change

Continue still uses the canonical conversation navigator first. If a long-lived PWA shell briefly
has the launchpad but not that exported navigator, it now activates the already-bound Chats row with
the same conversation ID. If neither route exists because the conversation is still syncing, the app
shows a truthful retry message and refreshes the card instead of silently doing nothing.

The service-worker cache advances to `r242`. The workspace loader and launchpad script use the
`5.9.76-recent-work-recovery-1` revision so returning PWAs receive the recovery path together.

## Verification

The new real-browser fixture deliberately omits the direct navigation export, presents two eligible
conversations, and proves that the card names and opens the newer one through the fallback without a
toast or extra analytics payload. The complete fail-closed browser inventory now contains 48 exact
verifiers.

Local release validation passed:

- browser-control matrix: **48/48**;
- complete backend suite: **1,063/1,063**;
- JavaScript validation: **54/54**;
- accessibility matrix: **33/33**;
- production build and native web bundle; and
- client credential boundary and diff integrity.

## Boundary

This release establishes executable coverage for every inventoried control and repairs the observed
Continue no-op recovery case. It does not claim that every possible provider response, network
failure, browser extension, or future dynamically introduced control is defect-free. The inventory
guard fails whenever a new verifier is added or removed without an explicit test update.

## Production closure

Commit `c78f792` passed GitHub CI `34869867352`, Android bundle verification `34869867351`,
and iOS source verification `34869867340`. Production deployment
`dpl_dXTeo5yw4rQa6PSLkiTeNvBihRiB` reached Ready on all six aliases with no alias error.

The live app, runtime loader, launchpad script, and service worker returned HTTP 200 and exposed the
same `5.9.76-recent-work-recovery-1` / `r242` asset chain. The deployed 22,654-byte launchpad script
is byte-identical to the commit at SHA-256
`a701a77d6670710d317496cbca2e254e7dbff02d2c49250167425e56e2f2ce38`.

A signed-in production replay opened Continue from the clean workspace. The visible card label and
the active Chats-row title matched exactly, the conversation rendered, and the browser log remained
empty. The initial exact-deployment error view was empty. This replay only opened an existing fixed
fictional quality-assurance conversation; it did not create work, spend credits, invoke a provider,
or change account data.
