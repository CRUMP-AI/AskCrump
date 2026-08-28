# Ask Crump 5.9.63 dedicated Library release

Date: 2026-08-28
Production version: 5.9.63
Feature commit: `4fc7b408d84e8a8addcdc83cd7231dc06d7f9351`
Production deployment: `dpl_H8AmzuGM8t6AvR1gVrZNNmPTYSeD`

## Outcome

Library previously referred to multiple surfaces. The top-level destination opened the shared
Projects/Create studio on a saved-files tab, the manuscript tab was renamed Library at runtime, and
the Files tool was intercepted as another saved-items shortcut. The result was redundant navigation
and two different product meanings for Library in addition to the separately named Chats control.

Production 5.9.63 makes Library one dedicated private destination. It contains the manuscript
bookshelf and saved documents, images, videos, exports, and uploads in one view. The shared workspace
tab is removed, Manuscripts keeps its own name and creation workflow, Files attaches a reference
file again, and Chats remains the separate conversation-history control.

## Scope and safety

- No Project, manuscript, file, conversation, account, or generated artifact was moved, renamed,
  copied, deleted, or migrated.
- File, manuscript, Project, and conversation ownership checks; storage; schema; RLS; authentication;
  synchronization; pricing; entitlements; credits; providers; analytics semantics; and payments did
  not change.
- The dedicated Library reuses the existing owner-scoped book and file sources. It changes their
  presentation and entry points, not the data model.
- Projects, Create, Manuscripts, Video, the document studio, and the existing editor/reader/export
  paths remain available.
- Production verification opened the owner's Library read-only and recorded structural counts only;
  it did not output titles, filenames, prompts, private content, or account identifiers.

## Verification

### Local contracts

- All 394 Python tests passed.
- Ruff passed across the backend and tests; backend compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight, native web bundle, store metadata, and signing-source checks passed.
- The expected Windows iOS-project gap and release-time reviewer, screenshot, privacy-form, billing,
  push, and signing gates remain unchanged; the hosted Android and iOS source gates passed.

### Isolated browser fixture

- Clicking the desktop Library destination opened one `Ask Crump Library` dialog, kept Library
  active, hid the shared workspace tabs, exposed exactly one visible panel, and reported zero browser
  errors.
- The dedicated panel contained both the manuscript bookshelf and saved-files grid, with no Library
  workspace tab remaining.
- Files exposed `Files: Attach a reference file`, invoked the fixture's attachment action exactly
  once, and did not open Library.
- Projects still opened the original workspace with its tabs and active destination; Create still
  opened the six-card non-generating creation hub.
- At a 390-by-844 viewport, the dedicated Library retained one visible panel, both content groups,
  and zero browser errors. Visual review confirmed a single-column, touch-sized layout.

### Hosted gates

- CI: [run 33204557657](https://github.com/CRUMP-AI/AskCrump/actions/runs/33204557657) — passed.
- Android store bundle: [run 33204557680](https://github.com/CRUMP-AI/AskCrump/actions/runs/33204557680) — passed.
- iOS store source: [run 33204557672](https://github.com/CRUMP-AI/AskCrump/actions/runs/33204557672) — passed.

### Production

- Git deployment `dpl_H8AmzuGM8t6AvR1gVrZNNmPTYSeD` reached READY on production and serves commit
  `4fc7b40`.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.63.
- The live app and all three changed navigation/Library assets returned HTTP 200 with the dedicated
  section, consolidated bookshelf, restored Files label, and removed Library workspace tab.
- The live service worker returned HTTP 200 with cache `ask-crump-new-body-v1-r97` and 5.9.63 assets.
- In the authenticated production shell, Library opened one dedicated dialog, exposed one visible
  panel containing both owner-scoped content groups, retained the active Library destination, and
  reported no browser error or warning.
- The live tool menu exposed Files as an attachment action and no longer contained the former
  `Open your private Library` alias.
- No Vercel runtime error cluster was reported in the inspected 30-minute release window.

## Outcome still to prove

The release verifies a clearer information architecture and working entry points. It does not yet
prove faster discovery, greater saved-artifact reuse, manuscript continuation, return behavior, or
retention. Those outcomes require legitimate post-release use and content-free aggregate evidence.
