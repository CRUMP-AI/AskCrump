# Ask Crump 5.9.70 database-read recovery release

Date: 2026-08-28

Production version: 5.9.70

Code commit: `abfc6ceff24a3ddc121dc10a41f7b4bd9cdc7606`

Production deployment: `dpl_8MwNZ78Rk5FFFgqEi1g2kYjQYVrY`

## Outcome

Transient Supabase Data API failures no longer fail a safe read immediately. Ask Crump now retries
only idempotent `GET` and `HEAD` database requests, at most three times, with bounded backoff. An
exhausted safe read returns explicit retry guidance to the existing client recovery path.

Inserts, updates, upserts, deletes, and RPC calls still receive exactly one server attempt. This
avoids silently duplicating a customer, billing, credit, conversation, or artifact mutation when a
write completed but its response was lost.

## Evidence that selected the work

The trailing 24-hour Vercel runtime review found 28 `/api` 5xx database failures in two clusters:

- 17 `503` failures between 15:06 and 15:39 UTC, affecting synchronization reads/writes and the
  credit-status read across two reported users;
- 11 earlier categorical database-connection failures across 11 reported users, including login
  and scheduled manuscript/check-in paths.

The newer cluster carried a string-shaped provider detail, while the older cluster carried an empty
string. Neither was sufficiently structured to justify a schema, query, or capacity change. The
current Supabase API requests had returned to HTTP 200, and the contemporaneous Postgres log review
showed ordinary checkpoints rather than a corresponding connection or resource-exhaustion cluster.
The evidence therefore supported a transient Data API transport repair and continued observation,
not a shared-database redesign.

The boundary follows Supabase's documented pattern: retry transient database reads, mark later
attempts with `X-Retry-Count`, and never apply unbounded retries. Supabase also identifies
`PGRST001` as a `503` internal database-connection error:

- [Automatic PostgREST retries for transient errors](https://supabase.com/changelog/45071-automatic-postgrest-retries-for-transient-errors)
- [PostgREST error codes](https://supabase.com/docs/guides/api/rest/postgrest-error-codes)

## Correction

- Safe reads retry transient network errors and HTTP `408`, `503`, `504`, or `520` responses.
- The delays are bounded to 0.25, 0.75, and 1.5 seconds, for no more than four total attempts.
- Retry attempts carry `X-Retry-Count: 1`, `2`, or `3` for server-side diagnosis.
- A new per-request timeout explicitly caps connection and pool acquisition at five seconds while
  retaining the prior overall request deadline.
- Retry logs contain only status, attempt, delay, and exception category. They exclude database
  tables, filters, account identifiers, session values, provider response text, and private data.
- An exhausted safe read returns `Retry-After: 2`, `shouldRetry: true`, and `retryAfter: 2`.
- A write or non-transient read never enters the automatic retry loop.
- The application advanced to 5.9.70 and PWA cache revision 104.

## Verification

- A mocked `503`, `503`, `200` read proved two retries, the exact retry headers, bounded delays,
  and one successful result.
- A repeated connection failure proved four total read attempts, categorical details only, and the
  bounded retry response.
- A `503` insert proved exactly one server call and no delay.
- A `400` read proved exactly one server call and no retry.
- The privacy response regression proved that exhausted reads expose only generic retry guidance.
- All 413 Python tests passed.
- Ruff passed for `backend` and `tests`; Python compilation passed for `backend` and `api`.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight, native web-bundle generation, Android API 36 source verification, store
  metadata checks, and mobile signing-source controls passed.
- GitHub CI run `33223161380` passed.
- Hosted unsigned Android App Bundle run `33223161346` passed.
- Hosted unsigned iOS Release compile run `33223161377` passed.

## Production evidence

- Deployment `dpl_8MwNZ78Rk5FFFgqEi1g2kYjQYVrY` reached `READY` from the exact feature commit.
- Production health returned HTTP 200 and version 5.9.70.
- The live application returned HTTP 200 and contained version 5.9.70.
- The live service worker returned `ask-crump-new-body-v1-r104` and versioned 5.9.70 assets.
- The exact deployment had no warning, error, or fatal runtime log and no runtime error group in
  the initial release window.

No production account, login, synchronization mutation, conversation, Project, artifact, payment,
subscription, credit charge, or synthetic analytics event was created for verification.

## Rollback

The prior production deployment `dpl_4fb9j634THuCAWbj8XcJUgPGdcME` remains available. This release
requires no database, schema, RLS, environment, authentication, payment, pricing, entitlement, or
provider migration.

## Remaining evidence

Observe organic traffic for another database-transport failure. A recovered read should leave only
the new categorical retry warning and no customer-visible `503`; an exhausted read should remain a
single bounded final failure. Reconcile any recurrence by route and attempt count before changing
the shared database boundary. Do not manufacture production faults or customer records to prove the
retry path.
