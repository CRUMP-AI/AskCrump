# Owner-isolation integration candidate — 2026-09-20

Status: local, unmerged, undeployed integration branch. This is not a production fix.

## Scope and decision

This branch combines the checkout reauthentication document reset with account-scoped
video job, retry, credit, reference-upload, and transient composer state. The checkout
selection is restored for review only; no purchase is submitted automatically. The
combined runtime and credit-dialog scripts use a fresh `5.9.76-owner-isolation-1`
asset version and PWA cache generation `r251`, while the changed authentication and
video modules retain their own explicit versions.

The conversational DOCX/PDF/PPTX delivery matrix from the production source revision
and the reviewed video account-deletion fence candidate (`61dbe84`) are also
integrated locally. The document matrix exercises real chat, artifact, and file
routes with local owned fixtures; it does not claim a real customer's
production download was observed.

## Verification on the isolated branch

- JavaScript integration contract passed for 54 files.
- The focused checkout and video-owner browser fixtures passed: two reauthentication
  handoffs with zero automatic checkout requests, cross-account DOM isolation, and
  16 video-owner scenarios without page errors. The latter now includes unresolved
  provider starts, server conflict, and a successful same-key replay that still
  reports reconciliation pending, across account switches and page reload.
- The full local browser-control matrix passed **49/49** verifiers, including the
  returning-PWA cache fixture.
- The full local Python suite passed when excluding only two previously diagnosed
  tests that require the unavailable Argon2 package in this bundled runtime.
- The integrated document-delivery API matrix passed, and the changed browser fixtures
  showed exact private DOCX/PDF/PPTX download targets plus the PDF Files viewer's
  same-origin fixture path at desktop and mobile sizes, with no browser errors.
- Ruff passed for the reconciled Python safety contracts. The staged integration diff
  passed whitespace integrity before commit.
- After the local video server integration, the combined Python suite passed with
  only the two documented, locally unavailable Argon2 tests excluded. The server
  branch's 98 focused race/deletion tests, Ruff, and diff check passed before
  cherry-pick. This does not validate staged SQL against PostgreSQL.
- The exact-origin PDF CSP parity test passed across backend, Vercel, and the
  fixture. An offline browser probe reached a real localhost 302 and received
  a synthetic signed-origin PDF response, but headless Chromium did not expose
  a rendered iframe. No visible PDF preview is claimed.
- Independent source review found no remaining confirmed P1/P2 in the
  deletion/provider-start fence, same-key claim settlement, fair worker
  scheduling, or protected demo-account reset. It did not replace real
  PostgreSQL execution.
- A 2026-09-21 02:44 UTC read-only public check returned HTTP 200 for Ask Crump,
  its app, and Clever Crump; Ask Crump's health route reported version 5.9.76.
  This is reachability, not proof of an authenticated customer journey.

## Additional source-only safety candidates

The client now retains an owner-scoped video idempotency key and job handle when
the server reports an ambiguous start or an unresolved prior start. Generate is
disabled while the owner-scoped GET reports `reconciliationPending`, even if
the job status looks failed. It clears the hold only after the server reports a
resolved claim. The corresponding server candidate is integrated in this local
branch only; its SQL remains staged and unapplied.

The PDF preview investigation reproduced a browser CSP block on the actual
same-origin-to-cross-origin redirect shape. A narrow exact-project Supabase
`frame-src` candidate is staged in source, with the existing anti-framing
policy preserved. It changes a security header and is not authorized for
production by this local test; an authenticated owned-file check of actual
signed-storage responses and both small/large PDF downloads is still required.

Because the video client changed after the current `r251` service-worker and
Product Studio asset versions were chosen, release packaging must advance
those cache versions and their source assertions before any production
promotion. This branch is intentionally not a deployable artifact yet.

## Release hold and next action

The server-side video-start versus account-deletion race has a source-only
candidate, not a production fix. Its SQL requires a numbered migration, real
two-connection PostgreSQL transaction/trigger/grant/RLS tests, a coordinated
migration-first rollout with old workers quiesced, and a retention/operator
policy for no-provider-ID claims. The native bundle and generated
client-artifact secret check are also unverified locally because this isolated worktree
does not have the locked esbuild dependency. GitHub's connected PR creation returned
403; a browser PR submission requires action-time confirmation.

Independent review found another release blocker: actual non-download PDFs redirect to
cross-origin signed storage URLs, while the deployed app frame policy allows only
same-origin frames. The original PDF fixture used same-origin synthetic bytes, so
its green result must not be described as a working production PDF preview.

Next: test staged SQL in a disposable two-connection PostgreSQL environment,
decide the unknown-claim
operator policy, advance the service-worker/asset cache versions, and run the
full CI/native build. Only then consider a controlled release and owned-file
PDF/account-switching/video continuity checks without using customer content.
