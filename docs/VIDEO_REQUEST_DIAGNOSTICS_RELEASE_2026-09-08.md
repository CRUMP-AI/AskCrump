# Video-request diagnostics release — 2026-09-08

## Outcome

Ask Crump now records every video-service rejection under a stable, privacy-safe stage and error
code. A rejected **Create video**, **Continue scene**, or status request can be distinguished as
request validation, reference preparation, provider budget protection, generation, continuation
parent validation, continuation generation, or status lookup.

The operational record contains only stage, HTTP status, stable code, and retryability. It excludes
the account ID, prompt, filename, file or job ID, Project, provider message, request identifier, and
all other customer content. Unknown stages and unstructured codes fail closed to `unknown` and
`VIDEO_ERROR`.

## Evidence and scope

A read-only seven-day production review found one HTTP 400 on `POST /api/media/video`. No media job
was created, which proves the rejection occurred before asynchronous provider work began. The old
route logged only the HTTP status, so its exact historical cause cannot be recovered honestly. The
Quick and Extendable duration path was inspected and tested; both are deliberately normalized to
the provider-supported eight seconds, so no working control was changed on speculation.

This release changes operational logging only. User-visible errors, HTTP statuses, provider budget
guards, plan/credit checks, confirmations, retries, refunds, video settings, saved files, Projects,
and provider routing remain unchanged. It creates no database or Storage migration and changes no
analytics, attribution, lifecycle, billing, marketing, or API-repository contract.

## Verification

- All **870 Python tests** were collected: **868 passed** and two environment-dependent tests were
  skipped.
- All **49 JavaScript files** and all six attribution runtime cases passed.
- Focused video-engine, product, and observability coverage passed 33 checks.
- Production preflight and diff integrity passed.
- The real browser button-state proof passed with the correct neutral and Project-context composer
  recovery, focused input, no stale tool chip, and no console error.
- Privacy coverage proves private user/provider text is absent from logs and unstructured stage/code
  inputs fail closed.
- Main CI run **34235795498** passed.
- The exact production deployment is `READY` on all six aliases.
- Both canonical Ask Crump health endpoints and both Clever Crump homepages returned HTTP 200.
- The initial production window contained no runtime-error cluster and no warning/error/fatal log.
- Verification created no account, prompt, video, provider request, media job, file, Project, event,
  credit charge, subscription, payment, or customer-data write.

## Release identity

- Feature commit: `9578d0c4e4a2680cf4beedaf482938c6e2f584e4`
- Production deployment: `dpl_7u3Mq1HrGDYgLV4T7p3U2qGds3K8`
- Status: `READY`
- CI: `https://github.com/CRUMP-AI/AskCrump/actions/runs/34235795498`
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases

## Remaining acceptance work

1. Observe the next legitimate video rejection and verify that its stage/code groups correctly.
2. Use repeated categorical evidence—not a single occurrence—to decide whether UI recovery, product
   copy, provider configuration, or budget policy needs a change.
3. Keep prompts, filenames, identifiers, provider messages, and customer content out of shared logs.
4. Preserve the already verified button-integrity release and repeat the full signed-device control
   audit on exact iPhone and Android store candidates before submission.
