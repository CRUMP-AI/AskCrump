# Durable Project recognition release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

Ask Crump now recognizes when the current conversation is already saved in an owned Project after
a reload or return from another device. The latest-result action restores **Open Project**, names the
exact Project for assistive technology, and opens that workspace directly instead of offering to
create or attach the same conversation again.

This is a deterministic continuing-work correction. It does not claim a retention improvement;
that outcome still requires legitimate users to save useful work and return later.

## Decision evidence

The saved state previously lived only on the rendered button. Reloading the app discarded that
state even though the owner-scoped `project_chats` relationship remained durable on the server. A
returning user could therefore see **Start a Project** again or a target derived from unrelated
current browser state.

The existing Project service already resolves a conversation through both owner ID and chat ID.
The release exposes a minimal authenticated lookup that returns only Project ID and name, caches the
result for the current page, and updates the latest-result action without selecting that Project or
injecting its context into the conversation.

## Product and privacy contract

- A saved conversation restores **Open Project** after reload without requiring a remembered active
  Project in local storage.
- The action opens the exact owned Project returned by the server.
- An unsaved conversation retains **Start a Project** and creates exactly one Project when chosen.
- Relationship lookup is authenticated and owner-scoped.
- The lookup returns only Project ID and name; it does not return messages, prompts, responses,
  files, descriptions, instructions, user IDs, or analytics metadata.
- A missing or invalid relationship returns no Project, and a lookup failure leaves the existing
  save action available.
- Generic app reload still does not silently activate Project context.

No authentication, account, chat creation, message, file, manuscript, generation, billing,
checkout, subscription, analytics, database schema, storage, provider, or entitlement behavior was
changed.

## Verification

- All 525 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production preflight and the generated native web-bundle build passed.
- Diff integrity passed.
- A credential-free real-runtime browser fixture started with no selected Project while the server
  reported that the conversation was already saved. It restored the named **Open Project** action,
  performed one relationship lookup, opened `Q3 Finance Forecast`, made no save request, and
  recorded zero browser errors.
- The same fixture with no saved relationship retained **Start a Project**, created one Project,
  transitioned to **Open Project**, and recorded zero browser errors.
- All browser verification tabs were closed and the temporary local server was stopped.
- All six production aliases reached the `READY` deployment without alias error. The canonical app,
  runtime loader, versioned UI and Project runtime, and service worker returned HTTP 200 with the
  expected contract.
- An unauthenticated production request to the new relationship lookup returned the expected HTTP
  401 boundary.

## Production release

- Feature commit: `71979fa`
- Deployment: `dpl_N2Y4TVPWtTNViDu5sqtHhQ52iZgW`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r150`
- Asset boundary: `5.9.76-durable-project-recognition-1`
- Framework: other / Vercel Functions
- Post-release observation: no warning/error/fatal deployment log and no 5xx response on the exact
  deployment after the release settled

No production account, credential, login, signup submission, funnel event, message, Project, file,
generation, checkout, payment, or subscription was created for verification.

## Next operating decision

Keep authentication and generic Project activation stable. Observe the first legitimate external
conversation-to-Project transition and later return without manufacturing production behavior.
Continue choosing deterministic first-use, durable-work, return, and conversion defects that can be
proven independently of small anonymous traffic samples.
