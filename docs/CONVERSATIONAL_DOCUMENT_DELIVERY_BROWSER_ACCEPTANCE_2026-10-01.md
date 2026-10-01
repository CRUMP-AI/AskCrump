# Conversational document delivery: browser-to-API acceptance

Date: 2026-10-01
Base: `97731131e1f864b36b822349e748de532a656c3d`
Branch: `test/document-delivery-browser-acceptance-20261001`
Status: verified local candidate; no production or customer-data mutation

## Decision

Conversational document delivery already had strong cross-format API coverage and separate browser
card coverage. The remaining regression risk was the seam between those layers. A new bounded gate
now drives a real production composer and renderer in Chromium through Ask Crump's real chat, file
listing, and private content routes in one session.

One Word journey is used for the browser bridge. The existing parameterized Python matrix remains
the authority for DOCX, PDF, PPTX, and XLSX formatter and byte correctness, avoiding four redundant
slow browser journeys.

## Production surfaces exercised

- `window.CrumpDocumentStudio`
- the production send-button replacement and `window.CrumpChatTransport`
- the production artifact-card renderer
- `/api/chat`
- `/api/files`
- `/api/files/{id}/content?download=1`
- `ArtifactService`, `FileService` owner lookup, and the DOCX formatter

The fixture replaces only identity, model, database, analytics, and storage with deterministic
in-memory substitutes. It binds to `127.0.0.1` on an ephemeral port, passes the server an allowlisted
credential-free environment, blocks server-side external socket connections, and guards ordinary
browser traffic to the selected loopback origin. The route guard is removed only for the real
browser download because intercepted downloads are canceled on Windows; that download's complete
URL is asserted to be the exact loopback private-file target before its bytes are accepted. The
browser and server stop on success or error.

## Acceptance evidence

The passing journey verified all of the following:

1. Choosing Word in the production document studio causes the actual chat request to carry
   `artifactFormat: "docx"`.
2. The real chat route creates one owner-scoped artifact and the production renderer shows **Open**,
   **Download**, and **Add to Project**.
3. The card's real Download click produces a browser download with the expected filename, ZIP bytes,
   and `word/document.xml`. A separate authenticated request to the exact same private target proves
   the Word MIME type and attachment disposition and returns identical bytes.
4. Retrying the identical request returns the cached response and does not create a second file.
5. After reloading the fixture page, a cached resend through the production transport returns the
   same artifact and the production renderer displays it again. This is not a startup-sync claim.
6. An unauthenticated context receives HTTP 401. A different owner receives HTTP 404 for the content
   target and an empty file list.
7. The fixture records packaging and download milestones, with zero external requests and zero
   browser errors.

Observed verifier result:

```json
{"cachedRetry":true,"cachedRerender":true,"ownerFiles":1,"blockedRequests":[],"browserErrors":[]}
```

The relational result is deterministic fixture evidence, not a production-customer metric. The
production composer generates a fresh message and artifact identifier per run, so that identifier
is intentionally omitted from the recorded summary.

## Validation

- Standalone browser-to-API verifier: passed.
- Focused document-delivery and CI-integrity tests: **31 passed**.
- Complete Python regression suite: **1,507 passed**, with one upstream Starlette deprecation
  warning.
- JavaScript validation: **54 files**, plus the existing attribution and store-packet cases.
- Fail-closed browser-control matrix: **53/53 passed**.
- Public accessibility matrix: **33/33 passed**.
- Fixture-server lint: passed.
- Browser-verifier syntax check: passed.

CI's JavaScript job now installs Python 3.12 and production Python dependencies before the browser
matrix, making the real FastAPI fixture available on clean runners. The verifier inventory and its
expected count are pinned by tests.

## Honest remaining boundary

This gate does not claim a legitimate production user's end-to-end outcome. It does not exercise a
real account, Supabase Storage, provider generation, signed URLs, cross-device continuity, or a
founder-observed desktop/iPhone journey. Those require privacy-safe, separately authorized product
acceptance. This gate prevents code-level browser/API drift while leaving that production evidence
boundary explicit.
