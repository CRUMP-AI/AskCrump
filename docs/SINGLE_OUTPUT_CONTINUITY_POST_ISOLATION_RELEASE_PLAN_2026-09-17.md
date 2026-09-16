# Single-output continuity post-isolation release plan — 2026-09-17

Status: **PREPARED / NOT AUTHORIZED BEFORE THE ISOLATION BOUNDARY**

## Candidate

- Current production source: `7833d89e2e5ee419fd27757f82c4fff92beed295`
- Held product commit: `9ad93c89fa71c48583266a12f164d862f1264cd4`
- Held branch: `candidate/artifact-continuity-dedupe-20260916`
- Evidence: `docs/SINGLE_OUTPUT_PROJECT_CONTINUITY_CANDIDATE_2026-09-16.md` in the candidate worktree
- Independent Marketing receipts:
  - `measurement/SINGLE_OUTPUT_PROJECT_CONTINUITY_SOURCE_ACCEPTANCE_2026-09-16_1457.md`
  - `measurement/HELD_CANDIDATE_PAIRWISE_MERGE_AUDIT_ACCEPTANCE_2026-09-16_1459.md`

The candidate changes one product outcome: generated documents and images expose one complete
Project action that preserves output plus source conversation and becomes **Open Project** after a
successful save. It removes the redundant conversation action for those outputs and fixes the image
action remaining stuck on **Saving…**. Ordinary responses retain their conversation-level action.

## Earliest decision point

Do not release before the Facebook isolation boundary at **2026-09-17 13:28 EDT**. At or after the
boundary:

1. Record legitimate Facebook exposure/reach evidence and the exact server-authoritative campaign
   tuple result.
2. Confirm the post, Featured state, distribution variables, and spend remained unchanged during
   the full window.
3. Confirm production reliability has no active runtime-error or 5xx cluster.
4. Separate campaign interpretation from the product-quality decision. Under-distribution is not a
   reason to redesign registration; the output-action fix is a verified reliability correction,
   not a campaign optimization.

## Source gate

1. Fetch without modifying the preserved dirty primary workspace.
2. Resolve current production from `origin/main` and the live deployment—not from local `main`.
3. If production still equals `7833d89`, use the already validated candidate directly.
4. If production advanced, create a fresh clean worktree from the exact new production commit and
   cherry-pick `9ad93c8`; do not merge from the dirty primary workspace.
5. Keep draft-to-clearer, resume-you-can-defend, Search Console, API, store, and campaign migrations
   outside this release. Pairwise compatibility does not authorize bundling them.

## Required validation on the exact release tree

- clean worktree and `git diff --check`;
- complete Python suite;
- focused Project, button-integrity, lifecycle, and asset-version tests;
- JavaScript integration contract and exact cache/version guards;
- complete browser-control matrix in installed Edge;
- explicit eight-case output matrix: desktop/phone × existing/new Project × document/image;
- production build preflight and native web bundle;
- client-secret boundary;
- current lockfile/package parity; and
- current hosted CI, Android Java 21 source/build verification, and iOS macOS source verification.

Every explicit output case must show exactly one output Project action, one offer impression, one
intent, ordered conversation/file requests, the correct generated output role, immediate **Open
Project**, exact destination reopening, retained feedback, and zero browser, fixture, or unexpected-
request errors.

## Release and observation

1. Commit only the exact product candidate plus any mechanically required then-current cache/test
   reconciliation.
2. Push the release commit and allow the normal production deployment path.
3. Require Ready state on every production alias.
4. Verify `/api/health`, `/app`, the runtime loader, both changed UI scripts, and the service worker
   return the exact committed bytes and new cache/version markers.
5. Run a signed-in, non-destructive smoke across ordinary response feedback, generated document
   Project save/open, generated image Project save/open, Projects, Files, and foreground preview.
6. After settlement, inspect grouped runtime errors, explicit 5xx, and warning/error/fatal logs.
7. Preserve the release if healthy; do not claim adoption lift until legitimate offer → intent →
   completion → later resume evidence exists.

## Rollback

If deployment, parity, signed-in smoke, or early production monitoring fails:

1. restore the prior exact production deployment/source `7833d89` (or the exact pre-release
   production commit if it advanced before release);
2. verify all aliases and health endpoints return to that exact source;
3. confirm the prior runtime/cache markers are restored;
4. recheck runtime errors and 5xx after settlement; and
5. keep the candidate isolated for diagnosis without changing the campaign or database.

No database rollback is required because this candidate contains no migration or schema change.
