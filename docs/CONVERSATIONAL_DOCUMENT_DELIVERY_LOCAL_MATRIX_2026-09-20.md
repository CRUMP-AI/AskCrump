# Conversational document delivery: local browser/API matrix

Date: 2026-09-20
Base: production commit `d2aa8573792f39d8687a314bf151c67de3fa7898`
Branch: `candidate/document-delivery-e2e-20260920`
Status: local verifier candidate; no publication or production mutation

## User story and result

An owner asks Crump for a Word document, PDF, or presentation in chat. The response should contain
a real, durable file; its chat card should offer a private download; Files should list the owned
artifact; PDF should open in the in-app Files viewer; and a different owner should not obtain it.

The bounded local matrix passes. It verifies the production route, formatter, file-service owner
lookup, chat artifact renderer, and the Files viewer's local control path against fixture-only
state. It does **not** prove that a PDF can render in the deployed viewer or claim a legitimate
production user's complete artifact journey.

## Executable boundaries

`tests/test_conversational_document_delivery_matrix.py` exercises the real FastAPI `/api/chat`,
`/api/files`, and `/api/files/{id}/content` routes with an in-memory database and storage substitute.
The model returns fixed fixture Markdown; no provider, Supabase, account, or external analytics call
is made. Three cases cover explicit Word/DOCX, explicit PDF, and a contextual PPTX follow-up when
semantic creation intent is absent. Each checks:

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
PDF, and PPTX chat cards. Clicking their real **Download** controls yields the exact private
`/api/files/{id}/content?download=1` targets and filenames without opening a new window.

`tests/fixtures/file-library-usability.html` and `scripts/verify-file-library-usability.cjs`
run the committed Files control and file viewer at 1440×1000 and 390×844. The PDF **Open** control
creates an in-app iframe and requests only a locally fulfilled **same-origin** synthetic PDF. Its viewer and Files
**Download** controls both target the private download route. Network guards abort every external
host and unexpected `/api/` request. Both verifiers observed zero browser errors.

## Validation

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

## Honest remaining gate

The Python API and Chromium halves use the same production source and response shape but separate
fixture processes; this is a boundary matrix, not one browser session talking to a live Supabase
storage service. The file route's real authentication, real storage upload/signed URL, cross-device
session, provider response, and delivered/downloaded production customer outcome remain untested
here. In production, non-download PDF content redirects to a cross-origin Supabase signed URL,
while the deployed frame policy does not permit that target. The local same-origin fixture
therefore cannot establish that PDF **Open** actually works; treat it as a release blocker until
a production-equivalent CSP/redirect test passes. The chat artifact card intentionally offers
**Download**, not an in-chat preview. Word and PPTX intentionally show download placeholders
rather than in-browser document rendering. A real production journey requires a separately authorized,
legitimate user action, not synthetic production traffic or customer-content inspection.

Follow-up source-only candidate: `tests/test_pdf_preview_csp_contract.py` verifies
that backend, Vercel, and the Files fixture allow `frame-src` only for self and
the exact configured Supabase origin, while `frame-ancestors 'none'` and
`X-Frame-Options: DENY` remain intact. An offline browser attempt followed a
localhost 302 and received synthetic PDF bytes at that origin, but headless
Chromium did not expose a rendered PDF iframe. The original same-origin Files
verifier remains unchanged; no end-to-end PDF Open claim is made. This
security-header candidate stays unmerged/undeployed pending a legitimate owned
signed-file check, including small and large downloads.
