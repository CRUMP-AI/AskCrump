# Ask Crump 5.9.52 private Project handoff recovery release

Date: 2026-08-28  
Production version: 5.9.52  
Code commit: `bde31da17caf5c91e62627f1b6e6130f72d162f9`  
Production deployment: `dpl_8mYEDxe4uVoEEUCy5qKt8UjMDBrx`

## Outcome

The primary post-result `Keep in a Project` action can no longer remain disabled forever when the
Project create or attach response stalls. The request is bounded through response parsing, the
action becomes available again with truthful retry guidance, and a successful save is confirmed
without waiting for a secondary Project-list refresh.

A retry after an uncertain create response is also safe. The server reuses the newest active owned
Project that already contains the conversation instead of creating a duplicate, including when the
first request brought the user to the plan's Project limit. The successful action now exposes the
accurate accessible name `Open the Project containing this conversation`.

This verifies delivery of the current durable-value boundary. It does not prove a higher Project
conversion or return rate; that still requires legitimate external use and later return.

## Reproduced failure

A credential-free loopback browser fixture loaded the real result renderer and Project runtime,
completed chat synchronization, and left the following `POST /api/projects` response pending.
Before the correction:

- the fixture issued one Project save request;
- `Keep in a Project` remained disabled after the test interval;
- the request had no abort signal;
- no status or retry path appeared; and
- the user's useful result could not move into the durable workspace.

The fixture used only `fixture-user`, two synthetic UUIDs, local HTML, and an intercepted loopback
request. It contained no password, production hostname, real account, or external write.

## Correction

- Added an optional request boundary to the existing product transport and applied a 15-second
  boundary specifically to conversation-to-Project create and attach calls, including JSON body
  parsing. Longer manuscript and video operations retain their existing behavior.
- Converted a local timeout into clear retry guidance and restored the result action in its existing
  `finally` path.
- Moved the nonessential Project-list refresh behind the success confirmation so a secondary read
  cannot delay or hide a completed durable save.
- Added an owner-scoped service lookup over `project_chats` and active `projects`. A create retry
  returns that existing Project instead of inserting another row.
- Allowed that idempotent retry through the existing plan-limit gate while preserving the limit for
  every genuinely new Project.
- Kept Project ownership, chat ownership, private mappings, authentication, RLS, pricing,
  entitlements, and the content-free `AhaReached:first-durable-project` milestone unchanged.

## Full-story verification report

**Story:** a signed-in user chooses `Keep in a Project` on a useful response, the browser first
persists chat state, the Project API creates or attaches the owned conversation, the private mapping
becomes durable, and the same result action confirms the Project and becomes an accessible resume
action.

| Boundary | Status | Evidence |
| --- | --- | --- |
| UI trigger | Passed | The real result renderer exposed one `Save this private conversation in a Project` button. |
| Client → API | Passed | The stalled fixture issued one Project POST with an abort signal; the corrected interval produced one abort, restored the button, and a second click produced a second recoverable attempt. |
| API route | Passed | Route coverage proves an uncertain-response retry at the three-Project plan limit returns the existing owned Project and does not call the create path. |
| API → data | Passed | Service coverage proves the lookup filters both mapping and Project rows by owner, conversation, active state, and Project ID, and performs no Project insert when a mapping already exists. |
| Data → response | Passed | The route returns the existing Project with `conversationSaved: true` and records the existing idempotent, content-free durable-value milestone. |
| Response → UI | Passed | The success fixture rendered `Saved to "Launch plan"`, exposed one accurately named `Open the Project containing this conversation` action, showed no error overlay, and recorded zero browser errors. |

The visual check showed meaningful rendered content rather than a blank page. The loopback server
served the fixture and exact runtime assets successfully; its only 404s were optional fixture
`favicon.ico` and root `sw.js` requests, neither of which affected the isolated product flow.

## Automated and native verification

- 367 Python tests passed.
- Ruff passed for `backend` and `tests`; Python compilation passed for `backend` and `app.py`.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight and the native web-bundle build passed.
- Android source verification passed for Ask Crump 5.9.52, build 50952, and API 36.
- Store metadata and tracked-signing-secret controls passed.
- GitHub CI run `33162073713` passed.
- Hosted unsigned Android App Bundle run `33162073773` passed.
- Hosted unsigned iOS Release compile run `33162073775` passed.

The local verifier correctly reports that the iOS project is absent on Windows. RevenueCat public
keys, Android Firebase, signing credentials, physical-device results, and store submission remain
separate open gates.

## Production evidence

- Deployment `dpl_8mYEDxe4uVoEEUCy5qKt8UjMDBrx` reached `READY` from the exact code commit with all
  production aliases and no alias error.
- `https://www.askcrump.com/api/health` returned version 5.9.52.
- The live app, Project runtime, UI runtime, and service worker returned HTTP 200.
- The Project runtime contained the 15-second save boundary, the UI runtime contained the corrected
  accessible resume action, and the worker served cache revision `ask-crump-new-body-v1-r86`.
- The one-hour project scan contained no runtime error cluster, and the exact deployment contained
  no warning, error, or fatal log.
- Verification made no production login, message, Project, account, payment, or synthetic event.

## Rollback

The prior production deployment `dpl_DYS4NCctHQPtd8rFJRySqFSd4gC7` remains an available rollback
candidate. This release requires no schema, RLS, environment, authentication, payment, pricing, or
infrastructure migration.

## Remaining evidence

Observe the first legitimate post-instrumentation conversation-to-Project completion and later
return. Reconcile the content-free `AhaReached`, Project resume, and retention aggregates before
claiming lift or scaling paid acquisition.
