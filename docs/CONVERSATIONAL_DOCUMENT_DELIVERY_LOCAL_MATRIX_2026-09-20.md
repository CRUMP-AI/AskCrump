# Conversational document delivery: local browser/API matrix

Date: 2026-09-20
Base: production commit `d2aa8573792f39d8687a314bf151c67de3fa7898`
Branch: `candidate/document-delivery-e2e-20260920`
Follow-up: 2026-10-01 browser-to-API acceptance added on base `97731131e1f864b36b822349e748de532a656c3d`
Status: local verifier candidate; no publication or production mutation

## User story and result

An owner asks Crump for a Word document, PDF, spreadsheet, or presentation in chat. The response should contain
a real, durable file; its chat card should offer a private download; Files should list the owned
artifact; PDF should open in the in-app Files viewer; and a different owner should not obtain it.

The bounded local matrix passes. It verifies the production route, formatter, file-service owner
lookup, chat artifact renderer, and Files PDF viewer against fixture-only state. It does **not**
claim a legitimate production user's complete artifact journey.

## Executable boundaries

`tests/test_conversational_document_delivery_matrix.py` exercises the real FastAPI `/api/chat`,
`/api/files`, and `/api/files/{id}/content` routes with an in-memory database and storage substitute.
The model returns fixed fixture Markdown; no provider, Supabase, account, or external analytics call
is made. Four cases cover explicit Word/DOCX, explicit PDF, explicit XLSX, and a contextual PPTX
follow-up when semantic creation intent is absent. Each checks:

- the generated DOCX/PPTX is a ZIP container or the PDF is parseable with its expected text;
- one owner-scoped generated-file row and the same file link in the API reply, persisted assistant
  message, and completed chat-job response;
- the owner can list and download the exact stored bytes with an attachment disposition;
- another fixture owner gets HTTP 404 for the link and no list entry, while no fixture identity
  gets HTTP 401; and
- PDF inline Open returns a local signed-URL stand-in redirect whose target serves PDF bytes.

The in-memory event collector checks only that the route attempts its expected milestone calls;
it never emits events externally.

`tests/fixtures/file-delivery.html` and `scripts/verify-file-delivery.cjs` run the committed
`public/crump-5.0.js` renderer wrapper in Chromium. Three fixture assistant messages produce DOCX,
PDF, and PPTX chat cards. Each card exposes distinct **Open**, **Download**, and **Add to Project**
actions. Download yields the exact private `/api/files/{id}/content?download=1` target and filename
without opening a new window. Open keeps the handoff inside Ask Crump, above an already mounted
Files or Project overlay.

`tests/fixtures/file-library-usability.html` and `scripts/verify-file-library-usability.cjs`
run the committed Files control and file viewer at 1440×1000 and 390×844. The PDF **Open** control
creates an in-app iframe and requests only a locally fulfilled synthetic PDF. Its viewer and Files
**Download** controls both target the private download route. Network guards abort every external
host and unexpected `/api/` request. Both verifiers observed zero browser errors.

## 2026-10-01 unified browser-to-API follow-up

`tests/fixtures/conversational-document-delivery.html`,
`scripts/serve-conversational-document-delivery-fixture.py`, and
`scripts/verify-conversational-document-delivery.cjs` close the former separate-process seam for
one representative Word journey. Chromium uses the committed production document studio, chat
transport, and artifact-card renderer while talking to a dynamic-port, loopback-only FastAPI app.
That app mounts the real `/api/chat`, `/api/files`, and private content routers with the production
artifact service and DOCX formatter. Only authentication, model, database, analytics, and storage
are replaced with deterministic in-memory fixtures.

The unified journey proves:

- the production composer sends `artifactFormat: "docx"` through the real chat route;
- the response renders one card with **Open**, **Download**, and **Add to Project**;
- the owner list contains the same durable artifact and its private download returns Word MIME,
  attachment disposition, ZIP bytes, and `word/document.xml`;
- an identical retry and a cached resend/re-render after reloading the fixture reuse the same
  artifact rather than create duplicates, without claiming startup-sync coverage;
- no fixture identity receives HTTP 401, a different owner receives HTTP 404 and an empty file
  list, and every browser request stays on the selected loopback origin; and
- attempted packaging and download milestones remain observable in fixture state without sending
  external analytics.

The verifier owns an ephemeral port and guarantees browser/server teardown. It is included in the
fail-closed browser inventory, so adding or removing a verifier without updating the declared
matrix fails CI.

## Original validation

- Focused chat/artifact/file regression suite: **52 passed**, one upstream Starlette deprecation
  warning.
- Both local Chromium verifiers passed; JavaScript syntax checks passed.
- JavaScript integration check: **54 files**, plus 24/24 rough-to-useful, 10/10 Word/PDF,
  10/10 résumé attribution, and 21/21 store-packet cases.
- Ruff and `git diff --check`: passed.
- A temporary localhost fixture server was stopped after the browser run.

The `agent-browser` CLI was unavailable on this host. Bundled Playwright performed the browser
checks and a separate visual-load gut check: fixture page loaded, key control appeared, body was
nonblank, and no framework overlay or console error appeared.

## 2026-10-01 follow-up validation

- Unified browser-to-API verifier: passed with one artifact, cached retry, cached re-render,
  zero blocked requests, and zero browser errors.
- Focused document-delivery and CI-integrity regression slice: **31 passed**, with one upstream
  Starlette deprecation warning.
- Complete Python regression suite: **1,507 passed**; JavaScript validation: **54 files**.
- Fail-closed browser-control matrix: **53/53 passed**, including the unified verifier.
- Public accessibility matrix: **33/33 passed**.
- Python fixture lint and Node syntax check: passed.

## Honest remaining gate

The 2026-10-01 follow-up now proves one browser session through the real application routes, but it
still uses deterministic fixture authentication, model, database, analytics, and storage. Real
authentication, real Supabase upload/signed URL, cross-device session, provider response, and a
delivered/downloaded production customer outcome remain untested here. The chat artifact card now
offers both **Open** and **Download**. PDF opens in the authenticated
in-app viewer; Word, PowerPoint, and Excel use the in-app download handoff because the browser does
not provide a trustworthy native editor/renderer for those private files. A real production journey requires a separately authorized,
legitimate user action, not synthetic production traffic or customer-content inspection.
