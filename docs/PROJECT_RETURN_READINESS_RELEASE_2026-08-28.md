# Ask Crump 5.9.53 Project return readiness release

Date: 2026-08-28  
Production version: 5.9.53  
Code commit: `23e6f9e6240ab372878f112803e2bdfba35ee410`  
Production deployment: `dpl_3VVnB261rupDFtaDQeENRrh3dc3K`

## Outcome

The private Projects workspace can no longer remain indefinitely on a loading state when its
Project list, saved-conversation list, Project-note response, or response body stalls. Each read is
bounded through response parsing and fails inside its own surface with an accurately named Retry
action. A failed Project-note read does not hide an already available saved conversation, and a
failed saved-conversation read does not discard the active Project.

This release verifies a recoverable return-to-work path. It does not prove a higher Project return
or retention rate; those outcomes still require legitimate external use and later return.

## Reproduced failure

A credential-free loopback browser fixture loaded the real Project runtime, supplied one synthetic
owner-scoped Project, and left the saved-conversation response pending. Before the correction:

- the fixture issued one saved-conversation request;
- the workspace remained on `Loading saved conversations…` after the test interval;
- the request was never aborted;
- no retry action appeared; and
- the user could not continue the saved conversation.

The fixture used only `fixture-user`, two synthetic UUIDs, local HTML, and intercepted loopback
requests. It contained no password, production hostname, real account, or external write.

## Correction

- Applied a 15-second boundary to the Project list, saved-conversation list, and Project-note reads,
  including JSON response-body parsing.
- Made the shared optional request boundary rethrow aborts raised while parsing a response body
  instead of converting the aborted body into an empty successful response.
- Added one focused Retry action to each failed surface so recovery is local and reusable.
- Captured the active Project ID around the Project-note request and ignored stale success or error
  results after a Project switch.
- Kept Project ownership, conversation ownership, authentication, RLS, pricing, entitlements,
  analytics, schema, and write behavior unchanged.

## Full-story verification report

**Story:** a signed-in user returns to Projects, opens an owned Project, sees saved conversations and
private Project notes, then continues the chosen conversation in the primary workspace. A stalled
read fails visibly and can be retried without discarding the other successfully loaded surfaces.

| Boundary | Status | Evidence |
| --- | --- | --- |
| UI trigger | Passed | The real Project runtime opened the stored `Launch plan` Project and rendered its independent conversation and note surfaces. |
| Client → API | Passed | Project-list, saved-conversation, Project-note, and response-body stall modes each issued one request with an abort signal and produced one bounded abort. |
| API route | Unchanged | The existing authenticated owner-scoped Project GET routes were used without a route, policy, or payload change. |
| API → data | Unchanged | No schema, RLS, ownership filter, write path, or production data was changed or exercised. |
| Response → UI | Passed | Each stalled surface rendered its accurately named Retry action. Retrying the saved-conversation stall produced a second bounded request and left the surface reusable. |
| Successful return | Passed | The success fixture exposed `Continue Launch plan`, loaded conversation `00000000-0000-4000-8000-000000000062`, closed the Projects studio, showed meaningful content, and recorded zero browser errors. |

The Project-list stall rendered `Retry loading Projects`; the saved-conversation stall rendered
`Retry loading saved conversations`; the note stall rendered `Retry loading Project notes` while
leaving the conversation continuation available; and the response-body stall proved that an abort
after successful headers propagates through JSON parsing. The loopback fixture's optional
`favicon.ico` and root `sw.js` 404s did not affect the isolated flow or produce a browser error.

## Automated and native verification

- 368 Python tests passed.
- Ruff passed for `backend` and `tests`; Python compilation passed for `backend` and `app.py`.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight and the native web-bundle build passed.
- Android source verification passed for Ask Crump 5.9.53, build 50953, and API 36.
- Store metadata and tracked-signing-secret controls passed.
- GitHub CI run `33168768095` passed.
- Hosted unsigned Android App Bundle run `33168768090` passed.
- Hosted unsigned iOS Release compile run `33168768141` passed.

The local verifier correctly reports that the iOS project is absent on Windows. RevenueCat public
keys, Android Firebase, signing credentials, physical-device results, and store submission remain
separate open gates.

## Production evidence

- Deployment `dpl_3VVnB261rupDFtaDQeENRrh3dc3K` reached `READY` from the exact code commit.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.53.
- The live app, Project runtime, and service worker returned HTTP 200.
- The Project runtime contained the 15-second read boundary, all three focused retry labels, and the
  response-body abort propagation; the worker served cache revision
  `ask-crump-new-body-v1-r87`.
- The one-hour project scan contained no runtime error cluster, and the exact deployment contained
  no error or fatal log.
- Verification made no production login, message, Project, account, payment, or synthetic event.

## Rollback

The prior production deployment `dpl_DWQZdQPcftTaxD8auX1zL1CY6wYY` remains an available rollback
candidate. This release requires no schema, RLS, environment, authentication, payment, pricing, or
infrastructure migration.

## Remaining evidence

Observe the first legitimate post-instrumentation Project continuation and later return. Reconcile
content-free Project resume and retention aggregates before claiming lift or scaling paid
acquisition.
