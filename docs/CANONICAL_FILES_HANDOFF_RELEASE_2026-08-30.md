# Canonical Files handoff release — 2026-08-30

## Outcome

Ask Crump now presents one consistent signed-in product map: **Ask → Projects → Create → Library → You**. The retired **Saved** destination no longer appears in the launchpad, and a stale cached Saved control now opens **Projects → Files** instead of the books-and-manuscripts-only Library.

This removes a deterministic first-use and returning-user contradiction without changing customer data, authentication, billing, entitlements, or analytics semantics.

## Decision evidence

- The launchpad footer was the remaining visible signed-in surface that still taught the retired five-step sequence ending in Saved.
- The legacy `saved` compatibility branch still redirected into Library, contradicting the released destination contract.
- Library remains solely for manuscripts and books. Generated, uploaded, and saved files belong in Projects → Files.
- The shared Files entry is now safe from any caller: it opens Projects, selects the Projects panel, clears a stale deep Project route, selects Files, and refreshes the owner-scoped file list.

## Product contract

- Launchpad destinations: Ask, Projects, Create, Library, You.
- Legacy Saved controls: Projects → Files.
- Finished-video Files action: the same public Projects → Files entry.
- Library: manuscripts and books only.
- No production account, conversation, file, Project, artifact, event, checkout, or payment was created for verification.

## Verification

- 525 Python tests passed.
- All 45 JavaScript validation files passed.
- Production preflight passed.
- Native web-bundle build passed.
- Diff-integrity check passed.
- A credential-free real-runtime browser fixture opened Projects and then Files and proved:
  - the Files sheet and Projects panel were visible;
  - the Files card was visible;
  - the Library panel remained hidden;
  - no book or deleted-book request ran;
  - zero browser errors were recorded.
- A local app markup check proved the exact `AskProjectsCreateLibraryYou` sequence and no Saved destination.

## Production evidence

- Feature commit: `1b68591` (`Align Saved work with Projects Files`).
- Deployment: `dpl_Bdwc2GnxzfAq1hS25Av6XeZmmVEy`.
- State: `READY`, with all six production aliases attached.
- Canonical app: `https://www.askcrump.com/app`.
- Delivery: Vercel Functions / framework `other`; build completed in 12 seconds.
- Cache: `crump-cache-v5.9.76-r151`.
- Versioned runtime assets: `5.9.76-canonical-files-handoff-1`.
- All four public hosts returned HTTP 200 through the canonical app route.
- Live asset checks confirmed the canonical destination map, the Projects → Files legacy handoff, the public Files API, and cache `r151`.
- After deployment settlement, the exact deployment had no warning/error/fatal runtime log and no 5xx response; the observed grouped runtime requests were HTTP 200.

## Measurement boundary

Delivery and deterministic behavior are verified. Activation, reuse, retention, and revenue lift are not yet claimed; those require legitimate external user behavior rather than synthetic production activity.
