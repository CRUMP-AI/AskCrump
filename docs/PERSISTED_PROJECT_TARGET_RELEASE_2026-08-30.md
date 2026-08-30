# Persisted Project-target release — 2026-08-30

## Outcome

Ask Crump now restores the last selected owned Project for the post-answer continuity action after a reload. An unsaved conversation can return to **Keep in “Project name”** without requiring the person to open Projects first, while a conversation that is already saved continues to resolve to **Open Project** and remains authoritative.

This closes a deterministic continuity gap that could show **Start a Project** after reload and create an unintended duplicate workspace even though the browser still remembered the intended Project.

## Product, privacy, and startup contract

- Conversation-to-Project recognition runs first. An existing owner-scoped relationship always wins and skips remembered-target lookup.
- Only an unsaved conversation may restore the stored target.
- The new authenticated target route is owner-scoped and returns only Project ID and name. It does not return descriptions, instructions, context, files, conversations, users, analytics, or billing data.
- The remembered target is not activated as conversation context. Opening it still performs the normal full owner-checked Project workspace load.
- Multiple post-answer actions coalesce the same pending target request.
- A Project selected while restoration is pending wins the race and is not overwritten by the older stored value.
- A missing, stale, unauthorized, timed-out, or unavailable target fails safely to the existing **Start a Project** action. The stored choice is not erased by a transient failure.
- Generic authenticated startup still does not fetch the Projects list, Library, Create availability, or Project Files. The minimal target request occurs only when a rendered post-answer action needs it.

No authentication, chat creation, message, Project, file, manuscript, generation, payment, subscription, entitlement, analytics, database schema, storage, or provider behavior changed.

## Verification

- All 526 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Ruff passed across the backend and tests; its optional local cache could not be written, but the lint result was clean.
- Production preflight passed.
- Native web-bundle creation passed.
- Store-metadata source validation passed.
- Diff integrity passed.
- A credential-free real-runtime browser fixture proved:
  - a slow relationship check immediately displayed **Checking Project…**, disabled the action, and set `aria-busy="true"`;
  - an unsaved reload restored **Keep in “Q3 Finance Forecast”** after exactly one relationship lookup and one minimal target lookup;
  - choosing that action saved to the exact restored Project and transitioned to **Open Project**;
  - an already-saved conversation resolved to **Open Project**, skipped remembered-target lookup, opened the exact workspace, and made no save request;
  - no remembered target retained **Start a Project** and created exactly one new Project;
  - stale and unavailable targets retained an enabled **Start a Project** recovery action;
  - every branch recorded zero browser errors and no warning/error console entry.
- The temporary browser tab and localhost server were closed after verification.
- No production account, login, signup, conversation, Project, file, generation, event, checkout, payment, subscription, or other customer record was created for verification.

## Production evidence

- Feature commit: `1f11cbd` (`Restore persisted Project targets on demand`).
- Deployment: `dpl_GWmhVMeNLZ3fW5BGjvR88zd6o5qE`.
- State: `READY`, with all six production aliases attached and no alias error.
- Canonical app: `https://www.askcrump.com/app`.
- Delivery: Vercel Functions / framework `other`; Vercel reported **Build Completed** in 13 seconds and the immutable deployment reached `READY` in about 47 seconds.
- Cache: `ask-crump-new-body-v1-r153`.
- UI and Project runtimes: `5.9.76-persisted-project-target-1`.
- All four public hosts returned HTTP 200 through their canonical destinations.
- Health returned HTTP 200 and version `5.9.76`.
- Live loader, service worker, UI runtime, and Project runtime returned HTTP 200 with the exact release boundary, resolver, and minimal target route.
- An unauthenticated request to the target route returned the expected HTTP 401 boundary.
- More than 60 seconds after `READY`, the exact deployment had no runtime-error cluster, warning/error/fatal runtime log, or 5xx response. The build-log query contained no build failure; its only warning was Vercel's non-blocking package-cache hardlink fallback before the successful build completion.

## Measurement boundary and rollback

The continuity correction, privacy boundary, startup boundary, and production delivery are verified. Project adoption, return behavior, retention, and revenue lift remain unclaimed until legitimate external behavior exists.

Rollback is the preceding verified deployment. Reverting `1f11cbd` removes only the lazy remembered-target resolver, minimal authenticated summary route, and cache/version updates; it does not migrate or delete conversations, Projects, files, accounts, entitlements, events, or payments.
