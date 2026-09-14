# Ask Crump database gateway recovery release — 2026-09-14

## Decision

Recover from observed transient Supabase gateway failures only where replay is safe. Read-only GET
and HEAD requests may now retry HTTP 500 and 502 responses with the existing bounded backoff.
Explicitly declared idempotent writes and RPCs may retry HTTP 502, but not HTTP 500. Ordinary inserts,
updates, deletes, and RPCs remain one-attempt operations.

## Production evidence

Between 13:26 and 13:32 UTC, four scheduled `/api/cron/manuscripts` calls returned 503. The underlying
database responses included one HTTP 500 and three HTTP 502 failures that the transport labeled
non-retryable after one attempt. The same worker returned 200 between those failures and on every
observed call from 13:33 through 13:39 UTC; several successful calls recovered from HTTP 504 through
the existing bounded read retry.

The service-role aggregate contained no active manuscript run and no pending Crump Code refund.
The incident therefore did not strand customer work, but it exposed a real recovery gap: safe reads
did not treat 500/502 gateway responses as transient, and retry-safe lease-claim RPCs did not treat
502 as transient.

No prompt, response, account identifier, filename, Project, database payload, provider output, or
customer content was read or retained in this review.

## Safety boundary

- Safe reads retry 500 and 502 with the existing delays of 0.25, 0.75, 1.5, and 3 seconds.
- A write or RPC retries only when its caller already declares the operation idempotent.
- Explicitly idempotent writes/RPCs retry 502, but a database-internal 500 remains one attempt.
- Every replay keeps the exact payload and adds only the categorical retry-count header.
- Non-idempotent writes remain one attempt for every failure status.
- Exhausted failures remain visible as bounded, content-free database errors.

## Verification

The transport suite proves successful 500/502 read recovery, successful same-payload 502 recovery
for an idempotent lease claim, and one-attempt behavior for an idempotent RPC receiving HTTP 500.
The adjacent sync, Crump Code, and manuscript durability contracts remain green.

Local verification passed:

- focused database/sync/code/manuscript coverage: **40/40**;
- complete backend suite: **1,063/1,063**;
- JavaScript validation: **54/54**; and
- browser-control matrix: **47/47**.

Commit `249da8f` passed GitHub CI `34862905848` and deployed automatically as
`dpl_Eb1FPK48ja68dghGShMcR5Vuob6K`. The deployment reached Ready on all six aliases. Its first five
observed requests were HTTP 200, with no grouped runtime error and no warning, error, or fatal log.
That clean initial window confirms delivery and ordinary worker operation; a later naturally
occurring 500/502 is still required to distinguish in-request recovery from simple non-recurrence.

A wider production observation through 2026-09-14 19:10 UTC covered **217** natural
`/api/cron/manuscripts` requests after the release boundary. The status grouping contained at least
**343 HTTP 200** responses and one expected HTTP 401 boundary across the application; an explicit
HTTP 503 query returned no result. The same window contained no warning/error/fatal log and no further
`refund_reconciliation_failed` signal. This is meaningful non-recurrence evidence across more than
three and a half hours of scheduled work; it does not prove recovery from a new 500/502 because no
such post-release gateway failure was observed, and it does not close the full 24-hour recurrence
gate.

## Follow-up

Observe the scheduled worker after release. Do not widen retry status, attempt count, or write scope
without another reproduced transient class and an idempotency proof. A future recurrence should be
classified separately as recovered within the request, recovered by the next cron invocation, or
stranded customer work.
