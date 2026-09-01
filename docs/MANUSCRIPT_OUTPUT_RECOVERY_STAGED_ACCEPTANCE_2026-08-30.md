# Manuscript output recovery staged acceptance

Date: 2026-08-30  
Status: accepted locally; not committed or deployed

## Outcome

A completed full-manuscript run can no longer lose its saved-export action
silently. Ask Crump keeps the run truthfully completed, distinguishes a
temporarily unavailable lookup from a confirmed missing export, and offers a
safe re-check only when that re-check can help.

## Defect closed

The manuscript route resolved `output_file_id` through the owner-scoped file
service but caught every exception and discarded it. A successful, potentially
credit-bearing manuscript therefore appeared complete with no download action,
no explanation, and no way to distinguish temporary infrastructure trouble
from a deleted or otherwise missing export.

## Staged behavior

- A successful lookup returns the existing private `outputFile` download.
- A temporary lookup failure returns a fixed `unavailable` recovery receipt and
  renders **Retry saved export**.
- The retry performs one authenticated GET for the existing manuscript run. It
  cannot start a run, call a model/provider, authorize a feature, consume a
  credit, recreate a file, or emit a synthetic activation event.
- A confirmed owner-scoped `FILE_NOT_FOUND` returns a fixed `missing` receipt,
  does not offer an automatic mutation, and explains that the manuscript
  remains saved. The user can deliberately use the existing export controls if
  they want a new export.
- A late retry result is ignored if the user has opened another manuscript.
- The recovery receipt contains only fixed status, code, message, and
  `shouldRetry` fields. It excludes manuscript text, filename, storage path,
  raw URL, account/file/manuscript identifiers, provider/model details,
  exception text, and arbitrary upstream data.
- At original acceptance, the changed product script used
  `5.9.76-manuscript-output-recovery-1`. The current shared worktree carries
  the later cumulative `5.9.76-video-project-recovery-1` cache key across web,
  service-worker precache, and native bundling. That later cache key does not
  broaden this manuscript release record or authorize the separate video
  recovery candidate.

## Verification

- Owner-scoped successful lookup is covered.
- Confirmed missing-file handling is covered and proves raw exception text is
  absent from the response.
- Unexpected/temporary lookup failure is covered and proves raw infrastructure
  detail is absent from the response.
- A source-level contract proves the retry uses only
  `GET /api/manuscripts/{id}/run` and contains no POST or run-creation path.
- Focused Python suite: 23 passed.
- JavaScript integration contract: 48 files passed.
- Full Python suite: 691 passed.
- JavaScript integration contract: 48 files passed.
- Production build preflight: passed. Its optional local Python compile guard
  did not discover the bundled runtime; the complete suite above executed with
  the bundled Python runtime.
- Native web bundle: regenerated successfully.
- Git diff integrity: passed, with only the existing `public/landing.js`
  CRLF-to-LF advisory.
- The connected desktop browser runtime remains unavailable because its sandbox
  helper fails before browser selection. No rendered-browser claim is made.

## Release boundary

No Supabase schema or migration, production manuscript/file/account write,
model/provider call, credit action, synthetic event, social publication, Search
Console action, price, plan, payment-provider setting, store submission,
lifecycle message, or spend changed. Commit and deployment remain a separate
action-time decision.
