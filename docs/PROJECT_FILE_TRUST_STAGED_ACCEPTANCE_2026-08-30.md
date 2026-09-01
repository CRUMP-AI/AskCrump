# Project file trust staged acceptance

Date: 2026-08-30  
Status: accepted locally; not committed or deployed

## Outcome

A temporary database failure can no longer masquerade as an empty Project file
list, and a late response from one Project can no longer overwrite the file view
after the person switches to another Project.

## Defects closed

The Project file-list route previously caught every exception raised while
loading an owner-scoped file mapping and continued. If Supabase was temporarily
unavailable, the endpoint returned `success: true` with an empty list. The UI
then showed **No Project files yet**, which looked indistinguishable from a
genuinely empty Project.

The attachment endpoint also converted a missing private file, a database
failure, and an unknown server failure into the same HTTP 400
`PROJECT_FILE_FAILED` response.

The client displayed an error after a failed file refresh but offered no direct
Retry action. It also did not check that the selected Project still matched the
request before rendering a success or failure.

## Staged behavior

- Every query remains authenticated and owner-scoped by both `project_id` and
  `user_id`.
- A confirmed `FILE_NOT_FOUND` mapping is treated as stale/deleted and skipped.
- `DatabaseError` returns HTTP 503, `PROJECTS_UNAVAILABLE`, and
  `shouldRetry: true`.
- Other `FileServiceError` values preserve their bounded public status, code,
  and message.
- An unknown attachment failure is classified as HTTP 500 instead of customer
  input error.
- The Project-files UI renders data or an error only when the originating
  Project remains selected.
- The error state includes a direct **Retry** action.
- The changed client asset uses the narrow
  `5.9.76-project-files-retry-1` cache version across web, service worker, and
  native bundling.

No filename, file content, prompt, response, URL, storage path, customer
identifier, or database error text is added to analytics or the public error
contract.

## Verification

- Focused Project continuity and Project 5.3.1 contract suite: 26 passed.
- JavaScript integration contract: 48 files passed.
- Full Python suite: 686 passed.
- Production build preflight: passed. Its optional local Python compile guard
  was skipped because that script does not discover the bundled runtime; the
  complete suite above executed with the bundled Python runtime.
- Native web bundle: regenerated successfully.
- Git diff integrity: passed, with only the existing `public/landing.js`
  CRLF-to-LF advisory.
- Owner-scope, confirmed-404, database-outage, and attachment failure semantics
  execute through route-level tests.
- The connected desktop browser runtime remains unavailable because its sandbox
  helper fails before browser selection. No rendered-browser claim is made.

## Release boundary

No Supabase schema, migration, RLS policy, production Project, file, account,
event, conversation, payment, price, plan, social profile, publication, Search
Console property, or store submission changed. Commit and deployment remain a
separate action-time decision.
