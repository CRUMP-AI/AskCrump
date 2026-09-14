# Sync push transient recovery gate release — 2026-09-13

## Production signal

At 00:05:00 UTC, production returned HTTP 503 for one `POST /api/sync/push` after Supabase returned
HTTP 504. The database wrapper correctly labeled the non-idempotent write as a one-attempt operation.
The same deployment then recorded a successful sync push at 00:05:08 and five more successful pushes
through 00:08:29.

The client already places every push into a user-scoped local queue before making the network request.
A failed or invalid response leaves the queue untouched. The next visible-tab synchronization,
reconnect, or explicit synchronization flushes that queue; it is deleted only after an accepted
response. Server chat writes use the atomic `apply_chat_sync` compare-and-apply function, and a replay
that is already present becomes an ignored/stale row followed by an authoritative pull.

This evidence supports preserving the existing write policy. Widening automatic database retries from
one isolated, already recovered event would add duplicate/latency risk without evidence of user-work
loss.

## Recurrence gate

Commit `b699d1adbc5b82bfdbc3a92f1a676ba3e3e48b74` adds a real-browser fixture using the production
`sync-manager.js`. It requires all of the following:

1. a 503 `DATABASE_ERROR` with `shouldRetry: false` still returns `queued: true`;
2. exactly one local queue entry remains after that response;
3. the next explicit flush sends the identical normalized payload;
4. a successful response marks the flush complete and removes the queue entry; and
5. the browser produces no console or page error.

The fail-closed browser inventory now requires this verifier, bringing the complete interaction matrix
to 47 exact flows.

## Verification

- Browser control matrix: 47/47.
- Python: 1,052/1,052.
- JavaScript: 54/54, including 21/21 store packet self-tests.
- Focused sync/button contracts: 41/41.
- Ruff and diff integrity: passed.
- Production deployment `dpl_72E2GAmSaUVEHHYQ8sAmSu8xEPXk`: Ready for the exact feature commit.
- GitHub CI `34793041425`: passed, including Python, JavaScript, browser controls, public
  accessibility, dependency audits, production bundle, and store evidence.
- Four public health endpoints: HTTP 200 at version 5.9.76.
- Initial exact-deployment sample: seven HTTP 200 responses and no warning, error, or fatal log.

## Boundaries and next action

This release adds deterministic prevention evidence; it does not create a synthetic sync write or
inspect conversation content. Preserve the current queue and atomic write semantics. Investigate a
server-side retry or durable server outbox only if production shows recurrence, a queue that does not
subsequently flush, or a legitimate user reports missing cross-device work.

No customer content, account, payment, credit, Project, file, generation, campaign, database row, or
external message was created or changed.
