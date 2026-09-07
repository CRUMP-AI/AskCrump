# Precision Edit complete workflow release — 2026-09-07

## Outcome

Ask Crump's Precision Edit Studio now completes the previously gated photo-editing workflow with
real crop and 90-degree rotation, a resettable frame, feathered manual selections, and a visible
private version history. Every applied edit creates a new owner-scoped file; the source is never
overwritten.

The release does not add person recognition, automatic subject selection, or a race/ethnicity
classifier. It does not expose a detect/change-race control. Visible-tone guidance remains explicit,
manual, reviewable text, and exact logos or readable text stay on the deterministic overlay path
instead of being redrawn by a model.

## User workflow

- **Crop** supports a manually drawn frame plus Free, 1:1, 4:5, and 16:9 starting frames.
- **Rotate left**, **Rotate right**, and **Reset frame** are provider-free and available before
  selection, appearance, or overlay work so later masks cannot drift from the working image.
- **Edge feather** softens the alpha boundary of a user-painted or lassoed selection from 0–3% and
  is reflected in both the live local preview and the protected AI-edit mask.
- **Versions** shows the connected Original, Local edit, Crop or rotation, and AI edit lineage. An
  earlier version can be opened as a new editing source without mutating any version.
- **Apply changes** persists geometry, local appearance, and exact overlays as one private,
  provider-free PNG with zero Crump Credits.
- **Continue with AI edit** first persists any unsaved geometry/local composition as a free private
  source version, then hands the matching source dimensions and transient mask to the existing
  server-authoritative credit-confirmation flow.

## Server and privacy boundary

The server accepts at most eight content-free geometry operations. Only -90, +90, and 180-degree
rotations and normalized in-bounds crops are valid; crops must remain at least 32×32 pixels. The
server replays geometry against the authenticated source before validating mask and overlay
dimensions. Stable file identity includes the source, bounded mask, bounded adjustments, exact
overlay raster, and normalized geometry operations, making retries safe without overwriting the
source.

Version history is assembled from the authenticated account's connected `sourceFileId` lineage.
It returns public file receipts and allowlisted edit labels only; storage paths, prompts, masks,
overlay source pixels/text, credentials, and unrelated image branches are excluded. No database
migration was required.

## Validation and release evidence

- Feature commit: `e8c6729`.
- Main CI: [34161563921](https://github.com/CRUMP-AI/AskCrump/actions/runs/34161563921).
- Android Store Bundle Verification:
  [34161563983](https://github.com/CRUMP-AI/AskCrump/actions/runs/34161563983).
- iOS Store Source Verification:
  [34161563941](https://github.com/CRUMP-AI/AskCrump/actions/runs/34161563941).
- Production deployment: `dpl_8CXBoL1QxtzdNuUu1sjhnDff9HXe`, READY on all six aliases with no
  alias error.
- All 845 Python tests were collected; 843 passed and two environment-gated tests skipped. All 49
  JavaScript validations, changed-file Ruff, Python compilation, production preflight, native web
  build, and diff integrity passed.
- The real desktop/mobile browser fixture exercised rotate, reset, 4:5 crop, save, version history,
  Brush/Lasso/Erase/Move/Place, invert, Undo/Redo, feather, all three live sliders, compare/reset,
  exact image/text overlays, AI handoff, focus return, Escape, containment, and horizontal-overflow
  checks with zero console or page errors.
- Production `/app` and `/api/health` returned HTTP 200. The live versioned script SHA-256 was
  `9931b3065ac5641e1cedbf54ca140f2254a8ad7d0790aabadf66fb910c27dcd9`; the stylesheet was
  `dc603fc261deaf7116075f859d7812e2e2aaf211da4c61d662984771516b516d`. Both matched the committed
  files byte for byte.
- The inspected deployment window had no grouped runtime error and no warning/error/fatal log.

No live image, customer file, conversation, Project, analytics event, credit, provider request,
payment object, entitlement, or database row was created or changed during production verification.

## Remaining acceptance work

1. On the exact signed iPhone and Android candidates, complete touch, software-keyboard,
   VoiceOver/TalkBack, crop/rotate/save/reopen/download, and interrupted-network recovery checks.
2. With a founder-approved rights-cleared fictional or consented fixture, prove one local save and
   one paid provider edit, including the pre-render quote, idempotent charge, protected-pixel
   comparison, and version reopen. Use a stricter benign-edit boundary for any image of a minor.
3. Keep claims about precision, identity preservation, and exact-logo fidelity private until those
   signed-device and legitimate-provider acceptance checks pass.
