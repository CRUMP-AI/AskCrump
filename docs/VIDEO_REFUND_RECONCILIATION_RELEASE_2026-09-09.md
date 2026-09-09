# Video refund reconciliation release — 2026-09-09

Status: verified in production; first legitimate paid rejection remains an outcome gate

## Evidence-led finding

A privacy-safe 30-day production aggregate contained 33 video jobs: 28 ready and five
failed. Every failure was an extendable-video continuation from 2026-08-17 with the
provider code `INVALID_ARGUMENT`, before the current continuation payload correction.
Later extendable jobs completed. All five failed rows recorded `providerAccepted=false`
and no paid or included usage receipt, so this is not evidence of customer credit loss.
No prompt, file, media, account identifier, or customer metadata was inspected.

The same review exposed a current latent accounting defect in the immediate provider-
rejection path. Ask Crump returned the usage charge after a newly reserved video or
continuation failed before provider acceptance, but the private `media_jobs` row remained
`billing_refunded=false`. If that row was later polled, the existing idempotent refund
path could unnecessarily attempt the same reconciliation again. A first real paid failure
would also leave operating evidence that contradicted the completed refund.

## Correction

- `VideoServiceError` can now carry the private ID of a job that was reserved and marked
  failed before provider acceptance.
- Both first-generation and continuation provider-rejection paths attach only that
  internal job identity after persisting their bounded diagnostic state.
- The route returns the usage or credit charge first, then marks that exact owner-scoped
  job `billing_refunded=true`.
- If the bookkeeping update is temporarily unavailable, Ask Crump emits only a fixed
  categorical warning. The flag remains false so the existing status route can retry the
  idempotent refund reconciliation after storage recovers.
- Rejections before any job is reserved still return their charge without inventing a
  database target. Non-refundable post-provider-acceptance failures remain unchanged.

The job identity is never added to the error response or log. Provider requests, video
prompts, files, billing receipts, prices, feature allowances, and database schema are
unchanged.

## Verification

- Feature commit: `159ff494255f60910e95568788627ac9897139a1`
- Focused video/refund/Project coverage: 26 passed
- Complete Python suite: 919 collected; 917 passed; two environment-dependent skips
- JavaScript validation: 49 files and six rough-to-useful attribution cases
- Ruff, Python compilation, production preflight, native web bundling, store metadata,
  source privacy, mobile signing controls, and Git diff integrity: passed
- Local native project verification remained at its documented Windows/source boundary:
  generated Android and iOS projects and RevenueCat public keys are not present in this
  checkout. The backend-only change did not match the native workflow path filters.
- Main CI: `34362161458`, passed
- Production deployment: `dpl_H4VsPxmvaXb87yzc56xVjBFd5i83`, READY on all six aliases
- Four custom-domain health requests returned HTTP 200 and version 5.9.76
- An unauthenticated production video request returned 401 before parsing, charging, or
  contacting a provider
- The exact deployment showed four 200 responses, the one expected 401, no 5xx response,
  no warning/error/fatal log, and no runtime-error cluster in the inspected window

No production video, provider request, usage charge, refund, customer-data write, account,
Project, file, payment, or synthetic growth event was created for verification.

## Outcome boundary

Delivery and deterministic reconciliation are verified. Observe the first legitimate
paid video rejection and reconcile the provider-acceptance flag, idempotent credit or
allowance return, private job marker, and visible recovery before claiming real-world
refund reliability.
