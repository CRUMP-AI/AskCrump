# Project-save measurement contract release — 2026-09-01

## Outcome

Ask Crump can now distinguish three different parts of durable-work continuity without inspecting
customer content:

1. `ProjectSaveIntentReached`: the authenticated client observed a user select the one-click
   result-to-Project action.
2. `ProjectSaveCompleted`: the server successfully created a Project from that conversation or
   attached it to an owned Project.
3. `RecentWorkResumed` with source `project`: the user later continued a saved conversation from
   its Project workspace.

`StarterIntentReached` is again reserved for the launchpad's first task-category choice. The
release therefore prevents a save click from being misread as launchpad intent, a completed save,
activation, retention, or revenue.

## Authority and privacy boundaries

- The client may submit only `ProjectSaveIntentReached` with fixed key `project-save-intent`, source
  `new_project` or `existing_project`, and no plan.
- The Project request carries only the fixed `result_action` marker; arbitrary values are rejected.
- Only the server emits `ProjectSaveCompleted`, after ownership-checked Project creation or
  attachment succeeds. The event uses fixed key `result-action-save` and a bounded Project source.
- Analytics failure remains fail-open and cannot block or falsify the user's Project save.
- The service-role-only `product_project_continuity_snapshot` returns grouped counts and rates by
  allowlisted immutable first-touch attribution. It exposes no user ID, email, Project or
  conversation identifier, Project name, title, prompt, response, file, filename, URL, referrer,
  customer content, or arbitrary metadata.
- Browser intent and server completion are paired when both exist, regardless of millisecond
  arrival order. A later Project resume must occur at or after the confirmed completion.
- The aggregate is an observed-to-date diagnostic. It is not D1/D7 retention and does not prove
  product lift.

## Database release

- Migration: `20260901190546_project_save_intent_measurement`
- Function: `public.product_project_continuity_snapshot`
- Security: `SECURITY INVOKER`, empty `search_path`
- Execute privilege: `postgres` and `service_role` only; `public`, `anon`, and `authenticated` are
  revoked
- Cohort boundary: exact `users.registration_environment`, non-deleted and non-internal by default,
  with the existing first-comparable-event lower bound
- Post-apply result: no comparable external production row yet; no event or Project was created to
  manufacture evidence
- Post-DDL advisors: no new lint class or warning tied to the migration or function

## Verification

- All **779 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Ruff, explicit Python compilation, production preflight, native web-bundle creation, store
  metadata, mobile signing-source controls, and diff integrity passed.
- The SQL function created, executed, and returned a content-free empty result inside a rolled-back
  remote preflight transaction before the real migration was applied.
- A 390×844 browser proof exercised the real Project-save runtime. The stalled path displayed
  **Saving…**, preserved the conversation, restored **Start a Project**, sent the fixed marker, and
  recorded one bounded intent. The success path displayed **Open Project**, named the private
  destination, sent one request, and produced no unexpected request or console error.
- The applied event constraint accepts both new events. The live function is invoker-safe with an
  empty search path and only `postgres`/`service_role` execute privileges.
- The five changed public assets matched the exact committed SHA-256 bytes in production.
- `/api/health` returned HTTP 200 and version 5.9.76.
- The settled production window contained no warning/error/fatal log and no runtime-error cluster.
  One deliberate mistargeted `/health` verification request returned 404; the canonical
  `/api/health` request returned 200.

## Release identity

- Feature commit: `e32acbf8bef272e7a5cb23fc3ca5cb71a036701e`
- Production deployment: `dpl_Nro1aexyWdhM49nQzJssMRMCwieE`
- Status: `READY`
- Build duration: about 46 seconds
- Canonical aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and both Vercel production aliases

## Remaining acceptance work

1. Observe legitimate external Project-save intent and server completion; investigate either
   missing-side diagnostic before changing acquisition.
2. Follow completed saves through later Project resume and eligible D1/D7 return. Do not infer
   retention from an observed-to-date resume rate.
3. Repeat save, recovery, open, and later resume on exact signed iPhone and Android candidates before
   store screenshots or physical-device reliability claims.
