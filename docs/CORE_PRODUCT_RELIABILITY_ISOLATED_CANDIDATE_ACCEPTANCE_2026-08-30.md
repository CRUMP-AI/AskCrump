# Core product reliability isolated candidate acceptance

Date: 2026-08-30  
Status: held in a clean detached local worktree; not committed or deployed  
Base commit: `86cd73feabc6b65b809999c5efc45dec239f3b68`

Revalidated on 2026-08-31 at
`C:/AskCrump-Core-Reliability-Candidate-20260830`. All 68 content hashes still
match the sealed manifest; manifest SHA-256:
`02552F372051CE2AD53E9C0093DF028C050BBBE9780CA556E443E37AB95E0525`.

## Outcome

The six compatible code-only reliability repairs are reconstructed on a clean
base instead of being selected from the shared dirty worktree. The resulting
candidate includes only:

1. truthful Project file-list and attachment failures with a Project-bound Retry;
2. durable generated document/image Project-attachment receipts, exact-target retry for temporary
   failure, and safe retargeting when the original Project no longer exists;
3. completed-manuscript saved-export recovery;
4. completed-video Project-link recovery;
5. saved-answer artifact packaging and conversation-link recovery, plus truthful server and browser
   delivery when an already-durable reply outlives chat-job cache, HTTP-response, account-sync,
   creation-navigation, or local presentation/render outages; and
6. fail-closed memory-preference persistence and request-level permission reduction.

The five changed browser assets share the single cache key
`5.9.76-core-reliability-1`; the service worker advances only from `r165` to
`r166`. No unrelated staged cache version is present.

## Exact isolation evidence

`docs/core-product-reliability-isolated-diff.json` pins the detached base,
complete path set, immutable SHA-256 hashes for the candidate content, required
feature markers, forbidden unrelated markers, and forbidden paths.

`scripts/verify-core-product-reliability-candidate.mjs` fails if:

- the base commit changes;
- any path enters or leaves the reviewed candidate;
- any hashed file changes;
- an index change is staged;
- a migration, Supabase file, deletion service, credit-confirmation asset,
  landing/auth attribution file, or demo operator script appears;
- added product source mentions credit confirmation/quotes, MarketingLanding,
  lifecycle/deletion workers, Word/PDF acquisition, demo identity, shared
  migration identities, or the credit-spending RPC; or
- the cumulative exact approval/isolation phrase disappears.

The shared all-candidate tree correctly fails this boundary by construction;
only this clean candidate is eligible for cumulative review.

## Verification

- Focused Project continuity, sync, artifact recovery, file, and chat authority suite: 50 passed.
- Complete clean-candidate Python suite: 654 passed.
- JavaScript integration contract: 47 files passed. The intentionally excluded
  credit-confirmation asset is the 48th file in the shared staging tree.
- The candidate contains no migration and no staged index change.
- Production preflight passed; its optional local Python discovery skipped, while
  the complete suite above ran with the bundled Python runtime.
- Native web bundling passed.
- The exact-diff verifier passed with 71 exact paths, 68 immutable content
  hashes, zero migrations, and zero staged index changes.
- Final diff integrity passed.
- The 2026-08-31 revalidation repeated the exact verifier, complete 654-test
  Python suite, 47-file JavaScript contract, production preflight, native web
  bundle, and diff-integrity check without changing the candidate boundary.
- A credential-free rendered Chromium fixture served from the exact detached candidate injected one
  local reply-render exception after the first HTTP response was lost and status recovery returned
  the durable assistant response. It observed one generation request, two bounded status reads,
  zero unexpected requests, `replyStatus: replied`, a null reply error, the saved assistant response
  in memory, and the fixed refresh guidance. The page contained the composer and Send action with no
  blank/error overlay, console error, page error, or `error`/`unhandledrejection` event.

The 2026-08-31 reseal also proves that a Project archived or removed between
generation and attachment is not mislabeled as retryable. The output remains
safe in Files, the receipt becomes non-retryable `missing`, and the action lets
the user choose a different Project. A later 404 during an exact-target retry
converges to the same state. Project-attachment receipts now survive account
sync through a strict allowlist of two output kinds, three fixed states, one
normalized Project UUID, fixed roles, booleans, and fixed copy; arbitrary
fields and customer-controlled receipt text are removed.

The final reseal closes a second false-failure boundary after successful generation. Once
`persist_chat_reply` has durably stored the assistant reply and generated file, the conversation is
authoritative. The later idempotency-cache completion write now opts into bounded transient database
retry and, if that cache remains unavailable, logs fixed content-free copy while still returning the
durable reply and file. It does not refund, regenerate, call AI again, or expose the exception. The
pre-fix regression reproduced the former unhandled failure after the durable write and now passes.
If the HTTP success response is lost as well, the owner-scoped status endpoint now checks the exact
active conversation before reporting a processing or retryable job. It returns only the matching
server-authored assistant message and an allowlisted public result projection when `inReplyTo`
matches the original message, with `no-store` response headers and no GET mutation. A lookup outage
falls back to the existing job state; it cannot expose another account or turn an active job into a
false completion. The new response-loss fixture proves the durable DOCX and conversation revision
are recovered while the job cache still says `processing`.

The browser completion boundary is now equally fail-closed. The primary client previously awaited
account pull after it had already marked the user message replied and rendered the assistant/file;
a rejected pull escaped into the outer send handler, which relabeled that durable success as failed.
The fallback client did not relabel success but left a rejected push unhandled. Both clients now
start their respective reconciliation in the background, catch synchronous throws and asynchronous
rejections with fixed copy, and leave the server-authoritative completed state intact. The pre-fix
source contract failed on the awaited primary sync and now proves neither runtime can route a
post-success sync failure back through message-generation error handling.
Manuscript/video creation handoffs now use the same post-success isolation in both runtimes. A
synchronous navigation throw formerly escaped directly into the message-send catch, while an async
rejection was unhandled. The clients still attempt the intended auto-open, but catch both failure
forms with fixed copy and preserve the saved reply/workspace. The corresponding pre-fix contract
failed before the wrapper existed and now proves completion owns no direct handoff call.

The final local-completion boundary now follows the same authoritative-success rule. After a normal
send or owner-scoped recovery has returned the durable server reply, a later local save, render, or
presentation exception can no longer escape into the outer send/retry catch and relabel the work
failed. Both runtimes retain the saved response as authoritative, stop the transient activity state,
and show fixed refresh guidance without inviting another generation or credit action. The pre-fix
contract failed because every normal and recovered completion call still flowed directly through
the failure-owning request scope; it now proves all five call sites use the non-throwing boundary.

## Explicit exclusions

This candidate contains no account-deletion worker or provider cleanup,
Supabase migration, credit-charge disclosure, pricing/plan/checkout change,
MarketingLanding or campaign attribution change, Word/PDF guide, lifecycle
decision/export change, demo-account tooling, API repository integration,
transcription integration, social/Search Console action, store submission,
provider run, production test write, or spend.

The API team's production v0.33 transcription endpoint remains a separate
future server-side, feature-flagged integration. Its API key must never be sent
to browser code and it is not part of this candidate.

## Action-time boundary

No commit, preview, deployment, promotion, or production mutation is authorized
by this record. The only applicable approval remains the exact phrase in
`docs/CORE_PRODUCT_RELIABILITY_RELEASE_ACTION_RECORD_2026-08-30.md`.
