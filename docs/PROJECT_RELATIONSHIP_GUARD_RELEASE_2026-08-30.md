# Project relationship guard release — 2026-08-30

## Outcome

Ask Crump now prevents the post-answer Project action from running until the owner-scoped relationship lookup determines whether that conversation is already saved. During the lookup, the action is disabled, marked busy, and labeled **Checking Project…**. It then becomes either the existing **Open Project** action or the correct unsaved **Start a Project** / **Keep in …** action.

This closes a deterministic race that could let a fast click on a slow connection use the last active Project before Ask Crump recognized the conversation's actual saved Project.

## Evidence and decision

- The live signed-in workspace displayed the durable-value action directly beneath the latest useful response.
- Source inspection showed that the asynchronous `projectForConversation` request set only an internal pending flag; the visible save action remained enabled while its temporary target could still be stale.
- Relationship recognition is owner-scoped and intentionally fail-open. The fix does not alter that API, Project ownership, conversation persistence, analytics, billing, entitlements, or chat content.
- The post-answer action now becomes unavailable before awaiting the lookup and restores its prior disabled/busy state after success or failure.
- A production-preflight guard enforces the disabled-before-lookup ordering and safe restoration.

## Verification

- All 525 Python tests passed.
- All 45 JavaScript files passed validation.
- Production preflight passed.
- Native web-bundle creation passed.
- Diff integrity passed.
- A credential-free real-runtime fixture delayed the relationship response by 1.6 seconds and proved:
  - the action immediately displayed **Checking Project…**;
  - the action was disabled with `aria-busy="true"` before the response settled;
  - an interaction begun during the delay waited for relationship recognition;
  - an already-saved conversation sent no save request and opened **Q3 Finance Forecast**;
  - an unsaved conversation retained its existing save/create behavior after the lookup;
  - exactly one relationship lookup ran in each branch;
  - zero browser errors were recorded.
- No production account, conversation, Project, file, event, checkout, payment, or other customer record was created for verification.

## Production evidence

- Feature commit: `1b25f26` (`Guard Project saves during relationship lookup`).
- Deployment: `dpl_EtYhTupsSj6SMeZxVLCst79AYQJi`.
- State: `READY`, with all six production aliases attached and no alias error.
- Canonical app: `https://www.askcrump.com/app`.
- Delivery: Vercel Functions / framework `other`; build completed in 9 seconds.
- Cache: `ask-crump-new-body-v1-r152`.
- UI runtime: `5.9.76-project-relationship-guard-1`.
- All four public hosts returned HTTP 200 through the canonical app route.
- Live loader, service-worker, and UI source checks confirmed the exact version, cache, disabled-before-lookup order, busy state, and safe restoration.
- More than 60 seconds after `READY`, the exact deployment had no warning/error/fatal runtime log and no 5xx response; the observed grouped request was HTTP 200.

## Measurement boundary and rollback

The race correction and production delivery are verified. Durable-value, activation, retention, and revenue lift remain unclaimed until legitimate external behavior exists.

Rollback is the preceding verified deployment. Reverting `1b25f26` removes only the pending relationship guard and cache/version updates; it does not migrate or delete conversations, Projects, files, accounts, entitlements, or events.
