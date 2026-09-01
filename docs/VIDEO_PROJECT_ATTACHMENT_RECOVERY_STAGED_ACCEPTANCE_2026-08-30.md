# Generated-video Project attachment recovery staged acceptance

Date: 2026-08-30  
Status: accepted locally; not committed or deployed

## Outcome

A completed generated video can no longer falsely imply that its selected
Project link succeeded. The MP4 remains safe in the owner's Files, and the
finished-video card now exposes the exact Project outcome and a bounded retry
when a retry can help.

## Defect closed

The completed-video status route attempted to attach the already-saved video
file to its selected Project, caught every exception, discarded it, and still
returned success. A temporary database failure therefore left the video in
Files but omitted it from the Project without an explanation or exact-target
recovery action.

## Staged behavior

- A successful attachment returns a fixed `attached` receipt and renders
  **Open Project**.
- A temporary attachment failure keeps the successful video and returns a
  fixed `failed` receipt. The card states **Safe in Files · Project link needs
  retry** and renders **Retry Project save**.
- The retry performs one authenticated POST to the existing owner-scoped,
  idempotent `/api/projects/{projectId}/files` endpoint with the existing file
  ID and `generated_video` role. It cannot generate or continue a video, call a
  provider, authorize a feature, consume a credit, or manufacture an event.
- A confirmed unavailable Project returns a fixed, non-retryable `missing`
  receipt. The video remains available in Files and the card does not offer a
  futile retry to the unavailable Project.
- The receipt contains only fixed status, Project ID, role, retry flag, and
  fixed message. It excludes prompts, filenames, storage paths, signed URLs,
  account details, provider/model details, exception text, and arbitrary
  upstream data.
- The changed product script uses `5.9.76-video-project-recovery-1` across web,
  service-worker precache, and native bundling.

## Verification

- Successful Project attachment and exact `generated_video` role are covered.
- Temporary attachment failure is covered and proves private exception text is
  absent while the video response remains successful and available.
- Confirmed missing-Project handling is covered and proves private exception
  text is absent and automatic retry is disabled.
- A source-level contract proves the UI retry uses only the existing
  Project-file endpoint and contains no continuation or credit path.
- Focused Python/Project/video suite: 53 passed.
- Full Python suite: 695 passed.
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

## Release boundary

No Supabase schema or migration, production Project/file/account write,
model/provider call, video generation or continuation, credit action, synthetic
event, social publication, profile link, Search Console action, price, plan,
payment-provider setting, store submission, lifecycle message, or spend
changed. Commit and deployment remain a separate action-time decision.
