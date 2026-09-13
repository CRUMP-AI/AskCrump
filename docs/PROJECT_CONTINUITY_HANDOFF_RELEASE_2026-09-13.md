# Project continuity handoff release — 2026-09-13

## Outcome

Ask Crump now presents the result-to-Project action as a distinct continuation
card instead of placing it on the same cramped line as response feedback. The
card says **Continue this work later**, explains that the conversation is kept
in a private Project, and uses the explicit action **Keep in a new Project** when
no Project is selected. Existing-Project saves still name their exact target.

This change addresses a repeated adoption signal without inventing a broken
backend: three external accounts have completed 17 successful AI jobs, but none
has created a Project or retained a file. The prior action worked in deterministic
tests, yet it visually competed with Yes/Not yet feedback. The release changes
the hierarchy and clarity while preserving the established behavior and
measurement boundaries.

## Preserved behavior

- Project creation remains a deliberate user action; no save or navigation is
  automatic.
- A selected Project remains the exact destination.
- Pending state remains **Saving…** with an accessible busy state.
- A failed save restores an actionable button and confirms that the conversation
  is still present.
- A successful save becomes **Open Project** only after the server returns the
  created or selected Project.
- `ProjectSaveIntentReached` remains the content-free client intent signal, and
  `ProjectSaveCompleted` remains server-authoritative.
- Feedback and referral actions remain available in their own rows.
- No provider run, credit spend, payment, destructive action, upload, download,
  customer-content read, or production Project creation was used for release
  verification.

## Verification

- The complete Python suite passed 1,004/1,004.
- JavaScript validation passed 54/54 files.
- The browser control matrix passed 45/45 verifiers.
- The Project-save browser fixture proved desktop and 390-by-844 layouts, a
  44-pixel mobile touch target, no horizontal overflow, pending state, bounded
  timeout recovery, successful save, exact request body, analytics, and zero
  console errors.
- Production build preflight, native web-bundle creation, client-secret
  boundary, and source privacy verification passed.
- Deployment `dpl_8RYr19eastRvuaDNHUt2zD4foNHB` is Ready.
- CI `34775266061`, Android source/bundle verification `34775266130`, and iOS
  source verification `34775266095` passed.
- Production `/api/health` returned HTTP 200 with version 5.9.76.
- The deployed app shell, runtime loader, conversation stylesheet, UI renderer,
  and service worker matched the committed SHA-256 bytes.
- Signed-in production inspection showed the new card and all three Project and
  feedback buttons inside the existing fictional QA conversation after the
  update was applied. The Project button was not clicked in production.
- The first 30-minute post-release runtime-error query was empty.

The local store-submission gate remains correctly closed because Android/iOS
platform projects, native billing keys, signed artifacts, screenshots, reviewer
access, and founder action-time approval are separate unfinished gates. Those do
not block this web/PWA release.

## Decision boundary

This release proves a clearer and functional control, not an adoption or
retention lift. Keep the interface stable and observe legitimate
`ProjectSaveIntentReached` and `ProjectSaveCompleted` events, later Project
resume, and eligible D1/D7 behavior before making another continuity change or
scaling acquisition.
