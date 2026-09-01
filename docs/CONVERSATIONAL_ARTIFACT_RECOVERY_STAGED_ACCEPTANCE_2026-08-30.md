# Conversational artifact recovery staged acceptance

Date: 2026-08-30  
Status: accepted locally; not committed or deployed

## Outcome

When Crump has already written a document, presentation, spreadsheet, Markdown,
or text response but downloadable-file packaging fails, the saved answer now
retains a visible recovery action. The user can package that existing answer
without sending the prompt again, calling AI again, or paying again.

## Defect closed

The chat route previously returned a transient `artifactError` only in the live
response. It did not persist that state on the assistant message, neither chat
client copied it, and the rendered conversation had no retry action. A user
could therefore receive useful written work but silently lose the requested
downloadable file after a storage or packaging interruption.

## Staged behavior

- Packaging failure persists an allowlisted `artifactRecovery` receipt on the
  server-authored assistant message and renders **Retry file packaging**.
- The retry request carries only the original user-message ID. The server
  owner-checks the completed chat job and conversation, then packages the
  already-saved assistant answer. It accepts no replacement prompt, response,
  filename, title, URL, provider, model, or arbitrary content from the client.
- DOCX, PDF, PPTX, XLSX, Markdown, and text recovery use a deterministic UUID
  derived from account, original message, and format. Stable storage upsert and
  metadata reuse make repeated or concurrent retries return one logical file
  instead of charging storage with duplicates; a prior object whose metadata
  write was interrupted can be completed on retry.
- The recovered artifact is merged into the existing assistant message through
  the owner-scoped atomic chat-reply RPC. A repeated endpoint call reuses the
  existing artifact instead of rebuilding it.
- If the file is packaged but the conversation merge temporarily fails, the
  response and chat-job cache keep the artifact available, render **Retry saved
  file link**, and never discard the file from Files.
- If the assistant reply and file have already been durably merged but the later
  chat-job completion-cache write fails, that cache outage no longer turns the
  completed request into an unhandled customer-facing failure. The idempotent
  cache write requests bounded transient retry; if it remains unavailable, the
  route returns the authoritative durable reply and file without refunding or
  inviting generation again.
- If that HTTP success response is also lost, the status route checks the exact
  owner-scoped, non-deleted conversation before returning `processing` or
  `retryable`. A matching server-authored assistant reply is projected back into
  the ordinary completed-response shape, including only the known output fields
  and conversation revision. The read is `no-store`, mutates nothing, and falls
  back to the prior job state if the reconciliation lookup is unavailable.
- After either browser runtime has accepted the completed server response, its
  account reconciliation is best-effort background work. A failed pull in the
  primary client can no longer escape into the send error handler and relabel the
  delivered reply/file as failed; a failed fallback push is caught rather than
  becoming an unhandled rejection. Both retain fixed, content-free console copy
  and allow the ordinary background sync system to retry later.
- Manuscript/video auto-open handoffs are likewise caught background work after
  completion. Synchronous navigation throws and asynchronous rejections preserve
  the saved reply/workspace and emit only fixed copy; they cannot route back into
  generation failure or retry handling.
- Once a normal send or owner-scoped status recovery has returned a completed
  server response, local save/render/presentation work is also isolated from the
  request failure handler. A local exception preserves authoritative success and
  shows fixed refresh guidance instead of labeling the reply failed or inviting
  another generation or credit action.
- If the conversation already belongs to an active Project, the existing
  idempotent Project-file attachment is restored and returns the same truthful
  attached/failed receipt used by ordinary generation.
- Successful real recovery records the existing content-free
  `ArtifactPackaged` and `AhaReached` milestones. Analytics failure remains
  incapable of breaking delivery.
- The recovery path contains no AI call, feature authorization, usage or credit
  consumption, refund, provider call, generation request, schema migration, or
  synthetic production event.
- Recovery metadata is limited to an allowlisted status, format, optional fixed
  `resume` purpose, retry boolean, and server-fixed message. The sync sanitizer
  replaces arbitrary client copy and rejects unknown formats or fields.
- The changed `app.js` and `crump-5.0.js` assets use
  `5.9.76-artifact-packaging-recovery-1` across web, service-worker precache,
  and native bundling.

## Verification

- Saved-answer packaging and deterministic file identity are covered.
- Repeated recovery proves one artifact creation and one stable artifact ID.
- Existing stable file metadata proves the second call performs no storage
  upload or database upsert.
- Packaging failure and chat-job lookup failure return fixed retryable responses
  and prove private exception details are absent.
- Conversation persistence failure proves the finished artifact remains
  available with a retryable saved-link receipt.
- A separate pre-fix regression proves that a chat-job cache finalization outage
  after successful conversation persistence cannot hide the durable document,
  trigger a refund, leak private diagnostics, or report the request as failed.
- The response-loss fixture leaves the job cache in `processing` while the
  conversation already contains the durable DOCX. Status recovery proves the
  exact owner/chat/message filters, returns the saved file and revision, and does
  not restart generation.
- A pre-fix browser contract proves primary completion no longer awaits account
  pull and that both primary/fallback sync promises handle rejections without
  feeding generation retry or error-state paths.
- A second pre-fix browser contract proves neither completion function directly
  invokes creation navigation and that both wrappers catch synchronous and
  asynchronous handoff failures.
- A third pre-fix browser contract proves all normal and recovered completion call
  sites enter a non-throwing presentation boundary, so local UI failure cannot
  re-enter send/retry failure handling after server success.
- The sanitizer proves arbitrary message text and unknown formats do not cross
  the recovery boundary.
- A client/server source contract proves the retry endpoint cannot resend the
  AI request, authorize a feature, consume/refund credits, or call AI.
- Focused artifact/chat/file/sync/analytics/cache suite: 142 passed before the
  final lookup-outage fixture; the complete suite below includes that fixture.
- Full Python suite: 702 passed.
- JavaScript integration contract: 48 files passed.
- Production build preflight: passed. Its optional local Python compile guard
  did not discover the bundled runtime; the complete suite above executed with
  the bundled Python runtime.
- Native web bundle: regenerated successfully.
- Git diff integrity: passed, with only the existing `public/landing.js`
  CRLF-to-LF advisory.
- The separate native store-readiness audit still reports the existing missing
  iOS project, RevenueCat Android/iOS public keys, and Android
  `google-services.json`. This candidate did not create or change those
  external prerequisites.
- The connected desktop browser runtime remains unavailable because its sandbox
  helper fails before browser selection. No rendered-browser claim is made.

The 2026-08-31 cumulative isolated reseal adds the post-persistence cache-outage
fixtures above. Its focused Project/sync/artifact/file/chat suite passes 50 tests;
the full clean candidate passes 654 Python tests, 47 JavaScript contracts, Ruff,
compilation, production preflight, native bundling, and diff integrity. The
historical 702-test shared staging result above remains the evidence for the
original standalone recovery acceptance.

## Release boundary

No Supabase schema or migration, production conversation/file/Project/account
write, AI/model/provider call, feature authorization, usage or credit action,
synthetic event, social publication, profile link, Search Console action,
price, plan, payment-provider setting, store submission, lifecycle message, or
spend changed. Commit and deployment remain a separate action-time decision.
