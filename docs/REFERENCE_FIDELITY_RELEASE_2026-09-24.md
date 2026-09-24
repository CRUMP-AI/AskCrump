# Reference-fidelity release evidence — 2026-09-24

## Outcome

Ask Crump now treats image and video references as an explicit, ordered contract instead of an
unlabeled attachment or loose style hint. The customer assigns a role to each reference, reviews
the mapping before credits are used, and receives a durable receipt showing which numbered input
controlled which part of the request.

After an image is generated, the server now performs a bounded local color-and-structure review
against every prepared reference. This review runs with Pillow on bytes already present for the
paid generation; it does not call a provider, start another generation, or use additional credits.

This improves adherence but does not claim that a generative model can reproduce a logo,
wordmark, mascot, type treatment, or layout pixel-for-pixel. When original pixels must remain
unchanged, the product directs the customer to **Exact Overlay**, a deterministic local editing
path that does not invoke an AI model or use generation credits.

## Image contract

- Image Studio accepts up to four ordered private image references.
- Each reference is assigned one reviewed role: base, subject, mascot, logo, typography, or style.
- The current client sends contract version 2 and cannot generate until the mapping is confirmed.
- The server revalidates the complete file/role plan before intelligence preparation, message
  usage, feature credits, or the image provider.
- Every confirmed reference is sent in order through the image-edit endpoint. A referenced image
  is billed as an image edit, not a fresh text-to-image request.
- Base and style roles are compared against the whole generated output. Subject, mascot, logo, and
  typography roles use a bounded local crop search at 100%, 75%, 50%, 33%, 20%, and 12% scales,
  across a fixed 3-by-3 position grid. The best candidate weights structure at 70% and color at 30%.
- Only bounded enum evidence is retained: per-reference pass/warn/mismatch, color and structure
  labels, required human checks, and the customer's optional review decision. Raw comparison
  scores and reference bytes are not placed in the receipt.
- The safe reference review is computed before file storage and is persisted both with the
  assistant response and in the generated image's `referenceReview` metadata.
- A local pass means only that the bounded color and structure signals align. Identity, mascot
  details, exact logo geometry and colors, spelling, letterforms, text layout, and pixel fidelity
  still require comparison with the originals by a person.
- Cached clients without the version-2 marker retain their prior compatible behavior; unsupported
  or stale versioned plans fail closed and can be reopened for correction.

## Video contract

- Images attached to a chat video request are carried into Video Studio without auto-starting the
  provider or charging credits.
- Video Studio displays the ordered files, role selectors, the selected engine's real reference
  limit, and its actual provider semantics.
- Before generation starts, each authenticated user's video reference draft is retained for up to
  24 hours using only bounded safe metadata and private backend file IDs; raw file bytes, data
  URLs, blob URLs, and preview URLs are never stored in browser draft storage.
- Reloading restores the reference order, assigned roles, selected engine, and any still-valid
  reviewed confirmation. Signing out or switching accounts clears the in-memory reference state,
  and drafts are isolated by user so references never cross account boundaries.
- An accepted generation start clears that user's saved pre-start draft.
- Quick and Cinematic accept one starting-frame image. Extendable accepts up to three best-effort
  appearance-guidance images. The UI does not call these pixel-locked frames or layout templates.
- The first click restates the numbered role plan; the second confirmed click starts the job.
- The completion receipt continues to report `referenceVerification: "not-performed"`. It records
  ordered inputs and provider semantics but does not claim that the finished video was visually
  matched against identities, logos, text, or other reference details.
- Owner scope, file type, count, order, roles, final expanded prompt length, budget, and
  idempotency are validated before the charge/provider boundary.
- Only bounded file IDs, roles, and safe metadata are persisted. Provider image bytes are not
  stored in chat synchronization or analytics.

## Privacy and safety boundary

- The release adds no database migration and changes no shared Supabase schema.
- Reference file access remains owner-scoped through the existing private Files service.
- Precision masks remain single-request private data and are excluded from synchronized messages,
  traces, and analytics.
- Image post-generation review is deterministic and local. It reuses already-prepared image bytes,
  never resends references or outputs to a model, and adds zero provider calls or credits.
- Video completion has no equivalent automated visual comparison and explicitly reports that
  verification was not performed.
- No live image or video provider request was used during release validation, and no customer
  credits were consumed.

## Verification

- Full Python suite: 1,174/1,174 tests passed.
- JavaScript contract: 54 files validated; 24/24, 10/10, and 10/10 attribution/runtime fixtures
  passed; Store packet self-test passed 21/21.
- Browser-control matrix: 48/48 verifiers passed in installed Microsoft Edge.
- Public accessibility matrix: 33/33 phone, tablet, and desktop scenarios passed.
- Production build preflight, native web bundle generation, backend compilation, client-secret
  boundary, and final diff checks passed.

The native release verifier continues to report the already-known store-submission gates: native
Android/iOS projects and RevenueCat public SDK configuration are not present in this Windows
worktree. Those gates are separate from this web/PWA reference-fidelity release.

## Release identity

- Browser/PWA/native asset token: `5.9.76-reference-fidelity-focused-1`
- Service-worker cache: `ask-crump-new-body-v1-r250`
- Release boundary: application, browser/native delivery, focused verifiers, release guards, and
  this evidence record only; no migration or pricing change.
