# Ask Crump database read recovery release — 2026-09-13

## Outcome

Safe database reads now get one additional bounded recovery attempt after a
transient gateway or transport failure. The retry window grows from three
delays totaling 2.5 seconds to four delays totaling 5.5 seconds. This directly
addresses the upstream HTTP 504 pattern observed in production without
replaying notifications, provider work, or ordinary database writes.

Product commit: `76a0b20`

Production deployment: `dpl_NKR33UX1Kznp2WbYXGUmi1nmHN3W`

CI: `34773670836`

## Production trigger

The 2026-09-13 reliability review found two hourly check-in scheduler requests
returning HTTP 503 after the underlying database read returned HTTP 504 on all
four attempts. One manuscript scheduler request showed the same dependency
pattern. The check-in scheduler later returned HTTP 200 at 16:00 and 17:00 UTC,
and the 14:00 run recovered after its first retry. No customer-facing runtime
error cluster was present.

The manuscript worker already runs every minute and uses a durable lease, so a
separate scheduler or whole-job replay would add duplication risk without
meaningful benefit. The check-in route is protected by the existing cron secret
and leaves an unprocessed preference eligible for the next invocation. Those
boundaries remain unchanged.

## Change boundary

- GET and HEAD database requests, plus explicitly idempotent operations, may
  make a fifth attempt after delays of 0.25, 0.75, 1.5, and 3.0 seconds.
- Every retry carries the same payload and an incremented internal retry count.
- Non-idempotent writes still make exactly one attempt.
- No scheduler cadence, authentication, notification, customer content,
  provider call, payment path, database schema, or public interface changed.
- Exhaustion remains visible as a retryable error; the application does not
  convert failed work into a false success.

## Verification

- A deterministic HTTP 504 fixture fails the first four safe reads and succeeds
  on the fifth, proving the exact delay and retry-header sequence.
- Transport exhaustion proves five attempts, content-free error details, and a
  retryable response.
- The non-idempotent-write fixture proves one attempt and no delay.
- Focused database, check-in, Code-worker, manuscript, and manuscript-output
  coverage passed 34/34.
- The complete Python suite passed 1,004/1,004.
- Ruff, Python compilation, 54 JavaScript checks, production preflight, and the
  client-secret boundary passed.
- GitHub CI passed both Python 3.12 and JavaScript jobs.
- The production deployment is Ready; `/api/health` returned HTTP 200 with
  version 5.9.76.
- The initial 15-minute production window contained no runtime-error cluster
  and no warning, error, or fatal log on the new deployment.

## Remaining evidence

The deterministic test proves recovery behavior; it does not claim the next
real upstream timeout will resolve inside 5.5 seconds. Continue observing the
scheduled routes. Escalate to a durable per-run retry design only if failures
repeat after this release or a legitimate check-in is demonstrably missed.

