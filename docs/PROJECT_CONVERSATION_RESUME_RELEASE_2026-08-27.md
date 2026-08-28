# Ask Crump Project conversation resume release

Date: 2026-08-27

Release: 5.9.31 / native build 50931

Code commit: `e67ff3bd654f9503ee89958ff4855cb8a99ac3b2`

Production deployment: `dpl_3FzSEnwGFXSTxh73AcdcXUD28U3t`

## Outcome

Work kept in a Project is now visible and resumable from that Project. Selecting an owned Project
loads a dedicated Conversations card with private titles and a clear Continue action. If the
conversation is not already present on the current device, Ask Crump first performs the existing
server-authoritative sync, confirms the conversation arrived, and only then opens it.

The new authenticated endpoint returns only conversation ID, private title, and created/updated
timestamps. It never returns prompts, replies, attachments, Project instructions, or file content.
Project ownership, conversation ownership, soft-deletion, and the existing authenticated session
remain required.

## Verification

- The local suite passed 306 backend and contract tests, Python lint, 41 JavaScript validations,
  production preflight, native web-bundle generation, store-metadata checks, mobile signing-source
  controls, and the Android 5.9.31/build 50931 source verifier.
- Hosted CI [33130217575](https://github.com/CRUMP-AI/AskCrump/actions/runs/33130217575), Android
  unsigned App Bundle verification [33130217571](https://github.com/CRUMP-AI/AskCrump/actions/runs/33130217571),
  and iOS unsigned Release compile [33130217560](https://github.com/CRUMP-AI/AskCrump/actions/runs/33130217560)
  all completed successfully. Neither native workflow had signing or upload credentials.
- Production health returned 5.9.31. The app shell, service worker, Project JavaScript, and Project
  styles returned 200 with the new resume markers. An unauthenticated Project-conversation probe
  returned the expected 401.
- An authenticated production Project rendered its two linked conversations on desktop and at a
  390-by-844 mobile viewport. Titles remained ellipsized, the count and Continue affordances were
  readable, and the existing Project files/canon controls remained intact. The Continue control was
  not clicked during the production audit so the release check would not create a synthetic
  `RecentWorkResumed` event; its sync-and-open behavior is covered by executable contracts.
- The inspected deployment reported no runtime error cluster. Its release window contained only
  informational logs, with 41 successful 200 responses and one expected 401 from the explicit
  unauthenticated ownership probe among the reported status groups.

## Safety and rollback

No schema, migration, entitlement, billing, Project limit, auth cookie, provider, or public route
changed. The previous verified production deployment remains a rollback candidate. The endpoint is
read-only and owner-scoped; removing the release restores the prior Project presentation without
changing stored Project/chat mappings.

## Remaining outcome gate

This release verifies the missing resume path, not improved retention. The comparable external
cohort remains empty, and the production audit deliberately did not generate a retention event.
Evaluate legitimate `RecentWorkResumed` observations and return behavior after external activated
accounts exist; do not claim a retention lift from owner testing.
