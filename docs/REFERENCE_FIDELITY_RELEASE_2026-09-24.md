# Reference-fidelity release evidence — 2026-09-24

## Outcome

Ask Crump now treats image and video references as an explicit, ordered contract instead of an
unlabeled attachment or loose style hint. The customer assigns a role to each reference, reviews
the mapping before credits are used, and receives a durable receipt showing which numbered input
controlled which part of the request.

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
- The generated response stores a bounded, byte-free reference receipt and requires manual review
  of logos, readable text, and mascot details.
- Cached clients without the version-2 marker retain their prior compatible behavior; unsupported
  or stale versioned plans fail closed and can be reopened for correction.

## Video contract

- Images attached to a chat video request are carried into Video Studio without auto-starting the
  provider or charging credits.
- Video Studio displays the ordered files, role selectors, the selected engine's real reference
  limit, and its actual provider semantics.
- Quick and Cinematic accept one starting-frame image. Extendable accepts up to three best-effort
  appearance-guidance images. The UI does not call these pixel-locked frames or layout templates.
- The first click restates the numbered role plan; the second confirmed click starts the job.
- Owner scope, file type, count, order, roles, final expanded prompt length, budget, and
  idempotency are validated before the charge/provider boundary.
- Only bounded file IDs, roles, and safe metadata are persisted. Provider image bytes are not
  stored in chat synchronization or analytics.

## Privacy and safety boundary

- The release adds no database migration and changes no shared Supabase schema.
- Reference file access remains owner-scoped through the existing private Files service.
- Precision masks remain single-request private data and are excluded from synchronized messages,
  traces, and analytics.
- No automatic second-pass visual comparison was added because that would resend private inputs
  and generated outputs to a model. Review is deterministic/manual and explicit.
- No live image or video provider request was used during release validation, and no customer
  credits were consumed.

## Verification

- Full Python suite: 1,165 tests passed.
- JavaScript contract: 54 files validated; 24/24, 10/10, and 10/10 attribution/runtime fixtures
  passed; store packet self-test passed 21/21.
- Browser-control matrix: 48/48 verifiers passed in installed Microsoft Edge.
- Public accessibility matrix: 33/33 phone, tablet, and desktop scenarios passed.
- Focused backend reference suites: 83/83 passed; video provider module: 18/18 passed.
- Production build preflight, native web bundle generation, backend compilation, client-secret
  boundary, and patch whitespace checks passed.

The native release verifier continues to report the already-known store-submission gates: native
Android/iOS projects and RevenueCat public SDK configuration are not present in this Windows
worktree. Those gates are separate from this web/PWA reference-fidelity release.

## Release identity

- Browser/PWA/native asset token: `5.9.76-reference-fidelity-focused-1`
- Service-worker cache: `ask-crump-new-body-v1-r250`
- Release boundary: application, browser/native delivery, focused verifiers, release guards, and
  this evidence record only; no migration or pricing change.
