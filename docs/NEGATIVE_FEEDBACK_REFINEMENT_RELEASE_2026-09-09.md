# Negative feedback refinement release — 2026-09-09

## Outcome

A user who marks the latest Ask Crump result **Not yet** and selects an optional issue category
now receives a clear **Refine this result** action. The action returns focus to the existing message
box so the user can describe the correction instead of reaching a dead-end thank-you state.

Nothing is sent automatically. The action does not start generation, consume credits, create a new
conversation, change the selected tool, alter the existing draft, or move the conversation scroll
position. Its accessible name states that it opens a follow-up and sends nothing automatically.

The recovery remains available after the conversation rerenders in the same session. A missing
composer fails visibly and retryably instead of claiming success.

## Why this was the next product action

Production had four internal **Needs work** signals versus three internal **Useful** signals, but no
comparable external cohort. That evidence supports improving the negative-result recovery path; it
does not support another signup rewrite, price change, acquisition claim, or model-quality claim.
The preceding fixed-category release made future misses diagnosable without collecting customer
content. This release makes the same moment immediately recoverable without incurring cost.

## Automated acceptance

- The phone-width outcome verifier forces a failed category write, proves retry, saves a second
  category, renders the refinement action, activates it, and verifies that the composer receives
  focus with the exact unfinished draft preserved.
- A second conversation render proves the refinement action remains available from the saved
  content-free category state.
- The verifier confirms exactly the expected analytics calls, no extra send or network action, no
  overflow, and zero browser/fixture errors.
- The fail-closed source inventory now covers **181** rendered and **94** programmatically created
  buttons: **275 reviewed construction sites**.
- All **35/35** browser control verifiers passed, including Precision Edit live preview/apply,
  image stability, Files/viewers, Projects, Video references, Library, navigation, Settings,
  account entry, billing, lifecycle, attribution, and close/back/retry behavior.
- Full Python suite: **933 collected**, **931 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution cases passed.
- Ruff, Python compilation, production preflight, native web build, store metadata, native privacy
  verification, and diff integrity passed.

## Production identity

- Commit: `fbcfad10a1a06a3ef5d591ac03a3f99fb03f32d4`.
- Deployment: `dpl_DUFdhUmo8WhYKV9rHdPwGtYK5VWb` — READY on all six aliases with no alias error.
- Main CI `34381149730`, Android verification `34381149813`, and iOS source verification
  `34381149755` completed successfully.
- Canonical `/api/health`, `/app`, runtime loader, `ui-functions.js`, and service worker returned
  HTTP 200; the live runtime, UI script, and worker expose the exact
  `outcome-refinement-recovery-1` marker.
- The first post-release runtime-error and deployment-scoped HTTP 5xx queries were empty.

## Evidence boundary

This proves deterministic recovery behavior and production delivery, not that negative outcomes
are resolved, model quality improved, or retention increased. The first legitimate category →
manual refinement → useful result → Project/artifact → return journey remains the outcome gate.
Physical-device, provider, permission, and payment states retain their separate release gates.
