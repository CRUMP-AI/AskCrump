# Project output attachment recovery staged acceptance

Date: 2026-08-30  
Status: accepted locally; not committed or deployed

## Outcome

A document or image created from inside a Project can no longer lose its final
Project association silently. The generated file remains safe in the owner's
Files collection, the response reports whether each output was attached, and a
failed association exposes a targeted retry that does not repeat generation or
credit use.

The 2026-08-31 isolated-candidate reseal closes two further truth gaps: a
deleted/archived original Project is a permanent `missing` state rather than a
retryable outage, and the bounded receipt survives reload/cross-device account
sync instead of being stripped.

## Defect closed

The chat route previously wrapped the final generated-output association in a
broad exception handler and discarded every failure. A successful document or
image therefore appeared complete even when its `project_files` relationship
was never created. The output still belonged to the account, but the person had
no explanation, no retained Project target, and no direct recovery action.

The same helper processed image and document outputs sequentially, so one
failure could also prevent a second valid output from being considered.

## Staged behavior

- Image and document associations execute independently.
- Each attachable output returns only a fixed receipt containing `status`, the
  owner-checked Project ID, the fixed role, `shouldRetry`, and—on failure—a
  fixed content-free message.
- An attached output renders **Open Project** for the exact destination.
- A failed output says it is safe in Files and renders **Retry Project save**.
- The retry uses the original Project ID and the allowlisted
  `generated_document` or `generated_image` role.
- A confirmed unavailable original Project renders **Add to another Project**,
  never retries the dead ID, and retains the already-created file in Files.
- If a retry receives a later Project 404, the local receipt converges to the
  same non-retryable missing state and asks for a different Project.
- Account sync retains only the two known output kinds, normalized Project UUID,
  fixed roles, `attached`/`failed`/`missing` states, derived retry boolean, and
  fixed copy. Arbitrary keys, messages, roles, and secrets are discarded.
- The retry calls only the existing owner-scoped, idempotent Project-file
  attachment endpoint. It does not call the model/provider, recreate the file,
  authorize a feature, spend credits, or manufacture an activation event.
- A generated image now has the same Add/Retry/Open Project continuity action
  as a generated document.
- At original acceptance, the changed `app.js` and `crump-5.0.js` assets used
  `5.9.76-project-output-recovery-1`. The current shared worktree carries the
  later cumulative `5.9.76-artifact-packaging-recovery-1` cache key across web,
  service worker, and native bundling. That later key does not broaden this
  Project-output release record or authorize the separate artifact-packaging
  recovery candidate.

The receipt contains no filename, file contents, prompt, response, storage path,
provider/model detail, exception text, customer identifier, or arbitrary URL.
All Project/file ownership checks remain server-authoritative.

## Verification

- Independent success/failure unit coverage proves one failed image association
  does not prevent a document association and preserves the owner/Project scope.
- Three pre-fix regressions prove permanent Project loss, stale retry-to-404,
  and cross-device receipt stripping; all pass after the repair.
- Route coverage proves the bounded failure receipt reaches the chat response.
- Existing Project-file endpoint coverage proves owner scope, confirmed 404,
  retryable database unavailability, and idempotent attachment behavior.
- Full Python suite: 687 passed.
- JavaScript integration contract: 48 files passed.
- Production build preflight: passed. Its optional local Python compile guard
  did not discover the bundled runtime; the complete suite above executed with
  the bundled Python runtime.
- Native web bundle: regenerated successfully.
- Git diff integrity: passed, with only the existing `public/landing.js`
  CRLF-to-LF advisory.
- The connected desktop browser runtime remains unavailable because its sandbox
  helper fails before browser selection. No rendered-browser claim is made.

The resealed clean candidate passes the 44-test Project/sync/artifact/chat
focus, all 649 clean-candidate Python tests, the 47-file JavaScript contract,
Ruff, compilation, production preflight, native bundling, and diff integrity.

## Release boundary

No Supabase schema, migration, production Project/file/account write, model or
provider call, credit action, synthetic event, social publication, Search
Console action, price, plan, payment-provider setting, store submission,
lifecycle message, or spend changed. Commit and deployment remain a separate
action-time decision.
