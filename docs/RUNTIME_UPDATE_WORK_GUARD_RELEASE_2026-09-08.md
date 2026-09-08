# Runtime update work guard release — 2026-09-08

## Outcome

Ask Crump no longer places a reload action over active work. Runtime updates now wait while a person is:

- typing or submitting account-entry information;
- writing an unsent conversation draft;
- holding a file ready to send;
- using Precision Edit;
- sending a message; or
- waiting on a visible busy app control.

If an update notice is already visible and work begins, the notice withdraws immediately. The reload handler also rechecks the same boundary at click time, so the action cannot race an editor opening. Once the work is cleared or safely closed, the update notice returns. A deliberately dismissed notice stays dismissed for that page session.

Untouched signed-out entry remains fast: the existing one-time safe refresh still occurs when there is no entered value, selected consent, selected file, draft, editor, upload, or in-flight action.

## Evidence that selected the work

A read-only production inspection found an older cached workspace displaying the runtime update notice at the same time as an open Precision Edit surface. The currently deployed source already contained the whole-image local-adjustment preview and **Apply changes** behavior, so changing the editor again would have treated stale client state as a source defect. The bounded fix instead protects every later update transition from interrupting work.

No image, conversation, file, account, analytics event, provider job, credit, entitlement, checkout, or customer data was changed during the inspection.

## Implementation

- Feature commit: `8c709d5a5a9ebe6ff92182fa41af6f0854127669`.
- Production deployment: `dpl_8dYAkwQJ1zsRpuo3eMZzUDqapM9t`.
- Deployment target: production, sourced from `main`, READY on all six aliases.
- Service-worker cache revision: `ask-crump-new-body-v1-r220`.
- Runtime guard asset: `/install-prompt.js?v=5.9.76-update-work-guard-1`.

The implementation is client-only. It adds no database migration, API shape, storage write, provider call, analytics field, billing behavior, entitlement rule, or new permission.

## Automated and browser verification

- Full Python suite: 873 collected; 871 passed and two environment-dependent tests skipped.
- JavaScript release contract: 49 files passed, including all six attribution runtime cases.
- Ruff: passed.
- Python compileall: passed.
- Production build preflight: passed.
- Native web bundle: passed.
- Diff integrity: passed.
- Main CI: `34245847374`, passed.
- Android store bundle verification: `34245847352`, passed.
- iOS store source verification: `34245847386`, passed.

The credential-free 390-by-430 browser fixture covered eight update states:

1. untouched signed-out entry reloaded exactly once;
2. typed email remained intact with no notice or reload;
3. checked consent remained intact with no notice or reload;
4. an unsent composer draft remained intact with no notice or reload;
5. a queued file remained intact with no notice or reload;
6. an open Precision Edit surface remained intact with no notice or reload;
7. an in-flight send remained intact with no notice or reload; and
8. work started after the notice appeared withdrew the notice and blocked the reload handler itself.

Every deferred state exposed the update only after work cleared. Every scenario had zero browser errors.

## Production verification

- `/app?release_probe=update-work-guard-1`: HTTP 200 with the exact versioned guard reference.
- `/install-prompt.js?v=5.9.76-update-work-guard-1`: HTTP 200 with the committed work boundaries and click-time recheck.
- `/sw.js`: HTTP 200 with cache revision `r220` and the exact guard URL.
- `/api/health`: HTTP 200, `Cache-Control: no-store`, service `Ask Crump`, version `5.9.76`.
- The deployment-scoped warning/error/fatal log query was empty.
- The post-release runtime-error cluster query was empty.

One initial verification request used `/health` and correctly returned 404; the canonical `/api/health` request returned 200.

## Rollback and remaining boundary

Rollback is the prior production commit `5fb4d2dd131980558bc2bc6815d59b6c0d5a408d`, cache revision `r219`, and `auth-update-guard-1` asset reference.

An already-open stale tab must still complete or close its current work before deliberately adopting the new runtime. The new guard protects subsequent update transitions; it cannot retroactively replace JavaScript already executing in that tab. Repeat this transition on exact signed iPhone and Android candidates before store submission.
