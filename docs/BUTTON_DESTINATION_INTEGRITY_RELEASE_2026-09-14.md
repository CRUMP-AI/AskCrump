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
