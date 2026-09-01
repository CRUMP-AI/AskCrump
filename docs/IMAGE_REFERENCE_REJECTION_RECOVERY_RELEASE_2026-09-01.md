# Image-reference rejection recovery release — 2026-09-01

## Outcome

Ask Crump now prevents large image-edit inputs from reaching the provider in an unsupported form and
turns a rejected edit reference into an actionable replacement flow. The user's prompt, image-tool
settings, and refunded usage remain available; the rejected file is not silently restored, the file
chooser opens, and another attempt cannot consume usage until a different JPG, PNG, or WebP reference
is attached.

The existing Precision Edit studio remains the deliberate product boundary for person edits. Users
select the pixels themselves with a brush or lasso, can preview bounded warmth, exposure, and
saturation changes locally, and can request guided visible-complexion changes inside that selection.
Ask Crump does not identify a person or infer, classify, or relabel race or ethnicity. Model-assisted
edits continue to require identity, facial-feature, skin-texture, and unselected-pixel preservation.

## Incident evidence and root cause

A read-only production review found 13 `/api/chat` HTTP 502 responses on one August 30 deployment.
Every sampled failure was a provider `invalid_image_file` rejection. All 13 occurred before the
August 31 visual-media hardening release began decoding, orienting, resizing, and normalizing edit
references to PNG. The current production window showed no later `invalid_reference` recurrence;
one unrelated later HTTP 400 did not contain enough evidence to assign the same cause.

The remaining pre-provider edge was bounded rather than guessed away. Regular edits limited only
their longest edge, so a large square or high-entropy RGBA input could still become an unexpectedly
large PNG. Ask Crump now caps regular edit inputs at 8,388,608 pixels, encodes the exact provider PNG
before spend, and rejects any encoded source or mask at the provider's 50 MB boundary. The official
[OpenAI image-generation guide](https://developers.openai.com/api/docs/guides/image-generation)
documents the same-format/same-size mask rule, alpha-mask requirement, and less-than-50-MB input
limit used by this guard.

## Recovery and privacy contract

- `IMAGE_SAFETY_REJECTED` requires changed wording or a changed reference.
- `INVALID_IMAGE_EDIT_SOURCE` and `IMAGE_EDIT_SOURCE_TOO_LARGE` require a different reference.
- Only allowlisted `action`, `usageRestored`, and `changeRequired` values survive browser transport
  and synchronized message state; provider messages, prompts, policy fields, and credit values cannot
  be injected into recovery metadata.
- Saved safety-recovery records from the previous release remain compatible, with their change rule
  derived from the server-owned error code.
- Invalid-reference recovery restores the prompt and image settings but removes the failed reference.
  Pressing Send without a different reference stops before usage preflight or provider work.
- This release adds no prompt, filename, image, mask, provider-message, request-ID, or customer-content
  logging. It changes no database, Storage, analytics, billing, entitlement, price, or API-repository
  contract.

## Verification

- All **770 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Changed-file Ruff checks, explicit Python compilation, production preflight, native web-bundle
  creation, store metadata, mobile signing-source controls, and diff integrity passed.
- A credential-free mobile browser fixture proved both recovery branches at a 390-by-844 viewport:
  the safety branch restored the reference and blocked an unchanged resend; the invalid-reference
  branch restored the prompt, removed the rejected file, opened the chooser, and blocked usage until
  replacement. No console error was observed.
- Both canonical health endpoints returned HTTP 200 and version 5.9.76.
- The five changed/runtime assets served by `www.askcrump.com` matched the exact local SHA-256 bytes.
- The deployment-specific observation window contained four HTTP 200 requests, no 4xx, no 5xx, no
  error/fatal log, and no runtime-error cluster.
- Verification created no production provider request, image, file, credit charge, customer write,
  analytics event, or database mutation.

## Release identity

- Feature commit: `f8feca89dfc6ba46308fbd40650ab59532cd9de1`
- Production deployment: `dpl_81rCqFpZMKTCZ8UuiW8K9u4JPuk5`
- Status: `READY`
- Build duration: about 35 seconds
- Canonical hosts verified: `askcrump.com` and `www.askcrump.com`

## Remaining acceptance work

1. Observe the next legitimate rejected image reference and confirm that the replacement action,
   refund, and successful follow-up are understandable without support.
2. Do not manufacture a production provider rejection or use a customer image for acceptance.
3. Continue evaluating selected-region identity fidelity on consented, non-sensitive test images;
   use the local deterministic controls for exact tonal changes and model assistance only when a
   generative transformation is actually necessary.
