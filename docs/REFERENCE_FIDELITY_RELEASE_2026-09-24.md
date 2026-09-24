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

The release also closes the browser account boundary around unsent media work. Logging out or
changing authenticated users aborts active uploads and video starts, revokes local preview URLs,
clears private prompts, masks, file inputs, previews, and results from memory, and prevents stale
callbacks or polling from repainting another account's interface.

The same account boundary now covers Project destinations. Active Project state is stored per
authenticated user, legacy global state is restored only after an owner-scoped server lookup, and
video creation resolves the current user's Project again before sending its ID. An in-place account
change therefore cannot reveal or submit the prior account's Project name or identifier.

## Image contract

- Image Studio accepts up to four ordered private image references.
- Each reference is assigned one reviewed role: base, subject, mascot, logo, typography, or style.
- The current client sends contract version 2 and cannot generate until the mapping is confirmed.
- The server revalidates the complete file/role plan before intelligence preparation, message
  usage, feature credits, or the image provider.
- Every confirmed reference is sent in order through the image-edit endpoint. A referenced image
  is billed as an image edit, not a fresh text-to-image request.
- Precision Edit keeps its painted selection as the only editable region of the base image while
  still sending any additional confirmed references in numbered role order. The protected pixels
  are composited back locally after generation.
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
- Provider image output is accepted only as bounded inline base64, decoded as one safe PNG, JPEG,
  or WebP frame under fixed byte/dimension/pixel ceilings, and canonically re-encoded to the MIME
  Ask Crump stores. Unexpected provider URLs, animated payloads, decompression bombs, and mislabeled
  or malformed bytes fail before fidelity review or private storage.

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
- Pending job and retry records are account-scoped. A pending request retains only the owner ID,
  idempotency key, timestamp, and a SHA-256 request digest; it does not retain the prompt or
  reference IDs. Same-account reloads reuse that key, while another account cannot resume or poll
  the job.
- New generations and scene continuations persist the same request key before network submission,
  retain it across ambiguous/retryable failures, and clear it only after a definitive outcome.
  Concurrent submissions using the same key converge on the already-reserved job rather than
  starting a second provider request.
- Pre-upgrade raw pending-job IDs are migrated only after the authenticated owner can successfully
  read the job. A different account's 404 does not destroy the original account's recovery path.
- Quick and Cinematic accept one starting-frame image. Extendable accepts up to three best-effort
  appearance-guidance images. The UI does not call these pixel-locked frames or layout templates.
- The first click restates the numbered role plan; the second confirmed click starts the job.
- The completion receipt continues to report `referenceVerification: "not-performed"`. It records
  ordered inputs and provider semantics but does not claim that the finished video was visually
  matched against identities, logos, text, or other reference details.
- Owner scope, file type, count, order, roles, final expanded prompt length, budget, and
  idempotency are validated before the charge/provider boundary.
- Browser budget and active-job checks are fast feedback only. A serialized database authorization
  is authoritative across different idempotency keys and includes the new reservation in user
  concurrency, global daily, user daily, and Runway monthly estimates before allowance or credits
  can be consumed.
- Allowance/credit consumption, the durable billing receipt, and the transition into a launchable
  provider reservation are one database transaction. Provider launch and terminal delivery use
  separate token-fenced leases so concurrent tabs cannot launch, store, complete, fail, or refund
  the same job twice.
- Completed provider output is stored under the media job's stable UUID, so a retry reuses the same
  owner-scoped private file identity instead of creating an orphan or duplicate.
- The provider object is uploaded privately first, but its `user_files` row and the media job's
  ready/file binding are published in one token-fenced database transaction. If the absolute
  finalization deadline wins that race, the job fails/refunds without exposing a free ready file
  and the exact unbound object is removed on a best-effort owner-scoped cleanup path.
- Provider video downloads validate every HTTPS redirect, reject credentials and non-public DNS
  targets, strip the Gemini key on cross-origin redirects, stream under the configured byte ceiling,
  and require an MP4-family `ftyp` signature before storage. These controls narrow server-side fetch
  exposure but do not claim full media-container validation or eliminate DNS rebinding risk.
- A protected five-minute Vercel cron invokes a service-role-only bounded lease sweeper. It releases
  expired unbilled reservations, safely settles abandoned billed launches without relaunching a
  provider, and either binds a deterministically stored completed file or settles an expired
  finalization according to its preserved refund eligibility.
- The same cron also polls a bounded oldest-first set of stale provider jobs and recoverable expired
  finalizations after the customer closes the tab. Video Studio lists the authenticated owner's
  recent jobs with Resume/View status actions, so navigation is no longer the durability boundary.
- Provider processing has a database-owned monotonic start time and an absolute 24-hour safety
  horizon. A job that remains nonterminal past that horizon is settled by the protected sweep and
  any refundable allowance or credits are returned; direct polling cannot move the horizon.
- Every unsuccessful or still-nonterminal background check receives durable retry spacing without
  changing its absolute processing/finalization age. This moves long-running or unhealthy provider
  jobs behind unvisited owners instead of allowing a small oldest cohort to monopolize each batch.
- Finalization has a database-owned monotonic start time. Ten-minute work leases may be reclaimed,
  but never move the absolute one-hour recovery deadline; after that deadline the sweep binds the
  deterministic stored file when present or terminally settles/refunds the job. Repeated provider,
  storage, or status failures therefore cannot keep a paid job processing forever.
- Every modern billing, launch, and finalization RPC takes the owner lock before trying its
  secondary job lock and row lock. Secondary locks are nonblocking and locked rows return a safe
  retry outcome. This prevents a rolling-deploy deadlock with an older instance whose compatibility
  trigger necessarily reaches the owner lock after PostgreSQL has already locked its row.
- Terminal launch/finalization paths validate the complete billing-receipt shape before they can
  mark a job settled: credit and included-use event IDs must be canonical UUID receipts, and
  internal/subscription receipts must have no event ID. Unknown or malformed receipts fail closed
  for review instead of suppressing refund recovery.
- Both video-start routes require a bounded nonblank idempotency key. A selected Project is
  owner-validated before reference preparation, allowance/credit consumption, or provider work.
- New video idempotency keys are capped consistently at 120 characters across chat handoff, request
  validation, job reservation, and billing identity so distinct jobs cannot share one truncated
  credit receipt. The migration preserves 121–160-character keys only for already-existing rows and
  narrowly identified pre-atomic rolling-deploy inserts; that compatibility window is not exposed
  through the current public routes.
- Only bounded file IDs, roles, and safe metadata are persisted. Provider image bytes are not
  stored in chat synchronization or analytics.

## Privacy and safety boundary

- The release requires `migrations/20260924121719_atomic_video_reservation_billing.sql`. It adds
  bounded request-identity and phase/lease columns and constraints to `public.media_jobs`, a
  rolling-deploy compatibility trigger for older video rows, and service-role-only capacity,
  billing, launch, finalization, and sweep functions. It does not add a customer-content table.
- The remote migration ledger was read on 2026-09-24 and ended at
  `20260917233900 ai_gateway_cost_observability`; this new migration follows it and has not been
  applied by this release-preparation task.
- Rollout order is mandatory: recheck the remote ledger, apply the migration, verify its entry,
  columns, functions, constraints, and grants, and only then deploy the application and cron.
  App-first deployment would call database functions that do not yet exist and is prohibited.
- Before production, apply this migration to a real PostgreSQL staging/shadow database and run
  two-session tests for old-writer/new-RPC lock order, absolute-deadline/finalization races, rollback,
  idempotent refund behavior, and global-sweep progress while the owners of the earliest candidate
  rows are deliberately locked. Static parsing and mocked tests do not replace that gate. The
  migration creates eight ordinary indexes, validates new CHECK constraints, and classifies the
  existing video rows in one transaction, so table size and lock duration must be measured; use a
  maintenance window or split migration plan if staging shows material blocking.
- Drain pre-release application instances before migration/app cutover and keep overlap at zero or
  as short as operationally possible. An older process can still crash after charging but before
  inserting its media row, or publish its separately written random file before a concurrent sweep
  closes the job. Monitor and clean owner-scoped orphan `generated_video` rows, and alert on
  `sweepNeedsReview` quarantine records. This is a production rollout gate, not a prompt-level fix.
- A full application rollback is not safe while any modern video row is reserved, launching,
  processing, or finalizing. Before rollback, either drain and verify zero active modern jobs or
  keep a compatible new backend and protected reconciler running until they settle. Only then may
  the older application be restored while the additive migration remains installed. Do not remove
  the new columns, constraints, trigger, or functions while any old or new instance may still write
  video jobs; a database rollback requires a separate maintenance plan.
- Reference file access remains owner-scoped through the existing private Files service.
- Direct-to-storage uploads are revalidated against the declared size, actual object size, MIME type,
  and application ceiling before a reference can be used. Downloads are streamed under a hard byte
  cap; invalid objects are failed and removed on a best-effort basis.
- Uploaded image, precision-mask, and video-reference decoders reject multi-frame, oversized,
  over-pixel, and Pillow decompression-bomb inputs before full decode, EXIF transpose, or resize.
- Precision masks remain single-request private data and are excluded from synchronized messages,
  traces, and analytics.
- One centralized authentication-boundary coordinator scrubs the composer and Video Studio on
  logout or authenticated user-ID change. Active uploads and generation requests are aborted,
  preview blob URLs are revoked, and stale asynchronous results are ignored.
- The lazily loaded Project detail layer follows the same boundary: queued raw `File` objects,
  Project-file requests, inputs, menus, rename sheets, and account-scoped Project targets are aborted
  or cleared before another authenticated user can render the workspace. An executable browser
  regression proves an Account A upload cannot attach after switching to Account B.
- The rolling-deploy trigger recognizes compatibility identity from the authoritative OLD row even
  if a pre-release process replaces metadata. For every finalizing row—modern or compatibility—it
  rejects unfenced stale status/metadata writes, preserves outcome/refund/deadline controls across
  lease reclaim or quarantine, and allows only the fenced terminal transition to clear the lease.
- Image post-generation review is deterministic and local. It reuses already-prepared image bytes,
  never resends references or outputs to a model, and adds zero provider calls or credits.
- Video completion has no equivalent automated visual comparison and explicitly reports that
  verification was not performed.
- No live image or video provider request was used during release validation, and no customer
  credits were consumed.

## Verification

- Focused integrated reference, video, credit, finalization, decoder, migration, route, and private
  file-binding suite: 101/101 tests passed.
- Full Python suite with the repository's optional security dependencies: 1,282/1,282 tests passed.
- PostgreSQL grammar validation accepted all 74 migration statements. Real PostgreSQL apply and
  concurrency execution remains the explicit production gate above.
- JavaScript contract: 54 files validated; 24/24, 10/10, and 10/10 attribution/runtime fixtures
  passed; Store packet self-test passed 21/21.
- Browser-control matrix: 49/49 verifiers passed in installed Microsoft Edge, including the lazy
  Product Studio account-switch regression.
- Public accessibility matrix: 33/33 phone, tablet, and desktop scenarios passed.
- Production build preflight, native web bundle generation, backend compilation, Python lint,
  source-native privacy verification, client-secret boundary, and final diff checks passed.

The native release verifier continues to report the already-known store-submission gates: native
Android/iOS projects and RevenueCat public SDK configuration are not present in this Windows
worktree. Those gates are separate from this web/PWA reference-fidelity release.

## Release identity

- Browser/PWA/native asset token: `5.9.76-reference-fidelity-focused-3`
- Service-worker cache: `ask-crump-new-body-v1-r252`
- Release boundary: application, required atomic-video migration, protected video reconciliation
  cron, browser/native delivery, focused verifiers, release guards, and this evidence record. No
  pricing change and no production migration or deployment occurred during preparation.
