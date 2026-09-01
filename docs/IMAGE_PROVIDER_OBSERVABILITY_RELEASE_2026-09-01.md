# Image-provider observability release — 2026-09-01

## Outcome

Ask Crump now records image-provider failures as stable, privacy-safe operational categories instead
of turning each provider request identifier or message into a separate apparent incident. The fixed
categories are `safety`, `verification_required`, `authentication`, `billing`, `invalid_reference`,
`rate_limit`, `request_rejected`, `upstream`, and `unexpected`.

Expected, user-correctable outcomes use warning severity. Provider configuration, upstream, and
unexpected failures use error severity. A safety rejection can add only allowlisted moderation stage
and category values at informational severity. Image prompts, reference-image names, provider
messages, request identifiers, and other request-specific content are excluded from these logs.

## Evidence and scope

A read-only 24-hour production review found 18 one-occurrence error groups on older deployments.
They represented only two actual failure families: 13 `invalid_image_file` responses and five
`moderation_blocked` responses. Unique provider request identifiers and response messages prevented
those outcomes from grouping into useful operational signals.

This release changes only failure classification and operational logging. Existing user-facing
messages, HTTP status codes, retry decisions, safety behavior, credit/refund behavior, generated-file
handling, and provider routing remain unchanged. No database, Storage, analytics, billing, campaign,
or API-repository contract changed.

## Verification

- All **756 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Changed-file Ruff checks, Python compilation, production preflight, native web-bundle creation,
  store metadata checks, mobile signing-source controls, and diff integrity passed.
- Executable coverage proves that two invalid-image responses with different provider request IDs
  and different private messages emit the exact same operational signature.
- Coverage also proves stable categorical logging for safety, upstream failure, and transient retry;
  unsafe provider code/type strings fail closed to `unknown`.
- The six-alias production deployment is `READY` on the exact feature commit.
- Both canonical health endpoints returned HTTP 200 and version 5.9.76.
- The inspected deployment window contained three HTTP 200 requests, no 4xx/5xx request, no
  warning/error/fatal log, and no runtime-error cluster.
- Verification created no provider request, image, file, credit charge, customer write, or database
  mutation.

## Release identity

- Feature commit: `5b5819c4cdac2c5d2003dad794569a96535457d8`
- Production deployment: `dpl_4jwfdMeuu3yJ3fFRmJ5uphfDNTNP`
- Status: `READY`
- Build duration: about 34 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`, `www.clevercrump.com`, and the two
  Vercel project/main aliases

## Remaining acceptance work

1. Observe the next legitimate production image-provider rejection and confirm that repeated outcomes
   aggregate under the stable category rather than fragmenting by provider request.
2. Compare category counts with user-visible recovery and refund outcomes before changing retry,
   recovery, or product copy.
3. Keep detailed provider diagnostics out of shared logs. If correlation later becomes necessary, use
   a bounded internal correlation mechanism that cannot expose prompts, filenames, customer content,
   or provider messages.
